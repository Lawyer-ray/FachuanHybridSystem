from django.db import models
from django.utils.translation import gettext_lazy as _

# 从 core.enums 导入枚举，保持向后兼容
# 其他模块应直接从 apps.core.enums 导入
from apps.core.enums import (
    CaseType,
    LegalStatus,
    CaseStatus,
    CaseStage,
    AuthorityType,
    SimpleCaseType,
    CaseLogReminderType,
    ChatPlatform,
)

# 重新导出以保持向后兼容
__all__ = [
    "CaseType",
    "LegalStatus",
    "CaseStatus",
    "CaseStage",
    "AuthorityType",
    "SimpleCaseType",
    "CaseLogReminderType",
    "ChatPlatform",
    # Models
    "Case",
    "CaseNumber",
    "SupervisingAuthority",
    "CaseParty",
    "CaseAssignment",
    "CaseAccessGrant",
    "CaseLog",
    "CaseLogAttachment",
    "CaseLogVersion",
    "CaseChat",
    "ChatAuditLog",
]


class Case(models.Model):
    contract = models.ForeignKey("contracts.Contract", on_delete=models.SET_NULL, null=True, blank=True, related_name="cases", verbose_name=_("关联合同"))
    is_archived = models.BooleanField(default=False, verbose_name=_("是否已建档"))
    name = models.CharField(max_length=255, verbose_name=_("案件名称"))
    status = models.CharField(max_length=32, choices=CaseStatus.choices, default=CaseStatus.ACTIVE, verbose_name=_("案件状态"))

    start_date = models.DateField(auto_now_add=True, verbose_name=_("收案日期"))
    effective_date = models.DateField(blank=True, null=True, verbose_name=_("生效日期"))
    cause_of_action = models.CharField(max_length=128, blank=True, null=True, default="合同纠纷", verbose_name=_("案由"))
    target_amount = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True, verbose_name=_("涉案金额"))
    case_type = models.CharField(
        max_length=32,
        choices=SimpleCaseType.choices,
        default=SimpleCaseType.CIVIL,
        blank=True,
        null=True,
        verbose_name=_("案件类型")
    )

    current_stage = models.CharField(max_length=64, choices=CaseStage.choices, blank=True, null=True, verbose_name=_("当前阶段"))

    class Meta:
        verbose_name = _("案件")
        verbose_name_plural = _("案件")
        indexes = [
            models.Index(fields=["contract"]),
            models.Index(fields=["is_archived"]),
            models.Index(fields=["start_date"]),
            models.Index(fields=["current_stage"]),
            models.Index(fields=["-start_date"]),  # 按日期倒序查询优化
        ]

    def __str__(self):
        return f"{self.name}"

    def clean(self):
        """
        基础数据验证
        复杂业务逻辑已移至 CaseService
        """
        from django.core.exceptions import ValidationError

        # 仅做基础验证，复杂的阶段验证在 Service 层处理
        if self.current_stage:
            valid_stages = {c[0] for c in CaseStage.choices}
            if self.current_stage not in valid_stages:
                raise ValidationError({
                    "current_stage": _("无效的案件阶段")
                })


class CaseNumber(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="case_numbers", verbose_name=_("案件"))
    number = models.CharField(max_length=128, verbose_name=_("案号"))
    remarks = models.TextField(blank=True, null=True, verbose_name=_("备注"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("案件案号")
        verbose_name_plural = _("案件案号")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.number}"

    def save(self, *args, **kwargs):
        """保存前格式化案号：统一括号、删除空格"""
        if self.number:
            # 统一括号：英文、六角、中括号 -> 中文括号
            self.number = self.number.replace("(", "（").replace(")", "）")
            self.number = self.number.replace("〔", "（").replace("〕", "）")
            self.number = self.number.replace("[", "（").replace("]", "）")
            # 删除所有空格（包括全角空格）
            self.number = self.number.replace(" ", "").replace("\u3000", "")
        super().save(*args, **kwargs)


class SupervisingAuthority(models.Model):
    """主管机关"""
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name="supervising_authorities",
        verbose_name=_("案件")
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("名称")
    )
    authority_type = models.CharField(
        max_length=32,
        choices=AuthorityType.choices,
        default=AuthorityType.TRIAL,
        blank=True,
        null=True,
        verbose_name=_("性质")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"))

    class Meta:
        verbose_name = _("主管机关")
        verbose_name_plural = _("主管机关")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["case"]),
            models.Index(fields=["authority_type"]),
        ]

    def __str__(self):
        if self.name and self.authority_type:
            return f"{self.get_authority_type_display()} - {self.name}"
        elif self.name:
            return self.name
        elif self.authority_type:
            return self.get_authority_type_display()
        return f"主管机关 #{self.id}"


