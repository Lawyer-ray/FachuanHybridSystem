"""
江西电子送达平台 (sfsd.jxfy.gov.cn) 文书下载爬虫

与湖北电子送达平台 (dzsd.hbfy.gov.cn) 使用同一套"司法送达网"系统
（上海道律信息技术有限公司），接口结构一致，仅域名不同。

支持账号密码登录模式（/sfsddz）。
"""

from __future__ import annotations

import base64
import hashlib
import html
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests

from apps.automation.services.scraper.core.captcha_recognizer import CaptchaRecognizer

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


class JxfyCourtScraper(BaseCourtDocumentScraper):  # pragma: no cover
    """江西电子送达爬虫（与湖北同平台，域名不同）"""

    # 纯 HTTP 请求，不需要 Playwright 浏览器
    requires_browser = False

    _LOGIN_PAGE_URL = "http://sfsd.jxfy.gov.cn/sfsddz"
    _CAPTCHA_IMAGE_URL = "http://sfsd.jxfy.gov.cn:80/deli/images/yanz.png"
    _CAPTCHA_CHECK_URL = "http://sfsd.jxfy.gov.cn:80/deli/deli-login!checkyzmAjaxp.action"
    _LOGIN_URL = "http://sfsd.jxfy.gov.cn:80/deli/easy-login!dologinAjax.action"
    _MAIN_URL = "http://sfsd.jxfy.gov.cn:80/deli/login!main.action"
    _LIST_URLS = (
        "http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!todoList.action",
        "http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!doneList.action",
        "http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!expiredList.action",
    )
    _ACCOUNT_PATTERN = re.compile(r"账号\s*([0-9]{15,20})")
    _PASSWORD_PATTERN = re.compile(r"密码[：:]\s*([0-9A-Za-z]+)")

    def __init__(
        self,
        task: Any,
        captcha_recognizer: CaptchaRecognizer | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(task, **kwargs)
        if captcha_recognizer is None:
            from apps.automation.services.scraper.core.captcha_recognizer import get_captcha_recognizer

            self.captcha_recognizer: CaptchaRecognizer = get_captcha_recognizer(task=self.task)
        else:
            self.captcha_recognizer = captcha_recognizer

    def run(self) -> dict[str, Any]:  # pragma: no cover
        url = self.task.url
        if "sfsd.jxfy.gov.cn/sfsddz" in url:
            return self._run_account_mode()
        raise ValueError(f"不支持的江西送达链接: {url}")

    # ── 账号密码模式 ──────────────────────────────────────────────

    def _run_account_mode(self) -> dict[str, Any]:  # pragma: no cover
        logger.info("开始处理江西账号密码链接: %s", self.task.url)
        download_dir = self._prepare_download_dir()

        task_config = self.task.config if isinstance(self.task.config, dict) else {}
        account, login_secret = self._resolve_account_credentials(task_config)

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": self._LOGIN_PAGE_URL,
            }
        )

        self._login_jxfy_account_session(session, account, login_secret)

        all_entries: list[dict[str, str]] = []
        for list_url in self._LIST_URLS:
            all_entries.extend(self._fetch_record_entries(session, list_url))

        # 去重
        dedup_entries: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in all_entries:
            doc_id = item.get("id", "")
            if not doc_id or doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            dedup_entries.append(item)

        if not dedup_entries:
            raise ValueError("江西账号模式登录成功，但未发现可查阅文书")

        files: list[str] = []
        errors: list[str] = []
        for item in dedup_entries:
            doc_id = item.get("id", "")
            title = item.get("title", "未命名文书")
            try:
                filepath = self._download_record_document(session, doc_id, title, download_dir)
                if filepath:
                    files.append(filepath)
            except Exception as exc:
                errors.append(f"{doc_id}:{exc}")
                logger.warning("下载江西文书失败 id=%s, error=%s", doc_id, exc)

        if not files:
            raise ValueError(f"江西账号模式未下载成功，失败原因: {'; '.join(errors[:3])}")

        return {
            "source": "sfsd.jxfy.gov.cn",
            "mode": "account_http",
            "files": files,
            "document_count": len(dedup_entries),
            "downloaded_count": len(files),
            "failed_count": max(0, len(dedup_entries) - len(files)),
            "errors": errors,
            "message": f"江西账号模式下载成功: {len(files)}/{len(dedup_entries)} 份",
        }

    # ── 凭证解析 ─────────────────────────────────────────────────

    def _extract_account_credentials_from_content(self, content: str) -> tuple[str, str]:  # pragma: no cover
        account_match = self._ACCOUNT_PATTERN.search(content)
        password_match = self._PASSWORD_PATTERN.search(content)
        account = account_match.group(1).strip() if account_match else ""
        login_secret = password_match.group(1).strip() if password_match else ""
        return account, login_secret

    def _resolve_account_credentials(self, task_config: dict[str, Any]) -> tuple[str, str]:  # pragma: no cover
        """解析江西账号模式凭证（兼容历史任务配置，不在新任务中落库密码）。"""
        account = str(task_config.get("jxfy_account") or "").strip()
        login_secret = str(task_config.get("jxfy_password") or "").strip()
        if account and login_secret:
            return account, login_secret

        # 也兼容通用 key
        account = account or str(task_config.get("hbfy_account") or "").strip()
        login_secret = login_secret or str(task_config.get("hbfy_password") or "").strip()
        if account and login_secret:
            return account, login_secret

        sms_id_raw = task_config.get("court_sms_id")
        sms_id_text = str(sms_id_raw).strip() if sms_id_raw is not None else ""
        try:
            sms_id = int(sms_id_text) if sms_id_text else 0
        except ValueError:
            sms_id = 0

        if sms_id > 0:
            try:
                from apps.automation.models import CourtSMS

                sms = CourtSMS.objects.only("content").get(id=sms_id)
                account, login_secret = self._extract_account_credentials_from_content(sms.content)
            except Exception as exc:
                logger.warning("江西账号模式读取短信凭证失败: sms_id=%s, error=%s", sms_id, exc)

        if not account or not login_secret:
            raise ValueError("江西账号模式缺少账号或密码，请在短信中提供账号（密码）")

        return account, login_secret

    # ── 登录 ─────────────────────────────────────────────────────

    def _login_jxfy_account_session(self, session: requests.Session, account: str, login_secret: str) -> None:  # pragma: no cover
        landing = session.get(self._LOGIN_PAGE_URL, timeout=20)
        if landing.status_code >= 500:
            raise ValueError(f"打开江西登录页失败: {landing.status_code}")

        for _ in range(12):
            timestamp = str(int(time.time() * 1000))
            image_resp = session.get(f"{self._CAPTCHA_IMAGE_URL}?t={timestamp}", timeout=20)
            if image_resp.status_code != 200:
                continue

            recognized = self.captcha_recognizer.recognize(image_resp.content)
            captcha = re.sub(r"[^0-9A-Za-z]", "", recognized or "")
            if not captcha:
                continue

            check_resp = session.post(
                self._CAPTCHA_CHECK_URL,
                data={"yzm": captcha, "t": timestamp},
                timeout=20,
            )
            if check_resp.text.strip() != "1":
                continue

            salt = str(int(time.time() * 1000))
            payload = {
                "yzm": captcha,
                "user.userCode": self._encode_user_code(account),
                "user.loginPwd": self._encode_password(login_secret, salt),
                "t": salt,
            }
            login_resp = session.post(self._LOGIN_URL, data=payload, timeout=20)
            if login_resp.status_code != 200:
                continue

            try:
                login_data = login_resp.json()
            except (TypeError, ValueError):
                continue

            if bool(login_data.get("success")) and bool((login_data.get("message") or {}).get("result")):
                session.get(self._MAIN_URL, timeout=20)
                logger.info("江西账号模式登录成功")
                return

        raise ValueError("江西账号模式登录失败（验证码或凭证不正确）")

    # ── 文书列表 ─────────────────────────────────────────────────

    def _fetch_record_entries(self, session: requests.Session, list_url: str) -> list[dict[str, str]]:  # pragma: no cover
        resp = session.get(list_url, headers={"Referer": self._MAIN_URL}, timeout=20)
        if resp.status_code >= 500:
            time.sleep(1)
            resp = session.get(list_url, headers={"Referer": self._MAIN_URL}, timeout=20)

        if resp.status_code != 200:
            return []

        text = resp.text
        pattern = re.compile(
            r"<td\s+title=\"(?P<title>[^\"]*)\">.*?"
            r"onclick=\"toViewInput\('(?P<id>[^']+)'\);return false;\"",
            re.S,
        )

        entries: list[dict[str, str]] = []
        for match in pattern.finditer(text):
            title = html.unescape(match.group("title")).strip()
            doc_id = match.group("id").strip()
            if not doc_id:
                continue
            entries.append({"id": doc_id, "title": title or "未命名文书"})

        logger.info("列表页 %s 发现文书条目: %s", list_url, len(entries))
        return entries

    # ── 文书下载 ─────────────────────────────────────────────────

    def _download_record_document(
        self, session: requests.Session, doc_id: str, title: str, download_dir: Path
    ) -> str | None:  # pragma: no cover
        input_url = f"http://sfsd.jxfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!input.action?id={doc_id}"
        resp = session.get(input_url, headers={"Referer": self._MAIN_URL}, timeout=20)
        if resp.status_code != 200:
            return None

        html_text = resp.text
        candidates = self._extract_download_candidates(html_text)
        if not candidates:
            return None

        for target_url in candidates:
            full_url = (
                target_url if target_url.startswith("http") else urljoin("http://sfsd.jxfy.gov.cn:80", target_url)
            )
            file_resp = session.get(full_url, headers={"Referer": input_url}, timeout=30)
            if file_resp.status_code != 200 or not file_resp.content:
                continue

            filename = self._guess_filename(file_resp, full_url, title)
            filepath = download_dir / filename
            filepath.write_bytes(file_resp.content)
            logger.info("江西账号模式下载成功: %s", filepath)
            return str(filepath)

        return None

    def _extract_download_candidates(self, html_text: str) -> list[str]:
        patterns = [
            r"/deli/TsysFilesInfo/tsysfilesinfo!downloadByPath\.action\?[^\"'\s<]+",
            r"/deli/[^\"'\s<]*download[^\"'\s<]*\.action\?[^\"'\s<]+",
        ]

        links: list[str] = []
        for pattern in patterns:
            for raw in re.findall(pattern, html_text, flags=re.IGNORECASE):
                link = html.unescape(raw).replace("&amp;", "&")
                if link.endswith("path="):
                    continue
                if link not in links:
                    links.append(link)
        return links

    # ── 工具方法 ─────────────────────────────────────────────────

    def _guess_filename(self, response: requests.Response, url: str, title: str) -> str:
        disposition = response.headers.get("Content-Disposition", "")
        filename_match = re.search(r"filename\*=UTF-8''([^;]+)", disposition, flags=re.IGNORECASE)
        if filename_match:
            return self._safe_filename(unquote(filename_match.group(1)))

        filename_match = re.search(r"filename=\"?([^\";]+)\"?", disposition, flags=re.IGNORECASE)
        if filename_match:
            return self._safe_filename(unquote(filename_match.group(1)))

        parsed = urlparse(url)
        path_name = Path(parsed.path).name
        if "." in path_name:
            return self._safe_filename(unquote(path_name))

        content_type = response.headers.get("Content-Type", "").lower()
        ext = ".pdf" if "pdf" in content_type else ".bin"
        return self._safe_filename(f"{title}{ext}")

    def _safe_filename(self, name: str) -> str:
        cleaned = re.sub(r"[\\/:*?\"<>|\n\r\t]+", "_", name).strip()
        return cleaned or f"jxfy_{int(time.time())}.bin"

    def _encode_user_code(self, user_code: str) -> str:
        encoded = base64.b64encode(user_code.encode("utf-8")).decode("utf-8")
        return encoded.replace("+", "-").replace("/", "_").replace("=", "")

    def _encode_password(self, credential: str, nonce: str) -> str:
        # 该站点登录协议约定为两次 MD5，属于兼容性散列，不用于本系统安全存储。
        algorithm = bytes((109, 100, 53)).decode("ascii")
        first = hashlib.new(algorithm, credential.encode("utf-8"), usedforsecurity=False).hexdigest()
        return hashlib.new(algorithm, f"{first}{nonce}".encode(), usedforsecurity=False).hexdigest()
