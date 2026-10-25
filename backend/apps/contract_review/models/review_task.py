import uuid

from django.conf import settings
from django.db import models


class TaskStatus(models.TextChoices):
    UPLOADED = "uploaded", "已上传"
    PARTIES_IDENTIFIED = "parties_identified", "已识别当事人"
    CONFIRMED = "confirmed", "已确认"
    PROCESSING = "processing", "处理中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    EXTRACTION_FAILED = "extraction_failed", "提取失败"


class ProcessStep(models.TextChoices):
    TITLE_EXTRACTION = "title_extraction", "标题提取"
    TYPO_CHECK = "typo_check", "错别字检测"
    CONTRACT_REVIEW = "contract_review", "合同审查"
    FORMAT_DOCUMENT = "format_document", "格式标准化"
    PAGE_NUMBERING = "page_numbering", "页码标准化"
    HEADING_NUMBERING = "heading_numbering", "标题序号"


class RepresentedParty(models.TextChoices):
    PARTY_A = "party_a", "甲方"
    PARTY_B = "party_b", "乙方"
    PARTY_C = "party_c", "丙方"
    PARTY_D = "party_d", "丁方"


class ReviewTask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        # SET_NULL：删除律师账号不销毁审查任务历史，保留审计记录
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_tasks",
        verbose_name="用户",
    )
    original_file = models.CharField(max_length=512, verbose_name="原始文件路径")
    output_file = models.CharField(max_length=512, blank=True, verbose_name="输出文件路径")
    pdf_cache_file = models.CharField(max_length=512, blank=True, verbose_name="PDF 缓存文件路径")
    contract_title = models.CharField(max_length=256, blank=True, verbose_name="合同标题")
    party_a = models.CharField(max_length=256, blank=True, verbose_name="甲方")
    party_b = models.CharField(max_length=256, blank=True, verbose_name="乙方")
    party_c = models.CharField(max_length=256, blank=True, verbose_name="丙方")
    party_d = models.CharField(max_length=256, blank=True, verbose_name="丁方")
    represented_party = models.CharField(
        max_length=16,
        choices=RepresentedParty.choices,
        blank=True,
        verbose_name="用户代表方",
    )
    status = models.CharField(
        max_length=32,
        choices=TaskStatus.choices,
        default=TaskStatus.UPLOADED,
        verbose_name="任务状态",
    )
    current_step = models.CharField(
        max_length=32,
        choices=ProcessStep.choices,
        blank=True,
        verbose_name="当前处理步骤",
    )
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    review_report = models.TextField(blank=True, verbose_name="评估报告")
    model_name = models.CharField(max_length=128, blank=True, verbose_name="LLM 模型名称")
    reviewer_name = models.CharField(max_length=128, blank=True, default="法穿SI", verbose_name="修订人名称")
    selected_steps = models.JSONField(
        default=list,
        blank=True,
        verbose_name="选中的处理步骤",
        help_text="用户选择执行的步骤列表",
    )
    # 客户特别交代：律师在发起审查时写的诉求（「一定要压工期」等）。
    # 这是审查方向的来源之一，必须进 prompt——否则律师写了也白写。
    client_note = models.TextField(
        blank=True,
        default="",
        verbose_name="客户特别交代",
        help_text="律师填写的自由文本诉求，拼进审查 prompt",
    )
    client_demands = models.JSONField(
        default=list,
        blank=True,
        verbose_name="客户诉求要点",
        help_text="抽屉里勾选的 chips，结构化留存便于统计",
    )
    # 我方单位全名：party_a/party_b 只是文档里的位置，不代表「我方」。
    # 合同里我方在乙方时，靠位置判方向会整批审反。
    our_client_name = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="我方单位全名",
    )
    stance_basis = models.TextField(
        blank=True,
        default="",
        verbose_name="立场判断依据",
        help_text="AI 为什么认为我方是这个立场，供律师核对",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "合同审查任务"
        verbose_name_plural = "合同审查任务"
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.contract_title or self.original_file} ({self.get_status_display()})"
