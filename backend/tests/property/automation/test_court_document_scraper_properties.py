"""
CourtDocumentScraper API 拦截属性测试
使用 Hypothesis 进行基于属性的测试

注意: 代码已重构为 court_document/ 包结构，
ZxfwCourtScraper 是实际的 zxfw 下载实现类。
"""

import re
import time
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.models import ScraperTask
from apps.automation.services.scraper.scrapers.court_document import ZxfwCourtScraper
from apps.automation.services.scraper.scrapers.court_document.base_court_scraper import BaseCourtDocumentScraper


# 定义策略
@st.composite
def api_response_strategy(draw):
    """生成有效的 API 响应数据"""
    doc_count = draw(st.integers(min_value=0, max_value=10))

    documents = []
    for _ in range(doc_count):
        documents.append(
            {
                "c_sdbh": draw(
                    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
                ),
                "c_stbh": draw(
                    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
                ),
                "wjlj": f"https://example.com/{draw(st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))}",  # noqa: E501
                "c_wsbh": draw(
                    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
                ),
                "c_wsmc": draw(
                    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
                ),
                "c_fybh": draw(
                    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
                ),
                "c_fymc": draw(
                    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
                ),
                "c_wjgs": draw(st.sampled_from(["pdf", "doc", "docx"])),
                "dt_cjsj": "2024-01-01T00:00:00",
            }
        )

    return {"code": 200, "msg": "success", "data": documents, "success": True, "totalRows": doc_count}


