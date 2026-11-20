"""`ContractWritePatch` —— 一栏提出的一处改写（草案区，**不落盘**）。

## 为什么模型放在 services 下而不是 `models/`

`models/` 放的是"合同审查任务"这一套领域对象（任务、修订、版本链）。这里的表
是**写入安全的暂存区**：它的生命周期只覆盖"三栏并答 → 律师裁决 → 单点应用"，
读写它的只有 `services/patch/`。放在同目录可以让"谁能碰这张表"一眼可见；
`models/__init__.py` 里只有一行 import 把它挂进 Django 的模型注册表（不挂就
不会建表、也不会被 migrations 发现）。

## 字段口径来自冻结契约

字段与 `apps/contract_review/services/write_contracts.py` 的 `WritePatch` 一一
对应（那边是**领域对象**，这边是**存储**）。契约注释里写 `patch_id` 是 ulid：
仓库没有 ulid 依赖，且本 lane 明令禁止新增第三方依赖，所以用 `uuid4().hex`
承载同一语义——全局唯一、不可预测；代价是不保证按时间单调（需要排序时用
`created_at, patch_id` 的完全键，不要用 id 猜先后）。

## 为什么 `original` 用 TextField 且不做任何归一化

定位靠"逐字原文"。一旦入库前把全角/空白归一化，应用时对不上原文，只能报
"找不到"——或者更糟：在别处撞上同一串字，改错位置。存原样是这条链路的底线。
"""

from __future__ import annotations

import uuid

from django.db import models


def new_patch_id() -> str:
    """新的 patch id（uuid4 hex；见模块 docstring 为何不是 ulid）。"""
    return uuid.uuid4().hex


class PatchStatus(models.TextChoices):
    """patch 生命周期（取值与 `write_contracts.PATCH_STATUSES` 逐项一致）。"""

    PROPOSED = "proposed", "草案"
    CONFLICT = "conflict", "有冲突"
    MERGED = "merged", "已合并"
    APPLIED = "applied", "已应用"
    REJECTED = "rejected", "已否决"


class PatchOwnerKind(models.TextChoices):
    """绑定文件夹的归属类型（与 `/direct-edit/*` 的 kind 同口径）。"""

    CONTRACT = "contract", "合同"
    CASE = "case", "案件"


class ContractWritePatch(models.Model):
    """一条候选改写（草案）。应用走 `services/patch/service.apply_patches`。"""

    patch_id = models.CharField(
        max_length=32,
        primary_key=True,
        default=new_patch_id,
        editable=False,
        verbose_name="patch ID",
    )
    session_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="会话标识",
        help_text="产出它的那一轮对话；MCP 侧只能拿到会话标识（拿不到 run_id）",
    )
    turn = models.IntegerField(
        default=0,
        verbose_name="轮次",
        help_text="同一次提问的多栏共用一个 turn；0 = 调用方没给",
    )
    agent_kind = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="产出后端",
        help_text="pi / dsh / openai-agents；B1 阶段 MCP 侧拿不到，留空",
    )
    run_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="运行 id",
        help_text="同一轮里区分栏；B1 阶段 MCP 侧拿不到，留空",
    )
    owner_kind = models.CharField(
        max_length=16,
        choices=PatchOwnerKind.choices,
        default=PatchOwnerKind.CONTRACT,
        verbose_name="归属类型",
    )
    owner_id = models.BigIntegerField(verbose_name="归属 id", help_text="合同 ID 或案件 ID")
    subpath = models.CharField(
        max_length=512,
        verbose_name="相对路径",
        help_text="绑定根下的 posix 相对路径（与 rewrite_folder_file 的 subpath 同口径）",
    )
    original = models.TextField(
        verbose_name="原文",
        help_text="逐字原文，定位用；**不做任何归一化**",
    )
    replacement = models.TextField(verbose_name="改写文本")
    base_mtime = models.FloatField(
        null=True,
        blank=True,
        verbose_name="产出时 mtime",
        help_text="应用前二次校验：律师在这期间动过文件就必须报冲突",
    )
    status = models.CharField(
        max_length=16,
        choices=PatchStatus.choices,
        default=PatchStatus.PROPOSED,
        verbose_name="状态",
    )
    note = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="应用备注",
        help_text="应用时律师给的一句话；B4 的 Decision 落地后这里只作快照",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "候选改写"
        verbose_name_plural = "候选改写"
        # 完全键：同一秒落库的多条也不能有"看运气"的顺序
        ordering = ["-created_at", "patch_id"]
        indexes = [
            models.Index(fields=["session_id", "turn"], name="cw_patch_session_turn_idx"),
            models.Index(fields=["owner_kind", "owner_id", "subpath"], name="cw_patch_owner_path_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.patch_id}@{self.subpath}"
