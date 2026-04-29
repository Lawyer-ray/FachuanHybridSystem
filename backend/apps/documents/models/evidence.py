"""
证据清单模型

本模块定义证据清单相关的数据模型:
- EvidenceList: 证据清单
- EvidenceItem: 证据明细
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import DocumentCaseFileSubType, DocumentTemplateType
from .evidence_storage import evidence_file_storage


class MergeStatus(models.TextChoices):
    """合并状态"""

    PENDING = "pending", _("待合并")
    PROCESSING = "processing", _("合并中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")


class ListType(models.TextChoices):
    """证据清单类型"""

    LIST_1 = "list_1", _("证据清单一")
    LIST_2 = "list_2", _("证据清单二")
    LIST_3 = "list_3", _("证据清单三")
    LIST_4 = "list_4", _("证据清单四")
    LIST_5 = "list_5", _("证据清单五")
    LIST_6 = "list_6", _("证据清单六")


# 清单类型的顺序和前置关系
LIST_TYPE_ORDER = {
    ListType.LIST_1: 1,
    ListType.LIST_2: 2,
    ListType.LIST_3: 3,
    ListType.LIST_4: 4,
    ListType.LIST_5: 5,
    ListType.LIST_6: 6,
}

# 清单类型的前置依赖(None 表示无前置依赖)
LIST_TYPE_PREVIOUS = {
    ListType.LIST_1: None,
    ListType.LIST_2: ListType.LIST_1,
    ListType.LIST_3: ListType.LIST_2,
    ListType.LIST_4: ListType.LIST_3,
    ListType.LIST_5: ListType.LIST_4,
    ListType.LIST_6: ListType.LIST_5,
}


if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


def _get_evidence_service() -> Any:
    """工厂函数: 获取 EvidenceService 实例"""
    from apps.documents.services.evidence.evidence_service import EvidenceService

    return EvidenceService()


def _get_evidence_storage() -> Any:
    """工厂函数: 获取证据文件存储实例"""
    from apps.documents.services.evidence.evidence_storage import evidence_file_storage

    return evidence_file_storage


class EvidenceList(models.Model):
    """
    证据清单

    关联案件,包含多个证据明细.支持跨清单连续页码和序号.
    通过 list_type 和 previous_list 实现链式关联,自动计算起始序号和页码.

    Requirements: 1.1-1.9
    """

    id: int
    previous_list_id: int  # 外键ID字段
    export_template_id: int  # 外键ID字段
    created_by_id: int  # 外键ID字段
    case_id: int  # 外键ID字段
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="evidence_lists",
        verbose_name=_("案件"),
    )
    list_type = models.CharField(
        max_length=20,
        choices=ListType.choices,
        default=ListType.LIST_1,
        verbose_name=_("清单类型"),
        help_text=_("选择清单类型,系统自动处理序号和页码的连续性"),
    )
    previous_list = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="next_lists",
        verbose_name=_("前置清单"),
        help_text=_("关联前一个清单,用于自动计算起始序号和页码"),
    )
    # 保留 title 字段用于显示,但由 list_type 自动生成
    title = models.CharField(
        max_length=100,
        verbose_name=_("标题"),
        blank=True,
        help_text=_("由清单类型自动生成"),
    )
    # 保留 order 字段用于排序,由 list_type 自动设置
    order = models.IntegerField(
        default=1,
        verbose_name=_("顺序"),
        editable=False,
    )
    merged_pdf = models.FileField(
        upload_to="evidence/merged/%Y/%m/",
        storage=evidence_file_storage,
        blank=True,
        null=True,
        verbose_name=_("合并PDF"),
        help_text=_("将所有证据文件合并为一个PDF,便于打印和提交"),
    )
    total_pages = models.IntegerField(
        default=0,
        verbose_name=_("总页数"),
    )
    export_version = models.IntegerField(
        default=1,
        verbose_name=_("导出版本号"),
        help_text=_("由用户手动控制,用于导出文件名版本控制"),
    )
    # 异步合并状态
    merge_status = models.CharField(
        max_length=20,
        choices=MergeStatus.choices,
        default=MergeStatus.PENDING,
        verbose_name=_("合并状态"),
    )
    merge_error = models.TextField(
        blank=True,
        verbose_name=_("合并错误信息"),
    )
    merge_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("合并开始时间"),
    )
    merge_finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("合并完成时间"),
    )
    merge_progress = models.IntegerField(
        default=0,
        verbose_name=_("合并进度"),
    )
    merge_current = models.IntegerField(
        default=0,
        verbose_name=_("合并进度-已处理文件数"),
    )
    merge_total = models.IntegerField(
        default=0,
        verbose_name=_("合并进度-总文件数"),
    )
    merge_message = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("合并进度信息"),
    )
    export_template = models.ForeignKey(
        "documents.DocumentTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_lists",
        verbose_name=_("导出模板"),
        help_text=_("选择用于导出证据清单的 Word 模板"),
        limit_choices_to={
            "is_active": True,
            "template_type": DocumentTemplateType.CASE,
            "case_sub_type": DocumentCaseFileSubType.EVIDENCE_MATERIALS,
        },
    )
    created_by = models.ForeignKey(
        "organization.Lawyer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_evidence_lists",
        verbose_name=_("创建人"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("更新时间"),
    )

    if TYPE_CHECKING:
        items: RelatedManager[EvidenceItem]
        next_lists: RelatedManager[EvidenceList]

    class Meta:
        app_label = "documents"
        ordering: ClassVar = ["order", "created_at"]
        verbose_name = _("证据清单")
        verbose_name_plural = _("证据清单")
        indexes: ClassVar = [
            models.Index(fields=["case", "order"]),
            models.Index(fields=["case", "list_type"]),
            models.Index(fields=["created_by"]),
        ]
        # 同一案件不能有重复的清单类型
        constraints: ClassVar = [models.UniqueConstraint(fields=["case", "list_type"], name="unique_case_list_type")]

    def __str__(self) -> str:
        return f"{self.case.name} - {self.title}"

    @property
    def start_order(self) -> int:
        """计算起始序号(委托给 Service 层)"""
        return _get_evidence_service().calculate_start_order(self)  # type: ignore[no-any-return]

    @property
    def start_page(self) -> int:
        """计算起始页码(委托给 Service 层)"""
        return _get_evidence_service().calculate_start_page(self)  # type: ignore[no-any-return]

    @property
    def end_page(self) -> int:
        """计算结束页码"""
        if self.total_pages == 0:
            return self.start_page
        return self.start_page + self.total_pages - 1

    @property
    def page_range_display(self) -> str:
        """页码范围显示"""
        if self.total_pages == 0:
            return ""
        return f"{self.start_page}-{self.end_page}"

    @property
    def order_range_display(self) -> str:
        """序号范围显示"""
        item_count = getattr(self, "item_count", None)
        if item_count is None:
            item_count = self.items.count()
        if item_count == 0:
            return "-"
        end_order = self.start_order + item_count - 1
        if self.start_order == end_order:
            return str(self.start_order)
        return f"{self.start_order}-{end_order}"


class EvidenceItem(models.Model):
    """
    证据明细

    单个证据的详细信息,包括名称、证明内容、文件、页码等.

    Requirements: 1.10-1.15
    """

    id: int
    evidence_list_id: int  # 外键ID字段
    evidence_list = models.ForeignKey(
        EvidenceList,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("证据清单"),
    )
    order = models.IntegerField(
        verbose_name=_("序号"),
        help_text=_("证据在清单中的序号"),
        default=0,
        blank=True,
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("证据名称"),
    )
    purpose = models.TextField(
        verbose_name=_("证明内容"),
    )
    file = models.FileField(
        upload_to="evidence/files/%Y/%m/",
        blank=True,
        null=True,
        verbose_name=_("证据文件"),
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("原始文件名"),
    )
    file_size = models.IntegerField(
        default=0,
        verbose_name=_("文件大小"),
        help_text=_("单位:字节"),
    )
    page_count = models.IntegerField(
        default=0,
        verbose_name=_("页数"),
    )
    page_start = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("起始页"),
    )
    page_end = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("结束页"),
    )
    # AI 扩展字段
    ai_analysis: Any = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("AI分析结果"),
        help_text=_("预留字段,用于未来 LLM 自动分析"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("更新时间"),
    )

    class Meta:
        app_label = "documents"
        ordering: ClassVar = ["order"]
        verbose_name = _("证据明细")
        verbose_name_plural = _("证据明细")
        indexes: ClassVar = [
            models.Index(fields=["evidence_list", "order"]),
        ]

    def __str__(self) -> str:
        return f"{self.order}. {self.name}"

    @property
    def page_range_display(self) -> str:
        """页码范围显示"""
        if self.page_start is None or self.page_end is None:
            return "-"
        if self.page_start == self.page_end:
            return str(self.page_start)
        return f"{self.page_start}-{self.page_end}"

    @property
    def file_size_display(self) -> str:
        """文件大小显示"""
        if self.file_size == 0:
            return "-"
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
