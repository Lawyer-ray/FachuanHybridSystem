from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, ClassVar

from django.conf import settings
from django.db import models


class PdfSplitJobStatus(models.TextChoices):
    PENDING = "pending", "待处理"
    PROCESSING = "processing", "处理中"
    REVIEW_REQUIRED = "review_required", "待复核"
    EXPORTING = "exporting", "导出中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"


class PdfSplitSourceType(models.TextChoices):
    UPLOAD = "upload", "上传文件"
    LOCAL_PATH = "local_path", "本地路径"


class PdfSplitMode(models.TextChoices):
    CONTENT_ANALYSIS = "content_analysis", "内容识别拆分"
    PAGE_SPLIT = "page_split", "按页拆分"
    MANUAL_SPLIT = "manual_split", "手动拆分"


class PdfSplitOcrProfile(models.TextChoices):
    FAST = "fast", "快速"
    BALANCED = "balanced", "均衡"
    ACCURATE = "accurate", "高精度"


class PdfSplitSegmentType(models.TextChoices):
    COMPLAINT = "complaint", "起诉状"
    EVIDENCE_LIST = "evidence_list", "证据清单及明细"
    PRESERVATION_MATERIALS = "preservation_materials", "财产保全资料"
    PARTY_IDENTITY = "party_identity", "双方当事人主体信息"
    AUTHORIZATION_MATERIALS = "authorization_materials", "授权委托材料"
    DELIVERY_ADDRESS_CONFIRMATION = "delivery_address_confirmation", "送达地址确认书"
    REFUND_ACCOUNT_CONFIRMATION = "refund_account_confirmation", "诉讼费用退费账户确认书"
    LOAN_CONTRACT = "loan_contract", "借款合同"
    LOAN_DISBURSEMENT_RECORD = "loan_disbursement_record", "放款凭证"
    BANK_STATEMENT = "bank_statement", "银行流水"
    INTEREST_CALCULATION = "interest_calculation", "利息计算表"
    DELIVERY_NOTE = "delivery_note", "送货单"
    GOODS_RECEIPT = "goods_receipt", "收货单"
    INVOICE = "invoice", "发票"
    # ── 银行信贷档案类 ──
    # 抵押房贷案的真实档案远比「合同+借据+流水」多：贷前尽调、抵押评估、
    # 抵押登记、内部不良监控报告，缺一类就会落 unrecognized。
    # 实测一份 30 页真实结构的档案，有 5 类材料识别不出。
    LOAN_APPLICATION = "loan_application", "贷款申请及调查审批材料"
    COLLATERAL_APPRAISAL = "collateral_appraisal", "抵押物估价报告"
    MORTGAGE_REGISTRATION = "mortgage_registration", "抵押登记及权属证明"
    NPL_MONITORING = "npl_monitoring", "不良贷款监控及催收申请"
    POST_LOAN_INSPECTION = "post_loan_inspection", "贷后检查报告"
    COLLECTION_RECORD = "collection_record", "催收记录"
    # ── 诉讼程序类文书 ──
    #
    # ⚠️ 这一组是后补的，补之前模型认不出它们：判决书/上诉状/答辩状
    # 全部落到 unrecognized，律师看到「未识别材料」而文件名明明是对的。
    # 根因是原枚举只覆盖了**一审起诉**的材料清单（起诉状/证据清单/借款合同…），
    # 二审、执行、再审阶段的文书一个都没有。
    # 拆解是「收到什么拆什么」，不能只认一个阶段。
    JUDGMENT = "judgment", "判决书"
    RULING = "ruling", "裁定书"
    MEDIATION_STATEMENT = "mediation_statement", "调解书"
    APPEAL_PETITION = "appeal_petition", "上诉状"
    DEFENSE_STATEMENT = "defense_statement", "答辩状"
    RETRIAL_APPLICATION = "retrial_application", "再审申请书"
    ENFORCEMENT_APPLICATION = "enforcement_application", "执行申请书"
    COURT_RECORD = "court_record", "庭审笔录"
    AGENT_OPINION = "agent_opinion", "代理词"
    UNRECOGNIZED = "unrecognized", "未识别材料"


