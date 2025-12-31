from django.db import models
from django.utils.translation import gettext_lazy as _


class AutomationTool(models.Model):
    name = models.CharField(max_length=64, default="Document Processor")

    class Meta:
        managed = False
        verbose_name = "文档处理"
        verbose_name_plural = "文档处理"


class NamerTool(models.Model):
    name = models.CharField(max_length=64, default="Namer Tool")

    class Meta:
        managed = False
        verbose_name = "自动命名工具"
        verbose_name_plural = "自动命名工具"


class TestCourt(models.Model):
    """测试法院系统虚拟模型"""
    name = models.CharField(max_length=64, default="Test Court")

    class Meta:
        managed = False
        verbose_name = "测试法院系统"
        verbose_name_plural = "测试法院系统"


class ScraperTaskType(models.TextChoices):
    """爬虫任务类型"""
    COURT_DOCUMENT = "court_document", _("下载司法文书")
    COURT_FILING = "court_filing", _("自动立案")
    JUSTICE_BUREAU = "justice_bureau", _("司法局操作")
    POLICE = "police", _("公安局操作")


class ScraperTaskStatus(models.TextChoices):
    """爬虫任务状态"""
    PENDING = "pending", _("等待中")
    RUNNING = "running", _("执行中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class CourtToken(models.Model):
    """法院系统 Token 存储"""
    site_name = models.CharField(
        max_length=128,
        verbose_name=_("网站名称"),
        help_text=_("如：court_zxfw")
    )
    account = models.CharField(
        max_length=128,
        verbose_name=_("账号")
    )
    token = models.TextField(
        verbose_name=_("Token"),
        help_text=_("JWT Token 或其他认证令牌")
    )
    token_type = models.CharField(
        max_length=32,
        default="Bearer",
        verbose_name=_("Token 类型"),
        help_text=_("如：Bearer, JWT")
    )
    expires_at = models.DateTimeField(
        verbose_name=_("过期时间")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("Token管理")
        verbose_name_plural = _("Token管理")
        unique_together = [["site_name", "account"]]
        indexes = [
            models.Index(fields=["site_name", "account"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return "{} - {}".format(self.site_name, self.account)
    
    def is_expired(self) -> bool:
        """判断是否过期"""
        from django.utils import timezone
        return self.expires_at <= timezone.now()


class TokenAcquisitionStatus(models.TextChoices):
    """Token获取状态"""
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")
    TIMEOUT = "timeout", _("超时")
    NETWORK_ERROR = "network_error", _("网络错误")
    CAPTCHA_ERROR = "captcha_error", _("验证码错误")
    CREDENTIAL_ERROR = "credential_error", _("账号密码错误")


class TokenAcquisitionHistory(models.Model):
    """Token获取历史记录"""
    site_name = models.CharField(
        max_length=128,
        verbose_name=_("网站名称"),
        help_text=_("如：court_zxfw")
    )
    account = models.CharField(
        max_length=128,
        verbose_name=_("使用账号")
    )
    credential_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("凭证ID"),
        help_text=_("关联的AccountCredential ID")
    )
    status = models.CharField(
        max_length=32,
        choices=TokenAcquisitionStatus.choices,
        verbose_name=_("获取状态")
    )
    trigger_reason = models.CharField(
        max_length=256,
        verbose_name=_("触发原因"),
        help_text=_("如：token_expired, no_token, manual_trigger")
    )
    attempt_count = models.IntegerField(
        default=1,
        verbose_name=_("尝试次数")
    )
    total_duration = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("总耗时（秒）")
    )
    login_duration = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("登录耗时（秒）")
    )
    captcha_attempts = models.IntegerField(
        default=0,
        verbose_name=_("验证码尝试次数")
    )
    network_retries = models.IntegerField(
        default=0,
        verbose_name=_("网络重试次数")
    )
    token_preview = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Token预览"),
        help_text=_("Token的前50个字符")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    error_details = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("详细错误信息"),
        help_text=_("包含完整的错误堆栈和上下文")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间")
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("开始时间")
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("完成时间")
    )

    class Meta:
        app_label = "automation"
        verbose_name = _("Token获取历史")
        verbose_name_plural = _("Token获取历史")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["site_name", "-created_at"]),
            models.Index(fields=["account", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return "{} - {} - {}".format(self.site_name, self.account, self.get_status_display())
    
    def get_success_rate_display(self) -> str:
        """获取成功率显示"""
        if self.status == TokenAcquisitionStatus.SUCCESS:
            return "100%"
        return "0%"


class ScraperTask(models.Model):
    """网络爬虫任务"""
    task_type = models.CharField(
        max_length=32,
        choices=ScraperTaskType.choices,
        verbose_name=_("任务类型")
    )
    status = models.CharField(
        max_length=32,
        choices=ScraperTaskStatus.choices,
        default=ScraperTaskStatus.PENDING,
        verbose_name=_("状态")
    )
    priority = models.IntegerField(
        default=5,
        verbose_name=_("优先级"),
        help_text=_("1-10，数字越小优先级越高")
    )
    url = models.URLField(verbose_name=_("目标URL"))
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scraper_tasks",
        verbose_name=_("关联案件")
    )
    config = models.JSONField(
        default=dict,
        verbose_name=_("配置"),
        help_text=_("存储账号、密码、文件路径等")
    )
    result = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("执行结果")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    retry_count = models.IntegerField(
        default=0,
        verbose_name=_("重试次数")
    )
    max_retries = models.IntegerField(
        default=3,
        verbose_name=_("最大重试次数")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("更新时间"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("计划执行时间"),
        help_text=_("留空则立即执行")
    )

    class Meta:
        app_label = "automation"
        verbose_name = _("任务管理")
        verbose_name_plural = _("任务管理")
        ordering = ["priority", "-created_at"]  # 优先级优先，然后按创建时间
        indexes = [
            models.Index(fields=["status", "priority", "-created_at"]),
            models.Index(fields=["task_type"]),
            models.Index(fields=["case"]),
            models.Index(fields=["scheduled_at"]),
        ]

    def __str__(self):
        return "{} - {}".format(self.get_task_type_display(), self.get_status_display())
    
    def can_retry(self) -> bool:
        """判断是否可以重试"""
        return self.retry_count < self.max_retries
    
    def should_execute_now(self) -> bool:
        """判断是否应该立即执行"""
        from django.utils import timezone
        if self.scheduled_at is None:
            return True
        return self.scheduled_at <= timezone.now()


class QuoteStatus(models.TextChoices):
    """询价任务状态"""
    PENDING = "pending", _("等待中")
    RUNNING = "running", _("执行中")
    SUCCESS = "success", _("成功")
    PARTIAL_SUCCESS = "partial_success", _("部分成功")
    FAILED = "failed", _("失败")


class QuoteItemStatus(models.TextChoices):
    """单个报价状态"""
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class PreservationQuote(models.Model):
    """财产保全询价任务"""
    preserve_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("保全金额"),
        help_text=_("需要保全的财产金额")
    )
    corp_id = models.CharField(
        max_length=32,
        default="2550",
        verbose_name=_("法院ID"),
        help_text=_("法院系统中的法院标识")
    )
    category_id = models.CharField(
        max_length=32,
        default="127000",
        verbose_name=_("分类ID"),
        help_text=_("保全分类ID (cPid)")
    )
    credential_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("凭证ID"),
        help_text=_("关联的账号凭证ID（可选，系统会自动获取Token）")
    )
    status = models.CharField(
        max_length=32,
        choices=QuoteStatus.choices,
        default=QuoteStatus.PENDING,
        verbose_name=_("任务状态")
    )
    total_companies = models.IntegerField(
        default=0,
        verbose_name=_("保险公司总数")
    )
    success_count = models.IntegerField(
        default=0,
        verbose_name=_("成功查询数")
    )
    failed_count = models.IntegerField(
        default=0,
        verbose_name=_("失败查询数")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间")
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("开始时间")
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("完成时间")
    )

    class Meta:
        app_label = "automation"
        verbose_name = _("财产保全询价")
        verbose_name_plural = _("财产保全询价")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["credential_id"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return "询价任务 #{} - {}元 - {}".format(self.id, self.preserve_amount, self.get_status_display())
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        if self.total_companies == 0:
            return 0.0
        return (self.success_count / self.total_companies) * 100


class InsuranceQuote(models.Model):
    """保险公司报价记录"""
    preservation_quote = models.ForeignKey(
        PreservationQuote,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name=_("询价任务")
    )
    company_id = models.CharField(
        max_length=64,
        verbose_name=_("保险公司ID"),
        help_text=_("cId")
    )
    company_code = models.CharField(
        max_length=64,
        verbose_name=_("保险公司编码"),
        help_text=_("cCode")
    )
    company_name = models.CharField(
        max_length=256,
        verbose_name=_("保险公司名称"),
        help_text=_("cName")
    )
    premium = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("报价金额"),
        help_text=_("保险公司给出的担保费报价（通常使用 minPremium）")
    )
    # 费率信息字段
    min_premium = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("最低收费1"),
        help_text=_("minPremium")
    )
    min_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("最低收费2"),
        help_text=_("minAmount")
    )
    max_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("最高收费"),
        help_text=_("maxAmount")
    )
    min_rate = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("最低费率"),
        help_text=_("minRate")
    )
    max_rate = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("最高费率"),
        help_text=_("maxRate")
    )
    max_apply_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("最高保全金额"),
        help_text=_("maxApplyAmount")
    )
    status = models.CharField(
        max_length=32,
        choices=QuoteItemStatus.choices,
        verbose_name=_("查询状态")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    response_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("完整响应"),
        help_text=_("API 返回的完整响应数据")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("创建时间")
    )

    class Meta:
        app_label = "automation"
        verbose_name = _("保险公司报价")
        verbose_name_plural = _("保险公司报价")
        ordering = ["min_amount"]  # 按最低报价排序
        indexes = [
            models.Index(fields=["preservation_quote", "status"]),
            models.Index(fields=["company_id"]),
            models.Index(fields=["premium"]),
        ]

    def __str__(self):
        if self.min_amount:
            return "{} - ¥{}".format(self.company_name, self.min_amount)
        return "{} - {}".format(self.company_name, self.get_status_display())


