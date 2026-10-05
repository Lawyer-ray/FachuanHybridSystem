"""zxfw API 拦截 Mixin 单元测试 — 响应处理与下载编排（纯 mock，禁止真网络）。

覆盖：
- 代理方法向宿主（super）转发 / 无宿主时的 NotImplementedError
- ``_process_api_data_and_download`` 的全部数据校验分支与成功/失败统计
- ``_download_via_api_intercept_with_navigation`` 的编排链路
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.scraper.scrapers.court_document._zxfw_intercept_mixin import ZxfwInterceptMixin


class _Host:
    """提供 mixin 依赖的宿主方法（记录调用）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _debug_log(self, message: str, data: Any = None) -> None:
        self.calls.append(f"debug_log:{message}")

    def navigate_to_url(self) -> None:
        self.calls.append("navigate")

    def random_wait(self, min_s: float, max_s: float) -> None:
        self.calls.append(f"wait:{min_s}-{max_s}")

    def _save_page_state(self, name: str) -> dict[str, Any]:
        self.calls.append(f"save_state:{name}")
        return {"screenshot": "/tmp/x.png"}

    def _download_document_directly(
        self, document_data: dict[str, Any], download_dir: Path, download_timeout: int
    ) -> tuple[bool, str | None, str | None]:
        self.calls.append(f"download:{document_data.get('c_wsmc')}")
        return True, f"/tmp/{document_data.get('c_wsmc')}.pdf", None

    def _save_documents_batch(
        self, documents_with_results: list[tuple[dict[str, Any], tuple[bool, str | None, str | None]]]
    ) -> dict[str, Any]:
        self.calls.append("save_batch")
        return {
            "total": len(documents_with_results),
            "success": len(documents_with_results),
            "failed": 0,
            "document_ids": [1],
        }


class _Scraper(ZxfwInterceptMixin, _Host):
    """模拟真实组合：ZxfwInterceptMixin 混入提供 _debug_log 等方法的宿主。"""

    def __init__(self) -> None:
        _Host.__init__(self)
        self.page = MagicMock()


class _BareScraper(ZxfwInterceptMixin):
    """未提供宿主实现的独立 mixin。"""


class TestDelegation:
    def test_debug_log_navigate_wait_delegate_to_host(self) -> None:
        s = _Scraper()
        s._debug_log("hi")
        s.navigate_to_url()
        s.random_wait(1.0, 2.0)
        assert s.calls == ["debug_log:hi", "navigate", "wait:1.0-2.0"]

    def test_save_page_state_delegates_to_host(self) -> None:
        s = _Scraper()
        assert s._save_page_state("stage") == {"screenshot": "/tmp/x.png"}
        assert "save_state:stage" in s.calls

    def test_save_documents_batch_delegates_to_host(self) -> None:
        s = _Scraper()
        result = s._save_documents_batch([({}, (True, None, None))])
        assert result["total"] == 1
        assert "save_batch" in s.calls

    def test_download_delegates_to_host(self) -> None:
        s = _Scraper()
        ok, path, err = s._download_document_directly({"c_wsmc": "裁定书"}, Path("/tmp"), 1000)
        assert ok is True
        assert path == "/tmp/裁定书.pdf"

    def test_download_without_host_raises_not_implemented(self) -> None:
        bare = _BareScraper()
        with pytest.raises(NotImplementedError, match="_download_document_directly"):
            bare._download_document_directly({}, Path("/tmp"), 1000)


