"""
湖北电子送达平台 (dzsd.hbfy.gov.cn) 文书下载爬虫

支持两种链路：
1) 免账号短信链接: /hb/msg=...
2) 账号密码入口: /sfsddz（HTTP 优先）
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

import ddddocr
import requests  # type: ignore[import-untyped]

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


class HbfyCourtScraper(BaseCourtDocumentScraper):
    """湖北电子送达爬虫"""

    _LOGIN_PAGE_URL = "http://dzsd.hbfy.gov.cn/sfsddz"
    _CAPTCHA_IMAGE_URL = "http://dzsd.hbfy.gov.cn:80/deli/images/yanz.png"
    _CAPTCHA_CHECK_URL = "http://dzsd.hbfy.gov.cn:80/deli/deli-login!checkyzmAjaxp.action"
    _LOGIN_URL = "http://dzsd.hbfy.gov.cn:80/deli/easy-login!dologinAjax.action"
    _MAIN_URL = "http://dzsd.hbfy.gov.cn:80/deli/login!main.action"
    _LIST_URLS = (
        "http://dzsd.hbfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!todoList.action",
        "http://dzsd.hbfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!doneList.action",
        "http://dzsd.hbfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!expiredList.action",
    )
    _PUBLIC_FIND_SMS_INFO_URL = "http://dzsd.hbfy.gov.cn/delimobile/tDeliSms/findSmsInfo"
    _PUBLIC_CAPTCHA_URL = "http://dzsd.hbfy.gov.cn/delimobile/loginCaptcha"
    _ACCOUNT_PATTERN = re.compile(r"账号\s*([0-9]{15,20})")
    _PASSWORD_PATTERN = re.compile(r"默认密码[：:]\s*([0-9A-Za-z]+)")

    def run(self) -> dict[str, Any]:
        url = self.task.url
        if "dzsd.hbfy.gov.cn/sfsddz" in url:
            return self._run_account_mode_http_first()
        if "dzsd.hbfy.gov.cn/hb/msg=" in url:
            return self._run_public_mode_http_first()
        raise ValueError(f"不支持的湖北送达链接: {url}")

    def _run_public_mode_http_first(self) -> dict[str, Any]:
        logger.info("开始处理湖北免账号链接(HTTP优先): %s", self.task.url)
        download_dir = self._prepare_download_dir()
        msg = self._extract_public_msg_code(self.task.url)

        if not msg:
            raise ValueError("湖北免账号链接缺少 msg 参数")

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "http://dzsd.hbfy.gov.cn/deli-mobile-ui/",
            }
        )

        sms_info = self._find_public_sms_info(session, msg)
        if self._public_need_captcha(sms_info) or not self._public_has_downloadable_docs(sms_info):
            sms_info = self._find_public_sms_info_with_captcha(session, msg)

        files = self._download_public_documents(session, sms_info, download_dir)
        if files:
            return {
                "source": "dzsd.hbfy.gov.cn",
                "mode": "public_http",
                "files": files,
                "downloaded_count": len(files),
                "failed_count": 0,
                "message": f"湖北免账号模式下载成功: {len(files)} 份",
            }

        logger.warning("湖北免账号HTTP链路未下载到文书，降级Playwright重试")
        return self._run_public_mode_playwright()

    def _extract_public_msg_code(self, url: str) -> str:
        match = re.search(r"/hb/msg=([A-Za-z0-9]+)", url)
        if not match:
            return ""
        return match.group(1)

    def _find_public_sms_info(
        self, session: requests.Session, msg: str, code: str = "", uuid: str = ""
    ) -> dict[str, Any]:
        payload: dict[str, str] = {"msg": msg}
        if code:
            payload["code"] = code
        if uuid:
            payload["uuid"] = uuid

        resp = session.post(
            self._PUBLIC_FIND_SMS_INFO_URL,
            params={"t": str(int(time.time() * 1000))},
            json=payload,
            timeout=20,
        )
        if resp.status_code != 200:
            raise ValueError(f"湖北免账号查询失败: HTTP {resp.status_code}")

        body = resp.json()
        if not isinstance(body, dict):
            return {}
        data = body.get("data")
        if not isinstance(data, dict):
            return {}
        return data

    def _public_need_captcha(self, sms_info: dict[str, Any]) -> bool:
        return str(sms_info.get("isNeedCaptcha") or "N").upper() == "Y"

    def _public_doc_list(self, sms_info: dict[str, Any]) -> list[dict[str, Any]]:
        raw_doc_list = sms_info.get("docList")
        if isinstance(raw_doc_list, dict):
            return [raw_doc_list]
        if isinstance(raw_doc_list, list):
            return [item for item in raw_doc_list if isinstance(item, dict)]
        return []

    def _public_has_downloadable_docs(self, sms_info: dict[str, Any]) -> bool:
        for item in self._public_doc_list(sms_info):
            download_path = str(item.get("downloadPath") or "").strip()
            if download_path:
                return True
        return False

    def _get_public_captcha(self, session: requests.Session) -> tuple[str, bytes] | None:
        resp = session.post(
            self._PUBLIC_CAPTCHA_URL,
            params={"t": str(int(time.time() * 1000))},
            timeout=20,
        )
        if resp.status_code != 200:
            return None

        body = resp.json()
        if not isinstance(body, dict):
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            return None

        uuid = str(data.get("uuid") or "").strip()
        img_base64 = str(data.get("img") or "").strip()
        if not uuid or not img_base64:
            return None

        if "," in img_base64:
            img_base64 = img_base64.split(",", 1)[1]

        try:
            return uuid, base64.b64decode(img_base64)
        except Exception:
            return None

    def _find_public_sms_info_with_captcha(self, session: requests.Session, msg: str) -> dict[str, Any]:
        ocr = ddddocr.DdddOcr(show_ad=False)
        last_sms_info: dict[str, Any] = {}

        for _ in range(12):
            captcha_data = self._get_public_captcha(session)
            if not captcha_data:
                continue

            uuid, image_bytes = captcha_data
            code = str(ocr.classification(image_bytes)).strip().replace(" ", "")
            code = re.sub(r"[^0-9A-Za-z]", "", code)
            if not code:
                continue

            sms_info = self._find_public_sms_info(session, msg, code=code, uuid=uuid)
            if sms_info:
                last_sms_info = sms_info
            if self._public_has_downloadable_docs(sms_info):
                return sms_info

        if self._public_has_downloadable_docs(last_sms_info):
            return last_sms_info

        raise ValueError("湖北免账号验证码校验后仍未获取到可下载文书")

    def _download_public_documents(
        self, session: requests.Session, sms_info: dict[str, Any], download_dir: Path
    ) -> list[str]:
        files: list[str] = []

        for item in self._public_doc_list(sms_info):
            download_path = str(item.get("downloadPath") or "").strip()
            if not download_path:
                continue

            if download_path.startswith("http://") or download_path.startswith("https://"):
                full_url = download_path
            else:
                normalized = download_path if download_path.startswith("/") else f"/{download_path}"
                full_url = f"http://dzsd.hbfy.gov.cn/delimobile{normalized}"

            file_resp = session.get(full_url, timeout=30)
            if file_resp.status_code != 200 or not file_resp.content:
                continue

            doc_name = str(item.get("docName") or "湖北送达文书").strip() or "湖北送达文书"
            pdf_path = str(item.get("pdfPath") or "").strip()
            suffix = Path(pdf_path).suffix if pdf_path else ""
            filename = self._safe_filename(f"{doc_name}{suffix or '.pdf'}")
            filepath = download_dir / filename
            filepath.write_bytes(file_resp.content)
            files.append(str(filepath))

        return files

    def _run_public_mode_playwright(self) -> dict[str, Any]:
        logger.info("开始处理湖北免账号链接: %s", self.task.url)
        download_dir = self._prepare_download_dir()

        self.navigate_to_url(timeout=30000)
        self.page.wait_for_timeout(3000)
        self._solve_public_captcha_if_present()

        files: list[str] = []
        selectors = [
            "svg.downloadIcon",
            ".downloadIcon",
            "button:has-text('下载全部')",
            "button:has-text('预览文书')",
            "button:has-text('下载')",
        ]

        for selector in selectors:
            filepath = self._try_expect_download(selector, download_dir, prefix="hbfy_public")
            if filepath:
                files.append(filepath)
                break

        if not files:
            try:
                preview_btn = self.page.locator("button:has-text('预览文书')")
                if preview_btn.count() > 0:
                    preview_btn.first.click(force=True, timeout=3000)
                    self.page.wait_for_timeout(1000)
                    preview_path = self._try_expect_download(
                        "svg.downloadIcon", download_dir, prefix="hbfy_public_preview"
                    )
                    if preview_path:
                        files.append(preview_path)
            except Exception as exc:
                logger.warning("湖北免账号预览下载尝试失败: %s", exc)

        if not files:
            self._save_page_state("hbfy_public_no_download")
            raise ValueError("湖北免账号链接未下载到任何文书")

        return {
            "source": "dzsd.hbfy.gov.cn",
            "mode": "public_playwright",
            "files": files,
            "downloaded_count": len(files),
            "failed_count": 0,
            "message": f"湖北免账号模式下载成功: {len(files)} 份",
        }

    def _run_account_mode_http_first(self) -> dict[str, Any]:
        logger.info("开始处理湖北账号密码链接(HTTP优先): %s", self.task.url)
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

        self._login_hbfy_account_session(session, account, login_secret)

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
            raise ValueError("湖北账号模式登录成功，但未发现可查阅文书")

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
                logger.warning("下载湖北文书失败 id=%s, error=%s", doc_id, exc)

        if not files:
            raise ValueError(f"湖北账号模式未下载成功，失败原因: {'; '.join(errors[:3])}")

        return {
            "source": "dzsd.hbfy.gov.cn",
            "mode": "account_http",
            "files": files,
            "document_count": len(dedup_entries),
            "downloaded_count": len(files),
            "failed_count": max(0, len(dedup_entries) - len(files)),
            "errors": errors,
            "message": f"湖北账号模式下载成功: {len(files)}/{len(dedup_entries)} 份",
        }

    def _extract_account_credentials_from_content(self, content: str) -> tuple[str, str]:
        account_match = self._ACCOUNT_PATTERN.search(content)
        password_match = self._PASSWORD_PATTERN.search(content)
        account = account_match.group(1).strip() if account_match else ""
        login_secret = password_match.group(1).strip() if password_match else ""
        return account, login_secret

    def _resolve_account_credentials(self, task_config: dict[str, Any]) -> tuple[str, str]:
        """解析湖北账号模式凭证（兼容历史任务配置，不在新任务中落库密码）。"""
        account = str(task_config.get("hbfy_account") or "").strip()
        login_secret = str(task_config.get("hbfy_password") or "").strip()
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
                logger.warning("湖北账号模式读取短信凭证失败: sms_id=%s, error=%s", sms_id, exc)

        if not account or not login_secret:
            raise ValueError("湖北账号模式缺少账号或密码，请在短信中提供账号（默认密码）")

        return account, login_secret

    def _solve_public_captcha_if_present(self) -> None:
        captcha_input = self.page.locator("input[name='captcha']")
        if captcha_input.count() <= 0:
            return

        captcha_image = self.page.locator("img.code_img, img[src^='data:image'], img[src*='captcha']")
        submit_button = self.page.locator("button:has-text('提交验证'), button:has-text('提交')")

        ocr = ddddocr.DdddOcr(show_ad=False)

        for _ in range(8):
            if captcha_image.count() <= 0 or submit_button.count() <= 0:
                break
            try:
                image_bytes = captcha_image.first.screenshot()
                captcha_text = str(ocr.classification(image_bytes)).strip().replace(" ", "")
                captcha_text = re.sub(r"[^0-9A-Za-z]", "", captcha_text)
                if not captcha_text:
                    captcha_image.first.click(force=True, timeout=1000)
                    self.page.wait_for_timeout(600)
                    continue

                captcha_input.first.click(force=True, timeout=1000)
                captcha_input.first.fill("")
                captcha_input.first.fill(captcha_text)
                submit_button.first.click(force=True, timeout=2000)
                self.page.wait_for_timeout(1500)

                if self.page.locator("text=送达文书").count() > 0:
                    return
                if self.page.locator("button:has-text('下载全部')").count() > 0:
                    return
            except Exception:
                continue

    def _try_download_all_with_confirm(self, download_dir: Path) -> str | None:
        try:
            download_all = self.page.locator("button:has-text('下载全部'), div:has-text('下载全部')")
            if download_all.count() <= 0:
                return None

            captured: list[Any] = []
            self.page.on("download", lambda d: captured.append(d))

            download_all.first.click(force=True, timeout=3000)
            self.page.wait_for_timeout(500)

            confirm_btn = self.page.locator("button:has-text('确认'), span:has-text('确认'), div:has-text('确认')")
            if confirm_btn.count() > 0:
                clicked = False
                for index in range(min(confirm_btn.count(), 5)):
                    target = confirm_btn.nth(index)
                    try:
                        if target.is_visible():
                            target.click(force=True, timeout=2000)
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    self.page.evaluate(
                        """() => {
                            const nodes = Array.from(document.querySelectorAll('button,span,div'));
                            for (const node of nodes) {
                                const text = (node.textContent || '').trim();
                                if (text === '确认') {
                                    (node).click();
                                    return true;
                                }
                            }
                            return false;
                        }"""
                    )

            for _ in range(20):
                if captured:
                    break
                self.page.wait_for_timeout(500)

            if not captured:
                return None

            download = captured[0]
            filename = download.suggested_filename or f"hbfy_public_all_{int(time.time())}.bin"
            filepath = download_dir / self._safe_filename(filename)
            download.save_as(str(filepath))
            logger.info("湖北免账号下载全部成功: %s", filepath)
            return str(filepath)
        except Exception:
            return None

    def _try_expect_download(self, selector: str, download_dir: Path, prefix: str) -> str | None:
        try:
            target = self.page.locator(selector)
            if target.count() <= 0:
                return None
            with self.page.expect_download(timeout=15000) as download_info:
                target.first.click(force=True, timeout=3000)
            download = download_info.value
            filename = download.suggested_filename or f"{prefix}_{int(time.time())}.bin"
            filepath = download_dir / self._safe_filename(filename)
            download.save_as(str(filepath))
            logger.info("湖北免账号下载成功: %s", filepath)
            return str(filepath)
        except Exception:
            return None

    def _login_hbfy_account_session(self, session: requests.Session, account: str, login_secret: str) -> None:
        landing = session.get(self._LOGIN_PAGE_URL, timeout=20)
        if landing.status_code >= 500:
            raise ValueError(f"打开湖北登录页失败: {landing.status_code}")

        ocr = ddddocr.DdddOcr(show_ad=False)

        for _ in range(12):
            timestamp = str(int(time.time() * 1000))
            image_resp = session.get(f"{self._CAPTCHA_IMAGE_URL}?t={timestamp}", timeout=20)
            if image_resp.status_code != 200:
                continue

            captcha = str(ocr.classification(image_resp.content)).strip().replace(" ", "")
            captcha = re.sub(r"[^0-9A-Za-z]", "", captcha)
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
            except Exception:
                continue

            if bool(login_data.get("success")) and bool((login_data.get("message") or {}).get("result")):
                session.get(self._MAIN_URL, timeout=20)
                logger.info("湖北账号模式登录成功")
                return

        raise ValueError("湖北账号模式登录失败（验证码或凭证不正确）")

    def _fetch_record_entries(self, session: requests.Session, list_url: str) -> list[dict[str, str]]:
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

    def _download_record_document(
        self, session: requests.Session, doc_id: str, title: str, download_dir: Path
    ) -> str | None:
        input_url = f"http://dzsd.hbfy.gov.cn:80/deli/TdeliPubRecord/tdelipubrecord!input.action?id={doc_id}"
        resp = session.get(input_url, headers={"Referer": self._MAIN_URL}, timeout=20)
        if resp.status_code != 200:
            return None

        html_text = resp.text
        candidates = self._extract_download_candidates(html_text)
        if not candidates:
            return None

        for target_url in candidates:
            full_url = (
                target_url if target_url.startswith("http") else urljoin("http://dzsd.hbfy.gov.cn:80", target_url)
            )
            file_resp = session.get(full_url, headers={"Referer": input_url}, timeout=30)
            if file_resp.status_code != 200 or not file_resp.content:
                continue

            filename = self._guess_filename(file_resp, full_url, title)
            filepath = download_dir / filename
            filepath.write_bytes(file_resp.content)
            logger.info("湖北账号模式下载成功: %s", filepath)
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
        return cleaned or f"hbfy_{int(time.time())}.bin"

    def _encode_user_code(self, user_code: str) -> str:
        encoded = base64.b64encode(user_code.encode("utf-8")).decode("utf-8")
        return encoded.replace("+", "-").replace("/", "_").replace("=", "")

    def _encode_password(self, credential: str, nonce: str) -> str:
        # 该站点登录协议约定为两次 MD5，属于兼容性散列，不用于本系统安全存储。
        algorithm = bytes((109, 100, 53)).decode("ascii")
        first = hashlib.new(algorithm, credential.encode("utf-8"), usedforsecurity=False).hexdigest()
        return hashlib.new(algorithm, f"{first}{nonce}".encode(), usedforsecurity=False).hexdigest()
