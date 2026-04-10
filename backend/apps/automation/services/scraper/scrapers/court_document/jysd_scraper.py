"""
集约送达平台 (jysd.10102368.com) 文书下载爬虫

流程：
1. 访问集约送达链接（会重定向到 sdPc 页面）
2. 页面内嵌 iframe (sd5.sifayun.com)，在 iframe 内输入手机号并登录
3. 登录后展示文书列表，逐个下载
4. 手机号验证策略：优先尝试案件承办律师手机号，逐一尝试直到成功
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")

# 登录后页面可能出现的状态标记
_LOGIN_SUCCESS_INDICATORS = [
    "text=送达文书",
    "text=文书列表",
    "text=下载",
    "text=查看",
    ".document-list",
    ".doc-list",
    "table",
]

# 登录失败标记
_LOGIN_FAIL_INDICATORS = [
    "text=手机号不正确",
    "text=手机号错误",
    "text=验证失败",
    "text=请输入正确的手机号",
    "text=该手机号未注册",
    "text=无权查看",
    "text=号码不匹配",
]


class JysdCourtScraper(BaseCourtDocumentScraper):
    """集约送达 (jysd.10102368.com) 文书下载爬虫"""

    # 最大尝试手机号数量
    _MAX_PHONE_ATTEMPTS = 10
    # 单个手机号登录后等待时间（秒）
    _LOGIN_WAIT_SECONDS = 5
    # 页面加载等待时间（秒）
    _PAGE_LOAD_WAIT_SECONDS = 3

    def run(self) -> dict[str, Any]:
        """执行文书下载任务"""
        logger.info("开始处理集约送达链接: %s", self.task.url)

        download_dir = self._prepare_download_dir()

        # 获取律师手机号列表
        lawyer_phones = self._get_lawyer_phones()
        if not lawyer_phones:
            raise ValueError("集约送达链接需要律师手机号登录，但未找到任何律师手机号")

        logger.info("集约送达: 共 %d 个律师手机号待尝试", len(lawyer_phones))

        # 导航到目标页面
        self.navigate_to_url(timeout=30000)
        self.page.wait_for_timeout(self._PAGE_LOAD_WAIT_SECONDS * 1000)  # type: ignore[union-attr]

        # 等待 iframe 加载
        iframe = self._wait_for_iframe()
        if iframe is None:
            self._save_page_state("jysd_no_iframe")
            raise ValueError("集约送达页面未加载 iframe，无法继续")

        logger.info("集约送达: iframe 已加载, src=%s", iframe.url[:100])

        # 逐一尝试律师手机号登录
        login_success = False
        phones_to_try = lawyer_phones[: self._MAX_PHONE_ATTEMPTS]

        for idx, phone in enumerate(phones_to_try):
            logger.info("集约送达: 尝试第 %d/%d 个手机号 %s", idx + 1, len(phones_to_try), phone[:3] + "****" + phone[-4:])

            # 每次尝试前刷新页面，确保状态干净
            if idx > 0:
                self.page.reload(wait_until="domcontentloaded", timeout=30000)  # type: ignore[union-attr]
                self.page.wait_for_timeout(self._PAGE_LOAD_WAIT_SECONDS * 1000)  # type: ignore[union-attr]
                iframe = self._wait_for_iframe()
                if iframe is None:
                    logger.warning("集约送达: 刷新后 iframe 未加载，跳过手机号 %s", phone[:3] + "****")
                    continue

            login_success = self._try_login_with_phone(iframe, phone)
            if login_success:
                logger.info("集约送达: 手机号 %s 登录成功", phone[:3] + "****" + phone[-4:])
                break

            logger.info("集约送达: 手机号 %s 登录失败，尝试下一个", phone[:3] + "****" + phone[-4:])

        if not login_success:
            self._save_page_state("jysd_all_phones_failed")
            raise ValueError(f"所有 {len(phones_to_try)} 个律师手机号均无法登录集约送达平台")

        # 登录成功后下载文书
        files = self._download_documents(iframe, download_dir)

        if not files:
            self._save_page_state("jysd_no_documents")
            raise ValueError("集约送达登录成功但未下载到任何文书")

        return {
            "source": "jysd.10102368.com",
            "files": files,
            "downloaded_count": len(files),
            "failed_count": 0,
            "message": f"集约送达下载成功: {len(files)} 份",
        }

    def _get_lawyer_phones(self) -> list[str]:
        """从任务配置中获取律师手机号列表"""
        task_config = self.task.config if isinstance(self.task.config, dict) else {}
        phones = task_config.get("jysd_lawyer_phones", [])
        if isinstance(phones, list):
            return [str(p).strip() for p in phones if str(p).strip()]
        return []

    def _wait_for_iframe(self) -> Any | None:
        """等待 iframe 加载并返回 iframe 的 frame 对象"""
        assert self.page is not None

        try:
            # 等待 iframe 出现在 DOM 中
            iframe_locator = self.page.locator("iframe#mainframe, iframe[src*='sifayun']")
            if iframe_locator.count() > 0:
                self.page.wait_for_timeout(2000)
                # 获取 iframe 的 frame 对象
                for frame in self.page.frames:
                    if "sifayun.com" in (frame.url or ""):
                        return frame
                # 备选: 通过 name/id 查找
                iframe_element = iframe_locator.first
                frame = iframe_element.content_frame()  # type: ignore[operator]
                if frame is not None:
                    return frame
        except Exception as exc:
            logger.warning("集约送达: 等待 iframe 时出错: %s", exc)

        # 备选方案: 直接遍历所有 frames
        try:
            for frame in self.page.frames:
                frame_url = frame.url or ""
                if "sifayun.com" in frame_url or "10102368" in frame_url:
                    return frame
        except Exception as exc:
            logger.warning("集约送达: 遍历 frames 时出错: %s", exc)

        return None

    def _try_login_with_phone(self, iframe: Any, phone: str) -> bool:
        """尝试在 iframe 内输入手机号并登录

        Args:
            iframe: Playwright Frame 对象
            phone: 手机号码

        Returns:
            True 表示登录成功
        """
        try:
            # 定位手机号输入框
            phone_input = iframe.locator("input[placeholder*='手机号'], input[placeholder*='手机号码'], input[type='tel']")
            if phone_input.count() == 0:
                logger.warning("集约送达: iframe 内未找到手机号输入框")
                self.screenshot("jysd_no_phone_input")
                return False

            # 清空并输入手机号
            phone_input.first.click(force=True, timeout=3000)
            phone_input.first.fill("")
            phone_input.first.fill(phone)
            logger.info("集约送达: 已输入手机号")

            # 等待一小段时间模拟人工操作
            iframe.page().wait_for_timeout(500)

            # 点击登录按钮
            login_btn = iframe.locator(
                "button:has-text('登录'), "
                "button:has-text('确 定'), "
                "button:has-text('确定'), "
                ".login-btn, "
                "button[type='submit']"
            )
            if login_btn.count() > 0:
                login_btn.first.click(force=True, timeout=3000)
                logger.info("集约送达: 已点击登录按钮")
            else:
                logger.warning("集约送达: 未找到登录按钮")
                self.screenshot("jysd_no_login_btn")
                return False

            # 等待页面响应
            iframe.page().wait_for_timeout(self._LOGIN_WAIT_SECONDS * 1000)

            # 检查登录结果
            return self._check_login_result(iframe)

        except Exception as exc:
            logger.warning("集约送达: 手机号登录过程出错: %s", exc)
            return False

    def _check_login_result(self, iframe: Any) -> bool:
        """检查登录是否成功

        通过检测成功/失败标记判断登录结果
        """
        try:
            # 先检查失败标记
            for fail_selector in _LOGIN_FAIL_INDICATORS:
                try:
                    fail_elem = iframe.locator(fail_selector)
                    if fail_elem.count() > 0 and fail_elem.first.is_visible():
                        fail_text = fail_elem.first.inner_text()
                        logger.info("集约送达: 检测到登录失败标记: %s", fail_text[:50])
                        return False
                except Exception:
                    continue

            # 检查成功标记
            for success_selector in _LOGIN_SUCCESS_INDICATORS:
                try:
                    success_elem = iframe.locator(success_selector)
                    if success_elem.count() > 0 and success_elem.first.is_visible():
                        logger.info("集约送达: 检测到登录成功标记: %s", success_selector)
                        return True
                except Exception:
                    continue

            # 如果既没有失败也没有明确的成功标记，检查 URL 变化
            iframe_url = iframe.url or ""
            if "login" not in iframe_url.lower() and "index" in iframe_url.lower():
                logger.info("集约送达: URL 变化暗示登录成功")
                return True

            logger.info("集约送达: 未检测到明确的登录结果标记，视为失败")
            return False

        except Exception as exc:
            logger.warning("集约送达: 检查登录结果时出错: %s", exc)
            return False

    def _download_documents(self, iframe: Any, download_dir: Path) -> list[str]:
        """登录成功后下载文书

        Args:
            iframe: Playwright Frame 对象
            download_dir: 下载目录

        Returns:
            下载文件路径列表
        """
        files: list[str] = []
        assert self.page is not None

        # 等待文书列表加载
        iframe.page().wait_for_timeout(2000)

        # 保存登录后页面状态
        self.screenshot("jysd_after_login")

        # 尝试多种下载策略

        # 策略1: 寻找"下载全部"按钮
        download_all_btn = iframe.locator(
            "button:has-text('下载全部'), "
            "a:has-text('下载全部'), "
            "button:has-text('全部下载'), "
            ".download-all"
        )
        if download_all_btn.count() > 0:
            logger.info("集约送达: 找到下载全部按钮")
            filepath = self._try_download_with_button(download_all_btn.first, download_dir, "jysd_all")
            if filepath:
                files.append(filepath)
                return files

        # 策略2: 逐个下载文书
        doc_items = self._find_document_items(iframe)
        if doc_items:
            logger.info("集约送达: 找到 %d 个文书条目", len(doc_items))
            for idx, item in enumerate(doc_items):
                filepath = self._download_single_document(item, download_dir, idx)
                if filepath:
                    files.append(filepath)

        # 策略3: 寻找所有下载链接/按钮
        if not files:
            files = self._try_download_all_links(iframe, download_dir)

        # 策略4: 如果有预览，尝试从预览页面下载
        if not files:
            files = self._try_preview_and_download(iframe, download_dir)

        return files

    def _find_document_items(self, iframe: Any) -> list[Any]:
        """在 iframe 中查找文书条目"""
        selectors = [
            ".doc-item",
            ".document-item",
            ".case-doc",
            "tr:has(td)",
            ".list-item",
            "[class*='document']",
            "[class*='doc-']",
        ]

        for selector in selectors:
            try:
                items = iframe.locator(selector)
                if items.count() > 0:
                    result = list(items.all())
                    logger.info("集约送达: 通过 '%s' 找到 %d 个文书条目", selector, len(result))
                    return result
            except Exception:
                continue

        return []

    def _download_single_document(self, item: Any, download_dir: Path, index: int) -> str | None:
        """下载单个文书

        Args:
            item: Playwright Locator 对象
            download_dir: 下载目录
            index: 文书序号

        Returns:
            下载文件路径，失败返回 None
        """
        try:
            # 查找下载按钮
            download_btn = item.locator(
                "button:has-text('下载'), "
                "a:has-text('下载'), "
                ".download-btn, "
                "svg.download-icon, "
                "img[alt*='下载']"
            )

            if download_btn.count() > 0:
                return self._try_download_with_button(download_btn.first, download_dir, f"jysd_doc_{index}")

            # 尝试点击条目本身
            return self._try_download_with_button(item, download_dir, f"jysd_doc_{index}")

        except Exception as exc:
            logger.warning("集约送达: 下载第 %d 个文书失败: %s", index, exc)
            return None

    def _try_download_with_button(self, button: Any, download_dir: Path, prefix: str) -> str | None:
        """尝试点击按钮下载文件

        Args:
            button: Playwright Locator 对象
            download_dir: 下载目录
            prefix: 文件名前缀

        Returns:
            下载文件路径，失败返回 None
        """
        assert self.page is not None

        try:
            captured: list[Any] = []
            self.page.on("download", lambda d: captured.append(d))

            button.click(force=True, timeout=5000)

            # 等待下载触发
            for _ in range(20):
                if captured:
                    break
                self.page.wait_for_timeout(500)

            if not captured:
                return None

            download = captured[0]
            filename = download.suggested_filename or f"{prefix}_{int(time.time())}.pdf"
            filename = self._safe_filename(filename)
            filepath = download_dir / filename
            download.save_as(str(filepath))
            logger.info("集约送达: 下载成功: %s", filepath)
            return str(filepath)

        except Exception as exc:
            logger.warning("集约送达: 点击下载失败: %s", exc)
            return None

    def _try_download_all_links(self, iframe: Any, download_dir: Path) -> list[str]:
        """尝试查找所有下载链接并下载"""
        assert self.page is not None
        files: list[str] = []

        try:
            # 查找所有可能包含下载功能的链接
            download_links = iframe.locator(
                "a[href*='download'], "
                "a[href*='.pdf'], "
                "a[download], "
                "button:has-text('下载')",
            )

            count = download_links.count()
            logger.info("集约送达: 找到 %d 个下载链接", count)

            for i in range(min(count, 20)):
                try:
                    filepath = self._try_download_with_button(
                        download_links.nth(i), download_dir, f"jysd_link_{i}"
                    )
                    if filepath:
                        files.append(filepath)
                except Exception as exc:
                    logger.warning("集约送达: 下载第 %d 个链接失败: %s", i, exc)

        except Exception as exc:
            logger.warning("集约送达: 查找下载链接时出错: %s", exc)

        return files

    def _try_preview_and_download(self, iframe: Any, download_dir: Path) -> list[str]:
        """尝试预览文书后下载"""
        assert self.page is not None
        files: list[str] = []

        try:
            # 查找预览按钮
            preview_btn = iframe.locator(
                "button:has-text('预览'), "
                "a:has-text('预览'), "
                "button:has-text('查看'), "
                "a:has-text('查看')",
            )

            if preview_btn.count() == 0:
                return files

            logger.info("集约送达: 找到预览按钮，尝试预览后下载")

            # 点击第一个预览按钮
            preview_btn.first.click(force=True, timeout=3000)
            iframe.page().wait_for_timeout(2000)

            # 在预览页面寻找下载按钮
            download_btn = iframe.locator(
                "button:has-text('下载'), "
                "a:has-text('下载'), "
                ".download-btn",
            )

            if download_btn.count() > 0:
                filepath = self._try_download_with_button(download_btn.first, download_dir, "jysd_preview")
                if filepath:
                    files.append(filepath)

        except Exception as exc:
            logger.warning("集约送达: 预览下载尝试失败: %s", exc)

        return files

    @staticmethod
    def _safe_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", name).strip()
        return cleaned or f"jysd_{int(time.time())}.pdf"
