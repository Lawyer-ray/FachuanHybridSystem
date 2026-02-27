import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class TaskStatus(models.TextChoices):
    UPLOADED = "uploaded", _("已上传")
    PARTIES_IDENTIFIED = "parties_identified", _("已识别当事人")
    CONFIRMED = "confirmed", _("已确认")
    PROCESSING = "processing", _("处理中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("失败")
    EXTRACTION_FAILED = "extraction_failed", _("提取失败")


class ProcessStep(models.TextChoices):
    TITLE_EXTRACTION = "title_extraction", _("标题提取")
    TYPO_CHECK = "typo_check", _("错别字检测")
    CONTRACT_REVIEW = "contract_review", _("合同审查")
    FORMAT_DOCUMENT = "format_document", _("格式标准化")
    PAGE_NUMBERING = "page_numbering", _("页码标准化")
    HEADING_NUMBERING = "heading_numbering", _("标题序号")


class RepresentedParty(models.TextChoices):
    PARTY_A = "party_a", _("甲方")
    PARTY_B = "party_b", _("乙方")
    PARTY_C = "party_c", _("丙方")
    PARTY_D = "party_d", _("丁方")


class ReviewTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_tasks",
        verbose_name=_("用户"),
    )
    original_file = models.CharField(max_length=512, verbose_name=_("原始文件路径"))
    output_file = models.CharField(
        max_length=512, blank=True, verbose_name=_("输出文件路径")
    )
    contract_title = models.CharField(
        max_length=256, blank=True, verbose_name=_("合同标题")
    )
    party_a = models.CharField(max_length=256, blank=True, verbose_name=_("甲方"))
    party_b = models.CharField(max_length=256, blank=True, verbose_name=_("乙方"))
    party_c = models.CharField(max_length=256, blank=True, verbose_name=_("丙方"))
    party_d = models.CharField(max_length=256, blank=True, verbose_name=_("丁方"))
    represented_party = models.CharField(
        max_length=16,
        choices=RepresentedParty.choices,
        blank=True,
        verbose_name=_("用户代表方"),
    )
    status = models.CharField(
        max_length=32,
        choices=TaskStatus.choices,
        default=TaskStatus.UPLOADED,
        verbose_name=_("任务状态"),
    )
    current_step = models.CharField(
        max_length=32,
        choices=ProcessStep.choices,
        blank=True,
        verbose_name=_("当前处理步骤"),
    )
    error_message = models.TextField(blank=True, verbose_name=_("错误信息"))
    review_report = models.TextField(blank=True, verbose_name=_("评估报告"))
    model_name = models.CharField(
        max_length=128, blank=True, verbose_name=_("LLM 模型名称")
    )
    reviewer_name = models.CharField(
        max_length=128, blank=True, default="法穿AI", verbose_name=_("修订人名称")
    )
    selected_steps = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("选中的处理步骤"),
        help_text=_("用户选择执行的步骤列表"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        verbose_name = _("合同审查任务")
        verbose_name_plural = _("合同审查任务")
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_title or self.original_file} ({self.get_status_display()})"