class PdfSplitReviewFlag(models.TextChoices):
    NORMAL = "normal", "正常"
    LOW_CONFIDENCE = "low_confidence", "低置信度"
    UNRECOGNIZED = "unrecognized", "未识别"
    OCR_FAILED = "ocr_failed", "OCR失败"


class PdfSplittingTool(models.Model):
    name = models.CharField(max_length=64, default="Pdf Splitting")

    class Meta:
        managed = False
        verbose_name = "PDF 拆解"
        verbose_name_plural = "PDF 拆解"


class PdfSplitJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_type = models.CharField(
        max_length=16,
        choices=PdfSplitSourceType.choices,
        verbose_name="来源类型",
    )
    source_abs_path = models.CharField(max_length=2048, blank=True, default="", verbose_name="源绝对路径")
    source_relpath = models.CharField(max_length=1024, blank=True, default="", verbose_name="源相对路径")
    source_original_name = models.CharField(max_length=255, verbose_name="源文件名")
    split_mode = models.CharField(
        max_length=32,
        choices=PdfSplitMode.choices,
        default=PdfSplitMode.CONTENT_ANALYSIS,
        verbose_name="拆分模式",
    )
    template_key = models.CharField(max_length=64, default="filing_materials_v1", verbose_name="模板键")
    template_version = models.CharField(max_length=32, default="1", verbose_name="模板版本")
    ocr_profile = models.CharField(
        max_length=16,
        choices=PdfSplitOcrProfile.choices,
        default=PdfSplitOcrProfile.BALANCED,
        verbose_name="OCR 档位",
    )
    status = models.CharField(
        max_length=32,
        choices=PdfSplitJobStatus.choices,
        default=PdfSplitJobStatus.PENDING,
        verbose_name="状态",
    )
    total_pages = models.PositiveIntegerField(default=0, verbose_name="总页数")
    processed_pages = models.PositiveIntegerField(default=0, verbose_name="已处理页数")
    progress = models.PositiveIntegerField(default=0, verbose_name="进度")
    current_page = models.PositiveIntegerField(default=0, verbose_name="当前页")
    task_id = models.CharField(max_length=64, blank=True, default="", verbose_name="任务ID")
    cancel_requested = models.BooleanField(default=False, verbose_name="请求取消")
    created_by: Any = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pdf_split_jobs",
        verbose_name="创建人",
    )
    summary_payload = models.JSONField(default=dict, blank=True, verbose_name="摘要")
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    export_zip_relpath = models.CharField(max_length=1024, blank=True, default="", verbose_name="导出ZIP路径")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "PDF 拆解任务"
        verbose_name_plural = "PDF 拆解任务"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_original_name} ({self.get_status_display()})"


class PdfSplitSegment(models.Model):
    job: Any = models.ForeignKey(
        PdfSplitJob,
        on_delete=models.CASCADE,
        related_name="segments",
        verbose_name="任务",
    )
    order = models.PositiveIntegerField(default=1, verbose_name="排序")
    page_start = models.PositiveIntegerField(verbose_name="起始页")
    page_end = models.PositiveIntegerField(verbose_name="结束页")
    segment_type = models.CharField(
        max_length=48,
        choices=PdfSplitSegmentType.choices,
        default=PdfSplitSegmentType.UNRECOGNIZED,
        verbose_name="段类型",
    )
    filename = models.CharField(max_length=255, verbose_name="文件名")
    confidence = models.FloatField(default=0.0, verbose_name="置信度")
    source_method = models.CharField(max_length=32, default="rule", verbose_name="来源方法")
    review_flag = models.CharField(
        max_length=32,
        choices=PdfSplitReviewFlag.choices,
        default=PdfSplitReviewFlag.NORMAL,
        verbose_name="复核标记",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "PDF 拆解片段"
        verbose_name_plural = "PDF 拆解片段"
        ordering: ClassVar[list[str]] = ["order", "id"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["job", "order"], name="pdf_splitting_segment_job_order_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.page_start}-{self.page_end} {self.segment_type}"
