"""格式调整详情模型

存储批注和版本管理信息
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from .review_task import ReviewTask


class FormatNormalizeDetail(models.Model):
    """格式调整详情"""

    task = models.OneToOneField(
        ReviewTask,
        on_delete=models.CASCADE,
        related_name='format_detail',
        verbose_name="关联任务"
    )

    # 格式化方法
    FORMAT_METHOD_CHOICES = [
        ('poi', 'POI服务'),
        ('python', 'Python'),
        ('auto', '自动选择'),
    ]
    format_method = models.CharField(
        max_length=20,
        choices=FORMAT_METHOD_CHOICES,
        default='auto',
        verbose_name="格式化方法"
    )

    # 版本信息
    version_number = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="版本号"
    )
    changelog = models.TextField(
        blank=True,
        verbose_name="变更说明"
    )

    # 批注信息（JSON格式）
    annotations = models.JSONField(
        default=list,
        blank=True,
        verbose_name="批注信息"
    )

    # 修改人
    modifier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="修改人"
    )

    # 时间戳
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="创建时间"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="完成时间"
    )

    # 处理日志
    processing_log = models.TextField(
        blank=True,
        verbose_name="处理日志"
    )

    class Meta:
        verbose_name = "格式调整详情"
        verbose_name_plural = "格式调整详情"
        ordering = ['-created_at']

    def __str__(self):
        return f"详情: {self.task.contract_title} ({self.format_method})"

    def add_annotation(self, author: str, content: str):
        """添加批注"""
        annotation = {
            'author': author,
            'content': content,
            'created_at': timezone.now().isoformat()
        }
        if not self.annotations:
            self.annotations = []
        self.annotations.append(annotation)
        self.save(update_fields=['annotations'])

    def mark_completed(self, method_used: str):
        """标记完成"""
        self.completed_at = timezone.now()
        self.processing_log += f"\n完成时间: {self.completed_at}"
        self.processing_log += f"\n使用方法: {method_used}"
        self.save(update_fields=['completed_at', 'processing_log'])

    def mark_failed(self, error_message: str):
        """标记失败"""
        self.completed_at = timezone.now()
        self.processing_log += f"\n失败时间: {self.completed_at}"
        self.processing_log += f"\n错误信息: {error_message}"
        self.save(update_fields=['completed_at', 'processing_log'])
