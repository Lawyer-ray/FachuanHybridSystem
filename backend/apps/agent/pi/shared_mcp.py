"""共享 MCP server 管理。

## 为什么必须共享

实测（macOS / Python 3.12 / 本仓库 mcp_server）：

- 单个 ``python -m mcp_server`` 常驻内存约 **225 MB**
- 冷启动到可服务约 **6 秒**

若每个 pi 进程各起一份 stdio MCP：

- 20 并发 → 20 × 225MB ≈ **4.5 GB**，且每路首响应都要等 6 秒以上
- 每次工具调用跨 3 层进程（Django → pi → mcp_server）

改成「一份常驻 + N 个 pi 通过 HTTP 连」：

- 内存固定 1 份（~225MB），与并发数解耦
- 冷启动只发生一次（应用启动 / 首次使用时预热）
- pi 连 HTTP endpoint，启动快

## 部署形态

    Django 启动
      └─ 确保共享 MCP 在 http://127.0.0.1:<port>/mcp 待命

    pi 进程（N 个）
      └─ .pi/mcp.json 指向该 endpoint（type: streamable_http）

## 降级

``FACHUAN_MCP_SHARED=0`` 时退回 stdio 模式：每个 pi 各起一份，
牺牲内存换部署简单。默认**启用共享**。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SHARED_ENV = "FACHUAN_MCP_SHARED"
PORT_ENV = "FACHUAN_MCP_HTTP_PORT"
HOST_ENV = "FACHUAN_MCP_HTTP_HOST"
DEFAULT_PORT = 8011
DEFAULT_HOST = "127.0.0.1"
ENDPOINT_PATH = "/mcp"
READY_TIMEOUT = 30.0

#: MCP 工具面 exposure 模式（对应 pi 的 McpExposure）。灰度开关：
#: - ``direct``（默认）：全部工具 schema 声明给模型。2026-10-25 实测
#:   409 工具 tools/list ≈ 257KB ≈ 8.8 万 token 常驻上下文（400 工具时
#:   ~215KB ≈ 60k+，补注册 workflow 10 件后上探），靠 prompt cache 摊薄
#:   成本；单体最大 mortgage_default_calculate 9.3KB 为真实领域知识。
#: - ``deferred``：工具不声明给模型，模型经 pi 内置 ``tool_search`` 按需
#:   加载后直接调用。省上下文，但两个已知代价：OpenAI 兼容网关上每次
#:   延迟加载会丢 prompt cache（pi 1.4.0 changelog #10940）；每次工具
#:   发现多一跳搜索轮次。切换前先小流量对比 AgentRun 成本/命中率。
#:
#: 历史背景：pi 默认 ``codemode`` 下工具不声明给模型，表现为「模型说去查、
#: 但没有 tool_call 直接 done」（见下方 server 字典注释），所以必须显式写。
#: 注意：审批四级按「工具全名」（``mcp__fachuan__delete_case``）匹配，
#: 任何「用通用分发工具代替具名工具」的裁剪方案都会破坏审批链，
#: ``deferred`` 没有此问题（加载后仍以真名调用）。
EXPOSURE_ENV = "FACHUAN_MCP_EXPOSURE"
_VALID_EXPOSURES = frozenset({"direct", "deferred", "codemode", "hidden"})


def resolve_exposure() -> str:
    """读工具面 exposure 模式；非法值告警并回退 ``direct``（保持现状行为）。"""
    raw = (os.environ.get(EXPOSURE_ENV, "direct") or "").strip().lower() or "direct"
    if raw not in _VALID_EXPOSURES:
        logger.warning("非法 %s=%r（合法值: %s），回退 direct", EXPOSURE_ENV, raw, ", ".join(sorted(_VALID_EXPOSURES)))
        return "direct"
    return raw


@dataclass(slots=True)
class McpEndpoint:
    """共享 MCP 的连接信息。"""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{ENDPOINT_PATH}"


def shared_enabled() -> bool:
    """是否启用共享 MCP（默认启用）。"""
    raw = os.environ.get(SHARED_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def resolve_endpoint() -> McpEndpoint:
    host = os.environ.get(HOST_ENV, DEFAULT_HOST).strip() or DEFAULT_HOST
    try:
        port = int(os.environ.get(PORT_ENV, DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT
    return McpEndpoint(host=host, port=port)


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """探测端口是否可连。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def wait_until_ready(endpoint: McpEndpoint, timeout: float = READY_TIMEOUT) -> bool:
    """等待共享 MCP 端口可连。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await asyncio.to_thread(port_open, endpoint.host, endpoint.port):
            return True
        await asyncio.sleep(0.3)
    return False


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _python_bin() -> str:
    candidate = _backend_dir() / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return os.environ.get("PYTHON", "python3")


def spawn_shared_server(endpoint: McpEndpoint) -> subprocess.Popen[bytes] | None:
    """以 streamable-http 方式拉起共享 MCP（独立进程，与 Django 解耦）。

    Returns:
        子进程句柄；端口已被占用（已有实例在跑）时返回 ``None``。
    """
    if port_open(endpoint.host, endpoint.port):
        logger.info("共享 MCP 已在 %s 运行，复用现有实例", endpoint.url)
        return None

    env = {
        **os.environ,
        "FACHUAN_MCP_TRANSPORT": "streamable-http",
        "FACHUAN_MCP_HTTP_HOST": endpoint.host,
        "FACHUAN_MCP_HTTP_PORT": str(endpoint.port),
    }
    # stderr 落到日志文件：MCP 启动失败（依赖缺失、端口冲突、Django 初始化报错）
    # 的唯一线索都在这里。之前直接 DEVNULL，表现为「378 个工具全没了」却无从查起。
    log_path = Path(tempfile.gettempdir()) / f"fachuan-shared-mcp-{endpoint.port}.log"
    logger.info("拉起共享 MCP: %s（日志: %s）", endpoint.url, log_path)
    with contextlib.suppress(OSError):
        log_file = log_path.open("ab")
        return subprocess.Popen(
            [_python_bin(), "-m", "mcp_server"],
            cwd=str(_backend_dir()),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=log_file,
            start_new_session=True,
        )
    return subprocess.Popen(
        [_python_bin(), "-m", "mcp_server"],
        cwd=str(_backend_dir()),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def ensure_shared_server(endpoint: McpEndpoint | None = None, *, wait_ready: bool = False) -> McpEndpoint:
    """确保共享 MCP 在跑；返回可用的 endpoint。

    同步版本，供 Django ``AppConfig.ready()`` 或管理命令调用。
    幂等：端口已被占用（已有实例在跑）时什么都不做。

    Args:
        wait_ready: 新拉实例时是否等到端口可连（冷启动实测 ~6s）。
            崩溃复活场景**必须等**——不等的话 spawn 返回后 pi 立刻连接，
            落在冷启动窗口里，这个会话照样没有工具。复用现有实例时
            本参数无效果（本来就 ready）。
    """
    resolved = endpoint or resolve_endpoint()
    if not shared_enabled():
        logger.info("共享 MCP 已禁用（%s=0），pi 将各自启动 stdio MCP", SHARED_ENV)
        return resolved
    proc = spawn_shared_server(resolved)
    if proc is not None and wait_ready:
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            if port_open(resolved.host, resolved.port):
                logger.info("共享 MCP 已就绪: %s", resolved.url)
                break
            time.sleep(0.2)
        else:
            # 就绪等待超时：不抛——会话退化为「无工具但能对话」，
            # 下一次 acquire 还会重试拉起。
            logger.warning("共享 MCP 就绪等待超时（%.0fs），本会话可能无工具", READY_TIMEOUT)
    return resolved


def write_pi_config(
    target_dir: str | Path,
    endpoint: McpEndpoint | None = None,
    model_hint: str = "",
) -> Path:
    """写出 pi 的完整配置（MCP + 模型），返回 MCP 配置文件路径。

    写到 **用户级** 位置（该目录同时充当 ``PI_CODING_AGENT_DIR``），
    而不是项目级 ``.pi/mcp.json``。原因：项目级配置要求「项目信任」，
    RPC 模式无法弹交互式信任提示，临时工作目录永远是未受信的 → 配置被静默
    忽略、MCP 根本不加载。

    模型优先从数据库 LLMProvider 渲染（Admin 改了就生效），
    渲染不出时才回退复制用户级凭证。

    另写一份 ``AGENTS.md``（系统提示词）：pi 无条件读取工作目录的 AGENTS.md
    （与项目信任无关），这是给 agent 注入法穿助手人格的唯一挂载点。
    """
    import json

    from .model_config import write_models_json
    from .user_token import USER_TOKEN_ENV

    resolved = endpoint or resolve_endpoint()
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)

    # 1) 模型配置：优先从数据库生成
    generated = write_models_json(root, model_hint=model_hint)
    if generated is None:
        logger.info("未能从 LLMProvider 生成 models.json，回退用户级凭证")

    # 1.5) 思考等级：写隔离目录的 settings.json
    #
    # pi 的思考开关**不是** models.json 的 ``reasoning``（那个只是能力声明，
    # 实测改为 true 也不思考），而是 settings.json 的 ``modelThinkingLevels``：
    #   {"<provider>/<modelId>": "off|minimal|low|medium|high|xhigh|max"}
    # 不写这个，会话 thinkingLevel 默认 off，模型不思考也不产 thinking_delta。
    # 必须写进隔离目录（PI_CODING_AGENT_DIR）：否则会沿用用户级
    # ~/.pi/agent/settings.json 里的默认 provider/model，我们生成的 models.json
    # 被静默绕过。
    _write_settings_json(root, model_hint=model_hint)

    # 2) MCP 配置
    #
    # headers 引用 pi 子进程 env 里的 ``${FACHUAN_USER_TOKEN}``（pi 支持 mcp.json
    # header 的环境变量展开）：值是发起会话的律师的 access token，由
    # ``pool.acquire(session_env=...)`` 注入。mcp_server 端透传该头，工具即以
    # 律师本人身份调 REST API（confused deputy 修复，见 ``pi/user_token.py``）。
    # token 缺失时展开为空，mcp_server 回退服务账号（stdio/手工场景）。
    config_path = root / "mcp.json"
    server = _build_server_entry(resolved, USER_TOKEN_ENV)
    config_path.write_text(
        json.dumps({"mcpServers": {"fachuan": server}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 3) 系统提示词（AGENTS.md）
    _write_agents_md(root)

    # 4) 仅供回退路径的凭证复制（不覆盖已生成的文件）
    _copy_user_credentials(root)
    return config_path


def _write_settings_json(target_dir: str | Path, *, model_hint: str = "") -> Path | None:
    """写隔离目录的 ``settings.json``（pin provider/model + 思考等级 + 图像闸门）。

    不写这份文件的后果：pi 会读用户级 ``~/.pi/agent/settings.json``，那里的
    ``defaultProvider`` / ``defaultModel`` 会胜出，我们生成的 models.json 被
    静默绕过（表现为实际请求打到了完全无关的端点）。

    ``images.blockImages`` 必须显式写 ``False``：pi 的默认值是 false，但**用户级
    settings.json 可能被改成了 true**，此时 pi 会把 image block 整块换成文本
    ``"Image reading is disabled."`` 且不报错。隔离目录显式声明可以盖掉该设置——
    否则我们在 models.json 里辛苦声明的 ``input: ["text", "image"]`` 会被
    用户机器上的一个开关静默作废，且日志里完全看不到原因。

    Args:
        target_dir: 会话临时目录（同时充当 PI_CODING_AGENT_DIR）。
        model_hint: 本会话使用的模型名。

    Returns:
        写出的路径；无法确定模型时返回 ``None``（不写，交给 pi 自己决定）。
    """
    from . import model_config

    provider = model_config._load_provider(model_hint)
    if provider is None:
        return None
    models = model_config._provider_models(provider)
    model_id = model_hint or str(getattr(provider, "default_model", "") or "")
    if not model_id or (models and model_id not in models):
        return None

    # provider 名固定为 models.json 里的 provider key
    provider_name = "fachuan"
    settings: dict[str, Any] = {
        "defaultProvider": provider_name,
        "defaultModel": model_id,
        "images": {"blockImages": False},
        # compaction：pi 默认 ``reserveTokens=16384`` / ``keepRecentTokens=20000``。
        # 对 128K 窗口来说 reserve 占 12.8%，意味着上下文用到 ~87% 才开始压，
        # 压完剩下的余量刚好够几个工具循环——一旦某轮工具返回大 JSON 就溢出、
        # 触发 compact-and-retry，用户看到的是「卡一下又继续」。
        # 显式写成比例化的值，并把 ``keepRecentTokens`` 抬到 32K：律师的
        # 一轮指令往往带一串工具调用（查案→查合同→查期限→起草），最近这一段
        # 被摘要掉等于模型忘了自己刚查过什么。
        "compaction": {
            "reserveTokens": 24576,
            "keepRecentTokens": 32768,
        },
    }
    level = model_config.resolve_thinking_level(model_id)
    if level:
        settings["modelThinkingLevels"] = {f"{provider_name}/{model_id}": level}

    path = Path(target_dir) / "settings.json"
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "pi settings.json 已写入: provider=%s model=%s thinking=%s",
        provider_name,
        model_id,
        level or "off",
    )
    return path


def _tiers_enabled() -> bool:
    """工具面分层是否启用（延迟 import，避免与 ``mcp_server`` 包耦合）。"""
    try:
        from mcp_server.tool_tiers import tiers_enabled
    except Exception as exc:
        logger.warning("工具面分层模块不可用，回退全量直连: %s", exc)
        return False
    return tiers_enabled()


def _build_tool_exposure() -> dict[str, str]:
    """生成 ``toolExposure`` 映射（失败返回空 → 不分层）。"""
    try:
        from mcp_server.tool_tiers import build_tool_exposure
    except Exception as exc:
        logger.warning("工具面分层清单读取失败，回退全量直连: %s", exc)
        return {}
    return build_tool_exposure()


def _describe_tiers() -> str:
    """分层摘要（日志用）。"""
    try:
        from mcp_server.tool_tiers import describe_tiers
    except Exception:
        return "（摘要不可用）"
    return describe_tiers()


def _build_server_entry(resolved: McpEndpoint, user_token_env: str) -> dict[str, Any]:
    """构造 ``mcp.json`` 的 server 条目（共享 HTTP / stdio 两种形态共用）。

    抽成一处的原因：``write_pi_config`` 与 ``write_pi_mcp_config`` 原本各写
    一份完全相同的字段表，改 exposure 时极容易只改一处——两处一旦不一致，
    "手工写配置"与"正式链路"的行为就分叉，排查时非常难定位。

    exposure 的取值优先级：

    1. 用户显式设了 ``FACHUAN_MCP_EXPOSURE``（非默认 direct）→ **从用户**，
       不叠分层（两套机制叠加的行为难预测）。
    2. 默认为 direct 且分层开关开 → 写 ``deferred`` + ``toolExposure``。
    3. 分层开关关 → ``direct``（全量声明，与改造前行为一致）。
    """
    exposure = resolve_exposure()
    tool_exposure: dict[str, str] = {}
    if exposure == "direct" and _tiers_enabled():
        tool_exposure = _build_tool_exposure()
        if tool_exposure:
            # 有 toolExposure 条目时服务端默认必须改为 deferred：未列出的
            # 工具靠 tool_search 加载，而不是全量声明。
            exposure = "deferred"
            logger.info("工具面分层已启用: %s", _describe_tiers())
    extra: dict[str, Any] = {"toolExposure": tool_exposure} if tool_exposure else {}

    if shared_enabled():
        return {
            "type": "streamable-http",
            "url": resolved.url,
            "headers": {"Authorization": f"Bearer ${{{user_token_env}}}"},
            # pi 默认 exposure=codemode：MCP 工具不声明给模型（只能经
            # codemode 脚本间接调），表现为「模型说去查，但没有 tool_call 直接
            # done」。法穿场景是模型直接挑工具，默认 direct 全量声明；
            # 按需加载见 resolve_exposure / FACHUAN_MCP_EXPOSURE 与
            # mcp_server/tool_tiers.py。
            "exposure": exposure,
            **extra,
            # deferred 下 pi 会把它列入 system prompt 的 mcp_servers 小节，
            # 也让 tool_search 按它排序——写清楚"这服务有什么"比堆关键词有用。
            "description": "法穿法律事务系统：案件、合同、文书、当事人、财务、期限、法规检索与自动化",
            # pi 每请求默认 60s 超时，会先于 client 侧 LLM 链路工具的 180s
            # （见 tools/documents/litigation.py 等 12 处 timeout=180）掐断——
            # 双端超时必须 pi > client，否则 client 的努力全部作废。200 给
            # 传输层留余量；工具发 progress notifications 可重置该计时。
            "timeout": 200,
        }
    return {
        "command": _python_bin(),
        "args": ["-m", "mcp_server"],
        "cwd": str(_backend_dir()),
        # stdio 回退同样不能落回 codemode 默认（工具将不可调用）
        "exposure": exposure,
        **extra,
        "timeout": 200,
    }


def write_pi_mcp_config(target_dir: str | Path, endpoint: McpEndpoint | None = None) -> Path:
    """兼容旧名：仅写 MCP 配置（不碰模型），保留供测试/脚本使用。"""
    import json

    from .user_token import USER_TOKEN_ENV

    resolved = endpoint or resolve_endpoint()
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "mcp.json"
    server = _build_server_entry(resolved, USER_TOKEN_ENV)
    config_path.write_text(
        json.dumps({"mcpServers": {"fachuan": server}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def _copy_user_credentials(target: Path) -> None:
    """把用户级凭证复制到独立配置目录（**仅在无法从 LLMProvider 生成时媛底**）。

    优先级：``model_config.write_models_json`` 从数据库渲染 > 复制用户级 ``models.json``。
    设了 ``PI_CODING_AGENT_DIR`` 后 pi 不再读 ``~/.pi/agent``，若不处理会报
    ``No API key found``。
    """
    import shutil

    # 已经由数据库配置生成了 models.json，就不再覆盖
    has_models = (target / "models.json").exists()
    source_dir = Path(os.environ.get("FACHUAN_PI_USER_DIR", Path.home() / ".pi" / "agent"))
    for name in ("models.json", "auth.json"):
        if name == "models.json" and has_models:
            continue
        source = source_dir / name
        if not source.exists():
            continue
        destination = target / name
        if destination.exists():
            continue
        with contextlib.suppress(OSError):
            shutil.copy2(source, destination)


def _write_agents_md(target: Path) -> None:
    """把系统提示词写进工作目录。

    默认用本 app 内置模板；``FACHUAN_PI_AGENTS_PATH`` 可指向自定义文件。
    写失败只降级（少一份人格说明不致命），不阻断会话。
    """
    import shutil

    source = Path(os.environ.get("FACHUAN_PI_AGENTS_PATH", "") or (Path(__file__).resolve().parent / "AGENTS.md"))
    try:
        if not source.is_file():
            logger.warning("AGENTS.md 模板不存在，agent 将缺少系统提示词: %s", source)
            return
        shutil.copyfile(source, target / "AGENTS.md")
    except OSError:
        logger.warning("写入 AGENTS.md 失败，agent 将缺少系统提示词", exc_info=True)