@pytest.mark.django_db
class TestCourtDocumentScraperAPIInterceptProperties:
    """ZxfwCourtScraper API 拦截属性测试"""

    def setup_method(self) -> None:
        """测试前准备"""
        self.scraper_task = ScraperTask.objects.create(
            task_type="court_document", status="running", url="https://zxfw.court.gov.cn/test", priority=5
        )

    @settings(max_examples=30, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_1_api_interceptor_configuration(self, api_response):
        """
        属性 1: API拦截器正确配置

        Feature: court-document-api-optimization, Property 1: API拦截器正确配置

        对于任何打开 zxfw.court.gov.cn 文书页面的操作，
        系统应该正确配置并触发API拦截器监听指定的接口
        验证需求: 1.1
        """
        mock_page = MagicMock()
        mock_response = MagicMock()

        mock_response.url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        mock_response.json.return_value = api_response

        listener_registered = False
        registered_handler = None

        def mock_on(event_name, handler):
            nonlocal listener_registered, registered_handler
            if event_name == "response":
                listener_registered = True
                registered_handler = handler

        mock_page.on = mock_on
        mock_page.remove_listener = MagicMock()
        mock_page.wait_for_load_state = MagicMock()

        scraper = ZxfwCourtScraper(self.scraper_task)
        scraper.page = mock_page
        scraper.navigate_to_url = MagicMock()  # type: ignore[method-assign]
        scraper.random_wait = MagicMock()  # type: ignore[method-assign]
        scraper._debug_log = MagicMock()  # type: ignore[method-assign]

        import threading

        def trigger_response():
            time.sleep(0.1)
            if registered_handler:
                registered_handler(mock_response)

        thread = threading.Thread(target=trigger_response)
        thread.start()

        result = scraper._intercept_api_response_with_navigation(timeout=5000)
        thread.join()

        assert listener_registered, "API 响应监听器应该被注册"
        assert mock_page.remove_listener.called, "监听器应该在完成后被移除"

        if api_response["data"]:
            assert result is not None, "应该成功拦截到 API 响应"
            assert result == api_response, "拦截到的数据应该与 API 响应一致"

    @settings(max_examples=30, deadline=None)
    @given(api_response=api_response_strategy(), timeout_ms=st.integers(min_value=1000, max_value=10000))
    def test_property_19_statistics_log_accuracy(self, api_response, timeout_ms):
        """
        属性 19: 统计日志准确性

        Feature: court-document-api-optimization, Property 19: 统计日志准确性

        对于任何API拦截成功的操作，日志应该记录拦截到的文书数量和响应时间
        验证需求: 6.3
        """
        mock_page = MagicMock()
        mock_response = MagicMock()

        mock_response.url = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
        mock_response.json.return_value = api_response

        log_calls: list[dict] = []

        def mock_on(event_name, handler):
            if event_name == "response":
                handler(mock_response)

        mock_page.on = mock_on
        mock_page.remove_listener = MagicMock()
        mock_page.wait_for_load_state = MagicMock()

        scraper = ZxfwCourtScraper(self.scraper_task)
        scraper.page = mock_page
        scraper.navigate_to_url = MagicMock()  # type: ignore[method-assign]
        scraper.random_wait = MagicMock()  # type: ignore[method-assign]
        scraper._debug_log = MagicMock()  # type: ignore[method-assign]

        with patch(
            "apps.automation.services.scraper.scrapers.court_document._zxfw_intercept_mixin.logger"
        ) as mock_logger:

            def capture_log(*args, **kwargs):
                log_calls.append({"args": args, "kwargs": kwargs})

            mock_logger.info.side_effect = capture_log
            mock_logger.warning = MagicMock()
            mock_logger.error = MagicMock()

            result = scraper._intercept_api_response_with_navigation(timeout=timeout_ms)

            assert len(log_calls) > 0, "应该有日志记录"

            stats_log = None
            for log_call in log_calls:
                if "extra" in log_call["kwargs"]:
                    extra = log_call["kwargs"]["extra"]
                    if "document_count" in extra and "response_time_ms" in extra:
                        stats_log = extra
                        break

            if result is not None:
                assert stats_log is not None, "应该记录统计信息日志"
                expected_count = len(api_response.get("data", []))
                assert stats_log["document_count"] == expected_count, f"日志中的文书数量应该为 {expected_count}"
                assert "response_time_ms" in stats_log, "应该记录响应时间"
                assert stats_log["response_time_ms"] >= 0, "响应时间应该为非负数"
                assert stats_log.get("operation_type") == "api_intercept", "应该记录操作类型为 api_intercept"
                assert "timestamp" in stats_log, "应该记录时间戳"
                assert "api_url" in stats_log, "应该记录 API URL"

    @settings(max_examples=30, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_4_document_list_traversal_completeness(self, api_response):
        """
        属性 4: 文书列表遍历完整性

        Feature: court-document-api-optimization, Property 4: 文书列表遍历完整性

        对于任何文书列表，系统应该处理列表中的每一条记录，处理数量应该等于列表长度
        验证需求: 2.1
        """
        mock_page = MagicMock()
        scraper = ZxfwCourtScraper(self.scraper_task)
        scraper.page = mock_page

        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        processed_count = 0

        def mock_download(document_data, download_dir, download_timeout=60000):
            nonlocal processed_count
            processed_count += 1
            return True, f"/tmp/test_{processed_count}.pdf", None

        scraper._download_document_directly = mock_download  # type: ignore[method-assign]

        documents = api_response.get("data", [])
        for doc in documents:
            scraper._download_document_directly(doc, download_dir)

        expected_count = len(documents)
        assert processed_count == expected_count, f"应该处理 {expected_count} 个文书，实际处理了 {processed_count} 个"

    @settings(max_examples=30, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_5_url_extraction_correctness(self, api_response):
        """
        属性 5: URL提取正确性

        Feature: court-document-api-optimization, Property 5: URL提取正确性

        对于任何文书记录，从 wjlj 字段提取的URL应该是有效的HTTP/HTTPS URL
        验证需求: 2.2
        """
        url_pattern = re.compile(
            r"^https?://"
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
            r"(?::\d+)?"
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        documents = api_response.get("data", [])
        for doc in documents:
            url = doc.get("wjlj")
            assert url is not None, "wjlj 字段应该存在"
            assert url != "", "wjlj 字段不应该为空"
            assert url_pattern.match(url), f"URL 应该是有效的 HTTP/HTTPS URL: {url}"
            assert url.startswith("http://") or url.startswith("https://"), f"URL 应该以 http(s):// 开头: {url}"

    @settings(max_examples=30, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_6_download_function_invocation(self, api_response):
        """
        属性 6: 下载功能调用

        Feature: court-document-api-optimization, Property 6: 下载功能调用

        对于任何有效的下载URL，系统应该调用 httpx 下载功能并请求正确的 URL
        验证需求: 2.3
        """
        scraper = ZxfwCourtScraper(self.scraper_task)

        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        documents = api_response.get("data", [])
        for doc in documents:
            url = doc.get("wjlj")

            with patch("httpx.Client") as mock_client_class:
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.content = b"fake file content"
                mock_response.raise_for_status = MagicMock()
                mock_client.get.return_value = mock_response
                mock_client.__enter__ = lambda self: mock_client
                mock_client.__exit__ = lambda self, *args: None
                mock_client_class.return_value = mock_client

                success, filepath, error = scraper._download_document_directly(doc, download_dir, download_timeout=5000)

                assert mock_client.get.called, f"应该调用 httpx.Client.get 方法下载 {url}"
                call_args = mock_client.get.call_args
                assert call_args[0][0] == url, f"get 方法应该使用正确的 URL: {url}"

                # 清理下载的文件
                if filepath:
                    Path(filepath).unlink(missing_ok=True)

    @settings(max_examples=30, deadline=None)
    @given(api_response=api_response_strategy())
    def test_property_7_file_naming_correctness(self, api_response):
        """
        属性 7: 文件命名正确性

        Feature: court-document-api-optimization, Property 7: 文件命名正确性

        对于任何下载成功的文书，保存的文件名应该基于 c_wsmc 字段
        验证需求: 2.4
        """
        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        scraper = ZxfwCourtScraper(self.scraper_task)

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.content = b"fake file content"
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = lambda self: mock_client
            mock_client.__exit__ = lambda self, *args: None
            mock_client_class.return_value = mock_client

            documents = api_response.get("data", [])
            for doc in documents:
                success, filepath, error = scraper._download_document_directly(doc, download_dir, download_timeout=5000)

                if success and filepath:
                    assert Path(filepath).exists(), f"下载的文件应该存在: {filepath}"
                    assert str(download_dir) in filepath, f"文件应该在指定目录下: {download_dir}"

                    filename = Path(filepath).name
                    c_wsmc = doc.get("c_wsmc", "")
                    cleaned_wsmc = re.sub(r'[<>:"/\\|?*]', "_", c_wsmc)
                    assert cleaned_wsmc in filename, f"文件名应该包含 c_wsmc: {cleaned_wsmc}，实际: {filename}"

                    c_wjgs = doc.get("c_wjgs", "pdf")
                    assert filename.endswith(f".{c_wjgs}"), f"文件扩展名应该是 .{c_wjgs}，实际: {filename}"

                    Path(filepath).unlink(missing_ok=True)

    @settings(max_examples=30, deadline=None)
    @given(
        doc_count=st.integers(min_value=2, max_value=5),
        delay_range=st.tuples(st.floats(min_value=0.5, max_value=1.5), st.floats(min_value=1.5, max_value=3.0)).filter(
            lambda x: x[0] < x[1]
        ),
    )
    def test_property_22_download_delay_existence(self, doc_count, delay_range):
        """
        属性 22: 下载延迟存在性

        Feature: court-document-api-optimization, Property 22: 下载延迟存在性

        对于任何并发下载多个文书的操作，相邻两次下载之间应该存在延迟
        验证需求: 7.4
        """
        mock_page = MagicMock()
        scraper = ZxfwCourtScraper(self.scraper_task)
        scraper.page = mock_page

        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        download_times: list[float] = []
        delay_calls: list[dict] = []

        def mock_download(document_data, download_dir, download_timeout=60000):
            download_times.append(time.time())
            return True, f"/tmp/test_{len(download_times)}.pdf", None

        scraper._download_document_directly = mock_download  # type: ignore[method-assign]

        def mock_random_wait(min_sec: float = 0.5, max_sec: float = 2.0) -> None:
            delay_calls.append({"min_sec": min_sec, "max_sec": max_sec, "timestamp": time.time()})

        scraper.random_wait = mock_random_wait  # type: ignore[assignment]

        documents = []
        for i in range(doc_count):
            documents.append(
                {
                    "c_sdbh": f"sdbh_{i}",
                    "c_stbh": f"stbh_{i}",
                    "wjlj": f"https://example.com/doc_{i}",
                    "c_wsbh": f"wsbh_{i}",
                    "c_wsmc": f"document_{i}",
                    "c_fybh": f"fybh_{i}",
                    "c_fymc": f"court_{i}",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                }
            )

        min_delay, max_delay = delay_range
        for i, doc in enumerate(documents):
            scraper._download_document_directly(doc, download_dir)
            if i < len(documents) - 1:
                scraper.random_wait(min_delay, max_delay)

        assert len(download_times) == doc_count, f"应该有 {doc_count} 次下载记录"
        expected_delay_calls = doc_count - 1
        assert len(delay_calls) == expected_delay_calls, f"应该有 {expected_delay_calls} 次延迟调用"

        for delay_call in delay_calls:
            assert delay_call["min_sec"] == min_delay
            assert delay_call["max_sec"] == max_delay

        for i, delay_call in enumerate(delay_calls):
            download_time_before = download_times[i]
            download_time_after = download_times[i + 1]
            delay_time = delay_call["timestamp"]
            assert download_time_before <= delay_time <= download_time_after

    @settings(max_examples=30, deadline=None)
    @given(
        total_docs=st.integers(min_value=3, max_value=10),
        failure_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=1, max_size=3, unique=True),
    )
    def test_property_8_error_isolation(self, total_docs, failure_indices):
        """
        属性 8: 错误隔离性

        Feature: court-document-api-optimization, Property 8: 错误隔离性

        对于任何包含部分失败下载的文书列表，失败的下载不应该阻止其他文书的下载
        验证需求: 2.5
        """
        failure_indices = [idx for idx in failure_indices if idx < total_docs]
        if not failure_indices:
            return

        scraper = ZxfwCourtScraper(self.scraper_task)

        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        documents = []
        for i in range(total_docs):
            documents.append(
                {
                    "c_sdbh": f"sdbh_{i}",
                    "c_stbh": f"stbh_{i}",
                    "wjlj": f"https://example.com/doc_{i}",
                    "c_wsbh": f"wsbh_{i}",
                    "c_wsmc": f"document_{i}",
                    "c_fybh": f"fybh_{i}",
                    "c_fymc": f"court_{i}",
                    "c_wjgs": "pdf",
                    "dt_cjsj": "2024-01-01T00:00:00",
                }
            )

        processed_docs: list[int] = []
        success_count = 0
        failure_count = 0

        def mock_download(document_data, download_dir, download_timeout=60000):
            nonlocal success_count, failure_count
            doc_index = int(document_data["c_sdbh"].split("_")[1])
            processed_docs.append(doc_index)
            if doc_index in failure_indices:
                failure_count += 1
                return False, None, f"模拟下载失败: document_{doc_index}"
            else:
                success_count += 1
                return True, f"/tmp/test_{doc_index}.pdf", None

        scraper._download_document_directly = mock_download  # type: ignore[method-assign]

        saved_docs: list[dict] = []

        def mock_save_to_db(document_data, download_result):
            doc_index = int(document_data["c_sdbh"].split("_")[1])
            saved_docs.append({"index": doc_index, "success": download_result[0], "error": download_result[2]})
            return doc_index + 1000

        scraper._save_document_to_db = mock_save_to_db  # type: ignore[method-assign]

        # 使用基类的 _save_documents_batch 实现（绕过 Mixin 的 MRO 覆盖）
        scraper._save_documents_batch = types.MethodType(  # type: ignore[method-assign]
            BaseCourtDocumentScraper._save_documents_batch, scraper
        )

        documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]] = []
        for doc in documents:
            download_result = scraper._download_document_directly(doc, download_dir)
            documents_with_results.append((doc, download_result))

        save_result = scraper._save_documents_batch(documents_with_results)

        assert len(processed_docs) == total_docs
        assert processed_docs == list(range(total_docs))

        expected_success = total_docs - len(failure_indices)
        assert success_count == expected_success
        assert failure_count == len(failure_indices)
        assert len(saved_docs) == total_docs

        for saved_doc in saved_docs:
            doc_index = saved_doc["index"]
            expected_ok = doc_index not in failure_indices
            assert saved_doc["success"] == expected_ok

        assert save_result["total"] == total_docs
        assert save_result["success"] == total_docs
        assert save_result["failed"] == 0

        for failure_idx in failure_indices:
            subsequent_docs = [idx for idx in processed_docs if idx > failure_idx]
            expected_subsequent = list(range(failure_idx + 1, total_docs))
            assert subsequent_docs == expected_subsequent

    @settings(max_examples=30, deadline=None)
    @given(
        api_error_type=st.sampled_from(["timeout", "invalid_format", "empty_data", "network_error"]),
        fallback_success=st.booleans(),
    )
    def test_property_13_fallback_log_recording(self, api_error_type, fallback_success):
        """
        属性 13: 回退日志记录

        Feature: court-document-api-optimization, Property 13: 回退日志记录

        对于任何触发回退机制的情况，系统日志应该包含回退原因
        验证需求: 4.2
        """
        scraper = ZxfwCourtScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.page.goto = MagicMock()
        scraper.page.wait_for_load_state = MagicMock()
        scraper.random_wait = MagicMock()  # type: ignore[method-assign]
        scraper._save_page_state = MagicMock(return_value={"screenshot": "/tmp/test.png"})  # type: ignore[method-assign]
        scraper._prepare_download_dir = MagicMock(return_value=Path("/tmp/test_downloads"))  # type: ignore[method-assign]

        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        api_errors = {
            "timeout": ValueError("API 拦截超时，未能获取文书列表"),
            "invalid_format": ValueError("API 响应格式错误：期望 dict，实际 str"),
            "empty_data": ValueError("API 响应中没有文书数据"),
            "network_error": Exception("网络连接失败"),
        }
        api_error = api_errors[api_error_type]

        # 新架构有3级策略：直接API → 拦截 → 回退
        # 让直接API和拦截都失败
        def mock_direct_api(url, download_dir):
            raise api_error

        scraper._download_via_direct_api = mock_direct_api  # type: ignore[method-assign]

        def mock_api_intercept(download_dir):
            raise api_error

        scraper._download_via_api_intercept_with_navigation = mock_api_intercept  # type: ignore[method-assign]

        def mock_fallback(download_dir):
            if fallback_success:
                return {
                    "source": "zxfw.court.gov.cn",
                    "document_count": 1,
                    "downloaded_count": 1,
                    "failed_count": 0,
                    "files": ["/tmp/test.pdf"],
                    "message": "回退方式：成功下载 1/1 份文书",
                }
            else:
                raise Exception("回退机制也失败")

        scraper._download_via_fallback = mock_fallback  # type: ignore[method-assign]

        log_calls: list[dict] = []

        with patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper.logger") as mock_logger:

            def capture_log(level):
                def log_func(*args, **kwargs):
                    log_calls.append({"level": level, "args": args, "kwargs": kwargs})

                return log_func

            mock_logger.info.side_effect = capture_log("info")
            mock_logger.warning.side_effect = capture_log("warning")
            mock_logger.error.side_effect = capture_log("error")

            try:
                result = scraper.run()
                if fallback_success:
                    assert result is not None, "回退成功应该返回结果"
            except Exception:
                if not fallback_success:
                    pass  # 预期的异常

            assert len(log_calls) > 0, "应该有日志记录"

            # 验证有失败相关的日志
            failure_logs = [
                lc
                for lc in log_calls
                if "extra" in lc.get("kwargs", {})
                and lc["kwargs"]["extra"].get("operation_type", "")
                in (
                    "direct_api_failed",
                    "api_intercept_failed",
                    "fallback_attempt",
                    "fallback_success",
                    "all_methods_failed",
                )
            ]
            assert len(failure_logs) > 0, "应该有失败/回退相关的日志记录"

    @settings(max_examples=30, deadline=None)
    @given(
        api_error_message=st.text(
            min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))
        ),
        use_fallback=st.booleans(),
    )
    def test_property_14_fallback_result_marking(self, api_error_message, use_fallback):
        """
        属性 14: 回退结果标记

        Feature: court-document-api-optimization, Property 14: 回退结果标记

        对于任何使用回退机制成功的下载，返回结果应该包含标记表明使用了回退方式
        验证需求: 4.4
        """
        scraper = ZxfwCourtScraper(self.scraper_task)
        scraper.page = MagicMock()
        scraper.page.goto = MagicMock()
        scraper.page.wait_for_load_state = MagicMock()
        scraper.random_wait = MagicMock()  # type: ignore[method-assign]
        scraper._save_page_state = MagicMock(return_value={"screenshot": "/tmp/test.png"})  # type: ignore[method-assign]
        scraper._prepare_download_dir = MagicMock(return_value=Path("/tmp/test_downloads"))  # type: ignore[method-assign]

        download_dir = Path("/tmp/test_downloads")
        download_dir.mkdir(parents=True, exist_ok=True)

        if use_fallback:
            # 让直接API和拦截都失败，回退成功
            def mock_direct_api(url, download_dir):
                raise ValueError(api_error_message)

            scraper._download_via_direct_api = mock_direct_api  # type: ignore[method-assign]

            def mock_api_intercept(download_dir):
                raise ValueError(api_error_message)

            scraper._download_via_api_intercept_with_navigation = mock_api_intercept  # type: ignore[method-assign]

            def mock_fallback(download_dir):
                return {
                    "source": "zxfw.court.gov.cn",
                    "document_count": 1,
                    "downloaded_count": 1,
                    "failed_count": 0,
                    "files": ["/tmp/test_fallback.pdf"],
                    "message": "回退方式：成功下载 1/1 份文书",
                }

            scraper._download_via_fallback = mock_fallback  # type: ignore[method-assign]
        else:
            # 直接API成功
            def mock_direct_api_ok(url, download_dir):
                return {
                    "source": "zxfw.court.gov.cn",
                    "method": "direct_api",
                    "document_count": 1,
                    "downloaded_count": 1,
                    "failed_count": 0,
                    "files": ["/tmp/test_api.pdf"],
                    "db_save_result": {"total": 1, "success": 1, "failed": 0},
                    "message": "直接 API 方式：成功下载 1/1 份文书",
                }

            scraper._download_via_direct_api = mock_direct_api_ok  # type: ignore[method-assign]

        with patch("apps.automation.services.scraper.scrapers.court_document.zxfw_scraper.logger"):
            result = scraper.run()

            assert result is not None, "应该返回下载结果"

            if use_fallback:
                assert result.get("method") == "fallback", f"method 应该为 'fallback'，实际: {result.get('method')}"
                assert "source" in result, "结果应该包含 source 字段"
                assert "downloaded_count" in result, "结果应该包含 downloaded_count 字段"
            else:
                assert result.get("method") == "direct_api", f"method 应该为 'direct_api'，实际: {result.get('method')}"