class DocumentRecognitionStatus(models.TextChoices):
    """文书识别任务状态"""
    PENDING = "pending", _("待处理")
    PROCESSING = "processing", _("识别中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class DocumentRecognitionTask(models.Model):
    """文书识别任务"""
    file_path = models.CharField(
        max_length=1024,
        verbose_name=_("文件路径")
    )
    original_filename = models.CharField(
        max_length=256,
        verbose_name=_("原始文件名")
    )
    status = models.CharField(
        max_length=32,
        choices=DocumentRecognitionStatus.choices,
        default=DocumentRecognitionStatus.PENDING,
        verbose_name=_("任务状态")
    )
    # 识别结果
    document_type = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        verbose_name=_("文书类型")
    )
    case_number = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        verbose_name=_("案号")
    )
    key_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("关键时间")
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("置信度")
    )
    extraction_method = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        verbose_name=_("提取方式")
    )
    raw_text = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("原始文本")
    )
    renamed_file_path = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        verbose_name=_("重命名后路径")
    )
    # 绑定结果
    binding_success = models.BooleanField(
        null=True,
        verbose_name=_("绑定成功")
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name=_("关联案件")
    )
    case_log = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_tasks",
        verbose_name=_("案件日志")
    )
    binding_message = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        verbose_name=_("绑定消息")
    )
    binding_error_code = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name=_("绑定错误码")
    )
    # 错误信息
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    # 通知状态字段
    notification_sent = models.BooleanField(
        default=False,
        verbose_name=_("通知已发送")
    )
    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("通知发送时间")
    )
    notification_error = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("通知错误信息")
    )
    notification_file_sent = models.BooleanField(
        default=False,
        verbose_name=_("文件已发送")
    )
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("开始时间"))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("完成时间"))

    class Meta:
        app_label = "automation"
        verbose_name = _("文书识别任务")
        verbose_name_plural = _("文书识别任务")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["case"]),
            models.Index(fields=["notification_sent"]),
        ]

    def __str__(self):
        return "识别任务 #{} - {}".format(self.id, self.get_status_display())


