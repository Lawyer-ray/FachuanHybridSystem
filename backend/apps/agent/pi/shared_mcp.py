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

## 与 ``backends/toolface`` 的分工（2026-11 抽取）

与后端无关的部分（``McpEndpoint`` / ``shared_enabled`` / ``resolve_endpoint`` /
``port_open`` / ``spawn_shared_server``）已下沉到 ``apps.agent.backends.toolface``，
pi 与 dsh 共用同一份实现。本模块**保留原有的全部符号名**并 re-export：

- ``tests/ci/unit/agent/test_shared_mcp_revive.py`` 用
  ``monkeypatch.setattr(shared_mcp_module, ...)`` patch **本模块属性**，符号消失
  会让 patch 静默失效并真的拉起子进程（撞 pytest 30s 超时）；
- ``scripts/verify_dsh_mcp.py`` 替换 ``shared_mcp.resolve_endpoint``，
  所以那个名字必须继续是**本模块命名空间里的可替换间接层**。

本文件还负责把**元典**的 MCP Server（``law`` / ``case`` / ``company`` / ``securities``）
一并挂进同一份 ``mcp.json``：清单与地址是代码常量，从系统配置读的只有 API Key 与
总开关 ``YUANDIAN_MCP_ENABLED``，key 只以 ``${FACHUAN_YUANDIAN_API_KEY}`` 占位落盘
（见 ``_build_yuandian_server_entries``）。

pi 专属的部分（``mcp.json`` 字段表 ``_build_server_entry``、exposure、模型配置、
AGENTS.md）留在本文件——``mcp_server`` 侧的漂移门禁
（``tests/ci/unit/mcp_server/test_pi_timeout_alignment.py``）按本文件路径扫
``"timeout": N`` 字面量。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from ..backends.toolface import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ENDPOINT_PATH,
    HOST_ENV,
    PORT_ENV,
    READY_TIMEOUT,
    SERVER_DESCRIPTION,
    SERVER_NAME,
    SESSION_HEADER,
    SESSION_ID_ENV,
    SHARED_ENV,
    McpEndpoint,
    backend_dir,
    endpoint_from_env,
    port_open,
    python_bin,
    shared_enabled,
    spawn_shared_server,
    tool_prefix,
)
from .session_store import agent_home

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ENDPOINT_PATH",
    "EXPOSURE_ENV",
    "HOST_ENV",
    "McpEndpoint",
    "PORT_ENV",
    "READY_TIMEOUT",
    "SERVER_DESCRIPTION",
    "SERVER_NAME",
    "SESSION_HEADER",
    "SHARED_ENV",
    "ensure_shared_server",
    "port_open",
    "resolve_endpoint",
    "resolve_exposure",
    "shared_enabled",
    "spawn_shared_server",
    "tool_prefix",
    "wait_until_ready",
    "YUANDIAN_API_KEY_ENV",
    "STREAMABLE_HTTP_TYPE",
    "write_pi_config",
    "write_pi_mcp_config",
]

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

#: 元典 MCP 的 Bearer key 在 pi 子进程 env 里的变量名。
#:
#: ``mcp.json`` 里只写 ``Authorization: Bearer ${FACHUAN_YUANDIAN_API_KEY}`` 占位
#: （pi 支持 mcp.json header 的环境变量展开，与 ``FACHUAN_USER_TOKEN`` 同一机制），
#: 真 key 由 :meth:`apps.agent.pi.pool.PiProcessPool.acquire` 注入子进程 env
#: （多把 key 时每个 pi 进程轮转一把，见 ``pool._yuandian_env``）。
#: 为什么必须这样：``mcp.json`` 是常驻的明文配置文件（会话目录复用到下一个用户），
#: 而元典 key 是长期凭证——落盘等于把 key 写进磁盘快照/备份/工单附件。
YUANDIAN_API_KEY_ENV = "FACHUAN_YUANDIAN_API_KEY"  # pragma: allowlist secret

