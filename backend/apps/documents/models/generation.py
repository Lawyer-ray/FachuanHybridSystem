"""
文书生成任务和配置模型

本模块定义文书生成相关的数据模型.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from .folder_template import FolderTemplate

logger = logging.getLogger("apps.documents")


class GenerationMethod(models.TextChoices):
    """生成方式"""

    TEMPLATE = "template", _("模板生成")
    AI = "ai", _("AI生成")


class GenerationStatus(models.TextChoices):
    """生成状态"""

    PENDING = "pending", _("等待中")
    PROCESSING = "processing", _("生成中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")


class GenerationTask(models.Model):
    """
    文书生成任务

    记录每次文书生成的任务信息,包括生成参数、结果等.
    支持模板生成和 AI 生成两种方式.

    Requirements: 6.1.3
    """

    id: int
    case_id: int  # 外键ID字段
    contract_id: int  # 外键ID字段
    litigation_session_id: int  # 外键ID字段
    created_by_id: int  # 外键ID字段
    case: models.ForeignKey[Any] = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="generation_tasks",
        verbose_name=_("关联案件"),
    )
    contract: models.ForeignKey[Any] = models.ForeignKey(
        "contracts.Contract",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="generation_tasks",
        verbose_name=_("关联合同"),
    )
    litigation_session: models.ForeignKey[Any] = models.ForeignKey(
        "litigation_ai.LitigationSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generation_tasks",
        verbose_name=_("AI生成会话"),
        help_text=_("如果是 AI 生成,关联到对应的会话"),
    )
    generation_method: str = models.CharField(
        max_length=20, choices=GenerationMethod.choices, default=GenerationMethod.TEMPLATE, verbose_name=_("生成方式")
    )
    document_type: str = models.CharField(
        max_length=100, verbose_name=_("文书类型"), help_text=_("如:起诉状、答辩状、合同等")
    )
    template_id: int | None = models.IntegerField(
        null=True, blank=True, verbose_name=_("模板ID"), help_text=_("使用的模板ID(模板生成时)")
    )
    status: str = models.CharField(
        max_length=20, choices=GenerationStatus.choices, default=GenerationStatus.PENDING, verbose_name=_("生成状态")
    )
    result_file: models.FileField = models.FileField(
        upload_to="generated_documents/%Y/%m/", null=True, blank=True, verbose_name=_("生成文件")
    )
    error_message: str = models.TextField(blank=True, verbose_name=_("错误信息"))
    metadata: dict[str, Any] = models.JSONField(
        default=dict, verbose_name=_("任务元数据"), help_text=_("存储生成参数、token消耗等信息")
    )
    created_by: models.ForeignKey[Any] = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_generation_tasks",
        verbose_name=_("创建人"),
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    completed_at: models.DateTimeField = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        app_label: str = "documents"
        verbose_name = _("文书生成任务")
        verbose_name_plural = _("文书生成任务")
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [
            models.Index(fields=["case", "-created_at"]),
            models.Index(fields=["contract", "-created_at"]),
            models.Index(fields=["litigation_session"]),
            models.Index(fields=["status"]),
            models.Index(fields=["generation_method"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        resource = self.case or self.contract
        resource_name = resource.name if resource else "未关联"
        return f"{resource_name} - {self.document_type} ({self.get_status_display()})"

    @property
    def is_ai_generated(self) -> bool:
        """是否为 AI 生成"""
        return self.generation_method == GenerationMethod.AI

    @property
    def duration_seconds(self) -> int:
        """生成耗时(秒)"""
        if self.completed_at and self.created_at:
            return int((self.completed_at - self.created_at).total_seconds())
        return 0

    @property
    def folder_template_id(self) -> int | None:
        return (self.metadata or {}).get("folder_template_id")

    @folder_template_id.setter
    def folder_template_id(self, value: int | None) -> None:
        self.metadata = self.metadata or {}
        self.metadata["folder_template_id"] = value

    @property
    def folder_template(self) -> FolderTemplate | None:
        template_id = self.folder_template_id
        if not template_id:
            return None
        from .folder_template import FolderTemplate

        return FolderTemplate.objects.filter(id=template_id).first()

    @property
    def output_path(self) -> str | None:
        return (self.metadata or {}).get("output_path")

    @output_path.setter
    def output_path(self, value: str | None) -> None:
        self.metadata = self.metadata or {}
        self.metadata["output_path"] = value

    @property
    def generated_files(self) -> list[Any]:
        return list((self.metadata or {}).get("generated_files", []))

    @generated_files.setter
    def generated_files(self, value: list[Any] | None) -> None:
        self.metadata = self.metadata or {}
        self.metadata["generated_files"] = list(value or [])

    @property
    def error_logs(self) -> list[Any]:
        return list((self.metadata or {}).get("error_logs", []))

    @error_logs.setter
    def error_logs(self, value: list[Any] | None) -> None:
        self.metadata = self.metadata or {}
        self.metadata["error_logs"] = list(value or [])


class GenerationConfig(models.Model):
    """
    文书生成配置

    存储文书生成的全局配置,如默认模板、生成参数等.

    Requirements: 6.1.3
    """

    id: int
    name: str = models.CharField(max_length=100, unique=True, verbose_name=_("配置名称"))
    config_type: str = models.CharField(
        max_length=50, verbose_name=_("配置类型"), help_text=_("如:default_template、ai_model、generation_params")
    )
    value: dict[str, Any] = models.JSONField(verbose_name=_("配置值"))
    description: str = models.TextField(blank=True, verbose_name=_("配置说明"))
    is_active: bool = models.BooleanField(default=True, verbose_name=_("是否启用"))
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label: str = "documents"
        verbose_name = _("文书生成配置")
        verbose_name_plural = _("文书生成配置")
        ordering: ClassVar = ["config_type", "name"]
        indexes: ClassVar = [
            models.Index(fields=["config_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.config_type} - {self.name}"

    @property
    def case_type(self) -> str | None:
        return (self.value or {}).get("case_type")

    @property
    def case_stage(self) -> str | None:
        return (self.value or {}).get("case_stage")

    @property
    def document_template_id(self) -> int | None:
        return (self.value or {}).get("document_template_id")

    @property
    def folder_path(self) -> str | None:
        return (self.value or {}).get("folder_path")

    @property
    def priority(self) -> int:
        return (self.value or {}).get("priority", 0)

    @property
    def condition(self) -> dict[str, Any]:
        return (self.value or {}).get("condition") or {}
