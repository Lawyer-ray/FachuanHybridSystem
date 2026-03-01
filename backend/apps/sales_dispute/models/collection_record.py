from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models.fields.related_descriptors import RelatedManager


class CollectionStage(models.TextChoices):
    PHONE_COLLECTION = "phone_collection", _("电话催款")
    WRITTEN_COLLECTION = "written_collection", _("书面催款")
    LAWYER_LETTER = "lawyer_letter", _("律师函")
    ULTIMATUM = "ultimatum", _("最后通牒")
    LITIGATION = "litigation", _("起诉")


# 阶段顺序列表，用于状态机校验
STAGE_ORDER: list[str] = [s.value for s in CollectionStage]


class CollectionRecord(models.Model):
    id: int
    case_id: int
    case: models.OneToOneField[models.Model, models.Model] = models.OneToOneField(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="collection_record",
        verbose_name=_("关联案件"),
    )
    current_stage: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=CollectionStage.choices,
        default=CollectionStage.PHONE_COLLECTION,
        verbose_name=_("当前催收阶段"),
    )
    start_date: date = models.DateField(  # type: ignore[assignment]
        verbose_name=_("催收启动日期"),
    )
    last_action_date: date | None = models.DateField(  # type: ignore[assignment]
        blank=True, null=True, verbose_name=_("最近操作日期"),
    )
    next_due_date: date | None = models.DateField(  # type: ignore[assignment]
        blank=True, null=True, verbose_name=_("下一节点到期日"),
    )
    remarks: str = models.TextField(  # type: ignore[assignment]
        blank=True, default="", verbose_name=_("催收备注"),
    )
    created_at: datetime = models.DateTimeField(  # type: ignore[assignment]
        auto_now_add=True, verbose_name=_("创建时间"),
    )
    updated_at: datetime = models.DateTimeField(  # type: ignore[assignment]
        auto_now=True, verbose_name=_("更新时间"),
    )

    if TYPE_CHECKING:
        logs: RelatedManager[CollectionLog]

    class Meta:
        verbose_name = _("催收记录")
        verbose_name_plural = _("催收记录")
        indexes: ClassVar = [
            models.Index(fields=["current_stage"]),
            models.Index(fields=["next_due_date"]),
        ]

    def __str__(self) -> str:
        return f"催收: {self.case} - {self.get_current_stage_display()}"  # type: ignore[attr-defined]

    @property
    def days_elapsed(self) -> int:
        """从催收启动日期到当前日期的天数"""
        return (date.today() - self.start_date).days

    @property
    def is_overdue(self) -> bool:
        """下一节点到期日是否已过"""
        if self.next_due_date is None:
            return False
        return self.next_due_date < date.today()


class CollectionLog(models.Model):
    id: int
    record_id: int
    record: CollectionRecord = models.ForeignKey(  # type: ignore[assignment]
        CollectionRecord,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name=_("关联催收记录"),
    )
    action_type: str = models.CharField(  # type: ignore[assignment]
        max_length=32,
        choices=CollectionStage.choices,
        verbose_name=_("操作类型"),
    )
    action_date: date = models.DateField(  # type: ignore[assignment]
        verbose_name=_("操作日期"),
    )
    description: str = models.TextField(  # type: ignore[assignment]
        verbose_name=_("操作描述"),
    )
    document_type: str = models.CharField(  # type: ignore[assignment]
        max_length=64, blank=True, default="", verbose_name=_("文书类型"),
    )
    document_filename: str = models.CharField(  # type: ignore[assignment]
        max_length=255, blank=True, default="", verbose_name=_("文书文件名"),
    )
    created_at: datetime = models.DateTimeField(  # type: ignore[assignment]
        auto_now_add=True, verbose_name=_("创建时间"),
    )

    class Meta:
        verbose_name = _("催收操作日志")
        verbose_name_plural = _("催收操作日志")
        ordering: ClassVar = ["-action_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.get_action_type_display()} - {self.action_date}"  # type: ignore[attr-defined]
