"""UI 动作台账的**只读**查询 —— 动作历史列表（M1）与聚合统计（LANE R）。

写路径（占位 / 送达 / 回执 / 核实 / 拒绝留痕）全在 :mod:`.audit`；本模块只读，不写一行。
「为什么只按 ``user`` 过滤、不按会话共享」的论证在 :func:`list_recent_for_user` 的 docstring 里。

**依赖方向只有 audit → audit_query**：查询不 import 写路径，否则两个模块成环。

**为什么模块顶层没有 Django 符号**：与 :mod:`.audit` 同一条纪律（完整论证见它的模块
docstring）——``python -m apps.agent.services.ui_action --ts`` 要在没有 Django settings 的
进程里 import 整个包，所以 Django 的模型一律下沉到函数内。

``outcome="unknown"`` 是「未结算」的唯一取值；本模块只把它当调用方传进来的过滤值，不另建
常量（写侧同一个字面量见 :data:`audit.OUTCOME_UNKNOWN`，两侧不得各写一套常量）。
本模块只额外声明**报表形状**用得着的档位表（:data:`OUTCOME_TIERS` /
:data:`DECISION_TIERS`）：它们是「报表必须给键」的清单，不是第二份业务常量——三个页面
回执档的值在 ``schemas/ui_schemas.py`` 的 ``Literal["ok", "error", "aborted"]``，未执行过的
两档与 ``decision`` 三档的值在 ``audit.OUTCOME_*`` / ``audit.DECISION_*``，改值时这几处
必须一起改（本模块不 import 写路径，见上一条依赖方向）。
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: 历史查询的每页硬上限（前端传再大也不给，避免一次拉全表）。
LIST_MAX_LIMIT = 200

#: 统计窗口的默认天数 / 上限天数。端点与查询共用这一份，API 层不再写第二套 clamp。
STATS_WINDOW_DAYS_DEFAULT = 7
STATS_WINDOW_DAYS_MAX = 90

#: 一次统计最多参与的行数。超了就只统计**最近**这么多行并置 ``truncated``：
#: 窗口可以到 90 天，一个活跃会话能把台账推到几万行，而报表是一次点击就要出结果的
#: 读操作——它不该成为一次全表扫。
STATS_MAX_ROWS = 2000

#: 统计里要单独筛的两个 ``outcome`` 值：``ok``（页面报成功）与 ``denied``（人拒绝）。
#: 起名是因为口径要按它们切（「页面报成功但没有核实结论」/「被拒了几次」），值同
#: ``schemas/ui_schemas.py`` 的 ``Literal["ok", "error", "aborted"]`` 与写侧
#: ``audit.OUTCOME_DENIED``。
OUTCOME_OK = "ok"
OUTCOME_DENIED = "denied"

#: 报表里 ``by_outcome`` **必须给出键**的档位（凑不满就报 0）。缺键会让「这段时间没人
#: 被拒」在前端变成 ``undefined`` 而不是 0。``unknown``（未结算）不在固定清单里：它只在
#: 真的出现时才多一个键——报表不替「一行都还没结算」编一个常驻的 0。
OUTCOME_TIERS: tuple[str, ...] = (OUTCOME_OK, "error", OUTCOME_DENIED, "aborted", "expired")

#: 报表里 ``approval`` 的三档（值同 ``audit.DECISION_*``）。``""``（还没人判定）不属于
#: 任何一档，所以三项之和**可以小于** ``total``——那是事实，不是漏算。
DECISION_TIERS: tuple[str, ...] = ("approved", "denied", "expired")


def clamp_window_days(days: Any) -> int:
    """把天数 clamp 到 1~:data:`STATS_WINDOW_DAYS_MAX`（不是报错，也不是返回空）。

    ``days=0`` / ``days=999`` 这类输入只有一个合理归宿：**夹到边界上继续算**。报 500 会
    让「前端传了个 0」变成一次白屏，而「按 0 天算」又会得到一份恒空的报表——两者都比
    「夹到 1 天 / 90 天」差。非数字（HTTP 层已经先拦一道）退回默认值。
    """
    try:
        value = int(days)
    except (TypeError, ValueError):
        return STATS_WINDOW_DAYS_DEFAULT
    return max(1, min(value, STATS_WINDOW_DAYS_MAX))


def empty_stats(days: int = STATS_WINDOW_DAYS_DEFAULT) -> dict[str, Any]:
    """全零报表：未登录 / 窗口内没有行 / 库报错三种情形共用同一个形状。

    共用形状不是图省事：前端拿到的键必须恒定（``by_outcome.denied`` 之类直接取值），
    而「未登录」和「这周真的什么都没做」在结构上只差一个 ``error`` 字段。
    """
    window_days = clamp_window_days(days)
    return {
        "window_days": window_days,
        "total": 0,
        "by_outcome": dict.fromkeys(OUTCOME_TIERS, 0),
        "by_action": [],
        "verified": {"true": 0, "false": 0, "unknown": 0, "not_checked": 0},
        "approval": dict.fromkeys(DECISION_TIERS, 0),
        # 名字就是口径：审批决定 → 台账落行（下发）这一段，**不是**执行耗时。
        # 没有样本时 p50/p95 是 None 而不是 0（0 会被读成「批准后立刻就下发了」）。
        "approval_to_dispatch_ms": {"p50": None, "p95": None, "samples": 0},
        "truncated": False,
    }


def _percentile(sorted_values: list[int], fraction: float) -> int:
    """最近秩法（nearest-rank）：第 ⌈p·n⌉ 小的那个值；``n = 0`` 由调用方挡住。

    选它而不是插值法：审计报表要的是「说出来能对上一条真实台账」的数字，插值会算出
    一条不存在的记录（如 820.5ms）。口径写在这里，免得读的人以为是别的方法。
    """
    index = max(0, math.ceil(fraction * len(sorted_values)) - 1)
    return sorted_values[index]


async def stats_for_user(
    user: Any,
    *,
    days: int = STATS_WINDOW_DAYS_DEFAULT,
    action: str = "",
) -> dict[str, Any]:
    """当前用户在最近 ``days`` 天里的动作汇总 —— 「AI 这段时间帮我做了多少事」。

    逐条列表回答不了这个问题（翻 50 行也数不出「成了几个、我拒过几个」），所以这里
    只出汇总。**口径逐条写在下面，含糊等于错**：

    - **只统计当前用户自己的行**（``filter(user=user)``），与 :func:`list_recent_for_user`
      同一口径：动作历史不是会话共享资产，换成同事看就成了另一件事。
    - **窗口**：``created_at >= now - days``（传 0 / 超上限按
      :func:`clamp_window_days` 夹住）。按 ``created_at`` 而不是 ``decided_at``：一行台账
      的出生时刻就是「系统发出（或拦下）这个动作」的时刻，后者的行根本没有。
    - ``total`` = 窗口内的**真实**行数。``truncated=true`` 时明细只覆盖最近
      :data:`STATS_MAX_ROWS` 行，因此 ``by_outcome`` 各项之和可能**小于** ``total``——
      这时 ``total`` 仍然是真话，明细只是样本。
    - ``by_outcome``：``ok`` / ``error`` / ``denied`` / ``aborted`` / ``expired`` 五个键
      恒定存在（没有就是 0）；另有 ``unknown``（已下发、没回执）等出现时才多一个键，
      所以**各项之和恒等于参与统计的行数**——丢一类不报，看的人会以为总数对不上是 bug。
    - ``by_action[].verified_rate`` = ``verified=True 的行数 / verified 非空的行数``
      （只算**服务端真的下过结论**的行）。分母为 0 时返回 ``None`` 而**不是 0**：
      0 会被读成「这个动作全都核实失败」，而那时的真相是「这次没有一行值得核实」。
    - ``verified`` 四桶构成一份**划分**（四项之和 = 参与统计的行数）：

      * ``true`` / ``false``：服务端核实的两种结论；
      * ``not_checked``：``outcome=ok`` 且 ``verified is null`` —— 页面报成功，但台账上
        没有核实结论（动作没声明 ``verify``，或声明了却核不了，后者 ``verify_note`` 非空）；
      * ``unknown``：``verified is null`` 且 ``outcome != ok`` —— 没成功过的行（未结算 /
        error / aborted / 被拒 / 过期），本来就没有可核实的对象。

      ``not_checked`` 与 ``false`` **必须分得开**：前者是「我们没看」，后者是「我们看了，
      库里没变」。合成一个数就等于把「没核实」报成「核实失败」。
    - ``approval``：按 ``decision`` 数「批准 / 拒绝 / 超时」三档。还没人判定的行
      （``decision=""``）不属于任何一档，三项之和可以小于 ``total``。
    - ``approval_to_dispatch_ms``：**审批到下发**这一段（``created_at - decided_at``），
      只统计两个时间都在的行，``samples`` 就是参与的行数。**它不是端到端时延，也不是
      执行耗时**：台账里没有「执行完成时刻」这一列，所以「页面到底花了多久」这一轮
      算不出来——**要端到端时延必须加 ``updated_at``（或 finished_at）列，本轮不加
      （那要迁移）**。宁可少一个字段，也不给一个会被当成执行耗时的数字。负数（时钟回拨 /
      先落行后补决定）一律按 0 计，并在 ``samples`` 里算作一行。
    - 聚合**在数据库里做**（``values().annotate(Count)`` / ``aggregate``），行数在库侧就
      收敛成几行结果。唯一的例外是 ``approval_to_dispatch_ms`` 的两个百分位：Django 没有
      百分位聚合，而 ``percentile_cont`` 只有 PostgreSQL 有（``DB_ENGINE`` 还支持
      sqlite / mysql），所以那一段取回**两列时间戳**、行数受 :data:`STATS_MAX_ROWS`
      封顶，python 只做排序取秩。

    Args:
        days: 回看天数，clamp 到 1~:data:`STATS_WINDOW_DAYS_MAX`。
        action: 动作名精确匹配；空串 = 不过滤（与列表端点的 ``action`` 同一口径）。

    Returns:
        形状见 :func:`empty_stats`；库报错时 warn 之后返回同一份全零结构（宁可缺数据，
        也不把一次读失败变成 500——报表不是写路径）。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError
    from django.db.models import Count, Q
    from django.utils import timezone

    from ...models import AgentUiAction

    report = empty_stats(days)
    window_days = int(report["window_days"])
    total = 0
    try:
        base = AgentUiAction.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(days=window_days),
        )
        if action:
            base = base.filter(action=action)
        total = await base.acount()
        if total == 0:
            return report
        if total > STATS_MAX_ROWS:
            # 截断口径：保留**最近** STATS_MAX_ROWS 行（报表问的是「最近在干什么」）。
            # 先取 id 再按 id 过滤，而不是 ``pk__in=Subquery(...)``：后者在 MySQL 上会撞
            # 「IN 子查询里不许带 LIMIT」，而这里最多回 2000 个整数，代价可以忽略。
            newest_ids = [pk async for pk in base.order_by("-created_at").values_list("pk", flat=True)[:STATS_MAX_ROWS]]
            base = AgentUiAction.objects.filter(pk__in=newest_ids)
            report["truncated"] = True

        # ── by_outcome：库侧 group by，补全固定五档 ──
        by_outcome = dict.fromkeys(OUTCOME_TIERS, 0)
        # ``.order_by()`` 不能省：Meta.ordering 是 ``-created_at``，不清掉的话 Django 会把
        # created_at 塞进 GROUP BY，于是每行自带一组——聚合出来的就不再是「按结局分组」。
        async for row in base.values("outcome").annotate(rows=Count("pk")).order_by():
            by_outcome[row["outcome"]] = by_outcome.get(row["outcome"], 0) + int(row["rows"])

        # ── by_action：一次 group by 拿齐 4 个计数 ──
        by_action: list[dict[str, Any]] = []
        async for row in (
            base.values("action")
            .annotate(
                rows=Count("pk"),
                ok_rows=Count("pk", filter=Q(outcome=OUTCOME_OK)),
                denied_rows=Count("pk", filter=Q(outcome=OUTCOME_DENIED)),
                verified_rows=Count("pk", filter=Q(verified__isnull=False)),
                verified_true_rows=Count("pk", filter=Q(verified=True)),
            )
            .order_by()
        ):
            verified_rows = int(row["verified_rows"])
            by_action.append(
                {
                    "action": row["action"],
                    "total": int(row["rows"]),
                    "ok": int(row["ok_rows"]),
                    "denied": int(row["denied_rows"]),
                    # 分母为 0 → None（0 会被读成「全都核实失败」），见 docstring。
                    "verified_rate": round(int(row["verified_true_rows"]) / verified_rows, 4)
                    if verified_rows
                    else None,
                }
            )
        # 谁最忙谁在前；同名并列按动作名排（顺序稳定，报表不会两次刷新换序）。
        by_action.sort(key=lambda item: (-item["total"], item["action"]))

        # ── verified 四桶（一份划分：四项之和 = 参与统计的行数）──
        verified_agg = await base.aaggregate(
            true_rows=Count("pk", filter=Q(verified=True)),
            false_rows=Count("pk", filter=Q(verified=False)),
            unset_rows=Count("pk", filter=Q(verified__isnull=True)),
            not_checked_rows=Count("pk", filter=Q(verified__isnull=True, outcome=OUTCOME_OK)),
        )
        not_checked = int(verified_agg["not_checked_rows"] or 0)
        verified = {
            "true": int(verified_agg["true_rows"] or 0),
            "false": int(verified_agg["false_rows"] or 0),
            # 「没有核实结论」里除去「页面报成功但没人核」的那些，剩下的全是没成功过的行。
            "unknown": int(verified_agg["unset_rows"] or 0) - not_checked,
            "not_checked": not_checked,
        }

        # ── approval：按 decision group by（"" 不进任何一档）──
        approval = dict.fromkeys(DECISION_TIERS, 0)
        async for row in base.values("decision").annotate(rows=Count("pk")).order_by():
            if row["decision"] in approval:
                approval[row["decision"]] = int(row["rows"])

        # ── approval_to_dispatch_ms：唯一一段 python 侧排序取秩，理由见 docstring ──
        samples = sorted(
            [
                # ``decided_at`` 已被 filter 排除 null；``or created_at`` 只是让 mypy 满意
                max(0, int((created_at - (decided_at or created_at)).total_seconds() * 1000))
                async for decided_at, created_at in base.filter(decided_at__isnull=False)
                .values_list("decided_at", "created_at")
                .order_by()
            ]
        )
        approval_to_dispatch_ms = {
            "p50": _percentile(samples, 0.5) if samples else None,
            "p95": _percentile(samples, 0.95) if samples else None,
            "samples": len(samples),
        }
    except (DatabaseError, ValueError):
        logger.warning("统计 UI 动作台账失败 user=%s", getattr(user, "pk", None), exc_info=True)
        return empty_stats(window_days)

    report.update(
        {
            "total": total,
            "by_outcome": by_outcome,
            "by_action": by_action,
            "verified": verified,
            "approval": approval,
            "approval_to_dispatch_ms": approval_to_dispatch_ms,
        }
    )
    return report