#: 远端 MCP Server 在 ``mcp.json`` 里的 ``type`` 取值。
#:
#: 元典官方示例写 ``"type": "http"``，但那是**没在 pi 上验证过**的写法；
#: 本仓库自己的共享 HTTP server 用的是这个值（``_build_server_entry`` 共享分支，
#: 已在 pi 上跑通），所以元典 server 跟着它走——同一个 pi 版本只认一套取值最稳。
STREAMABLE_HTTP_TYPE = "streamable-http"


def resolve_exposure() -> str:
    """读工具面 exposure 模式；非法值告警并回退 ``direct``（保持现状行为）。"""
    raw = (os.environ.get(EXPOSURE_ENV, "direct") or "").strip().lower() or "direct"
    if raw not in _VALID_EXPOSURES:
        logger.warning("非法 %s=%r（合法值: %s），回退 direct", EXPOSURE_ENV, raw, ", ".join(sorted(_VALID_EXPOSURES)))
        return "direct"
    return raw


def resolve_endpoint() -> McpEndpoint:
    """按环境变量解析共享 MCP endpoint（**保留为可替换的间接层**）。

    这个函数是仓库里的既定替换点：``scripts/verify_dsh_mcp.py`` 替换本模块的
    ``resolve_endpoint`` 把 :8011 指向假服务器，``backends.dsh_mcp._resolve_endpoint``
    每次从模块属性重取。实现已下沉到 ``toolface.endpoint.endpoint_from_env``，但
    **不要**把它改成 import 时绑定的别名（``resolve_endpoint = endpoint_from_env``）
    ——那样替换就不生效，验证会变假绿。
    """
    endpoint: McpEndpoint = endpoint_from_env()
    return endpoint


