"""zxfw 下载链路稳固性修复的单测（2026-10-27 任务 313 事故）。

覆盖四项修复：
1. 直接 API 列表接口运行内重试（法院服务端对新生成送达首次请求可能超 30s）
2. 纯 API 模式直接 API 失败后懒创建浏览器，降级链路不再死路
3. 一张网 getWsListBySdbhNew 响应已不含 dt_cjsj，落库不再强制该字段
4. 任务级自重试与 SMS 级重试并发去重，避免重复创建下载任务
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

_ZXFW_MOD = "apps.automation.services.scraper.scrapers.court_document._zxfw_direct_api_mixin"
_ZXFW_SCRAPER_MOD = "apps.automation.services.scraper.scrapers.court_document.zxfw_scraper"
_COURT_DOC_SVC_MOD = "apps.automation.services.scraper.court_document_service"
_SMS_MIXIN_MOD = "apps.automation.services.sms._sms_download_mixin"


# ──────────────────────────────────────────────────────────────────────────────
# 1. 直接 API 列表接口：运行内重试
# ──────────────────────────────────────────────────────────────────────────────


def _api_response_mock(code: int = 200, data: list | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"code": code, "msg": "成功！", "data": data if data is not None else []}
    return resp


class TestFetchDocumentsViaDirectApiRetry:
    def _mixin(self) -> object:
        from apps.automation.services.scraper.scrapers.court_document._zxfw_direct_api_mixin import ZxfwDirectApiMixin

        return ZxfwDirectApiMixin()

    @patch(f"{_ZXFW_MOD}.time.sleep")
    @patch("httpx.Client")
    def test_retry_then_success(self, mock_client_cls, mock_sleep):
        documents = [{"c_wsmc": "告知书", "wjlj": "https://oss/x.pdf"}]
        ok = _api_response_mock(data=documents)
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = [
            TimeoutError("read timeout"),
            TimeoutError("read timeout"),
            ok,
        ]

        result = self._mixin()._fetch_documents_via_direct_api({"sdbh": "s", "qdbh": "q", "sdsin": "t"})

        assert result == documents
        assert mock_client_cls.return_value.__enter__.return_value.post.call_count == 3

    @patch(f"{_ZXFW_MOD}.time.sleep")
    @patch("httpx.Client")
    def test_all_attempts_exhausted_raises_with_detail(self, mock_client_cls, mock_sleep):
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = TimeoutError("read timeout")

        with pytest.raises(ValueError, match=r"连续 3 次.*read timeout"):
            self._mixin()._fetch_documents_via_direct_api({"sdbh": "s", "qdbh": "q", "sdsin": "t"})

        assert mock_client_cls.return_value.__enter__.return_value.post.call_count == 3

    @patch(f"{_ZXFW_MOD}.time.sleep")
    @patch("httpx.Client")
    def test_business_code_error_not_retried(self, mock_client_cls, mock_sleep):
        # code != 200 是服务端明确答复而非瞬态超时，拿到即失败，不应消耗重试
        mock_client_cls.return_value.__enter__.return_value.post.return_value = _api_response_mock(code=500, data=[])

        with pytest.raises(ValueError, match="API 响应错误"):
            self._mixin()._fetch_documents_via_direct_api({"sdbh": "s", "qdbh": "q", "sdsin": "t"})

        assert mock_client_cls.return_value.__enter__.return_value.post.call_count == 1
        mock_sleep.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# 2. 纯 API 模式懒创建浏览器（run 级集成见 test_zxfw_scraper_round8.py）
# ──────────────────────────────────────────────────────────────────────────────


class TestEnsureBrowserContext:
    def _scraper(self) -> object:
        from apps.automation.services.scraper.scrapers.court_document.zxfw_scraper import ZxfwCourtScraper

        scraper = ZxfwCourtScraper.__new__(ZxfwCourtScraper)
        scraper.browser_service = MagicMock()
        scraper.page = None
        scraper.context = None
        return scraper

    def test_lazy_create_sets_page_and_context(self):
        scraper = self._scraper()

        created = scraper._ensure_browser_context()

        assert created is True
        scraper.browser_service.create_context.assert_called_once_with(use_anti_detection=True)
        assert scraper.page is scraper.browser_service.create_context.return_value.new_page.return_value
        assert scraper.context is scraper.browser_service.create_context.return_value

    def test_existing_page_is_noop(self):
        scraper = self._scraper()
        shared = MagicMock()
        scraper.page = shared

        created = scraper._ensure_browser_context()

        assert created is False
        scraper.browser_service.create_context.assert_not_called()
        assert scraper.page is shared

    def test_close_resets_references(self):
        scraper = self._scraper()
        scraper._ensure_browser_context()
        page, context = scraper.page, scraper.context

        scraper._close_browser_context()

        page.close.assert_called_once()
        context.close.assert_called_once()
        assert scraper.page is None
        assert scraper.context is None


# ──────────────────────────────────────────────────────────────────────────────
# 3. dt_cjsj 不再是落库必填字段
# ──────────────────────────────────────────────────────────────────────────────


def _valid_api_data(**overrides: object) -> dict[str, object]:
    base = {
        "c_sdbh": "sdbh-1",
        "c_stbh": "stbh-1",
        "wjlj": "https://oss/x.pdf",
        "c_wsbh": "wsbh-1",
        "c_wsmc": "告知书",
        "c_fybh": "2602",
        "c_fymc": "佛山市顺德区人民法院",
        "c_wjgs": "pdf",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
class TestCreateDocumentFromApiDataDtCjsj:
    def _service(self):
        from apps.automation.services.scraper.court_document_service import CourtDocumentService

        return CourtDocumentService()

    @patch(f"{_COURT_DOC_SVC_MOD}.CourtDocument.objects.get_or_create")
    @patch(f"{_COURT_DOC_SVC_MOD}.ScraperTask.objects.get")
    def test_missing_dt_cjsj_falls_back_to_now(self, mock_task_get, mock_goc):
        """一张网 API 响应已无 dt_cjsj（实测仅 8 字段），缺失时应回落当前时间而非拒收。"""
        mock_task_get.return_value = MagicMock()
        document = MagicMock(id=1)
        mock_goc.return_value = (document, True)

        created = self._service().create_document_from_api_data(1, _valid_api_data())

        assert created is document
        defaults = mock_goc.call_args.kwargs["defaults"]
        assert isinstance(defaults["dt_cjsj"], datetime)

    @patch(f"{_COURT_DOC_SVC_MOD}.CourtDocument.objects.get_or_create")
    @patch(f"{_COURT_DOC_SVC_MOD}.ScraperTask.objects.get")
    def test_empty_string_dt_cjsj_falls_back_to_now(self, mock_task_get, mock_goc):
        mock_task_get.return_value = MagicMock()
        mock_goc.return_value = (MagicMock(id=2), True)

        self._service().create_document_from_api_data(1, _valid_api_data(dt_cjsj=""))

        defaults = mock_goc.call_args.kwargs["defaults"]
        assert isinstance(defaults["dt_cjsj"], datetime)

    @patch(f"{_COURT_DOC_SVC_MOD}.CourtDocument.objects.get_or_create")
    @patch(f"{_COURT_DOC_SVC_MOD}.ScraperTask.objects.get")
    def test_iso_dt_cjsj_parsed(self, mock_task_get, mock_goc):
        mock_task_get.return_value = MagicMock()
        mock_goc.return_value = (MagicMock(id=3), True)

        self._service().create_document_from_api_data(1, _valid_api_data(dt_cjsj="2026-10-27T15:00:00+08:00"))

        defaults = mock_goc.call_args.kwargs["defaults"]
        assert isinstance(defaults["dt_cjsj"], datetime)
        assert defaults["dt_cjsj"].year == 2026

    @patch(f"{_COURT_DOC_SVC_MOD}.CourtDocument.objects.get_or_create")
    @patch(f"{_COURT_DOC_SVC_MOD}.ScraperTask.objects.get")
    def test_structural_field_still_required(self, mock_task_get, mock_goc):
        """结构性字段（下载链接、唯一键等）缺失仍然拒收。"""
        from apps.core.exceptions import ValidationException

        mock_task_get.return_value = MagicMock()
        data = _valid_api_data()
        del data["wjlj"]

        with pytest.raises(ValidationException, match="wjlj"):
            self._service().create_document_from_api_data(1, data)
        mock_goc.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# 4. 双层重试去重
# ──────────────────────────────────────────────────────────────────────────────


def _make_sms(*, status: str = "downloading", retry_count: int = 0) -> MagicMock:
    sms = MagicMock()
    sms.id = 284
    sms.status = status
    sms.retry_count = retry_count
    sms.error_message = ""
    return sms


def _make_task(*, status: str = "failed") -> MagicMock:
    task = MagicMock()
    task.id = 313
    task.pk = 313
    task.status = status
    task.error_message = "DOWNLOAD_ALL_METHODS_FAILED"
    return task


class TestHandleSmsDownloadFailedRetryDedup:
    def _mixin(self) -> object:
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        return SMSDownloadMixin()

    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.filter")
    def test_skips_when_task_back_to_pending(self, mock_filter):
        """任务级自重试已把任务翻回 PENDING 时，SMS 级不再排重试、不动短信状态。"""
        fresh = _make_task(status="pending")
        mock_filter.return_value.first.return_value = fresh
        sms = _make_sms()

        result = self._mixin()._handle_sms_download_failed(sms, _make_task())

        assert result is False
        assert sms.status == "downloading"
        sms.save.assert_not_called()

    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.filter")
    def test_skips_when_task_running(self, mock_filter):
        fresh = _make_task(status="running")
        mock_filter.return_value.first.return_value = fresh
        sms = _make_sms()

        assert self._mixin()._handle_sms_download_failed(sms, _make_task()) is False
        sms.save.assert_not_called()

    @patch("apps.core.tasking.ScheduleQueryService.create_once_schedule")
    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.filter")
    def test_schedules_sms_retry_on_terminal_failure(self, mock_filter, mock_schedule):
        """任务终态 FAILED（任务级重试耗尽）才触发 SMS 级重试。"""
        mock_filter.return_value.first.return_value = _make_task(status="failed")
        sms = _make_sms(retry_count=0)

        result = self._mixin()._handle_sms_download_failed(sms, _make_task())

        assert result is False
        assert sms.status == "download_failed"
        sms.save.assert_called()
        mock_schedule.assert_called_once()

    @patch("apps.core.tasking.ScheduleQueryService.create_once_schedule")
    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.filter")
    def test_marks_sms_failed_when_retry_exhausted(self, mock_filter, mock_schedule):
        mock_filter.return_value.first.return_value = _make_task(status="failed")
        sms = _make_sms(retry_count=3)

        result = self._mixin()._handle_sms_download_failed(sms, _make_task())

        assert result is False
        assert sms.status == "failed"
        mock_schedule.assert_not_called()


class TestCreateDownloadTaskDedup:
    def _mixin(self) -> object:
        from apps.automation.services.sms._sms_download_mixin import SMSDownloadMixin

        return SMSDownloadMixin()

    def _sms(self) -> MagicMock:
        sms = _make_sms()
        sms.download_links = ["https://zxfw.court.gov.cn/zxfw/#/index?sdbh=x&qdbh=y&sdsin=z"]
        return sms

    @patch(f"{_SMS_MIXIN_MOD}.submit_task")
    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.create")
    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.filter")
    def test_reuses_active_task_for_same_sms_and_url(self, mock_filter, mock_create, mock_submit):
        """同短信同 URL 已有活跃任务（含任务级自重试翻回 PENDING 的）时复用不新建。"""
        existing = _make_task(status="pending")
        mock_filter.return_value.order_by.return_value.first.return_value = existing

        result = self._mixin()._create_download_task(self._sms())

        assert result is existing
        mock_create.assert_not_called()
        mock_submit.assert_not_called()

    @patch(f"{_SMS_MIXIN_MOD}.submit_task", return_value="qid")
    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.create")
    @patch(f"{_SMS_MIXIN_MOD}.ScraperTask.objects.filter")
    def test_creates_new_task_when_none_active(self, mock_filter, mock_create, mock_submit):
        mock_filter.return_value.order_by.return_value.first.return_value = None
        created = _make_task(status="pending")
        mock_create.return_value = created

        result = self._mixin()._create_download_task(self._sms())

        assert result is created
        mock_create.assert_called_once()
        mock_submit.assert_called_once()
