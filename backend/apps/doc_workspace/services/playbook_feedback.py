"""驳回理由回流：把律师的「不要提这个」变成下一轮的标准。

## 这条机制是从哪来的

市面产品的共同点（一手证据见 `docs/analysis/onlyoffice-ai-2026-11-26/market-refresh.md`）：

- Harvey 首页把 **Memory**（"AI that remembers your preferences"）当一等能力；
- Spellbook / LegalOn 都把 **Playbooks**（"Encode your legal standards"）放在主导航；
- Definely 的说法最直白：**"Every finding sourced, every change approved by you"**。

我们已经有 `reject_reason_code`（商业让步 / 法域不适 / 已被覆盖 / 误报 / 客户拒绝），
但在此之前**没有任何消费方**——理由码只躺在库里。这里补上闭环。

## 判据：什么才算「不要提」

| 理由码 | 会不会降权 | 为什么 |
|---|:-:|---|
| 商业让步 `commercial` | ✅ | 律师知道这条谈不下来，再提只是噪音 |
| 客户明确拒绝 `client_refused` | ✅ | 客户已经拍板，再提等于让律师去挨第二次骂 |
| 已被覆盖 `already_covered` | ✅ | 是**报错了位置**，不是条款有问题 |
| 法域不适 `jurisdiction` | ✅ | 这套标准不该套在这份合同上 |
| 误报 `false_positive` | ❌ | 误报是**模型错了**，该进的是评测指标，不是「别再提」 |
| 其他 `other` | ❌ | 含义不明，不能据此改标准 |

**阈值**：同一条 `rule_key` 在同一 `(kind, owner_id)` 下累计 ≥2 次「可降权」驳回，
才降权一次。只驳回一次就永久闭嘴太激进——同一客户的不同合同未必是同一个立场。

## 降权不等于删除

降权后的效果是**严重度降一档**，而不是把这条从清单里抹掉。为什么：一份合同真的
缺了违约金上限，就算本所过去三次都「商业让步」了，律师偶尔也想知道它还在。
把结论删掉等于让 AI 替他决定「这次也不用看」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db.models import Count

from ..models import Finding, FindingStatus, RejectReason, Severity

#: 触发降权的理由码（误报与「其他」刻意排除，见模块注释）
SUPPRESSING_REASONS: frozenset[str] = frozenset(
    {
        RejectReason.COMMERCIAL,
        RejectReason.CLIENT_REFUSED,
        RejectReason.ALREADY_COVERED,
        RejectReason.JURISDICTION,
    }
)

#: 同一规则被降权驳回多少次之后开始生效
SUPPRESS_THRESHOLD = 2

_SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH]


@dataclass
class Feedback:
    """一份文件上的历史驳回统计。"""

    rules: dict[str, int] = field(default_factory=dict)
    """rule_key → 可降权驳回次数"""

    suppressed: set[str] = field(default_factory=set)
    """已达阈值、本轮要降权的 rule_key"""

    def describe(self) -> str:
        """给提示词用的一句话（没有可降权项时返回空串）。"""
        if not self.suppressed:
            return ""
        items = "、".join(f"{key}（{self.rules.get(key, 0)} 次）" for key in sorted(self.suppressed))
        return (
            "## 本所已多次驳回的条款\n"
            f"以下检查项在本客户过往审查中被律师以「商业让步/客户拒绝/已被覆盖/法域不适」驳回：{items}。\n"
            "对这些条款：**除非后果显著（会造成明确经济损失或诉讼风险）否则不要提**；"
            "确实要提时，`severity` 降一档，并在 `reason` 里写清为什么这次不一样。\n"
        )


def collect(*, kind: str, owner_id: int) -> Feedback:
    """统计该客户（kind+owner_id）历史上被驳回的规则。

    作用域刻意收在「同一客户」而不是全所：同一套标准套在不同客户身上，接受度
    可能完全相反（一个客户能接受无上限违约金，另一个死活不接受）。
    """
    rows = (
        Finding.objects.filter(
            run__owner_kind=kind,
            run__owner_id=owner_id,
            status=FindingStatus.REJECTED,
            reject_reason_code__in=SUPPRESSING_REASONS,
        )
        .values("rule_key", "reject_reason_code")
        .annotate(n=Count("id"))
    )
    rules: dict[str, int] = {}
    for row in rows:
        key = str(row["rule_key"] or "")
        if not key:
            continue
        rules[key] = rules.get(key, 0) + int(row["n"])
    return Feedback(rules=rules, suppressed={k for k, v in rules.items() if v >= SUPPRESS_THRESHOLD})


def downgrade(severity: str) -> str:
    try:
        index = _SEVERITY_ORDER.index(severity)  # type: ignore[arg-type]
    except ValueError:
        return severity
    return _SEVERITY_ORDER[max(0, index - 1)]


def apply_to_items(items: list[dict[str, Any]], feedback: Feedback) -> list[dict[str, Any]]:
    """对已达阈值的规则降一档严重度（**不删条目**）。"""
    if not feedback.suppressed:
        return items
    for item in items:
        if item.get("rule_key") in feedback.suppressed:
            item["severity"] = downgrade(str(item.get("severity") or Severity.MEDIUM))
            item["suppressed"] = True
    return items


__all__ = [
    "Feedback",
    "SUPPRESSING_REASONS",
    "SUPPRESS_THRESHOLD",
    "apply_to_items",
    "collect",
    "downgrade",
]