async def wait_until_ready(endpoint: McpEndpoint, timeout: float = READY_TIMEOUT) -> bool:
    """等待共享 MCP 端口可连。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await asyncio.to_thread(port_open, endpoint.host, endpoint.port):
            return True
        await asyncio.sleep(0.3)
    return False


def _spawn_shared_server(endpoint: McpEndpoint) -> Any:
    """``toolface.bootstrap.spawn_shared_server`` 的 pi 侧薄壳（注入日志目录）。

    为什么需要这一层：``toolface`` 不能 import ``pi.session_store``（``pi`` 依赖
    它，反向 import 成环），所以日志目录由调用方注入。落点仍是
    ``agent_home()``（0700 根目录），子进程以 0600 追加写，不放 /tmp——
    日志可能含业务数据。

    为什么还留一个同名 re-export：``spawn_shared_server`` 必须是本模块命名空间里
    ``test_shared_mcp_revive.py`` 的 ``monkeypatch.setattr`` 替换目标（挡住真起
    子进程），所以真正被调的是本函数，它经模块属性调 re-export 的那个名字。
    """
    # 只为「日志落在 agent home」这一件事加参数；测试把 ``spawn_shared_server``
    # 换成 ``lambda ep, **kw`` 时不会被这个关键字参数打挂。
    return spawn_shared_server(endpoint, log_dir=agent_home() / "logs")


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
    proc = _spawn_shared_server(resolved)
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
    *,
    api_key: str | None = None,
) -> Path:
    """写出 pi 的完整配置（MCP + 模型），返回 MCP 配置文件路径。

    写到 **用户级** 位置（该目录同时充当 ``PI_CODING_AGENT_DIR``），
    而不是项目级 ``.pi/mcp.json``。原因：项目级配置要求「项目信任」，
    RPC 模式无法弹交互式信任提示，临时工作目录永远是未受信的 → 配置被静默
    忽略、MCP 根本不加载。

    模型优先从数据库 LLMProvider 渲染（Admin 改了就生效），
    渲染不出时才回退复制用户级凭证。

    ``api_key`` 是本轮编排层指定的网关 key（``RunContext.api_key``），原样转交
    :func:`model_config.write_models_json`；``None`` 时写函数仍走 ``_next_key``
    轮转，行为与引入本参数前一致。

    另写一份 ``AGENTS.md``（系统提示词）：pi 无条件读取工作目录的 AGENTS.md
    （与项目信任无关），这是给 agent 注入法穿助手人格的唯一挂载点。
    """
    from . import model_config
    from .model_config import write_models_json

    resolved = endpoint or resolve_endpoint()
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)

    # provider 一次查询、多处复用（models.json / settings.json / 思考等级），
    # 避免同一轮配置渲染重复读库；查不到时各写入方自行降级，行为不变。
    provider = model_config._load_provider(model_hint)

    # 1) 模型配置：优先从数据库生成
    generated = write_models_json(root, model_hint=model_hint, provider=provider, api_key=api_key)
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
    _write_settings_json(root, model_hint=model_hint, provider=provider)

    # 2) MCP 配置
    #
    # headers 引用 pi 子进程 env 里的 ``${FACHUAN_USER_TOKEN}``（pi 支持 mcp.json
    # header 的环境变量展开）：值是发起会话的律师的 access token，由
    # ``pool.acquire(session_env=...)`` 注入。mcp_server 端透传该头，工具即以
    # 律师本人身份调 REST API（confused deputy 修复，见 ``pi/user_token.py``）。
    # token 缺失时展开为空，mcp_server 回退服务账号（stdio/手工场景）。
    config_path = _write_mcp_json(root, resolved)

    # 3) 系统提示词（AGENTS.md）
    _write_agents_md(root)

    # 4) 仅供回退路径的凭证复制（不覆盖已生成的文件）
    _copy_user_credentials(root)
    return config_path


def _write_settings_json(target_dir: str | Path, *, model_hint: str = "", provider: Any = None) -> Path | None:
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
        provider: 已查询的 LLMProvider；缺省 None 时自行查询（避免重复读库）。

    Returns:
        写出的路径；无法确定模型时返回 ``None``（不写，交给 pi 自己决定）。
    """
    from . import model_config

    if provider is None:
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
    level = model_config.resolve_thinking_level(model_id, provider=provider)
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
            "type": STREAMABLE_HTTP_TYPE,
            "url": resolved.url,
            "headers": {
                "Authorization": f"Bearer ${{{user_token_env}}}",
                # 会话标识：``ask_user`` 要靠它把提问推回对的 SSE 通道。
                # pi 支持 mcp.json header 里的环境变量展开，值由
                # ``chat_service`` 注入 pi 子进程 env（FACHUAN_SESSION_ID）。
                # 缺失时展开为空串，``ask_user`` 会返回 no_channel 而不是报错
                # （提问不是闸门，问不到就让模型按假设继续）。
                # 头名与 ``toolface.SESSION_HEADER`` 同源（HTTP 头大小写不敏感，
                # 那边是小写规范形式，这里按 pi 文档的写法保持 Title-Case）。
                "X-Fachuan-Session": "${" + SESSION_ID_ENV + "}",
            },
            # pi 默认 exposure=codemode：MCP 工具不声明给模型（只能经
            # codemode 脚本间接调），表现为「模型说去查，但没有 tool_call 直接
            # done」。法穿场景是模型直接挑工具，默认 direct 全量声明；
            # 按需加载见 resolve_exposure / FACHUAN_MCP_EXPOSURE 与
            # mcp_server/tool_tiers.py。
            "exposure": exposure,
            **extra,
            # deferred 下 pi 会把它列入 system prompt 的 mcp_servers 小节，
            # 也让 tool_search 按它排序——写清楚"这服务有什么"比堆关键词有用。
            "description": SERVER_DESCRIPTION,
            # pi 每请求默认 60s 超时，会先于 client 侧 LLM 链路工具的 180s
            # （见 tools/documents/litigation.py 等 12 处 timeout=180）掐断——
            # 双端超时必须 pi > client，否则 client 的努力全部作废。200 给
            # 传输层留余量；工具发 progress notifications 可重置该计时。
            #
            # 这里刻意写**字面量**而不是 ``TOOL_TIMEOUT_SECONDS``：
            # ``tests/ci/unit/mcp_server/test_pi_timeout_alignment.py`` 用正则扫
            # 本文件的 ``"timeout": N`` 文本，换成常量名会让那道门禁扫不到东西
            # 而硬失败。两处取值的一致性由 ``tests/ci/unit/agent/test_toolface.py``
            # 断言 == ``toolface.TOOL_TIMEOUT_SECONDS`` 守住。
            "timeout": 200,
        }
    return {
        "command": python_bin(),
        "args": ["-m", "mcp_server"],
        "cwd": str(backend_dir()),
        # stdio 回退同样不能落回 codemode 默认（工具将不可调用）
        "exposure": exposure,
        **extra,
        "timeout": 200,
    }


