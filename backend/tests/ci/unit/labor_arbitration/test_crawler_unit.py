"""FoshanLaborAwardCrawler 单元测试 — 解析辅助、增量调度与详情抓取（HTTP 全 mock）。

禁止真实网络：``_get`` / ``session`` 一律 mock。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.utils import timezone

from apps.labor_arbitration.models import (
    ArbitrationDocument,
    ArbitrationDocumentImage,
    ArbitrationDocumentSource,
    CrawlStatus,
    DocumentCrawlStatus,
)
from apps.labor_arbitration.services.crawler import _IMG_URL_RE, FoshanLaborAwardCrawler, _response_text

DETAIL_HTML = (
    "<html><body>"
    "发布时间：2026-03-15 10:30"
    '<img src="https://hrss.foshan.gov.cn/img/0/402/402072/5218478.png"/>'
    '<img src="https://hrss.foshan.gov.cn/img/0/402/402072/5218479.png"/>'
    "</body></html>"
)


@pytest.fixture
def source(db: Any) -> ArbitrationDocumentSource:
    return ArbitrationDocumentSource.objects.create(
        name="测试来源",
        list_url="https://example.com/list-1",
        category_id=123,
        parse_backend="local",
    )


@pytest.fixture
def doc(source: ArbitrationDocumentSource) -> ArbitrationDocument:
    return ArbitrationDocument.objects.create(source=source, title="文书", detail_url="https://example.com/d/1")


def _source(**kwargs: Any) -> ArbitrationDocumentSource:
    defaults: dict[str, Any] = {
        "name": "市直来源",
        "list_url": "https://hrss.foshan.gov.cn/list-1",
        "category_id": 123,
    }
    defaults.update(kwargs)
    return ArbitrationDocumentSource(**defaults)


def _crawler(source: ArbitrationDocumentSource, limit: int | None = None) -> FoshanLaborAwardCrawler:
    crawler = FoshanLaborAwardCrawler(source, limit=limit)
    return crawler


class TestImgUrlRegex:
    def test_matches_real_scan_urls(self) -> None:
        html = '<img src="https://hrss.foshan.gov.cn/img/0/402/402072/5218478.png">'
        assert _IMG_URL_RE.findall(html) == ["https://hrss.foshan.gov.cn/img/0/402/402072/5218478.png"]

    def test_matches_jpg_case_insensitive(self) -> None:
        html = "https://hrss.foshan.gov.cn/img/1/2/3/4.JPG"
        assert _IMG_URL_RE.findall(html) == ["https://hrss.foshan.gov.cn/img/1/2/3/4.JPG"]

    def test_other_hosts_ignored(self) -> None:
        assert _IMG_URL_RE.findall("https://evil.com/img/0/402/402072/1.png") == []


class TestResponseText:
    def test_charset_header_uses_response_text(self) -> None:
        resp = httpx.Response(200, text="中文内容", headers={"Content-Type": "text/html; charset=utf-8"})
        assert _response_text(resp) == "中文内容"

    def test_no_charset_uses_normalizer(self) -> None:
        content = "中文检测".encode()
        resp = httpx.Response(200, content=content, headers={"Content-Type": "text/html"})
        assert resp.charset_encoding is None

        class _Best:
            def __str__(self) -> str:
                return "中文检测"

        best = _Best()
        with patch("charset_normalizer.from_bytes", return_value=SimpleNamespace(best=lambda: best)) as m_fb:
            assert _response_text(resp) == "中文检测"
        m_fb.assert_called_once()

    def test_normalizer_no_best_falls_back(self) -> None:
        content = b"abc"
        resp = httpx.Response(200, content=content, headers={"Content-Type": "text/html"})
        with patch("charset_normalizer.from_bytes", return_value=SimpleNamespace(best=lambda: None)):
            assert _response_text(resp) == "abc"

    def test_normalizer_import_error_falls_back(self) -> None:
        import builtins

        resp = httpx.Response(200, content=b"raw", headers={"Content-Type": "text/html"})
        real_import = builtins.__import__

        def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "charset_normalizer":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_fake_import):
            assert _response_text(resp) == "raw"


class TestParseCaseNumber:
    def test_full_width_brackets(self) -> None:
        assert FoshanLaborAwardCrawler._parse_case_number("佛劳人仲案字〔2024〕1号") == "佛劳人仲案字〔2024〕1号"

    def test_half_width_and_suffix(self) -> None:
        assert FoshanLaborAwardCrawler._parse_case_number("顺劳人仲案字[2023]12号裁决书") == "顺劳人仲案字[2023]12号"

    def test_no_match_returns_empty(self) -> None:
        assert FoshanLaborAwardCrawler._parse_case_number("普通标题无案号") == ""
        assert FoshanLaborAwardCrawler._parse_case_number("") == ""

    def test_multi_numbers_takes_first(self) -> None:
        title = "佛劳人仲案字〔2024〕1号、佛劳人仲案字〔2024〕2号裁决书"
        assert FoshanLaborAwardCrawler._parse_case_number(title) == "佛劳人仲案字〔2024〕1号"


class TestParsePublish:
    def test_html_meta_with_time(self) -> None:
        crawler = _crawler(_source())
        d, dt = crawler._parse_publish(DETAIL_HTML, {})
        assert d == date(2026, 3, 15)
        assert dt is not None and dt.hour == 10 and dt.minute == 30
        assert timezone.is_aware(dt)

    def test_html_meta_date_only(self) -> None:
        crawler = _crawler(_source())
        d, dt = crawler._parse_publish("发布日期：2025/12/01", {})
        assert d == date(2025, 12, 1)
        assert dt is not None and dt.hour == 0

    def test_invalid_html_falls_to_publish_time(self) -> None:
        crawler = _crawler(_source())
        d, dt = crawler._parse_publish("发布时间：bad", {"publish_time": 1770000000})
        assert d is not None and dt is not None

    def test_publish_time_timestamp(self) -> None:
        crawler = _crawler(_source())
        ts = 1742015400  # 2026-03-15 依服务器时区换算
        d, dt = crawler._parse_publish("无meta", {"publish_time": ts})
        assert dt is not None
        assert dt.timestamp() == pytest.approx(ts, abs=5)

    def test_date_field_only(self) -> None:
        crawler = _crawler(_source())
        d, dt = crawler._parse_publish("无meta", {"date": "2024-06-01"})
        assert d == date(2024, 6, 1)
        assert dt is None

    def test_nothing_available(self) -> None:
        crawler = _crawler(_source())
        assert crawler._parse_publish("无meta", {}) == (None, None)

    def test_bad_date_string_ignored(self) -> None:
        crawler = _crawler(_source())
        assert crawler._parse_publish("无meta", {"date": "not-a-date"}) == (None, None)


class TestParseDateOnly:
    def test_valid(self) -> None:
        assert _crawler(_source())._parse_date_only({"date": "2024-01-02"}) == date(2024, 1, 2)

    def test_invalid_or_missing(self) -> None:
        crawler = _crawler(_source())
        assert crawler._parse_date_only({"date": "xx"}) is None
        assert crawler._parse_date_only({}) is None


class TestReachedLimit:
    def test_no_limit(self) -> None:
        crawler = _crawler(_source())
        assert crawler._reached_limit() is False

    def test_limit_reached_by_new_plus_skipped(self) -> None:
        crawler = _crawler(_source(), limit=2)
        crawler.stats["new"] = 1
        crawler.stats["skipped"] = 1
        assert crawler._reached_limit() is True

    def test_below_limit(self) -> None:
        crawler = _crawler(_source(), limit=5)
        crawler.stats["new"] = 2
        assert crawler._reached_limit() is False


class TestFetchArticles:
    def test_missing_category_id_raises(self) -> None:
        crawler = _crawler(_source(category_id=None))
        with pytest.raises(RuntimeError, match="category_id"):
            crawler._fetch_articles()

    def test_parses_articles_from_list_api(self) -> None:
        crawler = _crawler(_source(category_id=77))
        resp = MagicMock()
        resp.json.return_value = {
            "articles": [{"url": "https://x/1", "title": "A"}, {"url": "https://x/2", "title": "B"}]
        }
        with patch.object(crawler, "_get", return_value=resp) as m_get:
            articles = crawler._fetch_articles()
        assert len(articles) == 2
        m_get.assert_called_once_with(
            "https://hrss.foshan.gov.cn/postmeta/i/77.json", referer="https://hrss.foshan.gov.cn/list-1"
        )


class TestCrawlScheduling:
    def test_crawl_iterates_and_counts_discovered(self) -> None:
        crawler = _crawler(_source())
        articles = [{"url": f"https://x/{i}"} for i in range(3)]
        with (
            patch.object(crawler, "_fetch_articles", return_value=articles),
            patch.object(crawler, "_handle_article") as m_handle,
        ):
            stats = crawler.crawl()
        assert stats["discovered"] == 3
        assert m_handle.call_count == 3

    def test_crawl_stops_at_limit(self) -> None:
        crawler = _crawler(_source(), limit=1)
        crawler.stats["new"] = 1
        with patch.object(crawler, "_fetch_articles", return_value=[{"url": "https://x/1"}, {"url": "https://x/2"}]):
            with patch.object(crawler, "_handle_article") as m_handle:
                stats = crawler.crawl()
        assert m_handle.call_count == 0
        assert stats["discovered"] == 2


@pytest.mark.django_db
class TestHandleArticle:
    def test_missing_url_skipped(self) -> None:
        crawler = _crawler(_source())
        crawler._handle_article({"title": "no url"})
        assert crawler.stats == {"discovered": 0, "new": 0, "skipped": 0, "failed": 0, "images": 0}

    def test_existing_success_with_images_skipped(
        self, source: ArbitrationDocumentSource, doc: ArbitrationDocument
    ) -> None:
        doc.crawl_status = DocumentCrawlStatus.SUCCESS
        doc.save(update_fields=["crawl_status"])
        ArbitrationDocumentImage.objects.create(document=doc, page_index=0, source_url="https://x/1.png")
        crawler = _crawler(source)
        with patch.object(crawler, "_crawl_detail") as m_detail:
            crawler._handle_article({"url": doc.detail_url, "title": doc.title})
        m_detail.assert_not_called()
        assert crawler.stats["skipped"] == 1

    def test_failed_existing_retried(self, source: ArbitrationDocumentSource) -> None:
        doc = ArbitrationDocument.objects.create(
            source=source, title="失败文书", detail_url="https://x/f", crawl_status=DocumentCrawlStatus.FAILED
        )
        crawler = _crawler(source)
        with patch.object(crawler, "_crawl_detail") as m_detail:
            crawler._handle_article({"url": doc.detail_url, "title": doc.title})
        m_detail.assert_called_once()
        assert crawler.stats["new"] == 1

    def test_integrity_error_counted_skipped(self, source: ArbitrationDocumentSource) -> None:
        from django.db import IntegrityError

        crawler = _crawler(source)
        with patch.object(crawler, "_crawl_detail", side_effect=IntegrityError("dup")):
            crawler._handle_article({"url": "https://x/9", "title": "T"})
        assert crawler.stats["skipped"] == 1
        assert crawler.stats["failed"] == 0

    def test_generic_failure_marks_failed_record(self, source: ArbitrationDocumentSource) -> None:
        crawler = _crawler(source)
        with patch.object(crawler, "_crawl_detail", side_effect=RuntimeError("详情页 404")):
            crawler._handle_article({"url": "https://x/e1", "title": "Err", "date": "2026-01-01"})
        assert crawler.stats["failed"] == 1
        failed = ArbitrationDocument.objects.get(detail_url="https://x/e1")
        assert failed.crawl_status == DocumentCrawlStatus.FAILED
        assert "详情页 404" in failed.error_message
        assert failed.publish_date == date(2026, 1, 1)


@pytest.mark.django_db
class TestCrawlDetail:
    def _run(
        self,
        source: ArbitrationDocumentSource,
        html: str,
        art: dict[str, Any],
        existing: ArbitrationDocument | None = None,
    ) -> tuple[FoshanLaborAwardCrawler, ArbitrationDocument]:
        crawler = _crawler(source)
        resp = httpx.Response(200, text=html, headers={"Content-Type": "text/html; charset=utf-8"})
        with patch.object(crawler, "_get", return_value=resp):
            doc = crawler._crawl_detail(art, existing=existing)
        return crawler, doc

    def test_new_document_with_images(self, source: ArbitrationDocumentSource) -> None:
        crawler, doc = self._run(
            source,
            DETAIL_HTML,
            {"url": "https://x/d1", "title": "佛劳人仲案字〔2024〕1号裁决书"},
        )
        assert doc.crawl_status == DocumentCrawlStatus.SUCCESS
        assert doc.case_number == "佛劳人仲案字〔2024〕1号"
        assert doc.publish_date == date(2026, 3, 15)
        assert doc.images.count() == 2
        assert [img.page_index for img in doc.images.order_by("page_index")] == [0, 1]
        assert crawler.stats["images"] == 2

    def test_no_images_raises(self, source: ArbitrationDocumentSource) -> None:
        crawler = _crawler(source)
        resp = httpx.Response(200, text="<html></html>", headers={"Content-Type": "text/html; charset=utf-8"})
        with patch.object(crawler, "_get", return_value=resp):
            with pytest.raises(RuntimeError, match="未找到图片"):
                crawler._crawl_detail({"url": "https://x/none", "title": "T"})

    def test_duplicate_images_deduped(self, source: ArbitrationDocumentSource) -> None:
        html = (
            '<img src="https://hrss.foshan.gov.cn/img/0/1/2/3.png"/>'
            '<img src="https://hrss.foshan.gov.cn/img/0/1/2/3.png"/>'
        )
        crawler, doc = self._run(source, html, {"url": "https://x/dup", "title": "T"})
        assert doc.images.count() == 1

    def test_existing_document_updated_and_images_replaced(
        self, source: ArbitrationDocumentSource, doc: ArbitrationDocument
    ) -> None:
        ArbitrationDocumentImage.objects.create(document=doc, page_index=0, source_url="https://old/1.png")
        doc.crawl_status = DocumentCrawlStatus.FAILED
        doc.error_message = "上次失败"
        doc.save(update_fields=["crawl_status", "error_message"])

        crawler, updated = self._run(
            source,
            DETAIL_HTML.replace("5218478", "5219999"),
            {"url": doc.detail_url, "title": "新标题 佛劳人仲案字〔2025〕7号"},
            existing=doc,
        )

        assert updated.pk == doc.pk
        assert updated.title == "新标题 佛劳人仲案字〔2025〕7号"
        assert updated.crawl_status == DocumentCrawlStatus.SUCCESS
        assert updated.error_message == ""
        assert updated.case_number == "佛劳人仲案字〔2025〕7号"
        urls = list(updated.images.values_list("source_url", flat=True))
        assert urls == [
            "https://hrss.foshan.gov.cn/img/0/402/402072/5219999.png",
            "https://hrss.foshan.gov.cn/img/0/402/402072/5218479.png",
        ]


@pytest.mark.django_db
class TestMarkFailed:
    def test_existing_marked_failed(self, source: ArbitrationDocumentSource, doc: ArbitrationDocument) -> None:
        crawler = _crawler(source)
        crawler._mark_failed({"url": doc.detail_url}, doc, "boom")
        doc.refresh_from_db()
        assert doc.crawl_status == DocumentCrawlStatus.FAILED
        assert doc.error_message == "boom"

    def test_new_failed_record_created(self, source: ArbitrationDocumentSource) -> None:
        crawler = _crawler(source)
        crawler._mark_failed({"url": "https://x/nf", "title": "T"}, None, "boom")
        assert ArbitrationDocument.objects.filter(detail_url="https://x/nf", crawl_status="failed").exists()

    def test_integrity_error_swallowed(self, source: ArbitrationDocumentSource) -> None:
        from django.db import IntegrityError

        crawler = _crawler(source)
        with patch(
            "apps.labor_arbitration.services.crawler.ArbitrationDocument.objects.create",
            side_effect=IntegrityError("race"),
        ):
            crawler._mark_failed({"url": "https://x/race", "title": "T"}, None, "boom")  # 不抛异常
        # 并发冲突时不再补写失败记录
        assert not ArbitrationDocument.objects.filter(detail_url="https://x/race").exists()


@pytest.mark.django_db
class TestRecrawlDetail:
    def test_recrawl_updates_existing(self, source: ArbitrationDocumentSource, doc: ArbitrationDocument) -> None:
        crawler = _crawler(source)
        with patch.object(crawler, "_crawl_detail") as m_detail:
            result = crawler.recrawl_detail(doc)
        m_detail.assert_called_once_with({"url": doc.detail_url, "title": doc.title}, existing=doc)
        assert result is doc