class TestProcessApiDataValidation:
    def test_none_raises_timeout(self) -> None:
        s = _Scraper()
        with pytest.raises(ValueError, match="API 拦截超时"):
            s._process_api_data_and_download(None, Path("/tmp"))

    def test_non_dict_raises(self) -> None:
        s = _Scraper()
        with pytest.raises(ValueError, match="期望 dict"):
            s._process_api_data_and_download(["x"], Path("/tmp"))  # type: ignore[arg-type]

    def test_missing_data_field_raises(self) -> None:
        s = _Scraper()
        with pytest.raises(ValueError, match="缺少 data 字段"):
            s._process_api_data_and_download({"code": 0}, Path("/tmp"))

    def test_non_list_data_raises(self) -> None:
        s = _Scraper()
        with pytest.raises(ValueError, match="期望 list"):
            s._process_api_data_and_download({"data": {"a": 1}}, Path("/tmp"))

    def test_empty_documents_raises(self) -> None:
        s = _Scraper()
        with pytest.raises(ValueError, match="没有文书数据"):
            s._process_api_data_and_download({"data": []}, Path("/tmp"))


class TestProcessApiDataDownload:
    def _run(
        self, download_results: list[tuple[bool, str | None, str | None]], docs: list[dict[str, Any]] | None = None
    ) -> tuple[dict[str, Any], list[str], MagicMock]:
        s = _Scraper()
        docs = docs or [{"c_wsmc": "文书一"}, {"c_wsmc": "文书二"}]
        results = iter(download_results)
        download_mock = MagicMock(side_effect=lambda **kw: next(results))
        s._download_document_directly = download_mock  # type: ignore[assignment]
        batch_result = {"total": len(docs), "success": len(docs), "failed": 0, "document_ids": [1, 2]}
        s._save_documents_batch = MagicMock(return_value=batch_result)  # type: ignore[assignment]
        with patch("random.uniform", return_value=0.0), patch("time.sleep"):
            result = s._process_api_data_and_download({"data": docs}, Path("/tmp"))
        return result, s.calls, download_mock

    def test_all_success(self) -> None:
        result, calls, download_mock = self._run([(True, "/tmp/a.pdf", None), (True, "/tmp/b.pdf", None)])
        assert result["source"] == "zxfw.court.gov.cn"
        assert result["method"] == "api_intercept"
        assert result["document_count"] == 2
        assert result["downloaded_count"] == 2
        assert result["failed_count"] == 0
        assert result["files"] == ["/tmp/a.pdf", "/tmp/b.pdf"]
        assert result["db_save_result"]["success"] == 2
        assert "成功下载 2/2 份文书" in result["message"]
        # 逐文书调用了直接下载
        assert download_mock.call_count == 2
        called_names = [c.kwargs["document_data"]["c_wsmc"] for c in download_mock.call_args_list]
        assert called_names == ["文书一", "文书二"]

    def test_mixed_success_and_failure(self) -> None:
        result, _, download_mock = self._run([(True, "/tmp/a.pdf", None), (False, None, "超时")])
        assert result["downloaded_count"] == 1
        assert result["failed_count"] == 1
        assert result["files"] == ["/tmp/a.pdf"]
        assert download_mock.call_count == 2

    def test_success_without_filepath_not_collected(self) -> None:
        result, _, _ = self._run([(True, None, None), (True, None, None)])
        assert result["downloaded_count"] == 2
        assert result["files"] == []


class TestDownloadViaApiInterceptOrchestration:
    def test_orchestration_calls_intercept_save_and_process(self, tmp_path: Path) -> None:
        s = _Scraper()
        s._intercept_api_response_with_navigation = MagicMock(return_value={"data": [{"c_wsmc": "X"}]})  # type: ignore[assignment]
        s._save_page_state = MagicMock(return_value={})  # type: ignore[assignment]
        s._process_api_data_and_download = MagicMock(return_value={"document_count": 1})  # type: ignore[assignment]

        result = s._download_via_api_intercept_with_navigation(tmp_path)

        s._intercept_api_response_with_navigation.assert_called_once_with(timeout=30000)
        s._save_page_state.assert_called_once_with("zxfw_after_navigation")
        s._process_api_data_and_download.assert_called_once_with({"data": [{"c_wsmc": "X"}]}, tmp_path)
        assert result == {"document_count": 1}