def write_pi_mcp_config(target_dir: str | Path, endpoint: McpEndpoint | None = None) -> Path:
    """兼容旧名：仅写 MCP 配置（不碰模型），保留供测试/脚本使用。"""
    resolved = endpoint or resolve_endpoint()
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)
    return _write_mcp_json(root, resolved)


def _write_mcp_json(root: Path, resolved: McpEndpoint) -> Path:
    """写 ``mcp.json``：法穿共享 MCP + 元典 MCP（没配元典 key 时只有法穿那一条）。

    两处写入口（``write_pi_config`` / ``write_pi_mcp_config``）共用这一份，避免
    「手工写配置」与「正式链路」的 ``mcpServers`` 像历史上那样各写一份字段表、
    改一处漏一处。
    """
    from .user_token import USER_TOKEN_ENV

    servers: dict[str, Any] = {SERVER_NAME: _build_server_entry(resolved, USER_TOKEN_ENV)}
    servers.update(_build_yuandian_server_entries())
    config_path = root / "mcp.json"
    config_path.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


def _build_yuandian_server_entries() -> dict[str, Any]:
    """元典 MCP Server 的 ``mcpServers`` 条目；总开关关闭或没配 key 时返回空字典（不挂）。

    为什么没 key 就整块不挂：带空 key 的元典 server 每条 ``tools/list`` 都会 401，
    pi 仍会把这批工具声明给模型，结果是一堆「知道有但查不了」的工具把模型带进
    反复重试——用户没填 key 就不该有这些工具。总开关（``YUANDIAN_MCP_ENABLED``）
    关闭时同理：律所不允许把案情发给元典，就不该让模型看到这些工具。

    读库失败同样走降级（两个读取函数都不抛）：元典挂不上不该影响法穿自己的工具面。
    判定口径与 ``pool._yuandian_env`` 一致——挂了 server 就有 key 注入，反之亦然。

    清单与地址是代码常量（``apps.core.services.yuandian_settings``），因此这里
    没有任何「用户把 server 名写错」的入口。
    """
    from apps.core.services.yuandian_settings import (
        YUANDIAN_MCP_BASE_URL,
        YUANDIAN_MCP_SERVERS,
        load_yuandian_settings,
        yuandian_mcp_enabled,
    )

    if not yuandian_mcp_enabled() or not load_yuandian_settings().api_keys:
        return {}
    return {
        f"yuandian-{name}": {
            "type": STREAMABLE_HTTP_TYPE,
            "url": f"{YUANDIAN_MCP_BASE_URL}/mcp/{name}/stream",
            "headers": {
                # 元典实测要求显式要 SSE：缺这个头时服务端按一次性 JSON 应答，
                # 流式 MCP 工具结果拿不到。两个头的值都是官方配置原文。
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer ${{{YUANDIAN_API_KEY_ENV}}}",
            },
        }
        for name in YUANDIAN_MCP_SERVERS
    }


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
