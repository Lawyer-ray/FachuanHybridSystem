"""Module for material."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import ClassVar

from django.db import models

from .case import Case, SupervisingAuthority
from .log import CaseLogAttachment
from .party import CaseParty


class CaseMaterialCategory(models.TextChoices):
    PARTY = "party", "当事人材料"
    NON_PARTY = "non_party", "非当事人材料"


class CaseMaterialSide(models.TextChoices):
    OUR = "our", "我方当事人材料"
    OPPONENT = "opponent", "对方当事人材料"


class CaseMaterialType(models.Model):
    id: int
    category = models.CharField(max_length=32, choices=CaseMaterialCategory.choices, verbose_name="材料大类")
    name = models.CharField(max_length=64, verbose_name="类型名称")
    law_firm = models.ForeignKey(
        # SET_NULL：删除律所后材料类型退化为全局可用，不级联删除类型定义
        "organization.LawFirm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="case_material_types",
        verbose_name="律所",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "案件材料类型"
        verbose_name_plural = "案件材料类型"
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["law_firm", "category", "name"], name="uniq_case_material_type_scope"),
        ]
        indexes: ClassVar = [
            # (law_firm, category) 前缀已由唯一约束覆盖
            models.Index(fields=["category", "name"]),
        ]

    def __str__(self) -> str:
        # 用 law_firm_id 拼接，避免 admin/日志列表逐行触发 FK 查询（N+1）
        scope = f"律所#{self.law_firm_id}" if self.law_firm_id else "全局"
        category_display = self.get_category_display()
        return f"{scope}-{category_display}-{self.name}"


class CaseMaterial(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="materials", verbose_name="案件")
    category = models.CharField(max_length=32, choices=CaseMaterialCategory.choices, verbose_name="材料大类")
    type = models.ForeignKey(
        CaseMaterialType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="materials",
        verbose_name="材料类型",
    )
    type_name = models.CharField(max_length=64, verbose_name="类型名称")
    source_attachment = models.OneToOneField(
        CaseLogAttachment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bound_material",
        verbose_name="来源日志附件",
    )
    side = models.CharField(
        max_length=32,
        choices=CaseMaterialSide.choices,
        blank=True,
        default="",
        verbose_name="当事人方向",
    )
    parties = models.ManyToManyField(CaseParty, blank=True, related_name="materials", verbose_name="关联当事人")
    supervising_authority = models.ForeignKey(
        SupervisingAuthority,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="materials",
        verbose_name="主管机关",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "案件材料"
        verbose_name_plural = "案件材料"
        indexes: ClassVar = [
            models.Index(fields=["case", "category", "created_at"]),
            models.Index(fields=["case", "category", "side"]),
            models.Index(fields=["case", "category", "supervising_authority"]),
            models.Index(fields=["type_name"]),
        ]

    def __str__(self) -> str:
        category_display = self.get_category_display()
        return f"{self.case_id}-{category_display}-{self.type_name}"


class CaseMaterialGroupOrder(models.Model):
    id: int
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="material_group_orders", verbose_name="案件")
    category = models.CharField(max_length=32, choices=CaseMaterialCategory.choices, verbose_name="材料大类")
    side = models.CharField(
        max_length=32,
        choices=CaseMaterialSide.choices,
        blank=True,
        default="",
        verbose_name="当事人方向",
    )
    supervising_authority = models.ForeignKey(
        SupervisingAuthority,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="material_group_orders",
        verbose_name="主管机关",
    )
    type = models.ForeignKey(
        CaseMaterialType, on_delete=models.CASCADE, related_name="group_orders", verbose_name="材料类型"
    )
    sort_index = models.PositiveIntegerField(default=0, verbose_name="排序")

    class Meta:
        verbose_name = "案件材料分组顺序"
        verbose_name_plural = "案件材料分组顺序"
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["case", "category", "side", "supervising_authority", "type"],
                name="uniq_case_material_group_order",
            ),
        ]
        indexes: ClassVar = [
            models.Index(fields=["case", "category", "side", "sort_index"]),
            models.Index(fields=["case", "category", "supervising_authority", "sort_index"]),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}-{self.category}-{self.sort_index}"


class CaseFolderStorageType(models.TextChoices):
    """案件文件夹绑定的存储后端"""

    LOCAL = "local", "本地文件系统"
    WEBDAV = "webdav", "WebDAV"
    ONEDRIVE = "onedrive", "OneDrive"
    S3 = "s3", "S3 兼容存储"
    GOOGLE_DRIVE = "google_drive", "Google Drive"
    DROPBOX = "dropbox", "Dropbox"


class CaseFolderBinding(models.Model):
    """案件文件夹绑定"""

    id: int
    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name="folder_binding", verbose_name="案件")
    folder_path = models.CharField(max_length=1000, verbose_name="文件夹路径", help_text="绑定的本地或网络文件夹路径")
    relative_path = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="相对路径",
        help_text="相对合同文件夹的路径，如 2026.04.22-[民商事]某某案",
    )

    # ── Cloud storage fields ───────────────────────────────────
    storage_type = models.CharField(
        max_length=20,
        choices=CaseFolderStorageType.choices,
        default=CaseFolderStorageType.LOCAL,
        verbose_name="存储类型",
    )
    storage_account = models.ForeignKey(
        "cloud_storage.CloudStorageAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="云存储账号",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="绑定时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "案件文件夹绑定"
        verbose_name_plural = "案件文件夹绑定"
        indexes: ClassVar = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        # 用 case_id 拼接，避免 admin/日志列表逐行触发 FK 查询（N+1）
        return f"案件#{self.case_id} - {self.folder_path}"

    @property
    def folder_path_display(self) -> str:
        """格式化显示路径"""
        path = self.resolved_folder_path
        if not path:
            return ""
        max_length = 50
        if len(path) <= max_length:
            return path
        start_len = max_length // 2 - 2
        end_len = max_length - start_len - 3
        return f"{path[:start_len]}...{path[-end_len:]}"

    @property
    def resolved_folder_path(self) -> str:
        """解析后的绝对路径：优先合同路径+相对路径，降级到 folder_path."""
        if self.relative_path:
            contract_folder_path = self._get_contract_folder_path()
            if contract_folder_path:
                return str(PurePosixPath(contract_folder_path) / self.relative_path)
        return self.folder_path

    def _get_contract_folder_path(self) -> str | None:
        """获取关联合同的文件夹路径."""
        try:
            case = self.case
            if not case.contract_id or not case.contract:
                return None
            contract = case.contract
            if not hasattr(contract, "folder_binding") or not contract.folder_binding:
                return None
            return contract.folder_binding.folder_path
        except (AttributeError, TypeError, ValueError):
            return None
