"""采纳埋点 —— 只记录律师显式动作，不做任何自动采纳。

## 影子开关：``FACHUAN_REVIEW_SHADOW``（默认 ``1`` = 开）

三条规则，缺一条就会把"影子"做成"自动驾驶"：

1. **开着时**（默认）：评审只展示，不触发任何自动动作——不写 patch、不调
   ``apply_patches``、不做 LLM 判定之外的任何写操作。评审端点只落
   ``AgentReview`` 快照。
2. **关着时也不得自动采纳**：采纳只能由律师显式
   ``POST /agent/reviews/{review_id}/adopt`` 触发。开关不是"自动采纳"的开关。
3. 开关只决定「自动路径的前置条件是否满足」：``auto_path_allowed()`` 是唯一
   读法。将来的自动排序/自动应用在动手前必须先问它；B2.5 阶段没有任何自动
   路径调用方，``POST /adopt`` 本身也**故意不读**这个开关——律师显式动作与
   影子无关。

把第 1、2 条记混的后果：以为"关掉影子就会自动应用"，于是放心关掉，评审开始
替律师改文件——这正是 B1 花一整批修掉的静默覆盖问题。
"""

from __future__ import annotations

import os

from ...models import AgentReview, AgentReviewAdoption

#: 影子开关的环境变量名。默认开；只有显式 ``0/false/no/off`` 才算关。
SHADOW_ENV = "FACHUAN_REVIEW_SHADOW"

_DISABLED_VALUES = frozenset({"0", "false", "no", "off"})


def shadow_enabled() -> bool:
    """影子模式是否开启（缺省/空值/其他取值都按开处理——默认必须是开）。"""
    raw = os.environ.get(SHADOW_ENV, "").strip().lower()
    return raw not in _DISABLED_VALUES


def auto_path_allowed() -> bool:
    """自动路径的前置条件：影子关着才满足（当前阶段没有任何调用方）。

    存在的意义是把"开关只当前置条件"落成**唯一读法**，而不是将来在每个调用点
    各写一遍 ``if os.environ...``；B2.5 只做影子展示 + 律师显式采纳。
    """
    return not shadow_enabled()


async def find_owned_review(*, review_id: str, user_id: int | None) -> AgentReview | None:
    """按对外 ``review_id`` 取评审，并做与 review 端点同口径的归属过滤。

    归属锚在会话上（``session__user_id``）而不是 ``AgentReview.user``：会话才是
    权限边界，评审行上的 ``user`` 只是"谁触发了这次判定"。``user_id`` 为空时
    必须一条也匹配不到（同 ``session_service._scoped``），调用方统一按 404 处理。
    """
    if user_id is None:
        return None
    return await AgentReview.objects.filter(review_id=review_id, session__user_id=user_id).afirst()


async def record_adoption(
    *,
    review: AgentReview,
    user_id: int | None,
    lane: str | None,
    merged: bool,
    note: str = "",
) -> AgentReviewAdoption:
    """记录一次显式采纳；同一 review 重复采纳覆盖同一行并返回最新行。"""
    row, _created = await AgentReviewAdoption.objects.aupdate_or_create(
        review=review,
        defaults={
            "user_id": user_id,
            "lane": (lane or "").strip() or None,
            "merged": merged,
            "note": note.strip(),
        },
    )
    return row


async def load_adoption(review: AgentReview) -> AgentReviewAdoption | None:
    """取该评审当前的采纳结果；从未采纳返回 ``None``（前端按"未采纳"渲染）。"""
    return await AgentReviewAdoption.objects.filter(review=review).afirst()