class CaseParty(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="parties", verbose_name=_("案件"))
    client = models.ForeignKey("client.Client", on_delete=models.CASCADE, related_name="case_parties", verbose_name=_("当事人"))
    legal_status = models.CharField(max_length=32, choices=LegalStatus.choices, blank=True, null=True, verbose_name=_("诉讼地位"))

    class Meta:
        unique_together = ("case", "client")
        verbose_name = _("案件当事人")
        verbose_name_plural = _("案件当事人")

    def __str__(self):
        return f"{self.case_id}-{self.client_id}-{self.legal_status}"


class CaseAssignment(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="assignments", verbose_name=_("案件"))
    lawyer = models.ForeignKey("organization.Lawyer", on_delete=models.CASCADE, related_name="case_assignments", verbose_name=_("律师"))

    class Meta:
        verbose_name = _("案件指派")
        verbose_name_plural = _("案件指派")

    def __str__(self):
        return f"{self.case_id}-{self.lawyer_id}"






class CaseAccessGrant(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="access_grants", verbose_name=_("案件"))
    grantee = models.ForeignKey("organization.Lawyer", on_delete=models.CASCADE, related_name="case_access_grants", verbose_name=_("获授权律师"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("案件访问授权")
        verbose_name_plural = _("案件访问授权")

    def __str__(self):
        return f"{self.case_id}->{self.grantee_id}"



# CaseLogReminderType 已移至 apps.core.enums


def validate_log_attachment(file):
    import os
    name = getattr(file, "name", "")
    ext = os.path.splitext(name)[1].lower()
    allowed = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png"}
    if ext not in allowed:
        from django.core.exceptions import ValidationError
        raise ValidationError(_("不支持的文件类型"))
    size = getattr(file, "size", 0)
    if size and size > 50 * 1024 * 1024:
        from django.core.exceptions import ValidationError
        raise ValidationError(_("文件大小超过50MB限制"))


class CaseLog(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="logs", verbose_name=_("案件"))
    content = models.TextField(verbose_name=_("日志内容"))
    reminder_type = models.CharField(max_length=32, choices=CaseLogReminderType.choices, blank=True, null=True, verbose_name=_("提醒类型"))
    reminder_time = models.DateTimeField(blank=True, null=True, verbose_name=_("提醒时间"))
    actor = models.ForeignKey("organization.Lawyer", on_delete=models.PROTECT, related_name="case_logs", verbose_name=_("操作人"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建日期"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("修改日期"))

    class Meta:
        verbose_name = _("案件日志")
        verbose_name_plural = _("案件日志")
        indexes = [
            models.Index(fields=["case", "-created_at"]),
            models.Index(fields=["reminder_time"]),
            models.Index(fields=["actor"]),
        ]

    def __str__(self):
        return f"{self.case_id}-{self.actor_id}-{self.created_at}"


class CaseLogAttachment(models.Model):
    log = models.ForeignKey(CaseLog, on_delete=models.CASCADE, related_name="attachments", verbose_name=_("日志"))
    file = models.FileField(upload_to="case_logs/", validators=[validate_log_attachment], verbose_name=_("相关文书"))
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name=_("上传时间"))

    class Meta:
        verbose_name = _("案件日志附件")
        verbose_name_plural = _("案件日志附件")


class CaseLogVersion(models.Model):
    log = models.ForeignKey(CaseLog, on_delete=models.CASCADE, related_name="versions", verbose_name=_("日志"))
    content = models.TextField(verbose_name=_("历史内容"))
    version_at = models.DateTimeField(auto_now_add=True, verbose_name=_("版本时间"))
    actor = models.ForeignKey("organization.Lawyer", on_delete=models.PROTECT, related_name="case_log_versions", verbose_name=_("操作者"))

    class Meta:
        verbose_name = _("案件日志版本")
        verbose_name_plural = _("案件日志版本")

    def __str__(self):
        return f"{self.log_id}-{self.version_at}"


class CaseChat(models.Model):
    """案件群聊"""
    case = models.ForeignKey(
        Case, 
        on_delete=models.CASCADE, 
        related_name='chats',
        verbose_name=_('案件')
    )
    platform = models.CharField(
        max_length=32,
        choices=ChatPlatform.choices,
        default=ChatPlatform.FEISHU,
        verbose_name=_('平台')
    )
    chat_id = models.CharField(
        max_length=128,
        verbose_name=_('群聊ID')
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_('群名')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('是否有效')
    )
    
    # 群主相关字段 (Requirements: 1.5, 4.2)
    owner_id = models.CharField(
        max_length=64, 
        null=True, 
        blank=True,
        verbose_name=_("群主ID"),
        help_text=_("飞书用户的open_id或其他平台的用户标识符")
    )
    
    owner_verified = models.BooleanField(
        default=False,
        verbose_name=_("群主已验证"),
        help_text=_("群主设置是否已验证")
    )
    
    owner_verified_at = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name=_("群主验证时间"),
        help_text=_("群主设置验证成功的时间")
    )
    
    creation_audit_log = models.JSONField(
        default=dict,
        verbose_name=_("创建审计日志"),
        help_text=_("群聊创建过程的详细日志，包含群主设置信息")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间')
    )
    
    class Meta:
        verbose_name = _('案件群聊')
        verbose_name_plural = _('案件群聊')
        unique_together = [['case', 'platform', 'chat_id']]
        indexes = [
            models.Index(fields=['case', 'platform']),
            models.Index(fields=['chat_id']),
            models.Index(fields=['is_active']),
            models.Index(fields=['owner_id']),  # 新增群主ID索引
            models.Index(fields=['owner_verified']),  # 新增群主验证状态索引
            models.Index(fields=['owner_verified_at']),  # 新增群主验证时间索引
        ]
    
    def __str__(self):
        return f"[{self.get_platform_display()}] {self.name}"
    
    def get_owner_display(self) -> str:
        """获取群主显示信息
        
        Returns:
            str: 群主显示信息
        """
        if not self.owner_id:
            return _("未设置群主")
        
        status = _("已验证") if self.owner_verified else _("未验证")
        return f"{self.owner_id} ({status})"
    
    def is_owner_verified_recently(self, hours: int = 24) -> bool:
        """检查群主是否在最近时间内验证过
        
        Args:
            hours: 小时数
            
        Returns:
            bool: 是否在最近时间内验证过
        """
        if not self.owner_verified or not self.owner_verified_at:
            return False
        
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        return self.owner_verified_at >= cutoff_time
    
    def get_creation_summary(self) -> str:
        """获取创建摘要信息
        
        Returns:
            str: 创建摘要
        """
        summary_parts = [f"群聊: {self.name}"]
        
        if self.owner_id:
            summary_parts.append(f"群主: {self.owner_id}")
        
        if self.owner_verified:
            summary_parts.append("已验证")
        
        return " | ".join(summary_parts)
    
    def update_owner_verification(self, verified: bool = True, save: bool = True):
        """更新群主验证状态
        
        Args:
            verified: 是否验证成功
            save: 是否立即保存到数据库
        """
        from django.utils import timezone
        
        self.owner_verified = verified
        if verified:
            self.owner_verified_at = timezone.now()
        else:
            self.owner_verified_at = None
        
        if save:
            self.save(update_fields=['owner_verified', 'owner_verified_at', 'updated_at'])
    
    def add_creation_audit_entry(self, action: str, details: dict, save: bool = True):
        """添加创建审计日志条目
        
        Args:
            action: 操作类型
            details: 操作详情
            save: 是否立即保存到数据库
        """
        from django.utils import timezone
        
        if not isinstance(self.creation_audit_log, dict):
            self.creation_audit_log = {}
        
        if 'entries' not in self.creation_audit_log:
            self.creation_audit_log['entries'] = []
        
        entry = {
            'timestamp': timezone.now().isoformat(),
            'action': action,
            'details': details
        }
        
        self.creation_audit_log['entries'].append(entry)
        
        if save:
            self.save(update_fields=['creation_audit_log', 'updated_at'])


class ChatAuditLog(models.Model):
    """群聊审计日志"""
    
    # 操作类型选择
    ACTION_CHOICES = [
        ('CREATE_START', _('开始创建')),
        ('CREATE_SUCCESS', _('创建成功')),
        ('CREATE_FAILED', _('创建失败')),
        ('OWNER_SET', _('设置群主')),
        ('OWNER_VERIFY', _('验证群主')),
        ('OWNER_RETRY', _('重试群主设置')),
        ('OWNER_SET_FAILED', _('群主设置失败')),
        ('CONFIG_ERROR', _('配置错误')),
    ]
    
    chat = models.ForeignKey(
        CaseChat,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True,
        verbose_name=_("关联群聊"),
        help_text=_("关联的群聊，某些操作（如配置错误）可能没有关联群聊")
    )
    
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='chat_audit_logs',
        null=True,
        blank=True,
        verbose_name=_("关联案件"),
        help_text=_("关联的案件")
    )
    
    action = models.CharField(
        max_length=32,
        choices=ACTION_CHOICES,
        verbose_name=_("操作类型"),
        help_text=_("执行的操作类型")
    )
    
    details = models.JSONField(
        default=dict,
        verbose_name=_("操作详情"),
        help_text=_("操作的详细信息，以JSON格式存储")
    )
    
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("时间戳"),
        help_text=_("操作发生的时间")
    )
    
    success = models.BooleanField(
        default=True,
        verbose_name=_("操作成功"),
        help_text=_("操作是否成功执行")
    )
    
    error_message = models.TextField(
        blank=True,
        verbose_name=_("错误信息"),
        help_text=_("操作失败时的错误信息")
    )
    
    # 额外的索引字段，便于查询
    external_chat_id = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("群聊ID"),
        help_text=_("群聊的外部ID，便于查询")
    )
    
    platform = models.CharField(
        max_length=32,
        choices=ChatPlatform.choices,
        default=ChatPlatform.FEISHU,
        verbose_name=_("平台"),
        help_text=_("群聊平台")
    )
    
    # 审计版本，便于后续升级
    audit_version = models.CharField(
        max_length=16,
        default='1.0',
        verbose_name=_("审计版本"),
        help_text=_("审计日志格式版本")
    )
    
    class Meta:
        verbose_name = _('群聊审计日志')
        verbose_name_plural = _('群聊审计日志')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['chat', '-timestamp']),
            models.Index(fields=['case', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['success', '-timestamp']),
            models.Index(fields=['external_chat_id', '-timestamp']),
            models.Index(fields=['platform', '-timestamp']),
            models.Index(fields=['-timestamp']),  # 通用时间索引
        ]
    
    def __str__(self):
        chat_info = f"Chat:{self.external_chat_id}" if self.external_chat_id else f"ChatModel:{self.chat_id}"
        case_info = f"Case:{self.case_id}" if self.case_id else "NoCase"
        status = "SUCCESS" if self.success else "FAILED"
        return f"[{self.get_action_display()}] {chat_info} | {case_info} | {status}"
    
    def get_formatted_details(self) -> str:
        """获取格式化的详情信息
        
        Returns:
            str: 格式化的JSON字符串
        """
        import json
        try:
            return json.dumps(self.details, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(self.details)
    
    def get_summary(self) -> str:
        """获取操作摘要
        
        Returns:
            str: 操作摘要信息
        """
        summary_parts = [self.get_action_display()]
        
        if self.external_chat_id:
            summary_parts.append(f"群聊:{self.external_chat_id}")
        
        if self.case_id:
            summary_parts.append(f"案件:{self.case_id}")
        
        if not self.success and self.error_message:
            summary_parts.append(f"错误:{self.error_message[:50]}...")
        
        return " | ".join(summary_parts)
    
    def is_recent(self, hours: int = 24) -> bool:
        """检查是否为最近的日志
        
        Args:
            hours: 小时数
            
        Returns:
            bool: 是否为最近的日志
        """
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        return self.timestamp >= cutoff_time
