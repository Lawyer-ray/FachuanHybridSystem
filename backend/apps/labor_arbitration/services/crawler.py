"""佛山劳动仲裁文书爬虫（纯 HTTP，无浏览器）。

设计要点：
- 列表：调 ``postmeta/i/{category_id}.json`` 接口，一次返回全部文章（title/url/date/publish_time），
  无需 cookie、无需翻页、无需浏览器，比 Playwright 快数个量级。
- 详情：``requests`` 抓详情页 HTML，用正则提取扫描件图片 URL（``img/.../post_N.png``），
  **不下载图片**，只保存原图 URL（供后续 OCR 按需拉取）。
- 增量：已存在 ``detail_url`` 且 success 且有图片则跳过；failed / 无图记录则重试。
- 容错：列表接口 / 详情页请求均带有限重试；失败标记 failed，由增量 / 重试按钮兜底。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

import requests
from django.db import IntegrityError
from django.utils import timezone

from apps.labor_arbitration.models import ArbitrationDocument, ArbitrationDocumentImage, ArbitrationDocumentSource

logger = logging.getLogger(__name__)

_LIST_API = "https://hrss.foshan.gov.cn/postmeta/i/{category_id}.json"
# 真实文书扫描件图：https://hrss.foshan.gov.cn/img/0/402/402072/5218478.png
_IMG_URL_RE = re.compile(r"https://hrss\.foshan\.gov\.cn/img/\d+/\d+/\d+/\d+\.(?:png|jpe?g)", re.IGNORECASE)
_PUBLISH_RE = re.compile(r"发布(?:时间|日期)[:：]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})(?:\s*(\d{1,2}[:：]\d{1,2}))?")
_CASE_NO_RE = re.compile(r"([一-龥]{1,2}劳人仲案字〔\d+〕\d+(?:-\d+)?号)")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "*/*",
}

_RETRY_TIMES = 3
_RETRY_SLEEP = 2  # 秒


class FoshanLaborAwardCrawler:
    """佛山市人社局仲裁裁决书爬虫（HTTP 版）。"""

    def __init__(self, source: ArbitrationDocumentSource, *, limit: int | None = None) -> None:
        self.source = source
        self.limit = limit
        self.stats: dict[str, int] = {
            "discovered": 0,
            "new": 0,
            "skipped": 0,
            "failed": 0,
            "images": 0,
        }
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

    # ── 公共入口 ──────────────────────────────────────────────
    def crawl(self) -> dict[str, int]:
        """调列表接口拿全部文章，逐篇抓详情页图片 URL，增量入库。"""
        articles = self._fetch_articles()
        self.stats["discovered"] = len(articles)
        for art in articles:
            if self._reached_limit():
                break
            self._handle_article(art)
        return self.stats

    def recrawl_detail(self, doc: ArbitrationDocument) -> ArbitrationDocument:
        """重试抓取单篇文书的详情页（更新已有记录，供「重试」按钮调用）。"""
        art = {"url": doc.detail_url, "title": doc.title}
        self._crawl_detail(art, existing=doc)
        return doc

    def _reached_limit(self) -> bool:
        if self.limit is None:
            return False
        return (self.stats["new"] + self.stats["skipped"]) >= self.limit

    # ── HTTP 请求（带重试）───────────────────────────────────
    def _get(self, url: str, *, referer: str | None = None) -> requests.Response:
        headers: dict[str, str] = {}
        if referer:
            headers["Referer"] = referer
        last_exc: Exception | None = None
        for i in range(_RETRY_TIMES):
            try:
                resp = self.session.get(url, timeout=60, headers=headers)
                if resp.status_code == 403:
                    # 可能限流，稍等重试
                    time.sleep(_RETRY_SLEEP)
                    continue
                resp.raise_for_status()
                return resp
            except Exception as exc:
                last_exc = exc
                if i < _RETRY_TIMES - 1:
                    time.sleep(_RETRY_SLEEP)
        assert last_exc is not None
        raise last_exc

    # ── 列表 ──────────────────────────────────────────────────
    def _fetch_articles(self) -> list[dict[str, Any]]:
        if not self.source.category_id:
            raise RuntimeError("来源未配置 category_id，无法用接口抓取")
        url = _LIST_API.format(category_id=self.source.category_id)
        data = self._get(url, referer=self.source.list_url).json()
        articles = data.get("articles", [])
        logger.info("[劳动仲裁] 来源 %s 接口返回 %d 篇文章", self.source.id, len(articles))
        return articles

    # ── 单条处理 ──────────────────────────────────────────────
    def _handle_article(self, art: dict[str, Any]) -> None:
        detail_url = art.get("url") or ""
        if not detail_url:
            return
        existing = ArbitrationDocument.objects.filter(detail_url=detail_url).first()
        if existing is not None and existing.crawl_status == "success" and existing.images.exists():
            self.stats["skipped"] += 1
            return
        # 不存在 / failed / 有记录无图：都走抓取（重试）
        try:
            self._crawl_detail(art, existing=existing)
            self.stats["new"] += 1
        except IntegrityError:
            self.stats["skipped"] += 1
        except Exception as exc:
            logger.error("[劳动仲裁] 抓取详情失败 %s: %s", detail_url, exc, exc_info=True)
            self.stats["failed"] += 1
            self._mark_failed(art, existing, str(exc)[:2000])

    def _mark_failed(self, art: dict[str, Any], existing: ArbitrationDocument | None, error_message: str) -> None:
        if existing is not None:
            existing.crawl_status = "failed"
            existing.error_message = error_message
            existing.save(update_fields=["crawl_status", "error_message"])
            return
        try:
            ArbitrationDocument.objects.create(
                source=self.source,
                title=art.get("title", ""),
                detail_url=art.get("url", ""),
                publish_date=self._parse_date_only(art),
                crawl_status="failed",
                error_message=error_message,
            )
        except IntegrityError:
            pass

    def _crawl_detail(self, art: dict[str, Any], existing: ArbitrationDocument | None = None) -> ArbitrationDocument:
        detail_url = art["url"]
        html = self._get(detail_url, referer=self.source.list_url).text

        img_urls = _IMG_URL_RE.findall(html)
        img_urls = list(dict.fromkeys(img_urls))  # 去重保序
        if not img_urls:
            raise RuntimeError("详情页未找到图片")

        publish_date, publish_datetime = self._parse_publish(html, art)
        title = art.get("title") or (existing.title if existing else "")

        if existing is not None:
            existing.title = title
            existing.case_number = self._parse_case_number(title)
            existing.publish_date = publish_date or existing.publish_date
            existing.publish_datetime = publish_datetime or existing.publish_datetime
            existing.crawl_status = "success"
            existing.error_message = ""
            existing.save(
                update_fields=[
                    "title",
                    "case_number",
                    "publish_date",
                    "publish_datetime",
                    "crawl_status",
                    "error_message",
                ]
            )
            existing.images.all().delete()
            doc = existing
        else:
            doc = ArbitrationDocument.objects.create(
                source=self.source,
                title=title,
                case_number=self._parse_case_number(title),
                detail_url=detail_url,
                publish_date=publish_date,
                publish_datetime=publish_datetime,
                crawl_status="success",
            )

        # 只保存图片 URL，不下载到本地
        for idx, img_url in enumerate(img_urls):
            ArbitrationDocumentImage.objects.create(document=doc, page_index=idx, source_url=img_url)
        self.stats["images"] += len(img_urls)
        return doc

    # ── 解析辅助 ──────────────────────────────────────────────
    def _parse_publish(self, html: str, art: dict[str, Any]) -> tuple[Any, Any]:
        """返回 (date, datetime)，优先详情页正文 meta，其次列表接口字段。"""
        m = _PUBLISH_RE.search(html)
        if m:
            date_str = m.group(1).replace("/", "-")
            time_str = (m.group(2) or "").replace("：", ":")
            try:
                if time_str:
                    dt = timezone.make_aware(datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M"))
                else:
                    dt = timezone.make_aware(datetime.strptime(date_str, "%Y-%m-%d"))
                return dt.date(), dt
            except ValueError:
                pass
        publish_time = art.get("publish_time")
        if publish_time:
            try:
                dt = datetime.fromtimestamp(int(publish_time), tz=timezone.get_current_timezone())
                return dt.date(), dt
            except (ValueError, OSError, OverflowError):
                pass
        date_str = art.get("date")
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date(), None
            except ValueError:
                pass
        return None, None

    def _parse_date_only(self, art: dict[str, Any]) -> Any:
        date_str = art.get("date")
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_case_number(title: str) -> str:
        m = _CASE_NO_RE.search(title or "")
        return m.group(1) if m else ""
