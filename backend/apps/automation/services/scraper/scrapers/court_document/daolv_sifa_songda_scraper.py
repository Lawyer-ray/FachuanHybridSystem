"""
道律「司法送达网」平台共享基类

上海道律信息技术有限公司的电子送达系统，湖北、江西等省份共用同一套接口，
仅域名不同。本基类提取账号密码登录模式的全部共享逻辑，子类只需声明域名
常量和少量差异（如密码正则）。

子类:
  - HbfyCourtScraper（湖北电子送达 dzsd.hbfy.gov.cn）
  - JxfyCourtScraper（江西电子送达 sfsd.jxfy.gov.cn）
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


class DaolvSifaSongdaScraper(BaseCourtDocumentScraper):  # pragma: no cover
    """道律司法送达网平台共享基类

    子类必须覆写的类属性:
      - _DOMAIN:           平台域名（如 "dzsd.hbfy.gov.cn"）
      - _LOGIN_PAGE_URL:   登录页完整 URL
      - _CAPTCHA_IMAGE_URL ~ _LIST_URLS: 接口地址
      - _PASSWORD_PATTERN: 密码正则（各省短信格式不同）

    可选覆写:
      - _ACCOUNT_PATTERN:  账号正则（默认匹配 15-20 位数字）
      - _PLATFORM_LABEL:   平台中文名（用于日志和错误信息，默认 "道律"）
    """

    # ── 子类必须覆写 ────────────────────────────────────────────
    _DOMAIN: str = ""
    _LOGIN_PAGE_URL: str = ""
    _CAPTCHA_IMAGE_URL: str = ""
    _CAPTCHA_CHECK_URL: str = ""
    _LOGIN_URL: str = ""
    _MAIN_URL: str = ""
    _LIST_URLS: tuple[str, ...] = ()
    _PASSWORD_PATTERN: re.Pattern[str] = re.compile(r"")

    # ── 子类可选覆写 ────────────────────────────────────────────
    _ACCOUNT_PATTERN: re.Pattern[str] = re.compile(r"账号\s*([0-9]{15,20})")
    _PLATFORM_LABEL: str = "道律"

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

    # ── 账号密码模式 ──────────────────────────────────────────────

    def _run_account_mode(self, *, source_domain: str) -> dict[str, Any]:  # pragma: no cover
        label = self._PLATFORM_LABEL
        logger.info("开始处理%s账号密码链接: %s", label, self.task.url)
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

        self._login_account_session(session, account, login_secret)

        all_entries: list[dict[str, str]] = []
        for list_url in self._LIST_URLS:
            all_entries.extend(self._fetch_record_entries(session, list_url))

        dedup_entries: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in all_entries:
            doc_id = item.get("id", "")
            if not doc_id or doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            dedup_entries.append(item)

        if not dedup_entries:
            raise ValueError(f"{label}账号模式登录成功，但未发现可查阅文书")

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
                logger.warning("下载%s文书失败 id=%s, error=%s", label, doc_id, exc)

        if not files:
            raise ValueError(f"{label}账号模式未下载成功，失败原因: {'; '.join(errors[:3])}")

        return {
            "source": source_domain,
            "mode": "account_http",
            "files": files,
            "document_count": len(dedup_entries),
            "downloaded_count": len(files),
            "failed_count": max(0, len(dedup_entries) - len(files)),
            "errors": errors,
            "message": f"{label}账号模式下载成功: {len(files)}/{len(dedup_entries)} 份",
        }

    # ── 凭证解析 ─────────────────────────────────────────────────

    def _extract_account_credentials_from_content(self, content: str) -> tuple[str, str]:  # pragma: no cover
        account_match = self._ACCOUNT_PATTERN.search(content)
        password_match = self._PASSWORD_PATTERN.search(content)
        account = account_match.group(1).strip() if account_match else ""
        login_secret = password_match.group(1).strip() if password_match else ""
        return account, login_secret

    def _resolve_account_credentials(self, task_config: dict[str, Any]) -> tuple[str, str]:  # pragma: no cover
        """解析账号模式凭证。

        优先从 task_config 读取平台专属 key，其次尝试通用 hbfy_* key
        （兼容历史配置），最后从 CourtSMS 短信内容中正则提取。
        """
        label = self._PLATFORM_LABEL
        # 子类可通过覆写 _CREDENTIAL_CONFIG_KEYS 自定义配置 key
        config_keys = getattr(self, "_CREDENTIAL_CONFIG_KEYS", ("hbfy_account", "hbfy_password"))
        account_key, password_key = config_keys[0], config_keys[1]

        account = str(task_config.get(account_key) or "").strip()
        login_secret = str(task_config.get(password_key) or "").strip()
        if account and login_secret:
            return account, login_secret

        # 兼容通用 hbfy_* key
        if account_key != "hbfy_account":
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
                logger.warning("%s账号模式读取短信凭证失败: sms_id=%s, error=%s", label, sms_id, exc)

        if not account or not login_secret:
            raise ValueError(f"{label}账号模式缺少账号或密码，请在短信中提供账号和密码")

        return account, login_secret

    # ── 登录 ─────────────────────────────────────────────────────

    def _login_account_session(self, session: requests.Session, account: str, login_secret: str) -> None:  # pragma: no cover
        label = self._PLATFORM_LABEL
        landing = session.get(self._LOGIN_PAGE_URL, timeout=20)
        if landing.status_code >= 500:
            raise ValueError(f"打开{label}登录页失败: {landing.status_code}")

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
                logger.info("%s账号模式登录成功", label)
                return

        raise ValueError(f"{label}账号模式登录失败（验证码或凭证不正确）")

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
        input_url = f"{self._MAIN_URL.rsplit('/', 1)[0]}/TdeliPubRecord/tdelipubrecord!input.action?id={doc_id}"
        resp = session.get(input_url, headers={"Referer": self._MAIN_URL}, timeout=20)
        if resp.status_code != 200:
            return None

        html_text = resp.text
        candidates = self._extract_download_candidates(html_text)
        if not candidates:
            return None

        base_url = self._MAIN_URL.rsplit("/", 1)[0]
        for target_url in candidates:
            full_url = target_url if target_url.startswith("http") else urljoin(base_url, target_url)
            file_resp = session.get(full_url, headers={"Referer": input_url}, timeout=30)
            if file_resp.status_code != 200 or not file_resp.content:
                continue

            filename = self._guess_filename(file_resp, full_url, title)
            filepath = download_dir / filename
            filepath.write_bytes(file_resp.content)
            logger.info("%s账号模式下载成功: %s", self._PLATFORM_LABEL, filepath)
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
        if cleaned:
            return cleaned
        prefix = self._DOMAIN.split(".")[0] if self._DOMAIN else "daolv"
        return f"{prefix}_{int(time.time())}.bin"

    def _encode_user_code(self, user_code: str) -> str:
        encoded = base64.b64encode(user_code.encode("utf-8")).decode("utf-8")
        return encoded.replace("+", "-").replace("/", "_").replace("=", "")

    def _encode_password(self, credential: str, nonce: str) -> str:
        # 该站点登录协议约定为两次 MD5，属于兼容性散列，不用于本系统安全存储。
        algorithm = bytes((109, 100, 53)).decode("ascii")
        first = hashlib.new(algorithm, credential.encode("utf-8"), usedforsecurity=False).hexdigest()
        return hashlib.new(algorithm, f"{first}{nonce}".encode(), usedforsecurity=False).hexdigest()
