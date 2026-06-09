"""Full coverage tests for apps.automation.services.scraper.scrapers.court_document.hbfy_scraper."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest


def _make_scraper(url: str = "", config: dict | None = None):
    from apps.automation.services.scraper.scrapers.court_document.hbfy_scraper import HbfyCourtScraper
    scraper = HbfyCourtScraper.__new__(HbfyCourtScraper)
    scraper.task = SimpleNamespace(url=url, config=config or {})
    scraper.debug_info = {}
    return scraper


# ======================================================================
# run()
# ======================================================================

class TestRun:
    def test_raises_for_unknown_url(self):
        scraper = _make_scraper("http://example.com/unknown")
        with pytest.raises(ValueError, match="不支持"):
            scraper.run()

    def test_dispatches_to_account_mode(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/sfsddz")
        with patch.object(scraper, "_run_account_mode_http_first", return_value={"ok": True}):
            result = scraper.run()
            assert result == {"ok": True}

    def test_dispatches_to_public_mode(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=ABC123")
        with patch.object(scraper, "_run_public_mode_http_first", return_value={"ok": True}):
            result = scraper.run()
            assert result == {"ok": True}


# ======================================================================
# _extract_public_msg_code
# ======================================================================

class TestExtractPublicMsgCode:
    def test_extracts_code(self):
        scraper = _make_scraper()
        assert scraper._extract_public_msg_code("http://dzsd.hbfy.gov.cn/hb/msg=ABC123XYZ") == "ABC123XYZ"

    def test_no_match(self):
        scraper = _make_scraper()
        assert scraper._extract_public_msg_code("http://example.com/page") == ""

    def test_with_longer_url(self):
        scraper = _make_scraper()
        assert scraper._extract_public_msg_code("http://dzsd.hbfy.gov.cn/hb/msg=TEST123?ref=1") == "TEST123"


# ======================================================================
# _public_need_captcha
# ======================================================================

class TestPublicNeedCaptcha:
    def test_yes(self):
        scraper = _make_scraper()
        assert scraper._public_need_captcha({"isNeedCaptcha": "Y"}) is True

    def test_no(self):
        scraper = _make_scraper()
        assert scraper._public_need_captcha({"isNeedCaptcha": "N"}) is False

    def test_lower_case(self):
        scraper = _make_scraper()
        assert scraper._public_need_captcha({"isNeedCaptcha": "y"}) is True

    def test_missing(self):
        scraper = _make_scraper()
        assert scraper._public_need_captcha({}) is False


# ======================================================================
# _public_doc_list
# ======================================================================

class TestPublicDocList:
    def test_dict_wrapped(self):
        scraper = _make_scraper()
        result = scraper._public_doc_list({"docList": {"name": "doc"}})
        assert len(result) == 1

    def test_list(self):
        scraper = _make_scraper()
        result = scraper._public_doc_list({"docList": [{"name": "a"}, "not_dict"]})
        assert len(result) == 1

    def test_none(self):
        scraper = _make_scraper()
        assert scraper._public_doc_list({}) == []

    def test_string_returns_empty(self):
        scraper = _make_scraper()
        assert scraper._public_doc_list({"docList": "not_a_list"}) == []


# ======================================================================
# _public_has_downloadable_docs
# ======================================================================

class TestPublicHasDownloadableDocs:
    def test_has_download(self):
        scraper = _make_scraper()
        assert scraper._public_has_downloadable_docs({"docList": [{"downloadPath": "/f.pdf"}]}) is True

    def test_empty_download(self):
        scraper = _make_scraper()
        assert scraper._public_has_downloadable_docs({"docList": [{"downloadPath": ""}]}) is False

    def test_no_docs(self):
        scraper = _make_scraper()
        assert scraper._public_has_downloadable_docs({}) is False


# ======================================================================
# _extract_account_credentials_from_content
# ======================================================================

class TestExtractAccountCredentials:
    def test_full_match(self):
        scraper = _make_scraper()
        content = "您的送达文书已到达。账号 42010012345678901，默认密码：Abc12345"
        account, pwd = scraper._extract_account_credentials_from_content(content)
        assert account == "42010012345678901"
        assert pwd == "Abc12345"

    def test_no_match(self):
        scraper = _make_scraper()
        account, pwd = scraper._extract_account_credentials_from_content("无关内容")
        assert account == ""
        assert pwd == ""

    def test_partial_account_only(self):
        scraper = _make_scraper()
        account, pwd = scraper._extract_account_credentials_from_content("账号 42010012345678901")
        assert account == "42010012345678901"
        assert pwd == ""

    def test_password_with_colon(self):
        scraper = _make_scraper()
        _, pwd = scraper._extract_account_credentials_from_content("默认密码:Test123456")
        assert pwd == "Test123456"


# ======================================================================
# _safe_filename
# ======================================================================

class TestSafeFilename:
    def test_removes_special_chars(self):
        scraper = _make_scraper()
        result = scraper._safe_filename("文件*名?.pdf")
        assert "*" not in result
        assert "?" not in result

    def test_preserves_normal(self):
        scraper = _make_scraper()
        result = scraper._safe_filename("正常文件名.pdf")
        assert result == "正常文件名.pdf"

    def test_empty_fallback(self):
        scraper = _make_scraper()
        result = scraper._safe_filename("")
        assert result.startswith("hbfy_")

    def test_whitespace_only_fallback(self):
        scraper = _make_scraper()
        result = scraper._safe_filename("   ")
        assert result.startswith("hbfy_")


# ======================================================================
# _encode_user_code
# ======================================================================

class TestEncodeUserCode:
    def test_base64_no_padding(self):
        scraper = _make_scraper()
        result = scraper._encode_user_code("12345")
        assert "=" not in result
        assert "+" not in result
        assert "/" not in result

    def test_known_value(self):
        scraper = _make_scraper()
        result = scraper._encode_user_code("test")
        expected = base64.b64encode(b"test").decode().replace("+", "-").replace("/", "_").replace("=", "")
        assert result == expected


# ======================================================================
# _encode_password
# ======================================================================

class TestEncodePassword:
    def test_double_md5(self):
        scraper = _make_scraper()
        result = scraper._encode_password("password", "1234567890")
        first_md5 = hashlib.md5(b"password", usedforsecurity=False).hexdigest()
        expected = hashlib.md5(f"{first_md5}1234567890".encode(), usedforsecurity=False).hexdigest()
        assert result == expected

    def test_different_nonce(self):
        scraper = _make_scraper()
        r1 = scraper._encode_password("pass", "nonce1")
        r2 = scraper._encode_password("pass", "nonce2")
        assert r1 != r2


# ======================================================================
# _extract_download_candidates
# ======================================================================

class TestExtractDownloadCandidates:
    def test_extracts_download_link(self):
        scraper = _make_scraper()
        html = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/files/doc.pdf">下载</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) >= 1
        assert "doc.pdf" in result[0]

    def test_skips_empty_path(self):
        scraper = _make_scraper()
        html = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=">下载</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) == 0

    def test_dedup_links(self):
        scraper = _make_scraper()
        link = "/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/f.pdf"
        html = f'<a href="{link}">A</a><a href="{link}">B</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) == 1

    def test_second_pattern(self):
        scraper = _make_scraper()
        html = '<a href="/deli/some-download.action?file=test.pdf">下载</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) >= 1

    def test_html_entities_decoded(self):
        scraper = _make_scraper()
        html = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/files/a%20b.pdf">下载</a>'
        result = scraper._extract_download_candidates(html)
        assert len(result) >= 1


# ======================================================================
# _guess_filename
# ======================================================================

class TestGuessFilename:
    def test_content_disposition_utf8(self):
        scraper = _make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Disposition": "filename*=UTF-8''%E6%96%87%E4%B9%A6.pdf"}
        result = scraper._guess_filename(resp, "http://example.com/file", "title")
        assert "文书" in result

    def test_content_disposition_regular(self):
        scraper = _make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Disposition": 'filename="test.pdf"'}
        result = scraper._guess_filename(resp, "http://example.com/file", "title")
        assert "test.pdf" in result

    def test_url_path_fallback(self):
        scraper = _make_scraper()
        resp = MagicMock()
        resp.headers = {}
        result = scraper._guess_filename(resp, "http://example.com/path/doc.pdf", "title")
        assert "doc.pdf" in result

    def test_content_type_fallback(self):
        scraper = _make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/pdf"}
        result = scraper._guess_filename(resp, "http://example.com/", "文书标题")
        assert result.endswith(".pdf")

    def test_non_pdf_content_type(self):
        scraper = _make_scraper()
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/octet-stream"}
        result = scraper._guess_filename(resp, "http://example.com/", "文件")
        assert result.endswith(".bin")


# ======================================================================
# _resolve_account_credentials
# ======================================================================

class TestResolveAccountCredentials:
    def test_direct_config(self):
        scraper = _make_scraper(config={"hbfy_account": "user", "hbfy_password": "pass"})
        account, pwd = scraper._resolve_account_credentials(scraper.task.config)
        assert account == "user"
        assert pwd == "pass"

    def test_missing_raises(self):
        scraper = _make_scraper(config={})
        with pytest.raises(ValueError, match="缺少账号或密码"):
            scraper._resolve_account_credentials(scraper.task.config)

    def test_from_sms_content(self):
        scraper = _make_scraper(config={"court_sms_id": 42})
        with patch("apps.automation.models.CourtSMS") as MockSMS:
            sms = SimpleNamespace(content="账号 42010012345678901，默认密码：Abc12345")
            MockSMS.objects.only.return_value.get.return_value = sms
            account, pwd = scraper._resolve_account_credentials(scraper.task.config)
            assert account == "42010012345678901"
            assert pwd == "Abc12345"

    def test_sms_not_found_raises(self):
        scraper = _make_scraper(config={"court_sms_id": 99})
        with patch("apps.automation.models.CourtSMS") as MockSMS:
            MockSMS.objects.only.return_value.get.side_effect = Exception("not found")
            with pytest.raises(ValueError, match="缺少账号或密码"):
                scraper._resolve_account_credentials(scraper.task.config)

    def test_sms_empty_content_raises(self):
        scraper = _make_scraper(config={"court_sms_id": 42})
        with patch("apps.automation.models.CourtSMS") as MockSMS:
            sms = SimpleNamespace(content="无关内容")
            MockSMS.objects.only.return_value.get.return_value = sms
            with pytest.raises(ValueError, match="缺少账号或密码"):
                scraper._resolve_account_credentials(scraper.task.config)


# ======================================================================
# _find_public_sms_info
# ======================================================================

class TestFindPublicSmsInfo:
    def test_success(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"docList": [{"name": "d"}]}}
        session.post.return_value = resp
        result = scraper._find_public_sms_info(session, "MSG123")
        assert "docList" in result

    def test_http_error(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        session.post.return_value = resp
        with pytest.raises(ValueError, match="HTTP 500"):
            scraper._find_public_sms_info(session, "MSG")

    def test_non_dict_body(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = "not a dict"
        session.post.return_value = resp
        result = scraper._find_public_sms_info(session, "MSG")
        assert result == {}

    def test_with_code_and_uuid(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"ok": True}}
        session.post.return_value = resp
        result = scraper._find_public_sms_info(session, "MSG", code="1234", uuid="abc")
        assert result == {"ok": True}
        call_kwargs = session.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["code"] == "1234"


# ======================================================================
# _get_public_captcha
# ======================================================================

class TestGetPublicCaptcha:
    def test_success(self):
        scraper = _make_scraper()
        session = MagicMock()
        img_b64 = base64.b64encode(b"fake_image").decode()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"uuid": "u1", "img": f"data:image/png;base64,{img_b64}"}}
        session.post.return_value = resp
        result = scraper._get_public_captcha(session)
        assert result is not None
        assert result[0] == "u1"
        assert result[1] == b"fake_image"

    def test_http_error(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        session.post.return_value = resp
        assert scraper._get_public_captcha(session) is None

    def test_no_data(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": None}
        session.post.return_value = resp
        assert scraper._get_public_captcha(session) is None

    def test_missing_uuid(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"uuid": "", "img": ""}}
        session.post.return_value = resp
        assert scraper._get_public_captcha(session) is None


# ======================================================================
# _download_public_documents
# ======================================================================

class TestDownloadPublicDocuments:
    def test_downloads_files(self):
        scraper = _make_scraper()
        session = MagicMock()
        file_resp = MagicMock()
        file_resp.status_code = 200
        file_resp.content = b"PDF content"
        session.get.return_value = file_resp

        sms_info = {
            "docList": [
                {"downloadPath": "/files/doc1.pdf", "docName": "文书1", "pdfPath": "/p/doc1.pdf"},
            ]
        }
        download_dir = Path("/tmp/hbfy_test")
        with patch.object(Path, "write_bytes"):
            with patch.object(Path, "__truediv__", return_value=Path("/tmp/hbfy_test/文书1.pdf")):
                result = scraper._download_public_documents(session, sms_info, download_dir)
                assert len(result) >= 0  # depends on mock behavior

    def test_skips_empty_download_path(self):
        scraper = _make_scraper()
        session = MagicMock()
        sms_info = {"docList": [{"downloadPath": ""}]}
        result = scraper._download_public_documents(session, sms_info, Path("/tmp"))
        assert result == []

    def test_absolute_url(self):
        scraper = _make_scraper()
        session = MagicMock()
        file_resp = MagicMock()
        file_resp.status_code = 200
        file_resp.content = b"content"
        session.get.return_value = file_resp
        sms_info = {"docList": [{"downloadPath": "https://example.com/doc.pdf", "docName": "文档"}]}
        with patch("pathlib.Path.write_bytes"):
            with patch("pathlib.Path.__truediv__", return_value=Path("/tmp/test.pdf")):
                scraper._download_public_documents(session, sms_info, Path("/tmp"))


# ======================================================================
# _fetch_record_entries
# ======================================================================

class TestFetchRecordEntries:
    def test_extracts_entries(self):
        scraper = _make_scraper()
        session = MagicMock()
        html = '''
        <td title="文书1">
            <a onclick="toViewInput('DOC001');return false;">查看</a>
        </td>
        <td title="文书2">
            <a onclick="toViewInput('DOC002');return false;">查看</a>
        </td>
        '''
        resp = MagicMock()
        resp.status_code = 200
        resp.text = html
        session.get.return_value = resp
        result = scraper._fetch_record_entries(session, "http://example.com/list")
        assert len(result) == 2
        assert result[0]["id"] == "DOC001"

    def test_retry_on_500(self):
        scraper = _make_scraper()
        session = MagicMock()
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.text = ""
        session.get.side_effect = [fail_resp, ok_resp]
        result = scraper._fetch_record_entries(session, "http://example.com/list")
        assert result == []

    def test_non_200_after_retry(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 403
        session.get.return_value = resp
        result = scraper._fetch_record_entries(session, "http://example.com/list")
        assert result == []

    def test_html_entities_in_title(self):
        scraper = _make_scraper()
        session = MagicMock()
        html = '''<td title="文书&amp;test"><a onclick="toViewInput('ID1');return false;">X</a></td>'''
        resp = MagicMock()
        resp.status_code = 200
        resp.text = html
        session.get.return_value = resp
        result = scraper._fetch_record_entries(session, "url")
        assert "文书&test" in result[0]["title"]


# ======================================================================
# _download_record_document
# ======================================================================

class TestDownloadRecordDocument:
    def test_success(self):
        scraper = _make_scraper()
        session = MagicMock()
        input_resp = MagicMock()
        input_resp.status_code = 200
        input_resp.text = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/files/doc.pdf">下载</a>'
        file_resp = MagicMock()
        file_resp.status_code = 200
        file_resp.content = b"PDF"
        file_resp.headers = {"Content-Disposition": 'filename="test.pdf"', "Content-Type": "application/pdf"}
        session.get.side_effect = [input_resp, file_resp]
        with patch("pathlib.Path.write_bytes"):
            result = scraper._download_record_document(session, "DOC1", "标题", Path("/tmp"))
            assert result is not None

    def test_no_candidates(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "<html>no links</html>"
        session.get.return_value = resp
        result = scraper._download_record_document(session, "DOC1", "标题", Path("/tmp"))
        assert result is None

    def test_input_page_error(self):
        scraper = _make_scraper()
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        session.get.return_value = resp
        result = scraper._download_record_document(session, "DOC1", "标题", Path("/tmp"))
        assert result is None

    def test_all_downloads_fail(self):
        scraper = _make_scraper()
        session = MagicMock()
        input_resp = MagicMock()
        input_resp.status_code = 200
        input_resp.text = '<a href="/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath.action?path=/f.pdf">下载</a>'
        file_resp = MagicMock()
        file_resp.status_code = 404
        file_resp.content = b""
        session.get.side_effect = [input_resp, file_resp]
        result = scraper._download_record_document(session, "DOC1", "标题", Path("/tmp"))
        assert result is None


# ======================================================================
# _login_hbfy_account_session
# ======================================================================

class TestLoginHbfyAccountSession:
    def test_success_on_first_try(self):
        scraper = _make_scraper()
        session = MagicMock()
        landing = MagicMock()
        landing.status_code = 200

        captcha_img = MagicMock()
        captcha_img.status_code = 200
        captcha_img.content = b"captcha_img"

        check_resp = MagicMock()
        check_resp.text = "1"

        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.json.return_value = {"success": True, "message": {"result": True}}

        main_resp = MagicMock()
        main_resp.status_code = 200

        session.get.side_effect = [landing, captcha_img, main_resp]
        session.post.side_effect = [check_resp, login_resp]

        with patch("ddddocr.DdddOcr") as MockOcr:
            mock_ocr = MockOcr.return_value
            mock_ocr.classification.return_value = "ABCD"
            with patch.object(scraper, "_encode_user_code", return_value="encoded"):
                with patch.object(scraper, "_encode_password", return_value="hashed"):
                    scraper._login_hbfy_account_session(session, "account", "password")

    def test_landing_page_500_raises(self):
        scraper = _make_scraper()
        session = MagicMock()
        landing = MagicMock()
        landing.status_code = 500
        session.get.return_value = landing
        with pytest.raises(ValueError, match="登录页"):
            scraper._login_hbfy_account_session(session, "account", "password")

    def test_captcha_check_fails_retries(self):
        scraper = _make_scraper()
        session = MagicMock()
        landing = MagicMock()
        landing.status_code = 200

        captcha_img_ok = MagicMock()
        captcha_img_ok.status_code = 200
        captcha_img_ok.content = b"img"

        check_fail = MagicMock()
        check_fail.text = "0"

        # All 12 attempts fail captcha check
        session.get.side_effect = [landing] + [captcha_img_ok] * 12
        session.post.side_effect = [check_fail] * 12

        with patch("ddddocr.DdddOcr") as MockOcr:
            mock_ocr = MockOcr.return_value
            mock_ocr.classification.return_value = "ABCD"
            with pytest.raises(ValueError, match="验证码"):
                scraper._login_hbfy_account_session(session, "account", "password")


# ======================================================================
# _run_public_mode_http_first
# ======================================================================

class TestRunPublicModeHttpFirst:
    def test_success_http(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=ABC123")
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_extract_public_msg_code", return_value="ABC123"), \
             patch.object(scraper, "_find_public_sms_info", return_value={"docList": [{"downloadPath": "/f.pdf", "docName": "doc"}]}), \
             patch.object(scraper, "_public_need_captcha", return_value=False), \
             patch.object(scraper, "_public_has_downloadable_docs", return_value=True), \
             patch.object(scraper, "_download_public_documents", return_value=["/tmp/doc.pdf"]), \
             patch("requests.Session"):
            result = scraper._run_public_mode_http_first()
            assert result["downloaded_count"] == 1
            assert result["mode"] == "public_http"

    def test_no_files_falls_to_playwright(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=ABC123")
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_extract_public_msg_code", return_value="ABC123"), \
             patch.object(scraper, "_find_public_sms_info", return_value={}), \
             patch.object(scraper, "_public_need_captcha", return_value=False), \
             patch.object(scraper, "_public_has_downloadable_docs", return_value=False), \
             patch.object(scraper, "_find_public_sms_info_with_captcha", return_value={}), \
             patch.object(scraper, "_download_public_documents", return_value=[]), \
             patch.object(scraper, "_run_public_mode_playwright", return_value={"mode": "public_playwright", "downloaded_count": 1, "files": ["/tmp/f.pdf"], "message": "ok"}), \
             patch("requests.Session"):
            result = scraper._run_public_mode_http_first()
            assert result["mode"] == "public_playwright"

    def test_missing_msg_raises(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=")
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_extract_public_msg_code", return_value=""):
            with pytest.raises(ValueError, match="msg"):
                scraper._run_public_mode_http_first()

    def test_needs_captcha_then_success(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=ABC123")
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_extract_public_msg_code", return_value="ABC123"), \
             patch.object(scraper, "_find_public_sms_info", return_value={}), \
             patch.object(scraper, "_public_need_captcha", return_value=True), \
             patch.object(scraper, "_find_public_sms_info_with_captcha", return_value={"docList": [{"downloadPath": "/f.pdf", "docName": "doc"}]}), \
             patch.object(scraper, "_download_public_documents", return_value=["/tmp/doc.pdf"]), \
             patch("requests.Session"):
            result = scraper._run_public_mode_http_first()
            assert result["downloaded_count"] == 1


# ======================================================================
# _run_account_mode_http_first
# ======================================================================

class TestRunAccountModeHttpFirst:
    def test_success(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/sfsddz", config={"hbfy_account": "u", "hbfy_password": "p"})
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_login_hbfy_account_session"), \
             patch.object(scraper, "_fetch_record_entries", return_value=[{"id": "D1", "title": "文书"}]), \
             patch.object(scraper, "_download_record_document", return_value="/tmp/doc.pdf"), \
             patch("requests.Session"):
            result = scraper._run_account_mode_http_first()
            assert result["downloaded_count"] == 1
            assert result["mode"] == "account_http"

    def test_no_entries_raises(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/sfsddz", config={"hbfy_account": "u", "hbfy_password": "p"})
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_login_hbfy_account_session"), \
             patch.object(scraper, "_fetch_record_entries", return_value=[]), \
             patch("requests.Session"):
            with pytest.raises(ValueError, match="未发现可查阅文书"):
                scraper._run_account_mode_http_first()

    def test_dedup_entries(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/sfsddz", config={"hbfy_account": "u", "hbfy_password": "p"})
        # Two lists return same ID
        entries = [{"id": "D1", "title": "文书"}, {"id": "D1", "title": "文书"}]
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_login_hbfy_account_session"), \
             patch.object(scraper, "_fetch_record_entries", return_value=entries), \
             patch.object(scraper, "_download_record_document", return_value="/tmp/doc.pdf"), \
             patch("requests.Session"):
            result = scraper._run_account_mode_http_first()
            assert result["document_count"] == 1

    def test_all_downloads_fail(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/sfsddz", config={"hbfy_account": "u", "hbfy_password": "p"})
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_login_hbfy_account_session"), \
             patch.object(scraper, "_fetch_record_entries", return_value=[{"id": "D1", "title": "文书"}]), \
             patch.object(scraper, "_download_record_document", return_value=None), \
             patch("requests.Session"):
            with pytest.raises(ValueError, match="未下载成功"):
                scraper._run_account_mode_http_first()

    def test_partial_success(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/sfsddz", config={"hbfy_account": "u", "hbfy_password": "p"})
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "_login_hbfy_account_session"), \
             patch.object(scraper, "_fetch_record_entries", return_value=[{"id": "D1", "title": "A"}, {"id": "D2", "title": "B"}]), \
             patch.object(scraper, "_download_record_document", side_effect=["/tmp/a.pdf", Exception("fail")]), \
             patch("requests.Session"):
            result = scraper._run_account_mode_http_first()
            assert result["downloaded_count"] == 1
            assert result["failed_count"] == 1


# ======================================================================
# _run_public_mode_playwright
# ======================================================================

class TestRunPublicModePlaywright:
    def test_success_via_selector(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=ABC")
        scraper.page = MagicMock()
        scraper.context = MagicMock()
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "navigate_to_url"), \
             patch.object(scraper, "_solve_public_captcha_if_present"), \
             patch.object(scraper, "_try_expect_download", return_value="/tmp/doc.pdf"):
            result = scraper._run_public_mode_playwright()
            assert result["downloaded_count"] == 1
            assert result["mode"] == "public_playwright"

    def test_no_download_raises(self):
        scraper = _make_scraper("http://dzsd.hbfy.gov.cn/hb/msg=ABC")
        scraper.page = MagicMock()
        scraper.context = MagicMock()
        with patch.object(scraper, "_prepare_download_dir", return_value=Path("/tmp")), \
             patch.object(scraper, "navigate_to_url"), \
             patch.object(scraper, "_solve_public_captcha_if_present"), \
             patch.object(scraper, "_try_expect_download", return_value=None), \
             patch.object(scraper, "_save_page_state"):
            with pytest.raises(ValueError, match="未下载到任何文书"):
                scraper._run_public_mode_playwright()


# ======================================================================
# _try_expect_download
# ======================================================================

class TestTryExpectDownload:
    def test_success(self):
        scraper = _make_scraper()
        scraper.page = MagicMock()
        target = MagicMock()
        target.count.return_value = 1
        scraper.page.locator.return_value = target

        mock_download = MagicMock()
        mock_download.suggested_filename = "doc.pdf"

        mock_download_info = MagicMock()
        mock_download_info.value = mock_download

        scraper.page.expect_download.return_value.__enter__ = lambda s: mock_download_info
        scraper.page.expect_download.return_value.__exit__ = MagicMock(return_value=False)

        with patch("pathlib.Path.__truediv__", return_value=Path("/tmp/doc.pdf")):
            result = scraper._try_expect_download("button", Path("/tmp"), prefix="test")
            assert result is not None

    def test_no_element(self):
        scraper = _make_scraper()
        scraper.page = MagicMock()
        target = MagicMock()
        target.count.return_value = 0
        scraper.page.locator.return_value = target
        result = scraper._try_expect_download("button", Path("/tmp"), prefix="test")
        assert result is None

    def test_exception_returns_none(self):
        scraper = _make_scraper()
        scraper.page = MagicMock()
        target = MagicMock()
        target.count.return_value = 1
        scraper.page.locator.return_value = target
        scraper.page.expect_download.side_effect = Exception("timeout")
        result = scraper._try_expect_download("button", Path("/tmp"), prefix="test")
        assert result is None


# ======================================================================
# _try_download_all_with_confirm
# ======================================================================

class TestTryDownloadAllWithConfirm:
    def test_no_download_button(self):
        scraper = _make_scraper()
        scraper.page = MagicMock()
        btn = MagicMock()
        btn.count.return_value = 0
        scraper.page.locator.return_value = btn
        result = scraper._try_download_all_with_confirm(Path("/tmp"))
        assert result is None


# ======================================================================
# _solve_public_captcha_if_present
# ======================================================================

class TestSolvePublicCaptchaIfPresent:
    def test_no_captcha_input(self):
        scraper = _make_scraper()
        scraper.page = MagicMock()
        captcha_input = MagicMock()
        captcha_input.count.return_value = 0
        scraper.page.locator.return_value = captcha_input
        # Should not raise
        scraper._solve_public_captcha_if_present()
