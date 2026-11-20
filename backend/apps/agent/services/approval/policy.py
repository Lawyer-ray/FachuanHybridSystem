"""用户审批策略（P2-5）—— 精确匹配优先于前缀匹配。"""

from __future__ import annotations

import logging

from ...models import AgentApprovalPolicy
from .risk import short_tool_name

logger = logging.getLogger(__name__)


def lookup_approval_policy(*, user_id: int | None, tool_name: str) -> str | None:
    """查用户对某工具的审批策略（P2-5）。

    Returns:
        "allow" / "deny" / None（无策略或 ask——走系统默认分级）。

    查询优先级：精确匹配 > 前缀匹配；同步函数（request_approval 内
    经 sync_to_async 调用）。
    """
    if user_id is None:
        return None

    # 精确匹配：全名（mcp__fachuan__delete_case）或短名（delete_case）都行
    short_name = short_tool_name(tool_name)
    exact = (
        AgentApprovalPolicy.objects.filter(user_id=user_id, is_prefix=False, tool_pattern__in=[tool_name, short_name])
        .values_list("action", flat=True)
        .first()
    )
    if exact is not None:
        return exact
    # 前缀匹配：策略表里 is_prefix=True 的行，tool_pattern 是前缀
    prefix_rows = AgentApprovalPolicy.objects.filter(user_id=user_id, is_prefix=True).values_list(
        "tool_pattern", "action"
    )
    for pattern, action in prefix_rows:
        if tool_name.startswith(pattern) or short_name.startswith(pattern):
            return action
    return None


# ───────────────────── 多栏并答：写类工具一律拒写 ─────────────────────
#
# 多栏（同一个提问 >1 栏在跑）时，任何一栏直接改文件都会踩掉另一栏——第一栏
# 落盘后，其余栏手里的 `original` 已经失效，落笔要么失败要么改错位置。
# 工具面那一层已经把它们摘掉了（pi 的 `--exclude-tools`，见
# `services/chat/multi.multi_lane_tool_exclude`），但那是**只对 pi 生效**的
# 优化：dsh / openai-agents 的工具面走另一条路。所以真正的保证在这里——
# 审批层看到「多栏 + 写类工具」直接拒绝，**不弹审批卡**（弹卡等于让人批准
# 一件结构性错误的事），并回一句可执行的话让模型改走 patch 草案。

#: 多栏并答时禁止直接调用的写类工具（短名）。新增写文件的工具必须同时加进
#: 这里：漏加等于"多栏又能互相覆盖"，而这条路径没有别的地方会拦。
MULTI_LANE_WRITE_TOOLS: frozenset[str] = frozenset({"rewrite_folder_file", "apply_file_write_patches"})

#: 多栏会话登记键前缀。用**计数**而不是布尔：同一会话并发两轮时，先收尾的
#: 那一轮不能把仍在跑的多栏轮误判成单栏（宁可多拒一次，不可少拒一次）。
MULTI_LANE_KEY_PREFIX = "agent:multi_lane:"
#: 登记 TTL（秒）。收尾会显式递减；TTL 只兜「进程被杀/断连没走到 finally」的泄漏。
MULTI_LANE_TTL = 3600

#: 拒绝文案（模型据此换路径，因此要写清"该用什么"而不是只说"不行"）。
MULTI_LANE_WRITE_REFUSAL = (
    "多栏模式下不要直接改文件：请用 propose_write_patch 产出候选改写，"
    "由律师裁决后再单点应用（三栏同时落盘会互相覆盖）"
)


def _multi_lane_key(session_id: str) -> str:
    return f"{MULTI_LANE_KEY_PREFIX}{session_id}"


def mark_multi_lane_session(session_id: str) -> None:
    """登记「该会话有多栏并答的一轮在跑」（审批层据此拒写类工具）。

    缓存不可用时只记 warning、不阻断本轮：pi 那一路还有 `--exclude-tools` 兜着，
    拒写这层是**第二道**；真把整轮打死会让律师连读都做不了。
    """
    if not session_id:
        return
    from django.core.cache import cache

    key = _multi_lane_key(session_id)
    try:
        cache.add(key, 0, MULTI_LANE_TTL)
        cache.incr(key)
    except Exception:
        logger.warning("登记多栏并答会话失败（审批层将不拒写）session=%s", session_id, exc_info=True)


def clear_multi_lane_session(session_id: str) -> None:
    """撤销一次登记（收尾路径调用；计数归零即删键）。"""
    if not session_id:
        return
    from django.core.cache import cache

    key = _multi_lane_key(session_id)
    try:
        remaining = cache.decr(key)
    except ValueError:
        return  # 键已过期/不存在：本轮登记已被 TTL 清掉，无需再动
    except Exception:
        logger.warning("撤销多栏并答登记失败 session=%s", session_id, exc_info=True)
        return
    if remaining <= 0:
        from contextlib import suppress

        with suppress(Exception):
            cache.delete(key)


def is_multi_lane_session(session_id: str | None) -> bool:
    """该会话当前是否有多栏并答的一轮在跑（查不到/查失败 → 按单栏）。"""
    if not session_id:
        return False
    from django.core.cache import cache

    try:
        value = cache.get(_multi_lane_key(session_id))
    except Exception:
        logger.warning("读取多栏并答登记失败（按单栏处理）session=%s", session_id, exc_info=True)
        return False
    return bool(value)


def multi_lane_write_refusal(*, session_id: str | None, tool_name: str) -> str | None:
    """多栏在跑时，写类工具的直接调用 → 拒绝文案（``None`` = 放行）。

    放在**分级与用户策略之前**：`allow` 策略也不能给「三栏同时改同一份文件」
    开绿灯——那是结构性冲突，不是偏好问题。
    """
    if short_tool_name(tool_name) not in MULTI_LANE_WRITE_TOOLS:
        return None
    if not is_multi_lane_session(session_id):
        return None
    return MULTI_LANE_WRITE_REFUSAL
