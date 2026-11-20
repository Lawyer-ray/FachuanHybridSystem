"""`ContractDecision` —— 一次裁决的留痕（append-only）。

## 为什么模型放在 services 下

与 B1 的 `ContractWritePatch` 同口径：这张表的读写只发生在
`services/alignment/decision.py`，放在同目录让"谁能碰它"一眼可见。
`models/__init__.py` 只用一行 import 把它挂进 Django 模型注册表（不挂不建表）。

## 为什么 `chosen_patch_id` / `decided_by` 不建外键

这是**审计台账**：patch 草案区可以被清理、用户账号可以被删除，但"某年某月某日
某律师采纳了哪份改写、依据是什么"必须活下来。外键的 `CASCADE` 会连带删掉
留痕，`SET_NULL` 又会把"谁裁的"抹成空；所以只存 id 快照，不建约束。

`dissent` 保留但**不展示**：它记录被否掉的少数意见，将来做模型评估时比分数
更有价值（能回答"这家在哪些条款上总是与最终稿不同"）。展示层不得渲染它。
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


def new_decision_id() -> str:
    """新的 decision id（uuid4 hex；仓库无 ulid 依赖，语义同 B1 的 patch_id）。"""

    return uuid.uuid4().hex


class DecisionOwnerKind(models.TextChoices):
    """绑定文件夹的归属类型（与 `/direct-edit/*` 的 kind 同口径）。"""

    CONTRACT = "contract", "合同"
    CASE = "case", "案件"


class ContractDecision(models.Model):
    """一次裁决的留痕。字段与冻结契约 `write_contracts.Decision` 一一对应。"""

    decision_id = models.CharField(
        max_length=32,
        primary_key=True,
        default=new_decision_id,
        editable=False,
        verbose_name="裁决 ID",
    )
    session_id = models.CharField(max_length=64, blank=True, default="", verbose_name="会话标识")
    owner_kind = models.CharField(
        max_length=16,
        choices=DecisionOwnerKind.choices,
        default=DecisionOwnerKind.CONTRACT,
        verbose_name="归属类型",
    )
    owner_id = models.BigIntegerField(verbose_name="归属 id", help_text="合同 ID 或案件 ID")
    subpath = models.CharField(
        max_length=512,
        verbose_name="相对路径",
        help_text="绑定根下的 posix 相对路径（与 rewrite_folder_file 的 subpath 同口径）",
    )
    clause_key = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        default=None,
        verbose_name="条款坐标",
        help_text="行级降级/跨条款原文一律为空；不得把行号伪装成条款坐标",
    )
    chosen_patch_id = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        default=None,
        verbose_name="采纳的 patch id",
        help_text="律师自己改写时为空，改看 manual_text",
    )
    manual_text = models.TextField(null=True, blank=True, default=None, verbose_name="律师改写")
    basis = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="裁决依据",
        help_text='{"citations": [...], "rubric_ids": [...]}；必须可回溯到材料与判定项',
    )
    decided_by = models.BigIntegerField(
        null=True,
        blank=True,
        default=None,
        verbose_name="裁决人",
        help_text="user_id 快照；不建外键，用户删除后留痕仍在",
    )
    reason = models.TextField(blank=True, default="", verbose_name="理由")
    dissent = models.JSONField(
        blank=True,
        default=list,
        verbose_name="少数意见",
        help_text="保留不展示：用于后续模型评估，展示层不得渲染",
    )
    decided_at = models.DateTimeField(default=timezone.now, verbose_name="裁决时间")

    class Meta:
        verbose_name = "裁决留痕"
        verbose_name_plural = "裁决留痕"
        # 完全键：同一秒落库的两条也不能有"看运气"的顺序
        ordering = ["-decided_at", "decision_id"]
        indexes = [
            models.Index(fields=["owner_kind", "owner_id", "subpath"], name="cw_decision_owner_path_idx"),
            models.Index(fields=["session_id", "owner_kind", "owner_id"], name="cw_decision_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.decision_id}@{self.subpath}"