class CourtSMSStatus(models.TextChoices):
    """短信处理状态"""
    PENDING = "pending", _("待处理")
    PARSING = "parsing", _("解析中")
    DOWNLOADING = "downloading", _("下载中")
    DOWNLOAD_FAILED = "download_failed", _("下载失败")
    MATCHING = "matching", _("匹配中")
    PENDING_MANUAL = "pending_manual", _("待人工处理")
    RENAMING = "renaming", _("重命名中")
    NOTIFYING = "notifying", _("通知中")
    COMPLETED = "completed", _("已完成")
    FAILED = "failed", _("处理失败")


class CourtSMSType(models.TextChoices):
    """短信类型"""
    DOCUMENT_DELIVERY = "document_delivery", _("文书送达")
    INFO_NOTIFICATION = "info_notification", _("信息通知")
    FILING_NOTIFICATION = "filing_notification", _("立案通知")


class DocumentDownloadStatus(models.TextChoices):
    """文书下载状态"""
    PENDING = "pending", _("待下载")
    DOWNLOADING = "downloading", _("下载中")
    SUCCESS = "success", _("成功")
    FAILED = "failed", _("失败")


class CourtDocument(models.Model):
    """法院文书记录"""
    # 关联字段
    scraper_task = models.ForeignKey(
        ScraperTask,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name=_("爬虫任务")
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_documents",
        verbose_name=_("关联案件")
    )
    
    # API返回的原始字段
    c_sdbh = models.CharField(
        max_length=128,
        verbose_name=_("送达编号")
    )
    c_stbh = models.CharField(
        max_length=512,
        verbose_name=_("上传编号")
    )
    wjlj = models.URLField(
        max_length=1024,
        verbose_name=_("文件链接")
    )
    c_wsbh = models.CharField(
        max_length=128,
        verbose_name=_("文书编号")
    )
    c_wsmc = models.CharField(
        max_length=512,
        verbose_name=_("文书名称")
    )
    c_fybh = models.CharField(
        max_length=64,
        verbose_name=_("法院编号")
    )
    c_fymc = models.CharField(
        max_length=256,
        verbose_name=_("法院名称")
    )
    c_wjgs = models.CharField(
        max_length=32,
        verbose_name=_("文件格式")
    )
    dt_cjsj = models.DateTimeField(
        verbose_name=_("创建时间（原始）")
    )
    
    # 下载状态字段
    download_status = models.CharField(
        max_length=32,
        choices=DocumentDownloadStatus.choices,
        default=DocumentDownloadStatus.PENDING,
        verbose_name=_("下载状态")
    )
    local_file_path = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        verbose_name=_("本地文件路径")
    )
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("文件大小（字节）")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    
    # 时间戳
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("记录创建时间")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("更新时间")
    )
    downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("下载完成时间")
    )
    
    class Meta:
        app_label = "automation"
        verbose_name = _("法院文书")
        verbose_name_plural = _("法院文书")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["scraper_task", "download_status"]),
            models.Index(fields=["case"]),
            models.Index(fields=["c_wsbh"]),
            models.Index(fields=["c_fymc"]),
            models.Index(fields=["download_status"]),
            models.Index(fields=["created_at"]),
        ]
        unique_together = [["c_wsbh", "c_sdbh"]]  # 文书编号+送达编号唯一

    def __str__(self):
        return "{} - {}".format(self.c_wsmc, self.get_download_status_display())


