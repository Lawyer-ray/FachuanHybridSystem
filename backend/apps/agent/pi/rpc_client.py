"""pi RPC 客户端 —— Django 侧驱动 pi 子进程。

依据 pi 1.3.0 ``docs/rpc.md`` 的实现要点：

1. **JSONL 严格框定**：每条记录一个 JSON + LF。不能用通用 line reader——
   Node 的 ``readline`` 会把 U+2028/U+2029 当换行，而它们在 JSON 字符串里合法。
   这里用二进制读 pipe 再按 ``b"\\n"`` 切分。
2. **命令按 id 关联**：命令处理是异步的，不能假设响应顺序。
3. **运行结束用 ``agent_settled``**：``agent_end`` 之后还可能有重试 / 压缩 / steering。
4. **stdout 只放协议**：诊断信息在 stderr，不解析 stderr。
5. **``--no-session``**：会话状态由 Django 持有，pi 只当无状态执行器，
   多进程 / 多机部署无需共享磁盘。
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
#: 只向模型声明法穿 MCP 工具。pi 默认还带 read/bash/edit/write 四个内置工具，
#: 它们能以 Django 进程的权限读写文件、执行命令，且不在审批清单内——
#: 一段藏在工具输出里的提示注入就能免审批执行 bash。按 cli.md，``--tools``
#: 以 ``mcp__`` 开头的条目会整体替换工具选择，内置工具不再声明。
TOOL_SELECTION = "mcp__fachuan__*"
_READ_CHUNK = 65536
_SHUTDOWN_TIMEOUT = 5.0
_STDERR_LINE_LIMIT = 500


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
        "PI_CODING_AGENT",
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
    ) -> None:
        self._cwd = cwd
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
            "--no-session",
            "--approve",
            "--tools",
            TOOL_SELECTION,
            "--extension",
            self._extension,
        ]
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

    async def close(self) -> None:
        """关闭 stdin 请求优雅退出；超时则强杀。"""
        proc, self._proc = self._proc, None
        if proc is None:
            return
        for attr in ("_reader_task", "_stderr_task"):
            task = getattr(self, attr)
            if task is not None:
                task.cancel()
                # return_exceptions=True：取消产生的 CancelledError 作为结果装箱，不向上抛
                await asyncio.gather(task, return_exceptions=True)
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
            cmd_id = record.get("id")
            fut = self._pending.pop(str(cmd_id), None) if cmd_id is not None else None
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
        proc.stdin.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
        await proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout=self._command_timeout)
        finally:
            self._pending.pop(cmd_id, None)

    async def prompt(self, message: str) -> None:
        """发送一条 prompt。返回只代表「已接受」，不代表跑完。"""
        resp = await self._send({"type": "prompt", "message": message})
        if resp.get("success") is not True:
            raise PiError(f"prompt 被拒绝: {resp.get('error')}")

    async def abort(self) -> None:
        """中止当前运行。"""
        with contextlib.suppress(PiError, TimeoutError):
            await self._send({"type": "abort"})

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
