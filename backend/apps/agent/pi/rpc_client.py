"""pi RPC 客户端 —— Django 侧驱动 pi 子进程。

依据 pi 1.3.0 ``docs/rpc.md`` 的实现要点：

1. **JSONL 严格框定**：每条记录一个 JSON + LF。不能用通用 line reader——
   Node 的 ``readline`` 会把 U+2028/U+2029 当换行，而它们在 JSON 字符串里合法。
   这里用二进制读 pipe 再按 ``b"\\n"`` 切分。
2. **命令按 id 关联**：命令处理是异步的，不能假设响应顺序。
3. **运行结束用 ``agent_settled``**：``agent_end`` 之后还可能有重试 / 压缩 / steering。
4. **stdout 只放协议**：诊断信息在 stderr，不解析 stderr。
5. **session 归属**：默认按会话给 ``--session-dir`` + ``--session-id``，让 pi
   自己管上下文与 compaction（见 ``session_store.py``）；只在没有 session_id
   （脚本 / 单测）时才用 ``--no-session``。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PI_BIN_ENV = "FACHUAN_PI_BIN"
APPROVAL_EXTENSION_ENV = "FACHUAN_PI_APPROVAL_EXTENSION"
#: 记忆注入 extension（可选）。文件缺失时只告警不阻断——记忆是增强能力，
#: 与审批网关的 fail-closed 策略刻意不同。
MEMORY_EXTENSION_ENV = "FACHUAN_PI_MEMORY_EXTENSION"
#: 工具结果守卫 extension（可选）。剥离内部字段 / 出参敏感号码兜底脱敏 /
#: 不可见字符扫描。缺失时只告警不阻断——它是质量增强，不是安全闸门
#: （真正的安全闸门是审批 extension，那个 fail-closed）。
TOOL_RESULT_GUARD_ENV = "FACHUAN_PI_TOOL_RESULT_GUARD_EXTENSION"
#: 只向模型声明法穿 MCP 工具。pi 默认还带 read/bash/edit/write 四个内置工具，
#: 它们能以 Django 进程的权限读写文件、执行命令，且不在审批清单内——
#: 一段藏在工具输出里的提示注入就能免审批执行 bash。按 cli.md，``--tools``
#: 以 ``mcp__`` 开头的条目会整体替换工具选择，内置工具不再声明。
#:
#: **为什么现在多了 ``tool_search``**：工具面分层后（见
#: ``mcp_server/tool_tiers.py``）大部分业务工具是 ``deferred`` 暴露——不声明
#: 给模型，只能由 ``tool_search`` 按需加载。而 ``--tools`` 是**白名单**：
#: 不显式列出 ``tool_search``，那 350+ 个 deferred 工具就**永远不可达**
#: （模型说「我去查」，但没有 search 工具，只能用可见的 61 个）。
#: 按 cli.md：「只有 ``tool_search``，如果列出，才能加载它」。
#:
#: **安全边界仍然在**：``tool_search`` 只能发现/加载 MCP 工具（它不提供
#: 任何文件系统或 shell 能力），而加载后的每个调用照旧过 ``tool_call``
#: 钩子 → 四级审批。列它进来不会打开任何新攻击面。
TOOL_SELECTION = "mcp__fachuan__*,tool_search"
_READ_CHUNK = 65536
_SHUTDOWN_TIMEOUT = 5.0
_STDERR_LINE_LIMIT = 500
#: 关闭前写 abort 的 drain 超时（写不进去就算了，后面还有 kill 兜底）
_ABORT_DRAIN_TIMEOUT = 1.0


class PiError(RuntimeError):
    """pi 子进程或协议层错误。"""


class PiNotAvailableError(PiError):
    """pi 可执行文件缺失或版本不可用。"""


@dataclass(slots=True)
class PiEvent:
    """pi 推上来的一条记录。"""

    kind: str  # "response" | "event" | "extension_ui"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return str(self.raw.get("type") or "")


def resolve_pi_bin() -> str:
    """定位 pi 可执行文件；缺失时抛错而不是静默降级。"""
    configured = os.environ.get(PI_BIN_ENV, "").strip()
    if configured:
        if not Path(configured).exists():
            raise PiNotAvailableError(f"{PI_BIN_ENV} 指向的文件不存在: {configured}")
        return configured
    found = shutil.which("pi")
    if not found:
        raise PiNotAvailableError(
            f"未找到 pi 可执行文件。请安装 @earendil-works/pi-coding-agent，或通过环境变量 {PI_BIN_ENV} 指定路径。"
        )
    return found


def default_approval_extension() -> str:
    """本 app 内置的审批 extension 路径。"""
    configured = os.environ.get(APPROVAL_EXTENSION_ENV, "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parent / "approval-gate.ts")


def default_memory_extension() -> str:
    """本 app 内置的记忆注入 extension 路径。"""
    configured = os.environ.get(MEMORY_EXTENSION_ENV, "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parent / "memory-inject.ts")


def default_tool_result_guard_extension() -> str:
    """本 app 内置的工具结果守卫 extension 路径。"""
    configured = os.environ.get(TOOL_RESULT_GUARD_ENV, "").strip()
    if configured:
        return configured
    return str(Path(__file__).resolve().parent / "tool-result-guard.ts")


def resolve_extensions(primary: str | None = None) -> list[str]:
    """要加载的 extension 列表（审批在前，其余按注入顺序）。

    审批 extension 必须永远存在（工具调用的人工闸门）；记忆注入与结果守卫
    是可选的——文件缺失时只告警不阻断，因为它们是增强能力，缺了对话仍可
    正常进行。这与审批的 fail-closed 策略刻意不同：不能把「没有记忆」或
    「没有结果守卫」当成致命故障。
    """
    extensions = [primary or default_approval_extension()]
    optional = (
        ("记忆注入", default_memory_extension()),
        ("工具结果守卫", default_tool_result_guard_extension()),
    )
    for label, path in optional:
        if not path:
            continue
        if path in extensions:
            continue
        if not Path(path).exists():
            logger.warning("%s extension 不存在，本次会话不加载: %s", label, path)
            continue
        extensions.append(path)
    return extensions


def _clean_env() -> dict[str, str]:
    """构造子进程环境，剔除会干扰模型选择的继承变量。

    若 Django 本身跑在一个 pi 会话里（例如开发时用 pi 启动服务），
    ``PI_PROVIDER`` / ``PI_MODEL`` / ``PI_SESSION_*`` 会被子进程继承，
    覆盖我们生成的 models.json，导致 pi 去连完全无关的 provider
    （实际表现为每次请求都 ``Connection error`` 并重试 3 次）。
    这些变量一律不传给 agent 子进程。
    """
    noisy_prefixes = (
        "PI_PROVIDER",
        "PI_MODEL",
        "PI_SESSION",
        "PI_MCP",
        "PI_THINKING",
        "PI_REASONING",
        # 注意：不剔 PI_CODING_AGENT_DIR——那正是我们用来指定隔离配置目录的
        # 变量，剔掉后 pi 会回落到用户级 ~/.pi/agent，我们写的 models.json
        # （含 fachuan provider）被完全忽略，报 Unknown provider "fachuan"。
    )
    # 代理会阻断内网 LLM 网关：开发机的 HTTP(S)_PROXY 指向本地代理，
    # 而 NO_PROXY 往往只含 localhost，pi 连内网网关时会走代理绕一圈，
    # 表现为 ``Connection error`` 并重试 3 次。agent 只连内网服务，不需要代理。
    proxy_keys = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    }
    return {
        key: value for key, value in os.environ.items() if not key.startswith(noisy_prefixes) and key not in proxy_keys
    }


class PiRpcSession:
    """一条 pi RPC 子进程的生命周期封装。"""

    def __init__(
        self,
        *,
        cwd: str,
        model: str | None = None,
        provider: str | None = None,
        extension_path: str | None = None,
        extra_env: dict[str, str] | None = None,
        command_timeout: float = 30.0,
        session_dir: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._cwd = cwd
        self._session_dir = session_dir
        self._session_id = session_id
        self._model = model
        self._provider = provider
        self._extension = extension_path if extension_path is not None else default_approval_extension()
        self._extra_env = extra_env or {}
        self._command_timeout = command_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._events: asyncio.Queue[PiEvent | None] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0

    # ── 生命周期 ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._proc is not None:
            return
        # 审批 extension 是工具调用的唯一人工闸门。文件缺失时若只告警继续，
        # 等于所有高危工具裸奔（服务端清单只过滤「到达的回调」，没回调就没拦截），
        # 所以这里 fail-closed：拒绝启动。放在定位 pi 之前，便于无 pi 环境也能测到。
        if not self._extension or not Path(self._extension).exists():
            raise PiError(f"审批 extension 不存在，拒绝启动 pi（避免工具调用失去审批约束）: {self._extension}")
        pi_bin = resolve_pi_bin()
        # --approve：RPC 模式无法弹交互式信任提示，项目级 .pi/mcp.json 会被忽略。
        # 工作目录是本 app 自己创建的临时目录（内容由我们控制），可直接信任。
        args: list[str] = [
            pi_bin,
            "--mode",
            "rpc",
            "--approve",
            "--tools",
            TOOL_SELECTION,
        ]
        # 多个 --extension：审批网关 + 记忆注入。pi 支持重复传该参数。
        for extension in resolve_extensions(self._extension):
            args.extend(["--extension", extension])
        # 上下文管理交给 pi：每会话一个 session 文件，pi 负责裁剪与自动 compaction。
        # 没有 session_id 时退回 --no-session（脚本/测试场景）。
        if self._session_dir and self._session_id:
            args.extend(["--session-dir", self._session_dir, "--session-id", self._session_id])
        else:
            args.append("--no-session")
        if self._provider:
            args.extend(["--provider", self._provider])
        if self._model:
            args.extend(["--model", self._model])

        env = {**_clean_env(), **self._extra_env}
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=self._cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        # stderr 必须有人消费：pi 的诊断全走 stderr，管道缓冲（约 64KB）写满后
        # pi 会阻塞在写端，表现为整个请求卡死。这里顺手把内容记进日志，
        # extension 加载失败一类的问题才有迹可循。
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        logger.info(
            "pi RPC 已启动 pid=%s cwd=%s model=%s",
            self._proc.pid,
            self._cwd,
            self._model,
        )

    async def close(self, *, abort_running: bool = False) -> None:
        """关闭 stdin 请求优雅退出；超时则强杀。

        Args:
            abort_running: 关闭前先中止在途运行。用户主动停止 / 客户端断开时
                传 ``True``，让 provider 侧请求尽快结束（省钱）。正常跑完的路径
                保持 ``False``——那时已无在途运行，多发一条 abort 只会多一次握手。
        """
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if abort_running and proc.returncode is None:
            # 进程已摘出 self._proc，_send() 会因「未启动」失败；直接写 stdin。
            await self._abort_before_close(proc)
        for attr in ("_reader_task", "_stderr_task"):
            task = getattr(self, attr)
            if task is not None:
                task.cancel()
                # return_exceptions=True：取消产生的 CancelledError 作为结果装箱，不向上抛。
                # 返回值是有意丢弃的（收尾阶段不关心协程结果），显式赋值避免误判为无效语句。
                _ = await asyncio.gather(task, return_exceptions=True)
                setattr(self, attr, None)
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
            await asyncio.wait_for(proc.wait(), timeout=_SHUTDOWN_TIMEOUT)
        except (TimeoutError, ProcessLookupError):
            with contextlib.suppress(Exception):
                proc.kill()
                await proc.wait()
        finally:
            self._events.put_nowait(None)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(PiError("pi 进程已关闭"))
            self._pending.clear()

    async def __aenter__(self) -> PiRpcSession:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def _abort_before_close(self, proc: asyncio.subprocess.Process) -> None:
        """关闭前的最后一搏：直接往 stdin 写 clear_queue + abort。

        不复用 ``_send()``：它要等 response，而此刻读协程即将被取消，等不到。
        """
        if proc.stdin is None or proc.stdin.is_closing():
            return
        payloads = ({"type": "clear_queue", "id": "close-clear"}, {"type": "abort", "id": "close-abort"})
        try:
            for payload in payloads:
                proc.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
            await asyncio.wait_for(proc.stdin.drain(), timeout=_ABORT_DRAIN_TIMEOUT)
        except (TimeoutError, ConnectionResetError, BrokenPipeError, RuntimeError):
            logger.debug("关闭前 abort 写入失败（进程可能已退出）", exc_info=True)

    # ── stdout 读取（二进制按 LF 切分） ─────────────────────────────────────

    async def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        buffer = bytearray()
        try:
            while True:
                chunk = await proc.stdout.read(_READ_CHUNK)
                if not chunk:
                    break
                buffer.extend(chunk)
                while (idx := buffer.find(b"\n")) >= 0:
                    line = bytes(buffer[:idx]).rstrip(b"\r")
                    del buffer[: idx + 1]
                    if line:
                        self._dispatch_line(line)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pi stdout 读取失败")
        finally:
            self._events.put_nowait(None)

    async def _drain_stderr(self) -> None:
        """持续消费 stderr 并记日志（防管道写满卡死；诊断信息可查）。"""
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        buffer = bytearray()
        try:
            while True:
                chunk = await proc.stderr.read(_READ_CHUNK)
                if not chunk:
                    break
                buffer.extend(chunk)
                while (idx := buffer.find(b"\n")) >= 0:
                    line = bytes(buffer[:idx]).decode("utf-8", "replace").strip()
                    del buffer[: idx + 1]
                    if line:
                        logger.info("pi stderr: %s", line[:_STDERR_LINE_LIMIT])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("pi stderr 读取结束", exc_info=True)

    def _dispatch_line(self, line: bytes) -> None:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("pi 输出非 JSON 行，已忽略: %s", line[:200])
            return
        if not isinstance(record, dict):
            return

        rtype = record.get("type")
        if rtype == "response":
            # pi 的 response 不带我们发过去的 ``id``（回显的是 ``command``），
            # 按 id 匹配会永远落空 → prompt() 等到超时，前端表现为「(无内容)」。
            # 优先按 id 匹配，退化按 command 匹配。
            cmd_id = record.get("id")
            fut = self._pending.pop(str(cmd_id), None) if cmd_id is not None else None
            if fut is None:
                command = record.get("command")
                if command is not None:
                    fut = self._pending.pop(str(command), None)
            if fut is not None and not fut.done():
                fut.set_result(record)
            else:
                self._events.put_nowait(PiEvent("response", record))
            return

        if rtype == "extension_ui_request":
            self._events.put_nowait(PiEvent("extension_ui", record))
            return

        self._events.put_nowait(PiEvent("event", record))

    # ── 命令 ────────────────────────────────────────────────────────────────

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise PiError("pi 进程未启动")
        self._next_id += 1
        cmd_id = str(self._next_id)
        payload["id"] = cmd_id
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[cmd_id] = fut
        # pi 的 response 只回 command，不回 id；同时用 command 做键，两边都能匹配
        command = payload.get("type")
        if isinstance(command, str):
            self._pending[command] = fut
        proc.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
        await proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout=self._command_timeout)
        finally:
            self._pending.pop(cmd_id, None)
            if isinstance(command, str):
                self._pending.pop(command, None)

    async def prompt(self, message: str) -> None:
        """发送一条 prompt。返回只代表「已接受」，不代表跑完。"""
        resp = await self._send({"type": "prompt", "message": message})
        if resp.get("success") is not True:
            raise PiError(f"prompt 被拒绝: {resp.get('error')}")

    async def steer(self, message: str) -> str:
        """运行中插话：当前 assistant turn 的工具调用跑完、下次 LLM 调用前生效。

        Returns:
            pi 的 ``data.disposition``（``queued`` / ``handled``）。

        Raises:
            PiError: 命令被拒（典型：当前没在跑）。
        """
        return await self._queue_message("steer", message)

    async def follow_up(self, message: str) -> str:
        """追加一轮：agent 干完当前所有活（无工具调用、无 steering）后再跑。

        Returns:
            pi 的 ``data.disposition``。

        Raises:
            PiError: 命令被拒。
        """
        return await self._queue_message("follow_up", message)

    async def _queue_message(self, command: str, message: str) -> str:
        """steer / follow_up 共用的投递逻辑（两者协议形状一致）。"""
        resp = await self._send({"type": command, "message": message})
        if resp.get("success") is not True:
            raise PiError(f"{command} 被拒绝: {resp.get('error')}")
        data = resp.get("data")
        if isinstance(data, dict):
            return str(data.get("disposition") or "queued")
        return "queued"

    async def abort(self) -> bool:
        """中止当前运行；返回是否成功送达。

        调用时机是「用户点了停止」——此时前端已断开，但 pi 子进程仍在跑，
        provider 侧请求已发出。不发 abort 直接关进程，模型会在服务端跑完
        （继续烧 token），只是结果没人接收。

        按 ``rpc-commands.md`` 的交互式 Esc 语义，abort 后排队消息仍会继续；
        用户按停止的意思是「全停」，所以先 ``clear_queue`` 再 ``abort``。
        """
        cleared = await self.clear_queue()
        if cleared:
            logger.info("pi 运行中止前撤回排队消息 %s 条", len(cleared))
        try:
            resp = await self._send({"type": "abort"})
        except (PiError, TimeoutError):
            logger.debug("abort 发送失败（进程可能已退出）", exc_info=True)
            return False
        return resp.get("success") is True

    async def clear_queue(self) -> list[str]:
        """撤回排队的 steering / follow-up 消息，返回被撤回的文本。

        不是所有版本都支持该命令；失败按「无排队消息」处理，不阻断中止流程。
        """
        try:
            resp = await self._send({"type": "clear_queue"})
        except (PiError, TimeoutError):
            return []
        data = resp.get("data")
        if not isinstance(data, dict):
            return []
        texts: list[str] = []
        for key in ("steering", "followUp"):
            values = data.get(key)
            if isinstance(values, list):
                texts.extend(str(value) for value in values)
        return texts

    def drain_events(self) -> AsyncIterator[PiEvent]:
        """消费事件流；进程结束时迭代器自然结束。"""
        return self._iter_events()

    async def _iter_events(self) -> AsyncIterator[PiEvent]:
        while True:
            item = await self._events.get()
            if item is None:
                return
            yield item


def make_temp_workdir(prefix: str = "fachuan-agent-") -> str:
    """为一次会话准备隔离工作目录。"""
    return tempfile.mkdtemp(prefix=prefix)
