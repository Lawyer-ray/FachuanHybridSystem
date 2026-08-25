"""仲裁文书及其图片模型。"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models

from apps.core.filesystem.upload_paths import DatedUUIDPath, MediaEntity

logger = logging.getLogger(__name__)


class DocumentCrawlStatus(models.TextChoices):
    """文书爬取状态。"""

    PENDING = "pending", "待爬取"
    CRAWLING = "crawling", "爬取中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class ParseStatus(models.TextChoices):
    """文书解析状态。"""

    PENDING = "pending", "待解析"
    PROCESSING = "processing", "解析中"
    DONE = "done", "已完成"
    FAILED = "failed", "失败"


class ArbitrationDocument(models.Model):
    """单篇仲裁文书（一条列表项 = 一篇裁决书，含若干图片页）。"""

    id: int
    source = models.ForeignKey(
        "labor_arbitration.ArbitrationDocumentSource",
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="来源",
    )
    title = models.CharField("标题", max_length=512)
    case_number = models.CharField("案号", max_length=128, blank=True, default="")
    detail_url = models.URLField("详情页 URL", max_length=1024, unique=True)
    publish_date = models.DateField("发布日期", null=True, blank=True)
    publish_datetime = models.DateTimeField("发布时间", null=True, blank=True)
    content_hash = models.CharField(
        "内容指纹",
        max_length=64,
        blank=True,
        default="",
        help_text="详情页 HTML 指纹，用于变更探测",
    )
    crawl_status = models.CharField(
        "爬取状态",
        max_length=16,
        choices=DocumentCrawlStatus.choices,
        default=DocumentCrawlStatus.PENDING,
    )
    error_message = models.TextField("错误信息", blank=True, default="")
    # 解析相关
    parse_status = models.CharField(
        "解析状态",
        max_length=16,
        choices=ParseStatus.choices,
        default=ParseStatus.PENDING,
    )
    parse_backend = models.CharField("解析后端", max_length=16, blank=True, default="")
    parsed_text = models.TextField("解析文本", blank=True, default="")
    parsed_markdown = models.TextField("解析 Markdown", blank=True, default="")
    parse_error = models.TextField("解析错误", blank=True, default="")
    parsed_at = models.DateTimeField("解析时间", null=True, blank=True)
    # PostgreSQL 全文搜索向量（中文用 simple 配置）
    search_vector = SearchVectorField("全文搜索向量", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "labor_arbitration"
        verbose_name = "仲裁文书"
        verbose_name_plural = "仲裁文书"
        ordering: ClassVar = ["-publish_datetime", "-publish_date", "-id"]
        indexes: ClassVar = [
            models.Index(fields=["source", "crawl_status"]),
            models.Index(fields=["case_number"]),
            models.Index(fields=["parse_status"]),
            models.Index(fields=["-publish_datetime"]),
            models.Index(fields=["-publish_date"]),
            GinIndex(fields=["search_vector"], name="labor_doc_search_gin"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        super().save(*args, **kwargs)
        # 若 parsed_text 有值但 search_vector 为空，或刚刚更新了 parsed_text，则回填搜索向量
        if self.parsed_text and (
            not self.search_vector or (update_fields is not None and "parsed_text" in update_fields)
        ):
            # 使用数据库端函数构建搜索向量，保证一致
            ArbitrationDocument.objects.filter(pk=self.pk).update(
                search_vector=SearchVector("parsed_text", config="simple")
            )

    def trigger_parse(self, backend: str | None = None) -> str:
        """提交文档解析任务，返回任务 ID。"""
        from apps.core.tasking import submit_task

        task_id = submit_task(
            "apps.labor_arbitration.tasks.parse_document",
            self.id,
            backend,
            task_name=f"labor_parse_{self.id}",
            timeout=600,
        )
        self.parse_status = ParseStatus.PROCESSING
        self.save(update_fields=["parse_status"])
        return task_id

    def trigger_recrawl(self) -> str:
        """提交「重试抓取图片」任务，返回任务 ID。"""
        from apps.core.tasking import submit_task

        task_id = submit_task(
            "apps.labor_arbitration.tasks.recrawl_document",
            self.id,
            task_name=f"labor_recrawl_{self.id}",
            timeout=600,
        )
        self.crawl_status = DocumentCrawlStatus.CRAWLING
        self.save(update_fields=["crawl_status"])
        return task_id


class ArbitrationDocumentImage(models.Model):
    """仲裁文书的单个图片页（扫描件）。"""

    id: int
    document = models.ForeignKey(
        ArbitrationDocument,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="文书",
    )
    # 不再下载图片到本地，只保存原图 URL（source_url），供后续 OCR 按需拉取
    image = models.FileField("图片", upload_to=DatedUUIDPath(MediaEntity.LABOR_ARBITRATION_DOCS), null=True, blank=True)
    page_index = models.PositiveIntegerField("页码", default=0)
    source_url = models.URLField("原图 URL", max_length=1024, blank=True, default="")
    file_size = models.BigIntegerField("文件大小(字节)", null=True, blank=True)
    width = models.PositiveIntegerField("宽", null=True, blank=True)
    height = models.PositiveIntegerField("高", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "labor_arbitration"
        verbose_name = "文书图片"
        verbose_name_plural = "文书图片"
        ordering: ClassVar = ["document", "page_index"]
        indexes: ClassVar = [models.Index(fields=["document", "page_index"])]

    def __str__(self) -> str:
        return f"图片#{self.page_index} - {self.source_url[-40:]}"
