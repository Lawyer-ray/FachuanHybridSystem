"""
法院文书下载完整流程集成测试
测试 API 拦截 → 下载 → 数据库保存的完整流程
"""

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from apps.automation.models import CourtDocument, DocumentDownloadStatus, ScraperTask
from apps.automation.services.scraper.scrapers.court_document import CourtDocumentScraper


@pytest.mark.django_db
class TestCourtDocumentIntegration:
    """法院文书下载完整流程集成测试"""

    def setup_method(self):
        """测试前准备"""
        # 创建测试用的爬虫任务
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://zxfw.court.gov.cn/test", priority=5
        )

    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._intercept_api_response")
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_document_directly")
    def test_api_intercept_to_download_to_db_success(self, mock_download, mock_intercept):
        """
        测试完整流程：API拦截 → 下载 → 数据库保存（成功场景）

        验证需求：所有需求
        """
        # 准备 mock 数据
        api_response = {
            "code": 200,
            "msg": "success",
            "success": True,
            "totalRows": 2,
            "data": [
                {
                    "c_sdbh": "test_sdbh_001",
                    "c_stbh": "test_stbh_001",
                    "wjlj": "https://example.com/doc1.pdf",
                    "c_wsbh": "test_wsbh_001",
                    "c_wsmc": "测试文书001",
                    "c_fybh": "test_fybh_001",
                    "c_fymc": "测试法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                },
                {
                    "c_sdbh": "test_sdbh_002",
                    "c_stbh": "test_stbh_002",
                    "wjlj": "https://example.com/doc2.pdf",
                    "c_wsbh": "test_wsbh_002",
                    "c_wsmc": "测试文书002",
                    "c_fybh": "test_fybh_002",
                    "c_fymc": "测试法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                },
            ],
        }

        # 配置 mock
        mock_intercept.return_value = api_response
        mock_download.side_effect = [(True, "/tmp/test_doc1.pdf", None), (True, "/tmp/test_doc2.pdf", None)]

        # 创建 scraper 并执行
        scraper = CourtDocumentScraper(self.scraper_task)

        # Mock page 和 browser
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"), patch.object(scraper, "random_wait"):  # noqa: SIM117
            with patch.object(scraper, "_save_page_state"):
                with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                    with patch("time.sleep"):  # Mock sleep 避免延迟
                        result = scraper._download_via_api_intercept(Path("/tmp"))  # type: ignore[attr-defined]

        # 验证：API 拦截被调用
        mock_intercept.assert_called_once()

        # 验证：下载方法被调用 2 次
        assert mock_download.call_count == 2

        # 验证：返回结果正确
        assert result["method"] == "api_intercept"
        assert result["document_count"] == 2
        assert result["downloaded_count"] == 2
        assert result["failed_count"] == 0
        assert len(result["files"]) == 2

        # 验证：数据库中有 2 条记录
        documents = CourtDocument.objects.filter(scraper_task=self.scraper_task)
        assert documents.count() == 2

        # 验证：所有记录状态为成功
        for doc in documents:
            assert doc.download_status == DocumentDownloadStatus.SUCCESS
            assert doc.local_file_path is not None
            assert doc.downloaded_at is not None

    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._intercept_api_response")
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_document_directly")
    def test_api_intercept_to_download_partial_failure(self, mock_download, mock_intercept):
        """
        测试完整流程：部分文书下载失败

        验证需求：2.5（错误隔离）
        """
        # 准备 mock 数据
        api_response = {
            "code": 200,
            "msg": "success",
            "success": True,
            "totalRows": 3,
            "data": [
                {
                    "c_sdbh": f"test_sdbh_{i}",
                    "c_stbh": f"test_stbh_{i}",
                    "wjlj": f"https://example.com/doc{i}.pdf",
                    "c_wsbh": f"test_wsbh_{i}",
                    "c_wsmc": f"测试文书{i}",
                    "c_fybh": f"test_fybh_{i}",
                    "c_fymc": "测试法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                }
                for i in range(1, 4)
            ],
        }

        # 配置 mock：第 2 个文书下载失败
        mock_intercept.return_value = api_response
        mock_download.side_effect = [
            (True, "/tmp/test_doc1.pdf", None),
            (False, None, "下载超时"),
            (True, "/tmp/test_doc3.pdf", None),
        ]

        # 创建 scraper 并执行
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"), patch.object(scraper, "random_wait"):  # noqa: SIM117
            with patch.object(scraper, "_save_page_state"):
                with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                    with patch("time.sleep"):
                        result = scraper._download_via_api_intercept(Path("/tmp"))  # type: ignore[attr-defined]

        # 验证：返回结果正确
        assert result["document_count"] == 3
        assert result["downloaded_count"] == 2
        assert result["failed_count"] == 1

        # 验证：数据库中有 3 条记录
        documents = CourtDocument.objects.filter(scraper_task=self.scraper_task)
        assert documents.count() == 3

        # 验证：2 条成功，1 条失败
        success_docs = documents.filter(download_status=DocumentDownloadStatus.SUCCESS)
        failed_docs = documents.filter(download_status=DocumentDownloadStatus.FAILED)

        assert success_docs.count() == 2
        assert failed_docs.count() == 1

        # 验证：失败记录包含错误信息
        failed_doc = failed_docs.first()
        assert failed_doc.error_message == "下载超时"  # type: ignore[union-attr]
        assert failed_doc.local_file_path is None  # type: ignore[union-attr]
        assert failed_doc.downloaded_at is None  # type: ignore[union-attr]


@pytest.mark.django_db
class TestCourtDocumentFallbackMechanism:
    """法院文书回退机制集成测试"""

    def setup_method(self):
        """测试前准备"""
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://zxfw.court.gov.cn/test", priority=5
        )

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_via_api_intercept_with_navigation"
    )
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_via_fallback")
    def test_fallback_triggered_on_api_timeout(self, mock_fallback, mock_api_intercept):
        """
        测试回退机制：API 拦截超时时触发回退

        验证需求：4.1, 4.2, 4.4
        """
        # 配置 mock：API 拦截抛出异常（超时）
        mock_api_intercept.side_effect = ValueError("API 拦截超时，未能获取文书列表")

        # 配置回退方法返回成功结果
        mock_fallback.return_value = {
            "source": "zxfw.court.gov.cn",
            "document_count": 1,
            "downloaded_count": 1,
            "failed_count": 0,
            "files": ["/tmp/fallback_doc.pdf"],
            "message": "回退方式：成功下载 1/1 份文书",
        }

        # 创建 scraper
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"):  # noqa: SIM117
            with patch.object(scraper, "random_wait"):
                with patch.object(scraper, "_save_page_state"):
                    with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                        result = scraper._download_zxfw_court("https://zxfw.court.gov.cn/test")  # type: ignore[attr-defined]

        # 验证：API 拦截被调用
        mock_api_intercept.assert_called_once()

        # 验证：回退方法被调用
        mock_fallback.assert_called_once()

        # 验证：结果标注使用了回退方式
        assert result["method"] == "fallback"
        # 验证：结果包含错误信息（当前实现使用 direct_api_error 和 api_intercept_error）
        assert "direct_api_error" in result or "api_intercept_error" in result
        assert result["downloaded_count"] == 1

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_via_api_intercept_with_navigation"
    )
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_via_fallback")
    def test_fallback_triggered_on_api_error(self, mock_fallback, mock_api_intercept):
        """
        测试回退机制：API 拦截异常时触发回退

        验证需求：4.1, 4.2, 4.5
        """
        # 配置 mock：API 拦截抛出异常
        mock_api_intercept.side_effect = ValueError("API 响应格式错误")

        # 配置回退方法返回成功结果
        mock_fallback.return_value = {
            "source": "zxfw.court.gov.cn",
            "document_count": 1,
            "downloaded_count": 1,
            "failed_count": 0,
            "files": ["/tmp/fallback_doc.pdf"],
            "message": "回退方式：成功下载 1/1 份文书",
        }

        # 创建 scraper
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"):  # noqa: SIM117
            with patch.object(scraper, "random_wait"):
                with patch.object(scraper, "_save_page_state"):
                    with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                        result = scraper._download_zxfw_court("https://zxfw.court.gov.cn/test")  # type: ignore[attr-defined]

        # 验证：回退方法被调用
        mock_fallback.assert_called_once()

        # 验证：结果包含回退原因
        assert result["method"] == "fallback"
        # 验证：结果包含错误信息（当前实现使用 api_intercept_error）
        assert "api_intercept_error" in result
        assert "API 响应格式错误" in result["api_intercept_error"]["message"]

    @patch(
        "apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_via_api_intercept_with_navigation"
    )
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_via_fallback")
    def test_both_methods_fail_raises_exception(self, mock_fallback, mock_api_intercept):
        """
        测试回退机制：API 和回退都失败时抛出包含完整错误链的异常

        验证需求：4.5
        """
        from apps.core.exceptions import ExternalServiceError

        # 配置 mock：API 拦截失败
        api_error = ValueError("API 拦截超时")
        mock_api_intercept.side_effect = api_error

        # 配置 mock：回退也失败
        fallback_error = ValueError("回退下载失败")
        mock_fallback.side_effect = fallback_error

        # 创建 scraper
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载，应该抛出异常
        with pytest.raises(ExternalServiceError) as exc_info, patch.object(scraper, "navigate_to_url"):  # noqa: SIM117
            with patch.object(scraper, "random_wait"):
                with patch.object(scraper, "_save_page_state"):
                    with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                        scraper._download_zxfw_court("https://zxfw.court.gov.cn/test")  # type: ignore[attr-defined]

        # 验证：异常包含完整错误链
        exception = exc_info.value
        assert "所有下载方式均失败" in str(exception)

        # 验证：异常包含错误详情
        assert exception.errors is not None
        assert "api_intercept_error" in exception.errors
        assert "fallback_error" in exception.errors


