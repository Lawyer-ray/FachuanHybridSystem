"""qoder —— 第六个 agent 运行时（Qoder Agent SDK 驱动 ``qodercli`` 子进程）。

## 为什么接它（与 ``docs/03-技术分析与复盘/qoder-agent-sdk-vs-pi-2026-11-16.md`` 对照）

那份调研的结论是「别为了多一个选项而接」，理由是它与 pi 同构、并行不带来能力
互补。**本条接线的理由与当初不同**：

1. **它有自研模型与中文/法律场景的调优**（Qoder 云侧迭代，我们不需要跟）；
2. **它是同构的第二个实现**，正好当 pi 的对照栏——同一问题两栏并答，用来判断
   「答案不好」是模型的问题还是提示词/工具面的问题；
3. 一旦 BYOK 自定义 URL 的开关（``allow_byok >= 2``）对我们开放，它就能把
   内网网关当模型后端，且**本地直连、提示词不经过 Qoder 云**。

调研里列出的六条真问题在这一版里的处置：

| 问题 | 本模块的处置 |
|:-|:-|
| P0-1 身份与审计断裂 | MCP ``headers`` 每会话现拼律师 token（不走 Qoder 账号身份）。**Qoder 账号只用来跑模型**，业务读权限仍归律师本人；``credits`` 只在日志里，不混进 ``AgentRun`` 的 token 口径 |
| P0-2 工具面安全边界 | ``tools=[]`` + ``allowed_tools=[]`` + ``setting_sources=[]`` + ``strict_mcp_config``：内置 21 个工具全关，业务工具只来自共享 MCP |
| P1-3 高风险分级 | 三道闸：``disallowed_tools``（硬拒）→ ``PreToolUse`` hook 把高危强制置 ``ask`` → ``can_use_tool`` 接现有 ``services/approval`` |
| P1-4 压缩接管退化 | 承认退化：**不用原生 session**（每轮全新配置目录、不 ``resume``），上下文由编排层的 transcript 回退负责，因此不需要接管压缩 |
| P1-5 提示词与技能 | 默认 **append 到 qodercli preset**（不是全替换）；技能本轮不接（``skills=[]``、不挂插件） |
| P2-6 体积与离线 | 随 wheel 分发 165MB 的 ``qodercli``；**必须能连 Qoder 做鉴权**，纯离线部署不可用（``/backends`` 会如实标不可用） |

## 与 pi / claude-agent 的口径差异（都是刻意的）

- **无原生会话**：不传 ``resume`` / ``continue_conversation``。配置目录的处理分两种：
  **配了显式凭据**（令牌 / SA 密钥）时本轮新建临时目录、``finally`` 删除；
  **没配**时**必须**沿用默认目录（``~/.qoder``）——登录态就在那里，指到临时目录等于
  「未登录」。理由见两条：(1) 律师对话不能在多个会话/多个律师之间共用配置目录；
  (2) 编排层在「没有 pi session 但有历史」时会把历史渲染成 transcript 附在 prompt
  前，两套上下文叠在一起会让同一句话出现两次。``ctx.isolated`` 因此天然满足。
- **``steer=False``**：SDK 有 ``client.query(priority=...)``，但需要
  :class:`LiveBackendHandle` 接线；未接线前声明 ``True`` 只会渲染出一个
  「敲进去也没人接」的插话框。接线并实测后再改。
- **``compaction=True`` 但语义有限**：单轮内 CLI 自带 autocompact；跨轮没有原生
  历史，靠编排层的 transcript 回退（它有条数/字数上限）。
- **不发 ``done``**：与 ``pi_backend`` / ``claude_agent_backend`` 同口径，
  ``done`` 由编排层铸（后端再发一条会让单栏出现两条）。

## 尚未实机验证的三件事（上线前必须做）

1. 高危工具**必定**弹审批卡（qoder 自己的分类器不能替律师放行）；
2. MCP 工具全名是 ``mcp__fachuan__<raw>``（否则审批链按名字匹配会**静默失效**）；
3. 断网 / 未登录时的报错落在 :class:`BackendErrorKind` 的 AUTH，而不是「未知错误」。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    # 只为类型：SDK 是可选依赖，模块级 import 会把它变成硬依赖（见模块 docstring）。
    from qoder_agent_sdk import HookCallback, McpServerConfig, ModelPolicyProvider, ModelPolicyResult

from asgiref.sync import sync_to_async

from .base import BackendCapabilities, BackendError, BackendErrorKind, RunContext, StreamFrame
from .gateway_cache import GatewaySettings, get_gateway_settings, resolve_gateway_target
from .qoder_login import config_dir as login_config_dir
from .qoder_login import is_authenticated
from .ticks import with_ticks
from .toolface import (
    SERVER_NAME,
    TIER_FULL,
    TIER_LITE,
    TOOL_TIER_HEADER,
    agent_home,
    endpoint_from_env,
    port_open,
    shared_enabled,
    tool_prefix,
)

logger = logging.getLogger(__name__)

#: 后端标识。进事件流的 ``agent`` 字段与 ``AgentRun`` 归因，**改名等于历史数据对不上**。
KIND = "qoder"

#: 审批闸门开关（默认开）。关掉时 ``approval`` 能力声明同步为 ``False``——
#: 「声明与实现同源」，与 ``claude_agent_backend.approval_enabled`` 同款。
APPROVAL_ENV = "FACHUAN_QODER_APPROVAL"

#: 显式指定 CLI 路径（离线部署把自己放的二进制指过来）。留空则用 SDK 随 wheel
#: 分发的 ``qodercli``，再退回 PATH 上的 ``qodercli`` / ``qoder``（SDK 自己的查找顺序）。
CLI_PATH_ENV = "FACHUAN_QODER_CLI_PATH"

#: 工具面档位（``lite`` / ``full``）。**默认 ``lite``**：全量 434 个工具约 10.2 万
#: token/轮，且 qoder 未在 full 档验证过。
TOOL_TIER_ENV = "FACHUAN_QODER_TOOL_TIER"

#: 模型来源：``qoder``（默认，Qoder 云侧模型）/ ``gateway``（把律所网关当 BYOK 直连）。
#:
#: 为什么默认 ``qoder``：接它的理由就是「它自己的模型更适合中国法律」。``gateway``
#: 需要 Qoder 账号的 ``allow_byok >= 2``（服务端下发的开关，服务商不给就开不了），
#: 所以只作为**可选路径**存在，见 :func:`_resolve_gateway_target`。
MODEL_SOURCE_ENV = "FACHUAN_QODER_MODEL_SOURCE"
MODEL_SOURCE_QODER = "qoder"
MODEL_SOURCE_GATEWAY = "gateway"

#: 个人访问令牌 / 服务账号密钥的环境变量名（**SDK 自己的名字**，不是我们另起的）。
#: 两者都为空时退回 ``qodercli`` 在本机的登录态（``qodercli_auth()``）。
#:
#: ## 为什么不自己再造一个 ``FACHUAN_QODER_TOKEN``
#:
#: SDK 的 ``access_token_from_env()`` / ``service_account_from_env()`` 默认就读这两个
#: 名字。另起一套等于让运维在「SDK 的文档」和「我们的文档」之间二选一，而选错时的
#: 表现是「未登录」——排查方向会被带偏。**秘密不进日志**，与 ``RunContext.user_token``
#: 同级。
ACCESS_TOKEN_ENV = "QODER_PERSONAL_ACCESS_TOKEN"
SA_KEY_ENV = "QODER_SERVICE_ACCOUNT_KEY"

#: 出站代理（可选）。留空表示沿用宿主环境变量——与其它后端不同，**这里不清代理**：
#: qoder 云在公网，律所内网的直连假设不成立；要访问内网 BYOK 网关时再显式清。
PROXY_ENV = "FACHUAN_QODER_PROXY"

#: 一轮内最多模型循环次数。与其它后端同值同因：超限的代价是**这一栏一个字都不产出**。
MAX_TURNS = 24

#: 登录态预检的超时（秒）。现已改走磁盘凭据判据（见 ``qoder_login``），此常量仅供
#: 兼容旧部署的环境变量保留解析入口。
#:
#: 为什么要有这一步：``qodercli`` 未登录时会**立刻退出**并打印
#: ``Not logged in · Please run /login``，但 SDK 的 ``initialize`` 控制请求会一直等到
#: ``control_request_timeout_ms``（默认 60s）才抛 ``Control request timeout: initialize``。
#: 律师看到的是「转圈一分钟 + 未知错误」。预检把这两件事一起修掉：秒级、且能落到
#: ``AUTH`` 分类并给出「去登录 / 配令牌」的具体动作。
LOGIN_PROBE_ENV = "FACHUAN_QODER_LOGIN_PROBE_TIMEOUT"

#: 未登录时的人话（直接给可执行动作，不描述内部机制）。
#:
#: 动作给的是**前端入口**：律师没有服务器 shell，「去跑 qodercli login」对他们是
#: 一句废话。运维/离线部署仍可配令牌，所以两个选项都写在后面。
LOGIN_HINT = (
    "未登录 Qoder：在输入框的「选择 AI」菜单里点「登录 Qoder」完成浏览器授权"
    f"（或配置 {ACCESS_TOKEN_ENV} / {SA_KEY_ENV}）"
)

#: 判定「未登录」的输出特征（小写子串）。命中即 ``AUTH``。
_LOGIN_MISSING_MARKERS: tuple[str, ...] = ("not logged in", "please run /login", "/login to", "login required")

#: ``stderr`` 尾巴保留多少行（只在报错文案里用，截断到几百字符）。
STDERR_TAIL_LINES = 40

#: 每轮临时配置目录的目录名前缀（建在系统临时目录下）。
CONFIG_DIR_PREFIX = "fachuan-qoder-"

#: 超过这个时长的 ``fachuan-qoder-*`` 目录视为崩溃残留（进程被杀时 ``finally`` 不会
#: 执行），新建目录时顺手清掉。
CONFIG_DIR_STALE_SECONDS = 6 * 3600

#: 律师拒绝时回给模型的话。
APPROVAL_REJECTED_MESSAGE = "律师未批准该操作（已拒绝），请换一个只读方案或告知用户需要人工处理。"

#: 不可逆删除类：连审批卡都不弹，直接不给（与 ``claude_agent_backend.BLOCKED_TOOL_NAMES``
#: 同口径）。名字是 MCP **原始名**，本模块负责拼成全名。
BLOCKED_TOOL_NAMES: frozenset[str] = frozenset({"delete_case"})

#: ``result_for`` 最多保留多少轮的收尾事实。后端是单例，只增不删会随运行轮数无限增长。
MAX_KEPT_RESULTS = 256

#: qoder 的错误码 → （分类，给人看的一句话）。来源：官方 SDK 文档 + 二进制字符串。
#:
#: 为什么不复用消息子串匹配（claude 的做法）：qoder 的错误**带稳定数字码**，
#: 按码分支比按中文/英文措辞分支稳得多；但码只出现在错误文本里，没有结构化字段，
#: 所以仍要按 token 匹配（见 :func:`_error_code`）。
ERROR_CODES: dict[str, tuple[BackendErrorKind, str, bool]] = {
    # 码: (分类, 文案, 是否可重试)
    "105": (BackendErrorKind.AUTH, "Qoder 登录已过期，请重新登录或更新访问令牌", False),
    "110": (BackendErrorKind.BUSY, "Qoder 今日额度已用尽，请明天再试或改用其它后端", False),
    "113": (BackendErrorKind.BUSY, "Qoder 配额已用尽，请联系管理员", False),
    "118": (BackendErrorKind.BUSY, "Qoder 配额已用尽，请联系管理员", False),
    "116": (BackendErrorKind.BUSY, "Qoder 团队 Credits 已用尽，请联系管理员", False),
    "117": (BackendErrorKind.BUSY, "Qoder 成员 Credits 已用尽，请联系管理员", False),
    "406": (BackendErrorKind.UNKNOWN, "本轮内容被 Qoder 的安全策略拒绝，换个问法或补充说明后重试", False),
    "47902": (BackendErrorKind.UNKNOWN, "Qoder 超过最大轮次仍未完成，请把问题拆小后重试", False),
    "80411": (BackendErrorKind.CONTEXT_OVERFLOW, "本轮输入过长，请精简材料或新开会话", False),
    "500": (BackendErrorKind.UNAVAILABLE, "Qoder 服务暂时不可用，请稍后重试", True),
    "10408": (BackendErrorKind.UNAVAILABLE, "Qoder 请求超时，请稍后重试", True),
    "10500": (BackendErrorKind.UNAVAILABLE, "Qoder 服务内部错误，请稍后重试", True),
}

#: 从错误文本里取数字码。``\b`` 两侧锚定避免 ``1040`` 命中 ``10408``。
_ERROR_CODE_RE = re.compile(r"(?<!\d)(\d{3,5})(?!\d)")

#: 权限模式写死（不给调用方覆盖）。``bypassPermissions`` / ``acceptEdits`` / ``auto``
#: 都会让 ``can_use_tool`` **静默跳过**——那正是审批闸门存在的理由，所以只允许
#: ``default``（与 ``claude_agent_backend._HARDENED_PERMISSION_MODE`` 同款）。
_HARDENED_PERMISSION_MODE: Literal["default"] = "default"

#: 默认 system prompt（``ctx.system_prompt`` 为空时**追加**到 qodercli preset 后面）。
DEFAULT_INSTRUCTIONS = (
    "你是法穿法律事务系统的助手。用户是执业律师。"
    "需要事实时必须调用工具查询，不得编造案件、当事人、金额、期限或法条。"
    "回答简洁、直接给结论，再给依据。"
)


# ── 配置解析（纯函数，便于离线测试）────────────────────────────────────


def approval_enabled() -> bool:
    """审批闸门是否启用（默认启用）。"""
    raw = os.environ.get(APPROVAL_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def tool_tier() -> str:
    """本轮工具面档位；未知取值一律回落 ``lite``（fail-safe）。"""
    raw = os.environ.get(TOOL_TIER_ENV, TIER_LITE).strip().lower()
    return TIER_FULL if raw == TIER_FULL else TIER_LITE


def model_source() -> str:
    """模型来源；未知取值一律回落 ``qoder``（**不能**回落到 gateway）。

    方向很重要：``gateway`` 需要 Qoder 侧开关，回落过去会让「配置写错」变成
    「整栏跑不起来」；回落 ``qoder`` 最坏只是「用了它自己的模型」。
    """
    raw = os.environ.get(MODEL_SOURCE_ENV, MODEL_SOURCE_QODER).strip().lower()
    return MODEL_SOURCE_GATEWAY if raw == MODEL_SOURCE_GATEWAY else MODEL_SOURCE_QODER


def resolve_cli_path() -> str | None:
    """:data:`CLI_PATH_ENV` 指定的 CLI 路径；没配返回 ``None``（交给 SDK 自己找）。"""
    return os.environ.get(CLI_PATH_ENV, "").strip() or None


def resolve_proxy() -> str | None:
    """:data:`PROXY_ENV` 指定的出站代理；没配返回 ``None``（沿用宿主环境）。"""
    return os.environ.get(PROXY_ENV, "").strip() or None


def backend_capabilities() -> BackendCapabilities:
    """能力声明。``approval`` 与开关同源，其余是静态事实。"""
    return BackendCapabilities(
        streaming=True,
        tool_calls=True,
        approval=approval_enabled(),
        # 单轮内 CLI 自带 autocompact；跨轮靠编排层 transcript 回退（有上限），
        # 所以「不需要编排层再额外压缩」。语义边界见模块 docstring。
        compaction=True,
        # SDK 有 query(priority=...)，但需要 LiveBackendHandle 接线；未接线前不许声明。
        steer=False,
        # 每轮一条独立子进程 + 独立配置目录，无进程级共享状态。
        concurrent_in_session=True,
    )


def has_explicit_auth() -> bool:
    """是否配置了显式凭据（令牌 / 服务账号密钥）。

    两个用途：

    1. 决定 **配置目录能不能临时化**——登录态存在配置目录里，临时目录看不到
       宿主 ``~/.qoder`` 的登录态，所以「有显式凭据」才敢用临时目录；
    2. ``/backends`` 的可用性文案（未配置凭据时要求本机已 ``qodercli login``）。
    """
    return bool(os.environ.get(ACCESS_TOKEN_ENV, "").strip() or os.environ.get(SA_KEY_ENV, "").strip())


def is_available() -> bool:
    """本部署现在能不能用 qoder：**只看 SDK 装没装**（不拉进程、不查库）。

    与 ``opencode`` / ``codex`` 的探测同口径：这判的是「模块起得来吗」，不是
    「这一轮能不能跑通」。鉴权、网关、MCP 的失败在真正开跑时由 ``BackendError``
    报出来，文案比这里猜的准。

    **不探测登录态**：``qodercli`` 的登录检查要起进程 + 联网（秒级），而
    ``/agent/backends`` 每次打开切换器都会被调。用户没登录时第一轮会拿到
    ``AUTH`` 分类的可读报错，代价是一轮。
    """
    from importlib.util import find_spec

    return find_spec("qoder_agent_sdk") is not None


def qoder_auth() -> Any:
    """本轮的鉴权配置（SDK 对象）。

    顺序：个人令牌 → 服务账号密钥 → 复用本机 ``qodercli`` 登录态。

    为什么服务账号排在令牌后：令牌是「某个人」的身份、SA 是「某个组织」的身份。
    律所部署应当优先用 SA（人员流动不影响服务），但**探测顺序不能靠猜**——
    运维显式配了令牌就以令牌为准，配错时能在第一轮报错里看出来。

    Returns:
        ``QoderAgentOptions.auth`` 的取值。**类型是 ``Any``**：SDK 未安装时本模块
        仍要被 import（注册表探测依赖它），模块级 import SDK 类型会把整个后端变成
        硬依赖。
    """
    from qoder_agent_sdk import access_token, qodercli_auth, service_account

    token = os.environ.get(ACCESS_TOKEN_ENV, "").strip()
    if token:
        return access_token(token)
    key = os.environ.get(SA_KEY_ENV, "").strip()
    if key:
        return service_account(service_account_key=key)
    return qodercli_auth()


def make_config_dir() -> Path:
    """新建本轮的 ``QODER_CONFIG_DIR``（0700）；顺手清掉超时的崩溃残留。"""
    base = Path(tempfile.gettempdir())
    _sweep_stale_config_dirs(base)
    path = Path(tempfile.mkdtemp(prefix=CONFIG_DIR_PREFIX, dir=base))
    # mkdtemp 本就按 0700 创建；显式再设一次，不依赖实现细节与 umask。
    path.chmod(0o700)
    return path


def remove_config_dir(path: Path | None) -> None:
    """删除本轮的配置目录（含 CLI 写进去的会话记录）；删不掉只记日志。"""
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        logger.warning("qoder 配置目录删除失败（留给下次清理）: %s", path)


def _sweep_stale_config_dirs(base: Path) -> None:
    deadline = time.time() - CONFIG_DIR_STALE_SECONDS
    try:
        candidates = list(base.glob(f"{CONFIG_DIR_PREFIX}*"))
    except OSError:
        return
    for child in candidates:
        try:
            if child.is_dir() and child.stat().st_mtime < deadline:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


def resolve_cli_binary() -> str | None:
    """本地 ``qodercli`` 可执行文件的路径（预检用）；找不到返回 ``None``。

    查找顺序与 SDK 一致（勿改）：显式 ``cli_path`` → 随 wheel 分发的
    ``qoder_agent_sdk/_bundled/qodercli`` → ``PATH`` 上的 ``qodercli`` / ``qoder``。
    两边各写一套查找顺序就会在「SDK 找得到、我们找不到」时让预检静默失效——
    而失效的表现恰好是「又变回转圈 60 秒」，很难归因。
    """
    explicit = resolve_cli_path()
    if explicit:
        return explicit
    try:
        import qoder_agent_sdk
    except ImportError:  # pragma: no cover - 注册表已在 is_available() 拦住
        return None
    bundled = Path(qoder_agent_sdk.__file__).parent / "_bundled" / "qodercli"
    if bundled.exists():
        return str(bundled)
    return shutil.which("qodercli") or shutil.which("qoder")


def login_missing_reason(output: str) -> str | None:
    """CLI 输出里有没有「未登录」的特征；有则返回截断后的原文（给报错文案用）。

    返回原文而不是布尔：律师/运维看到 ``Not logged in · Please run /login`` 时
    一眼就知道该怎么处理，只看到「鉴权失败」就要多排查一轮。截断到 200 字，
    避免把整段 CLI 启动日志贴到界面上。
    """
    text = (output or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if not any(marker in lowered for marker in _LOGIN_MISSING_MARKERS):
        return None
    return text[:200]


async def ensure_logged_in() -> None:
    """未登录就**秒级报 ``AUTH``**，并告诉用户去前端点「登录 Qoder」。

    ## 为什么必须在拉起真会话之前拦

    未登录时 ``qodercli`` 会立刻退出，但 SDK 的 ``initialize`` 控制请求会一直等到
    ``control_request_timeout_ms``（默认 60s）才抛 ``Control request timeout: initialize``
    —— 用户体验是「转圈一分钟 + 未知错误」，而真实原因是一个 30 秒能修好的
    「没登录」。

    ## 判据是磁盘上的凭据文件，不是跑 CLI 去问

    ``<config dir>/.auth/user`` 存在即已登录（实测判据，见 ``qoder_login`` 的说明）。
    跑 ``qodercli`` 去问要起进程 + 联网（秒级，且联网失败与未登录难区分）；而登录
    已经是**前端按钮**触发的，服务端只需看它写下的凭据。

    配了显式凭据（令牌 / SA 密钥）时不看磁盘：那条路根本不读配置目录里的登录态。

    Raises:
        BackendError: 未登录（``AUTH``，不可重试）。
    """
    if is_authenticated():
        return
    raise BackendError(BackendErrorKind.AUTH, f"{LOGIN_HINT}（在输入框的「选择 AI」菜单里点「登录 Qoder」）")


def work_dir() -> Path:
    """本轮的 cwd（稳定，``<agent home>/qoder/work``，0700）。

    为什么稳定而不是临时目录：``qodercli`` 把「项目级配置 / 会话索引」挂在 cwd 上，
    每轮换一个目录会让同一会话在它眼里变成一堆互不相干的 project。**不放临时目录**
    还有第二个理由——临时目录可能被别的用户读到（``/tmp`` 共享）。

    为什么建在 ``agent_home`` 下：与 pi 的 ``work/config/sessions`` 同一套根目录
    （``FACHUAN_AGENT_HOME``，多 worker 部署必须共享），运维只需要管一个地方。
    """
    path = agent_home() / "qoder" / "work"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        logger.warning("无法收紧 %s 权限（忽略）", path, exc_info=True)
    return path


def build_env(*, config_dir: Path | None) -> dict[str, str | None]:
    """给 ``qodercli`` 子进程的环境变量（**叠加**在宿主环境之上，见 SDK 的 ``env`` 语义）。

    ``config_dir`` 必须与「登录凭据所在目录」**是同一个**：指到别处时 CLI 会认为没
    登录（登录态就在 ``<config dir>/.auth/user``）。所以本函数只负责如实透传，由调用方
    决定是本轮临时目录（配了显式凭据）还是共享登录目录（:func:`qoder_login.config_dir`）。

    ``env`` 的值写 ``None`` 在 SDK 里表示「从子进程环境里删掉该变量」。
    """
    env: dict[str, str | None] = {
        # 遥测/错误上报一律关：律师对话属于敏感数据。
        "QODER_DISABLE_TELEMETRY": "1",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
    }
    if config_dir is not None:
        env["QODER_CONFIG_DIR"] = os.fspath(config_dir)
    return env


def build_mcp_servers(*, url: str, user_token: str, session_id: str) -> dict[str, McpServerConfig]:
    """共享 MCP 的 ``mcp_servers`` 配置（``type="http"`` + headers）。

    ``Authorization`` 与 ``x-fachuan-session`` 都是**必须**的：

    - 前者是律师本人的业务读权限凭据（:8011 强制 Bearer，且刻意不回退服务账号）——
      这是「Qoder 账号只跑模型、业务权限仍归律师」那条边界的技术实现；
    - 后者让 MCP 服务端的审批闸门把审批卡投到正确会话，不带时会建「无会话单」，
      只有超管能批 → 等于高危工具全拒。

    **header 是静态字符串**（qoder 的 MCP 配置没有 env 展开机制，与 pi 的
    ``${FACHUAN_USER_TOKEN}`` 不同），所以只能每轮现拼。拼错/漏传的后果是整所律师
    以同一身份读数据，因此 :func:`QoderBackend._mcp_servers` 在没有 token 时
    **宁可不挂工具**，也不退回服务账号。
    """
    server: McpServerConfig = {
        "type": "http",
        "url": url,
        "headers": {
            "Authorization": f"Bearer {user_token}",
            "x-fachuan-session": session_id,
            TOOL_TIER_HEADER: tool_tier(),
        },
    }
    return {SERVER_NAME: server}


def short_tool_name(tool_name: str) -> str:
    """``mcp__fachuan__delete_case`` → ``delete_case``（非 MCP 名原样返回）。"""
    prefix = tool_prefix()
    return tool_name[len(prefix) :] if tool_name.startswith(prefix) else tool_name


def disallowed_tools() -> list[str]:
    """硬拒清单（MCP 全名）。

    ``delete_case`` 这类工具**连审批卡都不该弹**：它不是「律师可能想批」，而是
    系统层面不允许模型自主发起。名称必须拼成全名——``disallowed_tools`` 按工具全名
    匹配，写原始名会静默不生效（工具照旧可调，只是没人拦）。
    """
    return sorted(f"{tool_prefix()}{name}" for name in BLOCKED_TOOL_NAMES)


# ── 收尾事实 ────────────────────────────────────────────────────────────


@dataclass
class QoderRunResult:
    """一轮跑完后的事实（编排层用它回写会话模型与 ``AgentRun``）。"""

    model: str
    #: Qoder 的 Credit 消耗。**只记日志，不进 ``AgentRun``**：那是另一种货币，
    #: 混进 token 口径会让 ``/usage/by-model`` 的汇总失去意义（见模块 docstring P0-1）。
    credits: float = 0.0
    context_used: int = 0
    context_total: int = 0


@dataclass
class _RunState:
    """单轮的事件翻译状态。**按 run_id 归集**：后端是单例且允许多会话并发。"""

    #: 本轮**是否见过流式正文增量**（只由 ``text_delta`` 置真）。
    #:
    #: 判据是「流式通道通不通」，不是「发过没有」：流式通时 ``AssistantMessage``
    #: 的兜底必须完全关掉，否则同一段正文出现两遍；流式不通时每轮都要发，因为
    #: 工具循环里第 2、3 轮才有正文（claude 接入时在这一处踩过真机事故）。
    saw_stream_text: bool = False
    #: ``content_block`` index → 该块的状态（type / tool 名 / 累积的 JSON 片段）。
    blocks: dict[int, dict[str, Any]] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reported_usage: bool = False
    #: ``tool_use_id`` → 工具名（``tool_result`` 只有 id，没有名字）。
    tool_names: dict[str, str] = field(default_factory=dict)
    #: 最近一条 assistant 消息自报的模型名（用于回写 ``AgentSession.llm_model``）。
    model: str = ""
    #: CLI 的 stderr 尾巴（最多 :data:`STDERR_TAIL_LINES` 行）。
    #:
    #: 为什么必须收集：SDK 在初始化阶段失败时只给我们一句
    #: ``Control request timeout: initialize``，而真正的原因（未登录 / 配额 / 代理拦截）
    #: **只会出现在 CLI 的 stderr 里**。不收集就只能报「未知错误」。
    stderr: list[str] = field(default_factory=list)


class QoderBackend:
    """Qoder Agent SDK 运行时（每次 ``stream()`` 拉起一条 ``qodercli`` 子进程）。"""

    kind = KIND

    capabilities: BackendCapabilities

    #: 按 ``run_id`` 归集的收尾事实（并发两轮互不覆盖）。
    _results: OrderedDict[str, QoderRunResult]
    #: 按 ``run_id`` 归集的翻译状态。
    _states: dict[str, _RunState]

    def __init__(self) -> None:
        self.capabilities = backend_capabilities()
        self._results = OrderedDict()
        self._states = {}

    def result_for(self, run_id: str) -> QoderRunResult | None:
        """取某一轮的收尾事实；未跑过 / 本轮异常 / 已被挤出保留窗口时为 ``None``。"""
        return self._results.get(run_id)

    def _remember_result(self, run_id: str, result: QoderRunResult) -> None:
        """记下本轮收尾事实，只保留最近 :data:`MAX_KEPT_RESULTS` 条。

        不做「读一次就删」：编排层（``stream`` / ``multi`` / 综合）各读一次，
        读的次数是调用方的实现细节，按次数删会让第二次读悄悄拿到 ``None``。
        """
        self._results[run_id] = result
        self._results.move_to_end(run_id)
        while len(self._results) > MAX_KEPT_RESULTS:
            self._results.popitem(last=False)

    def stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        """跑一轮，产出 SSE 事件（``agent`` / ``run_id`` 已带）。

        Raises:
            BackendError: 未登录 / 配额耗尽 / 模型不可用 / SDK 异常。
                ``asyncio.CancelledError`` 原样上抛（用户按停止不是错误）。
        """
        return self._stream(ctx)

    # ── 主流程 ──────────────────────────────────────────────────────────

    async def _stream(self, ctx: RunContext) -> AsyncGenerator[StreamFrame, None]:
        # 延迟 import：SDK 未安装时本模块仍可被注册表 import（见 builtin 的说明）。
        from qoder_agent_sdk import HookMatcher, QoderAgentOptions, QoderSDKClient

        self._results.pop(ctx.run_id, None)
        state = _RunState()
        self._states[ctx.run_id] = state
        session_id = str(ctx.session.session_id)
        max_turns = ctx.max_turns if ctx.max_turns is not None else MAX_TURNS
        #: 本轮临时配置目录（配了显式凭据时才有）。**只删它，不删共享登录目录**——
        #: 后者装着 qoder 的登录凭据，删一次全所都要重新授权。
        temp_config_dir: Path | None = None
        config_dir: Path | None = None
        resolved_model = ""

        try:
            # 未登录时先秒级报 AUTH（否则要等 SDK 的 60s 控制请求超时，见 ensure_logged_in）。
            await ensure_logged_in()
            target = await self._resolve_gateway_target(ctx)
            resolved_model = target.model if target is not None else ""
            # 配了显式凭据 → 本轮临时目录（执业数据不落盘）；否则用**共享登录目录**
            # （前端按钮写下的凭据就在那里面，换台 worker 也读得到）。
            temp_config_dir = make_config_dir() if has_explicit_auth() else None
            config_dir = temp_config_dir or login_config_dir()
            mcp_servers = self._mcp_servers(ctx)

            options = QoderAgentOptions(
                cwd=work_dir(),
                env=build_env(config_dir=config_dir),
                auth=qoder_auth(),
                cli_path=resolve_cli_path(),
                proxy=resolve_proxy(),
                # 模型来源=Qoder 时**不传 model**：由 CLI 按账号能力选，跑完再把
                # 真实模型回写会话（见 ``result_for``）。把网关模型名传给 qoder 云
                # 必然 404，而「静默换模型」又会污染成本口径，所以两条路都不走。
                model=target.model if target is not None else None,
                max_turns=max_turns,
                # ── 工具面：内置工具全关，业务工具只来自共享 MCP（四件套）──
                tools=[],
                skills=[],
                setting_sources=[],
                allowed_tools=[],
                disallowed_tools=disallowed_tools(),
                mcp_servers=mcp_servers,
                # 只允许我们自己那个 MCP server：否则用户级 settings 里配的第三方
                # MCP 也会被挂上（``setting_sources=[]`` 已挡一层，这里再锁一次）。
                allowed_mcp_server_names=[SERVER_NAME] if mcp_servers else [],
                strict_mcp_config=bool(mcp_servers),
                permission_mode=_HARDENED_PERMISSION_MODE,
                system_prompt=_system_prompt(ctx),
                # 逐 token 增量：不开只有「整段 assistant 消息」一种粒度，
                # 前端表现为长时间空白后突然出现一大段。
                include_partial_messages=True,
                # CLI 的 stderr 只进本轮状态（用于把「初始化超时」翻译成人话），不落库、
                # 不进日志正文：里面可能含账号邮箱等标识。
                stderr=_bind_stderr(state),
                # 本轮 ctx 由闭包绑定：SDK 回调的参数不携带任何业务上下文。
                can_use_tool=_bind_can_use_tool(ctx),
                hooks={
                    "PreToolUse": [
                        HookMatcher(matcher=None, hooks=[_bind_pre_tool_use(ctx)]),
                    ]
                },
                resolve_model=_bind_resolve_model(target),
                on_auth_expired=_on_auth_expired,
            )

            async with QoderSDKClient(options=options) as client:
                await client.query(ctx.prompt)
                async for msg in with_ticks(client.receive_response()):
                    if msg is None:
                        # 本 tick 无新消息：让出一帧，编排层借它把审批事件推进来。
                        yield None
                        continue
                    for frame in self._translate(msg, ctx.run_id):
                        yield {**frame, "agent": self.kind, "run_id": ctx.run_id}

                    result_msg = _result_message(msg)
                    if result_msg is None:
                        continue
                    failure = self._result_failure(result_msg, max_turns=max_turns)
                    # 失败的一轮同样产生了费用：用量帧照发，再报错。
                    usage = self._usage_frame(result_msg, state)
                    if usage is not None:
                        yield {**usage, "agent": self.kind, "run_id": ctx.run_id}
                    if failure is not None:
                        raise failure
                    credits = float(getattr(result_msg, "total_credits", None) or 0.0)
                    if credits:
                        # Credits 是**另一种货币**，不进 AgentRun 的 token 口径（混进去
                        # 会让 ``/usage/by-model`` 的汇总失去意义），但完全丢掉就再也没
                        # 有任何地方能回答「这一栏花了多少额度」。所以落一条 info。
                        logger.info("qoder 本轮消耗 credits=%.4f session=%s run=%s", credits, session_id, ctx.run_id)
                    self._remember_result(
                        ctx.run_id,
                        QoderRunResult(
                            model=state.model or _model_from_result(result_msg) or resolved_model,
                            credits=credits,
                        ),
                    )
                    break
        except BackendError:
            raise
        except BaseException as exc:
            # 边界处统一转 ``BackendError``（base.py 的硬要求）。``CancelledError`` /
            # ``GeneratorExit`` 必须原样上抛——包成 BackendError 会让编排层把
            # 「用户按了停止」记成运行失败，``AgentRun`` 的成功率统计就废了。
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            logger.warning("qoder 本轮失败 session=%s run=%s", session_id, ctx.run_id, exc_info=True)
            raise self._wrap_error(exc, stderr_tail=state.stderr) from exc
        finally:
            self._states.pop(ctx.run_id, None)
            # ``async with`` 已退出（子进程已关）后才删，CLI 不会再往里写。
            # **只删本轮临时目录**（``temp_config_dir``）：共享登录目录里的凭据不能动。
            remove_config_dir(temp_config_dir)
            if ctx.run_id not in self._results:
                # 取消 / 出错也要留一条事实：模型名至少能回写会话，``AgentRun``
                # 不至于记成「不知道用了什么模型」（与 pi 的截断兜底同口径）。
                self._remember_result(ctx.run_id, QoderRunResult(model=state.model or resolved_model))

    async def _resolve_gateway_target(self, ctx: RunContext) -> Any | None:
        """``MODEL_SOURCE=gateway`` 时解析律所网关；``qoder`` 模式下恒为 ``None``。

        ## 为什么 ``gateway`` 模式需要 Qoder 侧的开关

        BYOK 自定义 base URL 由服务端下发的 ``featureSwitches.allow_byok >= 2``
        控制（见调研 §五）。我们开不了这个开关，所以这条路径**默认关闭**，打开后
        若账号没有权限，SDK 会返回 ``accessDenied``，由 :meth:`_wrap_error` 归成
        ``AUTH`` 并附上人话。

        Raises:
            BackendError: 显式选了 gateway 但平台没配好（base_url / key / 模型缺失）。
                这种错误必须报出来而不是悄悄回落 qoder 云模型——那会把「提示词
                出不出境」这条合规判断静默改掉。
        """
        if model_source() != MODEL_SOURCE_GATEWAY:
            return None

        settings = await sync_to_async(get_gateway_settings, thread_sensitive=True)(ctx.model)
        target = resolve_gateway_target(settings, ctx.model, api_key=ctx.api_key)
        if settings is None or target is None:
            raise BackendError(
                BackendErrorKind.UNAVAILABLE,
                "已把 qoder 配成「走律所网关」，但没有可用的 AI 平台（base_url / api_key）；"
                "请联系管理员，或把 FACHUAN_QODER_MODEL_SOURCE 改回 qoder",
            )
        return target

    def _mcp_servers(self, ctx: RunContext) -> dict[str, McpServerConfig]:
        """本轮该连哪个 MCP；不该连/连不上返回空 dict（降级为「无工具但能对话」）。"""
        token = (ctx.user_token or "").strip()
        if not token:
            # **不退回服务账号**：那会让全所数据以同一身份外流（模块 docstring P0-1）。
            logger.warning("qoder 本轮没有律师 token，无业务工具（仍可对话）")
            return {}
        if not shared_enabled():
            logger.warning("共享 MCP 已禁用（FACHUAN_MCP_SHARED=0），qoder 本轮无业务工具")
            return {}
        endpoint = endpoint_from_env()
        if not port_open(endpoint.host, endpoint.port):
            logger.warning("共享 MCP %s 不可连，qoder 本轮无业务工具", endpoint.url)
            return {}
        return build_mcp_servers(url=endpoint.url, user_token=token, session_id=str(ctx.session.session_id))

    # ── 事件翻译 ────────────────────────────────────────────────────────

    def _translate(self, msg: Any, run_id: str) -> list[dict[str, Any]]:
        """SDK 消息 → 0..n 个 SSE 事件（契约见 ``sse_types.py``）。

        正文/思考走 ``StreamEvent``（``include_partial_messages`` 打开时的原始 API
        事件）；工具调用在 ``content_block_stop`` 时才发（此时 ``input_json_delta``
        已拼完）；工具结果走 ``UserMessage`` 里的 ``ToolResultBlock``。
        """
        from qoder_agent_sdk import (
            AssistantMessage,
            StreamEvent,
            TextBlock,
            ThinkingBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        state = self._states.get(run_id)
        if state is None:
            return []

        if isinstance(msg, StreamEvent):
            event = msg.event if isinstance(msg.event, dict) else {}
            return self._translate_stream_event(event, state)

        if isinstance(msg, AssistantMessage):
            state.model = str(getattr(msg, "model", "") or state.model)
            frames: list[dict[str, Any]] = []
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text and not state.saw_stream_text:
                    # 兜底：仅当流式通道没吐过正文时，把整段补上。
                    # 工具循环里每一轮 assistant 消息都可能带正文，所以这里
                    # **不复位任何标志**——不置真，下一轮继续能发。
                    frames.append({"type": "delta", "content": block.text})
                elif isinstance(block, ThinkingBlock) and block.thinking and not state.saw_stream_text:
                    frames.append({"type": "thinking", "content": block.thinking})
                elif isinstance(block, ToolUseBlock) and block.id not in state.tool_names:
                    # 同理兜底：没有 stream 事件时也要让前端看到工具调用。
                    state.tool_names[block.id] = block.name
                    frames.append(
                        {
                            "type": "tool_call",
                            "tool_call_id": block.id,
                            "name": block.name,
                            "arguments": json.dumps(block.input, ensure_ascii=False) if block.input else None,
                        }
                    )
            return frames

        if isinstance(msg, UserMessage):
            frames = []
            content = msg.content if isinstance(msg.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    frames.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": block.tool_use_id,
                            "name": state.tool_names.get(block.tool_use_id, ""),
                            "result": _stringify(block.content),
                            "is_error": bool(getattr(block, "is_error", False)),
                        }
                    )
            return frames

        return []

    @staticmethod
    def _translate_stream_event(event: dict[str, Any], state: _RunState) -> list[dict[str, Any]]:
        """一个上游原始流事件 → 0..n 帧。

        只认四种事件；其余（``message_start`` / ``content_block_stop`` /
        ``message_stop`` …）只更新状态、不发帧，避免把生命周期事件刷进前端。

        形状按 Anthropic Messages 的 SSE 事件写（qoder 的 CLI 与 claude 同源），
        但**每处都做了取值兜底**：上游换个字段名时最坏是退化成「整段正文一次发」，
        而不是抛 KeyError 把整轮打挂。
        """
        etype = str(event.get("type") or "")

        if etype == "message_start":
            usage = (event.get("message") or {}).get("usage") or {}
            state.input_tokens += int(usage.get("input_tokens") or 0)
            state.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)
            state.cache_write_tokens += int(usage.get("cache_creation_input_tokens") or 0)
            if usage:
                state.reported_usage = True
            return []

        if etype == "content_block_start":
            index = int(event.get("index") or 0)
            block = event.get("content_block") or {}
            state.blocks[index] = {
                "type": str(block.get("type") or ""),
                "name": block.get("name") or "",
                "id": block.get("id") or "",
                "json": "",
            }
            return []

        if etype == "content_block_delta":
            index = int(event.get("index") or 0)
            block = state.blocks.get(index) or {}
            delta = event.get("delta") or {}
            dtype = str(delta.get("type") or "")
            if dtype == "text_delta":
                text = str(delta.get("text") or "")
                if not text:
                    return []
                state.saw_stream_text = True
                return [{"type": "delta", "content": text}]
            if dtype == "thinking_delta" and block.get("type") == "thinking":
                # 只在真正的 thinking 块里转发：网关的部分路由会把 thinking_delta
                # 塞进 text 块（协议违例），转了会让前端把思考当正文。
                text = str(delta.get("thinking") or "")
                return [{"type": "thinking", "content": text}] if text else []
            if dtype == "input_json_delta":
                block["json"] = str(block.get("json") or "") + str(delta.get("partial_json") or "")
                state.blocks[index] = block
            return []

        if etype == "content_block_stop":
            index = int(event.get("index") or 0)
            block = state.blocks.pop(index, None) or {}
            if block.get("type") != "tool_use":
                return []
            call_id = str(block.get("id") or "")
            name = str(block.get("name") or "")
            if not call_id or not name:
                return []
            state.tool_names[call_id] = name
            raw = str(block.get("json") or "")
            return [
                {
                    "type": "tool_call",
                    "tool_call_id": call_id,
                    "name": name,
                    "arguments": raw or None,
                }
            ]

        if etype == "message_delta":
            usage = event.get("usage") or {}
            state.output_tokens += int(usage.get("output_tokens") or 0)
            # 部分路由只在 message_delta 里给 input_tokens（message_start 恒 0）。
            state.input_tokens = max(state.input_tokens, int(usage.get("input_tokens") or 0))
            state.cache_read_tokens = max(state.cache_read_tokens, int(usage.get("cache_read_input_tokens") or 0))
            state.cache_write_tokens = max(state.cache_write_tokens, int(usage.get("cache_creation_input_tokens") or 0))
            if usage:
                state.reported_usage = True
            return []

        return []

    @staticmethod
    def _usage_frame(result_msg: Any, state: _RunState | None = None) -> dict[str, Any] | None:
        """一轮结束时的 ``usage`` 帧（一轮**只发一帧**）。

        优先用 ``ResultMessage.usage``（SDK 汇总的整轮值）；它缺失或全为 0 时退回
        ``state`` 里流事件的累加值。**两边都拿不到就返回 ``None``**（不发 0/0 假帧：
        编造的 0 无法与真实 0 区分）。
        """
        usage = getattr(result_msg, "usage", None) or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_write = int(usage.get("cache_creation_input_tokens") or 0)
        if input_tokens + output_tokens <= 0 and state is not None and state.reported_usage:
            input_tokens = state.input_tokens
            output_tokens = state.output_tokens
            cache_read = state.cache_read_tokens
            cache_write = state.cache_write_tokens
        if input_tokens + output_tokens <= 0:
            return None
        return {
            "type": "usage",
            "input_tokens": max(0, input_tokens),
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
        }

    # ── 错误分类 ────────────────────────────────────────────────────────

    @classmethod
    def _result_failure(cls, result_msg: Any, *, max_turns: int) -> BackendError | None:
        """错误的 ``ResultMessage`` → 可读的 ``BackendError``；正常结果返回 ``None``。

        只 ``break`` 不报错的话，这一栏就是一片空白、也没有任何提示。
        """
        subtype = str(getattr(result_msg, "subtype", "") or "")
        if not getattr(result_msg, "is_error", False) and not subtype.startswith("error"):
            return None

        terminal_reason = str(getattr(result_msg, "terminal_reason", "") or "")
        if subtype == "error_max_turns" or terminal_reason == "max_turns":
            return BackendError(
                BackendErrorKind.UNKNOWN,
                f"qoder 超过 {max_turns} 轮仍未完成，已停止；请把问题拆小或减少要查的内容后重试",
            )

        errors = [item.strip() for item in (getattr(result_msg, "errors", None) or []) if isinstance(item, str)]
        detail = "；".join(item for item in errors if item) or str(getattr(result_msg, "result", "") or "").strip()

        code = _error_code(detail)
        if code is not None:
            kind, message, retryable = ERROR_CODES[code]
            return BackendError(kind, f"{message}（qoder 错误码 {code}）", retryable=retryable)

        status = getattr(result_msg, "api_error_status", None)
        message = f"qoder 本轮失败（{subtype or 'error'}）：{(detail or '未给出原因')[:300]}"
        if isinstance(status, int):
            if status == 429:
                return BackendError(BackendErrorKind.RATE_LIMITED, message, retryable=True)
            if status in (401, 403):
                return BackendError(BackendErrorKind.AUTH, message)
            if status >= 500:
                return BackendError(BackendErrorKind.UNAVAILABLE, message, retryable=True)
        return cls._wrap_error(RuntimeError(message))

    @staticmethod
    def _wrap_error(exc: BaseException, *, stderr_tail: list[str] | None = None) -> BackendError:
        """SDK / CLI 异常 → ``BackendError``（分类口径见 ``base.py`` 的映射表）。

        ``stderr_tail`` 是 CLI 最后几行 stderr：SDK 在初始化阶段只会给
        ``Control request timeout: initialize`` 这种零信息量的话，真正原因（未登录 /
        配额 / 代理）只在 stderr 里。先看 stderr 再按异常文本分类，且把尾巴截一段
        拼进消息——**不拼进日志正文**（可能含账号标识）。
        """
        if isinstance(exc, BackendError):
            return exc
        name = type(exc).__name__
        tail = "\n".join((stderr_tail or [])[-5:]).strip()
        login_reason = login_missing_reason(tail)
        if login_reason is not None:
            error = BackendError(BackendErrorKind.AUTH, f"{LOGIN_HINT}（CLI 输出：{login_reason}）")
            error.__cause__ = exc
            return error
        text = (str(exc) or name).lower()

        if "control request timeout" in text:
            # SDK 在 CLI 初始化阶段没收到握手响应时的通用超时。真实原因八成是
            # 「未登录」（CLI 静默退出，控制请求无人应答），此时 stderr 尾巴就是
            # 唯一线索。归 UNAVAILABLE 而不是 AUTH：没有明确证据时不要把用户引到
            # 「重新登录」上（可能是代理 / 网络）。
            suffix = f"（CLI 输出：{tail[:200]}）" if tail else ""
            error = BackendError(
                BackendErrorKind.UNAVAILABLE,
                f"qoder CLI 初始化超时：未能与 qodercli 握手（常见原因：未登录、代理/网络不通、"
                f"或 qodercli 版本与 SDK 不匹配）{suffix}",
            )
            error.__cause__ = exc
            return error

        if "notfound" in name.lower() or "not found" in text:
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE)
        if "connection" in name.lower() or "timeout" in name.lower():
            return BackendError.wrap(exc, BackendErrorKind.UNAVAILABLE, retryable=True)
        # 「未登录 / 令牌过期 / 无 BYOK 权限」都归 AUTH：重试无用，要让用户重新登录或找管理员。
        if "auth" in text or "login" in text or "accessdenied" in text or "401" in text or "403" in text:
            return BackendError.wrap(exc, BackendErrorKind.AUTH)
        if "429" in text or "rate limit" in text:
            return BackendError.wrap(exc, BackendErrorKind.RATE_LIMITED, retryable=True)
        if "context" in text and ("window" in text or "length" in text or "overflow" in text):
            return BackendError.wrap(exc, BackendErrorKind.CONTEXT_OVERFLOW)
        code = _error_code(str(exc))
        if code is not None:
            kind, _message, retryable = ERROR_CODES[code]
            return BackendError.wrap(exc, kind, retryable=retryable)
        return BackendError.wrap(exc, BackendErrorKind.UNKNOWN)


# ── system prompt 与审批回调 ─────────────────────────────────────────────


def _system_prompt(ctx: RunContext) -> Any:
    """本轮的 system prompt。

    两条路径刻意不同（与 ``claude_agent_backend._instructions`` 的差异，理由写在这里）：

    - ``ctx.system_prompt`` 非空（综合结论这类一次性任务要**全量替换**规则）→ 直接
      传字符串，SDK 会拼成 ``--system-prompt <text>``；
    - 为空 → ``{"type": "preset", "preset": "qodercli", "append": ...}``，**追加**到
      qoder 自己的预设后面，而不是替换。

    为什么默认走追加：qoder 的预设里装着它的 agent 循环约定（什么时候用工具、怎么
    收尾）。全替换成我们这三句话，很可能把工具使用纪律一起删掉——而这一点在拿到
    真实账号前无法验证。等实测确认「全替换不掉工具能力」再改，比先改后查便宜。
    """
    if ctx.system_prompt:
        return ctx.system_prompt
    return {"type": "preset", "preset": "qodercli", "append": DEFAULT_INSTRUCTIONS}


def _bind_stderr(state: _RunState) -> Callable[[str], None]:
    """把 CLI 的 stderr 收进本轮状态（只留最后 :data:`STDERR_TAIL_LINES` 行）。

    不能直接写进日志：CLI 会把账号邮箱、配置目录、代理地址打出来。这些属于部署
    细节，需要时可以用 ``FACHUAN_LOG_LEVEL=DEBUG`` 把 ``logger.debug`` 打开。
    """

    def on_stderr(line: str) -> None:
        text = (line or "").rstrip()
        if not text:
            return
        logger.debug("qodercli stderr: %s", text)
        state.stderr.append(text)
        if len(state.stderr) > STDERR_TAIL_LINES:
            del state.stderr[:-STDERR_TAIL_LINES]

    return on_stderr


def _bind_can_use_tool(ctx: RunContext) -> Callable[[str, dict[str, Any], Any], Awaitable[Any]]:
    """把本轮 ``ctx`` 绑进审批回调，返回符合 SDK ``CanUseTool`` 签名的协程函数。

    每次 ``_stream`` 各自绑定：后端是单例且允许并发，两轮的回调互不串用。
    """

    async def can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
        return await _can_use_tool(ctx, tool_name, tool_input, context)

    return can_use_tool


async def _can_use_tool(ctx: RunContext, tool_name: str, tool_input: dict[str, Any], context: Any) -> Any:
    """高危工具执行前的审批闸门。

    **这是本后端能声明 ``approval=True`` 的唯一依据**，且只有在
    ``permission_mode="default"`` + ``allowed_tools=[]`` + ``setting_sources=[]``
    同时成立时才可能被调用（其余组合会被 CLI 静默跳过）。

    会话 / 轮次 / 用户一律取自 ``ctx``（由 :func:`_bind_can_use_tool` 绑定）；
    ``context`` 是 SDK 的 ``ToolPermissionContext``，只用它的 ``tool_use_id``
    关联审批卡与工具卡。

    拒绝一律返回 ``PermissionResultDeny``（**不抛异常**）：抛异常会被 SDK 包成
    「工具故障」，而真实语义是「律师拒了，本轮继续，模型换个只读方案」。
    """
    from qoder_agent_sdk import PermissionResultAllow, PermissionResultDeny

    from ..services.approval import RiskLevel, classify_risk, request_approval
    from ..services.approval.policy import multi_lane_write_refusal

    args = tool_input if isinstance(tool_input, dict) else {}
    short = short_tool_name(tool_name)

    # 1) 不可逆删除类：连审批卡都不该弹，直接不给。
    if short in BLOCKED_TOOL_NAMES:
        return PermissionResultDeny(message=f"该操作（{short}）已被系统禁用，请换只读方案。")

    session_id = str(ctx.session.session_id)

    # 2) 多栏并答时禁止写（结构性冲突，不是偏好问题）。
    refusal = multi_lane_write_refusal(session_id=session_id, tool_name=tool_name)
    if refusal:
        return PermissionResultDeny(message=refusal)

    # 3) 分级：只有高危 / 紧急才停下来问人。
    if classify_risk(tool_name, args) not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return PermissionResultAllow()

    approved, _approval_id, _reason = await request_approval(
        tool_name=tool_name,
        tool_args=args,
        user_id=ctx.user_id,
        session_id=session_id,
        run_id=ctx.run_id,
        tool_call_id=str(getattr(context, "tool_use_id", "") or ""),
    )
    if approved:
        return PermissionResultAllow()
    return PermissionResultDeny(message=APPROVAL_REJECTED_MESSAGE)


def _bind_pre_tool_use(ctx: RunContext) -> HookCallback:
    """把本轮 ``ctx`` 绑进 ``PreToolUse`` hook（每次 ``_stream`` 各自绑定）。

    返回类型用 SDK 自己的 ``HookCallback``（而非泛型 Callable）：hook 的入参是一个
    20 多个成员的联合类型，手写签名一定会漂——SDK 加一个 hook 事件我们就类型不过。
    实现内部把入参当 ``Any`` 读（只取 ``tool_name`` / ``tool_input``）。
    """

    async def pre_tool_use(hook_input: Any, _tool_use_id: str | None = None, _context: Any = None) -> Any:
        return await _pre_tool_use(ctx, hook_input)

    return pre_tool_use


async def _pre_tool_use(ctx: RunContext, hook_input: Any) -> dict[str, Any]:
    """``PreToolUse`` hook：把高危工具**强制置成「要问」**，其余放行。

    ## 为什么需要第三道闸（``disallowed_tools`` 与 ``can_use_tool`` 之外）

    qoder 的 ``can_use_tool`` 只在「CLI 自己觉得需要问」时才被调用（官方文档明说
    它不是完整调用日志，已被 ``permission_mode`` / 规则 / 分类器预放行的调用**不会
    进回调**）。这意味着：如果 qoder 的 auto 分类器把某个高危写工具判成可放行，
    审批闸门就**静默失效**——工具照旧执行，只是没人被问过。

    ``PreToolUse`` 是唯一能看到**每一次**工具调用的地方，它的
    ``permissionDecision`` 支持 ``"ask"``：由我们（而不是 CLI 的分类器）决定
    「这个调用必须问人」，然后由 ``can_use_tool`` 去做真正的审批。

    ## 为什么这里不做审批本身

    hook 只能返回 allow/deny/ask 三个词，不能挂起等外部决策；把审批搬到这里会
    丢掉 ``services/approval`` 的落库与离线挂起能力。**分工：hook 决定「必须问」，
    回调决定「批不批」**。

    返回空 dict = 不干预（CLI 按自己的规则继续）。
    """
    from ..services.approval import RiskLevel, classify_risk

    tool_name = str(getattr(hook_input, "tool_name", "") or "")
    tool_input = getattr(hook_input, "tool_input", None)
    args = tool_input if isinstance(tool_input, dict) else {}
    short = short_tool_name(tool_name)

    if short in BLOCKED_TOOL_NAMES:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"该操作（{short}）已被系统禁用",
            }
        }

    if not approval_enabled():
        # 审批闸门被显式关掉时，hook 也不再升级为 ask——否则 CLI 会等一个永远
        # 不会到来的回调（表现为工具卡住直到超时）。能力声明已同步为 False。
        return {}

    if classify_risk(tool_name, args) in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "该操作会对外发出/改文件/删除数据，需要律师确认",
            }
        }
    return {}


def _bind_resolve_model(target: Any | None) -> ModelPolicyProvider | None:
    """``MODEL_SOURCE=gateway`` 时返回「每次 LLM 调用都用律所网关」的模型策略回调。

    SDK 的语义：``ModelPolicyResult.model`` 可以是 ``CustomModel``
    （``{model, url, api_key, style}``），transport 会**从本地直连**那个地址，
    提示词不经过 Qoder 云（调研 §四的二进制证据）。

    返回 ``None`` 表示不接管——即 ``qoder`` 模式，模型由 Qoder 云侧决定。
    """
    if target is None:
        return None

    def resolve_model(_context: Any) -> ModelPolicyResult:
        return {
            "model": {
                "model": target.model,
                "url": target.base_url,
                "api_key": target.api_key,
                "style": "openai",
            }
        }

    return resolve_model


def _on_auth_expired() -> None:
    """SDK 观察到鉴权失败时的回调。只记日志（不含任何凭据）。"""
    logger.warning("qoder 鉴权失效（令牌过期或被吊销），请更新 QODER_PERSONAL_ACCESS_TOKEN / SA 密钥")


# ── 杂项 ────────────────────────────────────────────────────────────────


def _error_code(text: str) -> str | None:
    """从错误文本里取 qoder 的数字错误码；没有已知码返回 ``None``。

    取**最长匹配**：``10408`` 里含 ``104``/``1040``，先按已知码表过滤再取最长，
    避免「超时」被误判成别的码。
    """
    if not text:
        return None
    candidates = [token for token in _ERROR_CODE_RE.findall(text) if token in ERROR_CODES]
    if not candidates:
        return None
    return str(max(candidates, key=len))


def _model_from_result(result_msg: Any) -> str:
    """``ResultMessage.model_usage`` 的键（没有就空串）。

    只在 assistant 消息没带 model 时兜底：``model_usage`` 是按模型聚合的字典，
    键就是模型名。
    """
    usage = getattr(result_msg, "model_usage", None) or {}
    if isinstance(usage, dict) and usage:
        return str(next(iter(usage)))
    return ""


def _stringify(value: Any) -> str:
    """工具结果 → 文本（字符串原样，其余 JSON 序列化）。"""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _result_message(msg: Any) -> Any | None:
    """``ResultMessage`` 判定（延迟 import，避免模块级依赖 SDK）。"""
    try:
        from qoder_agent_sdk import ResultMessage
    except ImportError:  # pragma: no cover - SDK 缺失时不会跑到这里
        return None
    return msg if isinstance(msg, ResultMessage) else None


__all__ = [
    "ACCESS_TOKEN_ENV",
    "APPROVAL_ENV",
    "APPROVAL_REJECTED_MESSAGE",
    "BLOCKED_TOOL_NAMES",
    "CLI_PATH_ENV",
    "CONFIG_DIR_PREFIX",
    "DEFAULT_INSTRUCTIONS",
    "ERROR_CODES",
    "KIND",
    "LOGIN_HINT",
    "LOGIN_PROBE_ENV",
    "MAX_KEPT_RESULTS",
    "MODEL_SOURCE_ENV",
    "MODEL_SOURCE_GATEWAY",
    "MODEL_SOURCE_QODER",
    "PROXY_ENV",
    "QoderBackend",
    "QoderRunResult",
    "SA_KEY_ENV",
    "TOOL_TIER_ENV",
    "approval_enabled",
    "backend_capabilities",
    "build_env",
    "build_mcp_servers",
    "disallowed_tools",
    "ensure_logged_in",
    "has_explicit_auth",
    "is_available",
    "login_missing_reason",
    "make_config_dir",
    "model_source",
    "qoder_auth",
    "remove_config_dir",
    "resolve_cli_binary",
    "resolve_cli_path",
    "resolve_proxy",
    "short_tool_name",
    "tool_tier",
    "work_dir",
]