class DocumentQueryHistory(models.Model):
    """文书查询历史"""
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.CASCADE,
        related_name="document_query_histories",
        verbose_name=_("账号凭证")
    )
    case_number = models.CharField(
        max_length=128,
        verbose_name=_("案号")
    )
    send_time = models.DateTimeField(
        verbose_name=_("文书发送时间")
    )
    court_sms = models.ForeignKey(
        "CourtSMS",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="query_histories",
        verbose_name=_("关联短信记录")
    )
    queried_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("查询时间")
    )
    
    class Meta:
        app_label = "automation"
        verbose_name = _("文书查询历史")
        verbose_name_plural = _("文书查询历史")
        unique_together = [["credential", "case_number", "send_time"]]
        indexes = [
            models.Index(fields=["credential", "case_number"]),
            models.Index(fields=["send_time"]),
        ]

    def __str__(self):
        return "{} - {} - {}".format(
            self.credential, 
            self.case_number, 
            self.send_time.strftime("%Y-%m-%d %H:%M")
        )


class DocumentDeliverySchedule(models.Model):
    """文书送达定时任务"""
    credential = models.ForeignKey(
        "organization.AccountCredential",
        on_delete=models.CASCADE,
        related_name="delivery_schedules",
        verbose_name=_("账号凭证")
    )
    runs_per_day = models.PositiveIntegerField(
        default=1,
        verbose_name=_("每天运行次数")
    )
    hour_interval = models.PositiveIntegerField(
        default=24,
        verbose_name=_("运行间隔（小时）"),
        help_text=_("在24小时内的运行间隔")
    )
    cutoff_hours = models.PositiveIntegerField(
        default=24,
        verbose_name=_("截止时间（小时）"),
        help_text=_("只处理最近N小时内的文书")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("是否启用")
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("上次运行时间")
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("下次运行时间")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = "automation"
        verbose_name = _("文书送达定时任务")
        verbose_name_plural = _("文书送达定时任务")
        indexes = [
            models.Index(fields=["is_active", "next_run_at"]),
            models.Index(fields=["credential"]),
        ]

    def __str__(self):
        return "{} - 每天{}次 - {}".format(
            self.credential, 
            self.runs_per_day,
            "启用" if self.is_active else "禁用"
        )


class CourtSMS(models.Model):
    """法院短信记录"""
    # 原始内容
    content = models.TextField(verbose_name=_("短信内容"))
    received_at = models.DateTimeField(verbose_name=_("收到时间"))
    
    # 解析结果
    sms_type = models.CharField(
        max_length=32,
        choices=CourtSMSType.choices,
        null=True,
        blank=True,
        verbose_name=_("短信类型")
    )
    download_links = models.JSONField(
        default=list,
        verbose_name=_("下载链接列表")
    )
    case_numbers = models.JSONField(
        default=list,
        verbose_name=_("案号列表")
    )
    party_names = models.JSONField(
        default=list,
        verbose_name=_("当事人名称列表")
    )
    
    # 处理状态
    status = models.CharField(
        max_length=32,
        choices=CourtSMSStatus.choices,
        default=CourtSMSStatus.PENDING,
        verbose_name=_("处理状态")
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("错误信息")
    )
    retry_count = models.IntegerField(
        default=0,
        verbose_name=_("重试次数")
    )
    
    # 关联
    scraper_task = models.ForeignKey(
        "ScraperTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_sms_records",
        verbose_name=_("下载任务")
    )
    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_sms_records",
        verbose_name=_("关联案件")
    )
    case_log = models.ForeignKey(
        "cases.CaseLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="court_sms_records",
        verbose_name=_("案件日志")
    )
    
    # 飞书通知
    feishu_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("飞书发送时间")
    )
    feishu_error = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("飞书发送错误")
    )
    
    # 时间戳
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = "automation"
        verbose_name = _("法院短信")
        verbose_name_plural = _("法院短信")
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["status", "-received_at"]),
            models.Index(fields=["sms_type"]),
            models.Index(fields=["case"]),
        ]

    def __str__(self):
        return "短信 #{} - {} - {}".format(
            self.id, 
            self.get_sms_type_display() or "未分类", 
            self.get_status_display()
        )