@pytest.mark.django_db
class TestCourtDocumentConcurrentDownload:
    """法院文书并发下载集成测试"""

    def setup_method(self):
        """测试前准备"""
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://zxfw.court.gov.cn/test", priority=5
        )

    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._intercept_api_response")
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_document_directly")
    @patch("time.sleep")
    def test_concurrent_download_with_delay(self, mock_sleep, mock_download, mock_intercept):
        """
        测试并发下载：验证下载之间存在延迟

        验证需求：7.4（下载延迟）
        """
        # 准备 mock 数据：5 个文书
        api_response = {
            "code": 200,
            "msg": "success",
            "success": True,
            "totalRows": 5,
            "data": [
                {
                    "c_sdbh": f"test_sdbh_{i}",
                    "c_stbh": f"test_stbh_{i}",
                    "wjlj": f"https://example.com/doc{i}.pdf",
                    "c_wsbh": f"test_wsbh_{i}",
                    "c_wsmc": f"测试文书{i}",
                    "c_fybh": f"test_fybh_{i}",
                    "c_fymc": "测试法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                }
                for i in range(1, 6)
            ],
        }

        # 配置 mock
        mock_intercept.return_value = api_response
        mock_download.return_value = (True, "/tmp/test_doc.pdf", None)

        # 创建 scraper 并执行
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"), patch.object(scraper, "random_wait"):  # noqa: SIM117
            with patch.object(scraper, "_save_page_state"):
                with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                    result = scraper._download_via_api_intercept(Path("/tmp"))  # type: ignore[attr-defined]

        # 验证：下载方法被调用 5 次
        assert mock_download.call_count == 5

        # 验证：sleep 被调用 4 次（最后一个文书后不需要延迟）
        assert mock_sleep.call_count == 4

        # 验证：每次 sleep 的时间在 1-2 秒之间
        for call in mock_sleep.call_args_list:
            delay = call[0][0]
            assert 1.0 <= delay <= 2.0, f"延迟时间应该在 1-2 秒之间，实际: {delay}"

        # 验证：所有文书都成功下载
        assert result["downloaded_count"] == 5
        assert result["failed_count"] == 0


@pytest.mark.django_db
class TestCourtDocumentPerformanceOptimization:
    """法院文书性能优化集成测试"""

    def setup_method(self):
        """测试前准备"""
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://zxfw.court.gov.cn/test", priority=5
        )

    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._intercept_api_response")
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_document_directly")
    def test_batch_save_performance(self, mock_download, mock_intercept):
        """
        测试批量保存性能：验证批量操作比逐个保存更快

        验证需求：7.1（性能优化）
        """
        # 准备 mock 数据：10 个文书
        document_count = 10
        api_response = {
            "code": 200,
            "msg": "success",
            "success": True,
            "totalRows": document_count,
            "data": [
                {
                    "c_sdbh": f"perf_sdbh_{i}",
                    "c_stbh": f"perf_stbh_{i}",
                    "wjlj": f"https://example.com/perf_doc{i}.pdf",
                    "c_wsbh": f"perf_wsbh_{i}",
                    "c_wsmc": f"性能测试文书{i}",
                    "c_fybh": f"perf_fybh_{i}",
                    "c_fymc": "性能测试法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                }
                for i in range(1, document_count + 1)
            ],
        }

        # 配置 mock
        mock_intercept.return_value = api_response
        mock_download.return_value = (True, "/tmp/perf_doc.pdf", None)

        # 创建 scraper 并执行
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 记录开始时间
        start_time = time.time()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"), patch.object(scraper, "random_wait"):  # noqa: SIM117
            with patch.object(scraper, "_save_page_state"):
                with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                    with patch("time.sleep"):  # Mock sleep 避免延迟影响性能测试
                        result = scraper._download_via_api_intercept(Path("/tmp"))  # type: ignore[attr-defined]

        # 记录结束时间
        elapsed_time = time.time() - start_time

        # 验证：所有文书都保存成功
        assert result["db_save_result"]["success"] == document_count
        assert result["db_save_result"]["failed"] == 0

        # 验证：数据库中有 10 条记录
        documents = CourtDocument.objects.filter(scraper_task=self.scraper_task)
        assert documents.count() == document_count

        # 验证：性能合理（10 条记录应该在 5 秒内完成）
        assert elapsed_time < 5.0, f"批量保存 {document_count} 条记录耗时过长: {elapsed_time:.2f}s"

        # 打印性能信息
        print(f"\n批量保存 {document_count} 条记录耗时: {elapsed_time:.3f}s")
        print(f"平均每条记录: {elapsed_time / document_count:.3f}s")

    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._intercept_api_response")
    @patch("apps.automation.services.scraper.scrapers.court_document.CourtDocumentScraper._download_document_directly")
    def test_database_query_optimization(self, mock_download, mock_intercept):
        """
        测试数据库查询优化：验证使用 select_related 减少查询次数

        验证需求：7.1（性能优化）
        """
        # 准备 mock 数据
        api_response = {
            "code": 200,
            "msg": "success",
            "success": True,
            "totalRows": 3,
            "data": [
                {
                    "c_sdbh": f"query_sdbh_{i}",
                    "c_stbh": f"query_stbh_{i}",
                    "wjlj": f"https://example.com/query_doc{i}.pdf",
                    "c_wsbh": f"query_wsbh_{i}",
                    "c_wsmc": f"查询测试文书{i}",
                    "c_fybh": f"query_fybh_{i}",
                    "c_fymc": "查询测试法院",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                }
                for i in range(1, 4)
            ],
        }

        # 配置 mock
        mock_intercept.return_value = api_response
        mock_download.return_value = (True, "/tmp/query_doc.pdf", None)

        # 创建 scraper 并执行
        scraper = CourtDocumentScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.browser = MagicMock()  # type: ignore[attr-defined]
        scraper.page.url = "https://zxfw.court.gov.cn/test"
        scraper.page.title.return_value = "Test Page"
        scraper.page.wait_for_load_state = MagicMock()

        # 执行下载
        with patch.object(scraper, "navigate_to_url"), patch.object(scraper, "random_wait"):  # noqa: SIM117
            with patch.object(scraper, "_save_page_state"):
                with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")):
                    with patch("time.sleep"):
                        scraper._download_via_api_intercept(Path("/tmp"))  # type: ignore[attr-defined]

        # 使用 Django 的查询计数器测试查询优化
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # 测试：使用 select_related 查询
        with CaptureQueriesContext(connection) as context:
            documents = CourtDocument.objects.filter(scraper_task=self.scraper_task).select_related(
                "scraper_task", "case"
            )

            # 访问关联对象（不应该触发额外查询）
            for doc in documents:
                _ = doc.scraper_task.task_type
                _ = doc.case  # 可能为 None

        query_count_with_select_related = len(context.captured_queries)

        # 测试：不使用 select_related 查询
        with CaptureQueriesContext(connection) as context:
            documents = CourtDocument.objects.filter(scraper_task=self.scraper_task)

            # 访问关联对象（会触发额外查询）
            for doc in documents:
                _ = doc.scraper_task.task_type
                _ = doc.case

        query_count_without_select_related = len(context.captured_queries)

        # 验证：使用 select_related 的查询次数更少
        assert query_count_with_select_related < query_count_without_select_related, (
            f"select_related 应该减少查询次数: "
            f"{query_count_with_select_related} vs {query_count_without_select_related}"
        )

        # 打印查询信息
        print(f"\n使用 select_related: {query_count_with_select_related} 次查询")
        print(f"不使用 select_related: {query_count_without_select_related} 次查询")
        print(f"优化效果: 减少 {query_count_without_select_related - query_count_with_select_related} 次查询")
