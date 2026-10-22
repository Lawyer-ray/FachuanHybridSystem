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


def ensure_shared_server(endpoint: McpEndpoint | None = None) -> McpEndpoint:
    """确保共享 MCP 在跑；返回可用的 endpoint。

    同步版本，供 Django ``AppConfig.ready()`` 或管理命令调用。
    不等待就绪（就绪由 pi 侧连接时自然等待），避免拖慢启动。
    """
    resolved = endpoint or resolve_endpoint()
    if not shared_enabled():
        logger.info("共享 MCP 已禁用（%s=0），pi 将各自启动 stdio MCP", SHARED_ENV)
        return resolved
    spawn_shared_server(resolved)
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
    if shared_enabled():
        server: dict[str, Any] = {
            "type": "streamable-http",
            "url": resolved.url,
            "headers": {"Authorization": f"Bearer ${{{USER_TOKEN_ENV}}}"},
            # pi 1.3.0 默认 exposure=codemode：MCP 工具不声明给模型（只能经
            # codemode 脚本间接调），表现为「模型说去查，但没有 tool_call 直接
            # done」。法穿场景是模型直接挑工具，必须 direct 全量声明。
            "exposure": "direct",
        }
    else:
        server = {
            "command": _python_bin(),
            "args": ["-m", "mcp_server"],
            "cwd": str(_backend_dir()),
        }
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
    """写隔离目录的 ``settings.json``（pin provider/model + 思考等级）。

    不写这份文件的后果：pi 会读用户级 ``~/.pi/agent/settings.json``，那里的
    ``defaultProvider`` / ``defaultModel`` 会胜出，我们生成的 models.json 被
    静默绕过（表现为实际请求打到了完全无关的端点）。

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


def write_pi_mcp_config(target_dir: str | Path, endpoint: McpEndpoint | None = None) -> Path:
    """兼容旧名：仅写 MCP 配置（不碰模型），保留供测试/脚本使用。"""
    import json

    from .user_token import USER_TOKEN_ENV

    resolved = endpoint or resolve_endpoint()
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "mcp.json"
    if shared_enabled():
        server: dict[str, Any] = {
            "type": "streamable-http",
            "url": resolved.url,
            "headers": {"Authorization": f"Bearer ${{{USER_TOKEN_ENV}}}"},
            # pi 1.3.0 默认 exposure=codemode：MCP 工具不声明给模型（只能经
            # codemode 脚本间接调），表现为「模型说去查，但没有 tool_call 直接
            # done」。法穿场景是模型直接挑工具，必须 direct 全量声明。
            "exposure": "direct",
        }
    else:
        server = {
            "command": _python_bin(),
            "args": ["-m", "mcp_server"],
            "cwd": str(_backend_dir()),
        }
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
