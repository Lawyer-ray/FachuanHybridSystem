"""劳动仲裁文书来源（各地市/区列表页）模型。"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models

logger = logging.getLogger(__name__)


class District(models.TextChoices):
    """佛山各区县。"""

    SHI_ZHI = "shizhi", "佛山市直"
    SHUN_DE = "shunde", "顺德区"
    CHAN_CHENG = "chancheng", "禅城区"
    NAN_HAI = "nanhai", "南海区"
    SAN_SHUI = "sanshui", "三水区"
    GAO_MING = "gaoming", "高明区"


class ParseBackend(models.TextChoices):
    """文档解析后端。"""

    LOCAL = "local", "本地 OCR (PyMuPDF)"
    MINERU = "mineru", "MinerU (云端)"
    TEXTIN = "textin", "TextIn (云端)"
    AUTO = "auto", "自动"


class CrawlStatus(models.TextChoices):
    """来源爬取状态。"""

    IDLE = "idle", "未爬取"
    RUNNING = "running", "爬取中"
    SUCCESS = "success", "成功"
    FAILED = "failed", "失败"


class ArbitrationDocumentSource(models.Model):
    """仲裁文书来源：佛山市人社局各区的仲裁裁决书公开列表页。"""

    id: int
    name = models.CharField("名称", max_length=128)
    district = models.CharField("区县", max_length=32, choices=District.choices, default=District.SHI_ZHI)
    list_url = models.URLField("列表页 URL", max_length=512, unique=True)
    enabled = models.BooleanField("启用", default=True)
    parse_backend = models.CharField(
        "解析后端", max_length=16, choices=ParseBackend.choices, default=ParseBackend.LOCAL
    )
    max_pages = models.PositiveIntegerField("最大翻页数", default=5, help_text="单次更新最多翻几页列表")
    # 选择器（可配置，空则使用默认启发式探测）
    detail_image_container_selector = models.CharField(
        "详情图容器选择器",
        max_length=256,
        blank=True,
        default="",
        help_text="如 #content / .article；留空则自动探测内容容器",
    )
    detail_image_selector = models.CharField(
        "详情图片选择器",
        max_length=256,
        blank=True,
        default="img",
        help_text="容器内匹配图片的 CSS 选择器",
    )
    last_crawl_at = models.DateTimeField("上次爬取时间", null=True, blank=True)
    last_crawl_status = models.CharField(
        "上次爬取状态",
        max_length=16,
        choices=CrawlStatus.choices,
        default=CrawlStatus.IDLE,
    )
    last_crawl_summary = models.JSONField("上次爬取摘要", null=True, blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "labor_arbitration"
        verbose_name = "仲裁文书来源"
        verbose_name_plural = "仲裁文书来源"
        ordering: ClassVar = ["district", "id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_district_display()})"

    def trigger_update(self, limit: int | None = None) -> str | None:
        """提交增量爬取任务到后台队列，返回任务 ID。

        若该来源已在爬取/排队中（last_crawl_status == RUNNING）则返回 None，防止
        重复提交导致同一 detail_url 并发插入冲突。
        """
        from apps.core.tasking import submit_task

        if self.last_crawl_status == CrawlStatus.RUNNING:
            logger.info("[劳动仲裁] 来源 %s 已在爬取中，跳过重复提交", self.id)
            return None

        task_id = submit_task(
            "apps.labor_arbitration.tasks.crawl_source",
            self.id,
            limit,
            task_name=f"labor_crawl_{self.id}",
            timeout=1800,
        )
        self.last_crawl_status = CrawlStatus.RUNNING
        self.save(update_fields=["last_crawl_status"])
        return task_id
