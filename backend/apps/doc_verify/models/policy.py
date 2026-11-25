"""案件级核对策略：哪些文书回传后要自动核对内容。

## 为什么策略要落库，而不是只写在代码里

代码里的 `services/verify/policy.py` 只回答「**默认**该不该核」——那四类回签文书
默认要核。但律师会按案子调：批量小额案件全部关掉省时间，某个疑难案子把证据清单
也打开。策略不落库，前端那个勾选框就只是画着好看。

## 为什么键是「文书名主干」而不是 doc_type 精确值

卷宗里的写法不统一（`民事起诉状（一审）`、`起诉状_定稿_20261106`）。策略行存主干
（`起诉状`），命中判定用子串（见 `services/policy_store.is_required`）——与
`services/verify/policy.py` 的默认口径同一套规则，不给第二套说法。
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class VerificationPolicy(models.Model):
    """一条案件级策略：该案某类文书回传后是否自动核对。"""

    id: int
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="verification_policies",
        verbose_name="案件",
    )
    doc_type = models.CharField(max_length=64, verbose_name="文书名主干（如「起诉状」）")
    enabled = models.BooleanField(default=True, verbose_name="是否自动核对")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "回传件核对策略"
        verbose_name_plural = "回传件核对策略"
        ordering: ClassVar[list[str]] = ["case_id", "doc_type"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["case", "doc_type"], name="uniq_case_doc_type_policy"),
        ]

    def __str__(self) -> str:
        return f"case={self.case_id} {self.doc_type}={'on' if self.enabled else 'off'}"