async def list_recent_for_user(
    user: Any,
    *,
    limit: int = 50,
    action: str = "",
    outcome: str = "",
    risk: str = "",
    decision: str = "",
    since_days: int = 0,
) -> list[dict[str, Any]]:
    """当前用户自己的动作历史（新 → 旧）。

    **只按 ``user`` 过滤，不按会话共享**：同一会话被转交给同事后，新负责人也不该看见
    前任按过哪些高危按钮——动作历史是「谁让 AI 干了什么」，换成别人看就成了另一件事。

    Args:
        limit: 条数，clamp 到 1~:data:`LIST_MAX_LIMIT`（传 0 或负数按 1 处理）。
        action / outcome / risk / decision: 精确匹配的过滤条件，**空串 = 不过滤**。都做成
            「空串即全部」而不是 ``None``：查询参数在 HTTP 层天然是字符串，让 None 与
            "" 表示同一件事只会在两端各写一个分支。``decision`` 的三档是 ``approved`` /
            ``denied`` / ``expired``（「他到底同不同意」），与 ``outcome`` 是两个主体的问题
            ——后者记的是页面做成了没有。
        since_days: 只看最近这么多天（``created_at`` 起算），**0 = 不过滤**（保默认行为），
            正的按 :func:`clamp_window_days` 夹到 1~:data:`STATS_WINDOW_DAYS_MAX`。
            0 是「不过滤」而不是「夹到 1」：这个参数是后加的，不传等于老行为。

    Returns:
        每项 ``{session_id, action, risk, outcome, decision, decided_at, verified,
        verify_note, batch_id, approved_by_name, created_at, observed_location}``。
        时间字段是 ISO 8601 字符串（前端直接 ``new Date()``），为空时给空串；
        没有审批关联时 ``approved_by_name`` 为空串，``verified`` 保持 ``None``
        （「无法核实」与「没核实过」在列表里同形，细节看 ``verify_note``）。
    """
    # 延迟 import：理由见模块 docstring。
    from django.db import DatabaseError
    from django.utils import timezone

    from ...models import AgentUiAction

    bounded = max(1, min(int(limit), LIST_MAX_LIMIT))
    filters: dict[str, Any] = {}
    if action:
        filters["action"] = action
    if outcome:
        filters["outcome"] = outcome
    if risk:
        filters["risk"] = risk
    if decision:
        filters["decision"] = decision
    if since_days:
        filters["created_at__gte"] = timezone.now() - timedelta(days=clamp_window_days(since_days))
    try:
        rows = [
            row
            async for row in AgentUiAction.objects.filter(user=user, **filters)
            .select_related("session", "approved_by")
            .order_by("-created_at")[:bounded]
        ]
    except (DatabaseError, ValueError):
        logger.warning("查询 UI 动作历史失败 user=%s", getattr(user, "pk", None), exc_info=True)
        return []
    return [
        {
            "session_id": str(row.session.session_id) if row.session is not None else "",
            "action": row.action,
            "risk": row.risk,
            "outcome": row.outcome,
            "decision": row.decision,
            "decided_at": row.decided_at.isoformat() if row.decided_at is not None else "",
            "verified": row.verified,
            "verify_note": row.verify_note,
            "batch_id": row.batch_id,
            # ``Lawyer.__str__`` = real_name or username，台账里要人能认出的名字。
            "approved_by_name": str(row.approved_by) if row.approved_by is not None else "",
            "created_at": row.created_at.isoformat(),
            "observed_location": row.observed_location,
        }
        for row in rows
    ]
