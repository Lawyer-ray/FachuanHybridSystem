"""
简易送达平台 (jysd.10102368.com) 文书下载爬虫

流程：
1. 访问简易送达链接（重定向到 sdPc 页面，iframe 加载 checkLoginPc）
2. 在 iframe (sd5.sifayun.com) 内输入手机号并点击"登录"
3. 登录成功 → iframe 跳转到 middlePagePc（中间页面，显示案号和"查看文书详情"按钮）
4. 点击"查看文书详情" → iframe 跳转到 home（文书详情页面）
5. 文书详情页面有 el-table 表格，每行一个文书，操作列有"下载"按钮
6. 逐个点击下载按钮下载文书
7. 手机号验证策略：优先尝试案件承办律师手机号，逐一尝试直到成功
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from .base_court_scraper import BaseCourtDocumentScraper

logger = logging.getLogger("apps.automation")


class JysdCourtScraper(BaseCourtDocumentScraper):
    """简易送达 (jysd.10102368.com) 文书下载爬虫"""

    # 最大尝试手机号数量
    _MAX_PHONE_ATTEMPTS = 10
    # 登录后等待时间（毫秒）
    _LOGIN_WAIT_MS = 10000
    # 页面加载等待时间（毫秒）
    _PAGE_LOAD_WAIT_MS = 5000

    def run(self) -> dict[str, Any]:
        """执行文书下载任务"""
        logger.info("开始处理简易送达链接: %s", self.task.url)

        download_dir = self._prepare_download_dir()

        # 获取律师手机号列表
        lawyer_phones = self._get_lawyer_phones()
        if not lawyer_phones:
            raise ValueError("简易送达链接需要律师手机号登录，但未找到任何律师手机号")

        logger.info("简易送达: 共 %d 个律师手机号待尝试", len(lawyer_phones))

        # 导航到目标页面
        self.navigate_to_url(timeout=30000)
        assert self.page is not None
        self.page.wait_for_timeout(self._PAGE_LOAD_WAIT_MS)

        # 逐一尝试律师手机号登录
        login_success = False
        phones_to_try = lawyer_phones[: self._MAX_PHONE_ATTEMPTS]

        for idx, phone in enumerate(phones_to_try):
            logger.info(
                "简易送达: 尝试第 %d/%d 个手机号 %s",
                idx + 1,
                len(phones_to_try),
                self._mask_phone(phone),
            )

            # 每次尝试前刷新页面（除第一次），确保状态干净
            if idx > 0:
                self.page.reload(wait_until="domcontentloaded", timeout=30000)
                self.page.wait_for_timeout(self._PAGE_LOAD_WAIT_MS)

            # 获取 iframe
            iframe = self._get_sifayun_iframe()
            if iframe is None:
                logger.warning("简易送达: iframe 未加载，跳过手机号 %s", self._mask_phone(phone))
                continue

            # 检查是否已经登录（可能是之前的 session）
            if "checkLoginPc" not in (iframe.url or ""):
                logger.info("简易送达: iframe 不在登录页（URL=%s），视为已登录", iframe.url[:80])
                login_success = True
                break

            # 输入手机号并登录
            login_success = self._try_login_with_phone(iframe, phone)
            if login_success:
                logger.info("简易送达: 手机号 %s 登录成功", self._mask_phone(phone))
                break

            logger.info("简易送达: 手机号 %s 登录失败，尝试下一个", self._mask_phone(phone))

        if not login_success:
            self._save_page_state("jysd_all_phones_failed")
            raise ValueError(f"所有 {len(phones_to_try)} 个律师手机号均无法登录简易送达平台")

        # 登录成功 → 处理中间页面 → 进入文书详情页
        iframe = self._navigate_to_document_page()
        if iframe is None:
            self._save_page_state("jysd_no_doc_page")
            raise ValueError("简易送达: 无法进入文书详情页面")

        # 下载文书
        files = self._download_documents_from_table(iframe, download_dir)

        if not files:
            self._save_page_state("jysd_no_documents")
            raise ValueError("简易送达: 文书详情页面未下载到任何文书")

        return {
            "source": "jysd.10102368.com",
            "files": files,
            "downloaded_count": len(files),
            "failed_count": 0,
            "message": f"简易送达下载成功: {len(files)} 份",
        }

    # ==================== 手机号管理 ====================

    def _get_lawyer_phones(self) -> list[str]:
        """从任务配置中获取律师手机号列表"""
        task_config = self.task.config if isinstance(self.task.config, dict) else {}
        phones = task_config.get("jysd_lawyer_phones", [])
        if isinstance(phones, list):
            return [str(p).strip() for p in phones if str(p).strip()]
        return []

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """手机号脱敏：136****0615"""
        if len(phone) >= 7:
            return phone[:3] + "****" + phone[-4:]
        return "***"

    # ==================== iframe 管理 ====================

    def _get_sifayun_iframe(self) -> Any | None:
        """获取 sifayun.com 的 iframe frame 对象"""
        assert self.page is not None

        # 直接遍历 page.frames 查找（最可靠）
        try:
            for frame in self.page.frames:
                frame_url = frame.url or ""
                if "sifayun.com" in frame_url:
                    return frame
        except Exception as exc:
            logger.warning("简易送达: 遍历 frames 时出错: %s", exc)

        return None

    # ==================== 登录流程 ====================

    def _try_login_with_phone(self, iframe: Any, phone: str) -> bool:
        """在 iframe 内输入手机号并登录

        iframe 当前应该在 checkLoginPc 页面，包含：
        - input[placeholder='请输入手机号']（注意是'手机号'不是'手机号码'）
        - button:has-text('登录')
        """
        try:
            # 定位手机号输入框（placeholder 是"请输入手机号"）
            phone_input = iframe.locator("input[placeholder*='手机号']")
            if phone_input.count() == 0:
                logger.warning("简易送达: iframe 内未找到手机号输入框")
                self.screenshot("jysd_no_phone_input")
                return False

            # 清空并输入手机号
            phone_input.first.click(force=True, timeout=5000)
            phone_input.first.fill("")
            phone_input.first.fill(phone)
            logger.info("简易送达: 已输入手机号")

            # 等待一小段时间模拟人工操作
            assert self.page is not None
            self.page.wait_for_timeout(500)

            # 点击登录按钮
            login_btn = iframe.locator("button:has-text('登录')")
            if login_btn.count() > 0:
                login_btn.first.click(force=True, timeout=5000)
                logger.info("简易送达: 已点击登录按钮")
            else:
                logger.warning("简易送达: 未找到登录按钮")
                self.screenshot("jysd_no_login_btn")
                return False

            # 等待页面响应
            self.page.wait_for_timeout(self._LOGIN_WAIT_MS)

            # 检查登录结果：iframe URL 应该从 checkLoginPc 变为 middlePagePc
            return self._check_login_result()

        except Exception as exc:
            logger.warning("简易送达: 手机号登录过程出错: %s", exc)
            return False

    def _check_login_result(self) -> bool:
        """检查登录是否成功

        登录成功：iframe URL 从 checkLoginPc 变为 middlePagePc
        """
        iframe = self._get_sifayun_iframe()
        if iframe is None:
            logger.info("简易送达: 登录后找不到 iframe，视为失败")
            return False

        iframe_url = iframe.url or ""
        # 登录成功后 iframe 会跳转到 middlePagePc
        if "middlePagePc" in iframe_url:
            logger.info("简易送达: iframe 已跳转到中间页面，登录成功")
            return True

        # 检查是否还在登录页
        if "checkLoginPc" in iframe_url:
            logger.info("简易送达: iframe 仍在登录页，登录失败")
            return False

        # 其他 URL，可能是已登录状态
        logger.info("简易送达: iframe URL=%s，可能已登录", iframe_url[:80])
        return "home" in iframe_url or "middlePage" in iframe_url

    # ==================== 中间页面 → 文书详情 ====================

    def _navigate_to_document_page(self) -> Any | None:
        """从中间页面导航到文书详情页面

        中间页面 (middlePagePc) 有"查看文书详情"按钮，点击后进入文书详情 (home)。
        如果已经在文书详情页面，直接返回 iframe。
        """
        assert self.page is not None

        iframe = self._get_sifayun_iframe()
        if iframe is None:
            return None

        iframe_url = iframe.url or ""

        # 已经在文书详情页
        if "home" in iframe_url:
            logger.info("简易送达: 已在文书详情页面")
            return iframe

        # 在中间页面，需要点击"查看文书详情"
        if "middlePagePc" in iframe_url:
            logger.info("简易送达: 在中间页面，点击'查看文书详情'")

            view_btn = iframe.locator("button:has-text('查看文书详情')")
            if view_btn.count() > 0:
                view_btn.first.click(force=True, timeout=5000)
                self.page.wait_for_timeout(self._PAGE_LOAD_WAIT_MS)

                # 重新获取 iframe
                iframe = self._get_sifayun_iframe()
                if iframe is not None:
                    logger.info("简易送达: 已进入文书详情页面, URL=%s", iframe.url[:80])
                    return iframe

            logger.warning("简易送达: 中间页面未找到'查看文书详情'按钮")
            # 尝试截图调试
            self.screenshot("jysd_no_view_btn")
            return iframe  # 返回当前 iframe 尝试继续

        # 还在登录页或其他页面
        logger.warning("简易送达: iframe 不在预期的页面, URL=%s", iframe_url[:80])
        return iframe

    # ==================== 文书下载 ====================

    def _download_documents_from_table(self, iframe: Any, download_dir: Path) -> list[str]:
        """从文书详情页面的 el-table 表格中下载文书

        文书详情页面结构：
        - el-table 表格，每行一个文书
        - 列：文书类型 | 文书名称 | 最新查看时间 | 操作
        - 操作列有 <button class="el-button el-button--danger el-button--mini is-plain">下载</button>

        策略：逐行遍历，每行重新定位按钮，用 JS click 作为 Playwright click 的 fallback。
        """
        assert self.page is not None
        files: list[str] = []

        # 等待表格加载
        self.page.wait_for_timeout(3000)
        self.screenshot("jysd_doc_page")

        # 获取表格行数
        rows = iframe.locator(".el-table__body-wrapper tr.el-table__row")
        total = rows.count()
        logger.info("简易送达: 文书表格共 %d 行", total)

        if total == 0:
            # 备选选择器
            rows = iframe.locator(".el-table__body tr")
            total = rows.count()
            logger.info("简易送达: 备选选择器找到 %d 行", total)

        for i in range(total):
            try:
                # 每次重新获取 iframe（下载可能触发页面变化）
                iframe = self._get_sifayun_iframe() or iframe
                rows = iframe.locator(".el-table__body-wrapper tr.el-table__row")
                if rows.count() <= i:
                    rows = iframe.locator(".el-table__body tr")

                row = rows.nth(i)

                # 获取文书名称
                doc_name = ""
                try:
                    doc_name_cell = row.locator("td:nth-child(2) .cell")
                    if doc_name_cell.count() > 0:
                        doc_name = doc_name_cell.first.inner_text().strip()
                except Exception:
                    pass

                logger.info(
                    "简易送达: 下载第 %d/%d 个文书%s",
                    i + 1,
                    total,
                    f" ({doc_name})" if doc_name else "",
                )

                filepath = self._download_row_document(row, iframe, download_dir, doc_name, i)
                if filepath:
                    files.append(filepath)

                # 下载间隔
                self.page.wait_for_timeout(1500)

            except Exception as exc:
                logger.warning("简易送达: 下载第 %d 个文书失败: %s", i + 1, exc)

        return files

    def _download_row_document(
        self, row: Any, iframe: Any, download_dir: Path, doc_name: str, index: int
    ) -> str | None:
        """下载单行文书

        策略：
        1. Playwright click + expect_download
        2. 失败则 JS click + expect_download
        3. 检查确认对话框

        Args:
            row: 表格行 Locator
            iframe: iframe Frame 对象
            download_dir: 下载目录
            doc_name: 文书名称
            index: 文书序号

        Returns:
            下载文件路径，失败返回 None
        """
        assert self.page is not None

        # 策略1: Playwright click
        try:
            download_btn = row.locator("button:has-text('下载')")
            if download_btn.count() > 0:
                with self.page.expect_download(timeout=15000) as download_info:
                    download_btn.first.click(force=True, timeout=5000)
                return self._save_download(download_info.value, download_dir, doc_name, index)
        except Exception:
            logger.info("简易送达: Playwright click 超时，尝试 JS click")

        # 策略2: JS click（Playwright force click 有时无法触发 Vue 事件）
        try:
            with self.page.expect_download(timeout=15000) as download_info:
                row.evaluate("r => r.querySelector('button')?.click()")
            return self._save_download(download_info.value, download_dir, doc_name, index)
        except Exception:
            logger.info("简易送达: JS click 也超时，检查确认对话框")

        # 策略3: 检查是否弹出了确认对话框
        try:
            self.page.wait_for_timeout(1000)
            confirm_btn = iframe.locator(
                ".checkFileDialog .el-dialog__wrapper:not([style*='display: none']) button:has-text('下载文书并核验')"
            )
            if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                logger.info("简易送达: 检测到下载确认对话框，点击'下载文书并核验'")
                with self.page.expect_download(timeout=30000) as download_info:
                    confirm_btn.first.click(force=True, timeout=5000)
                return self._save_download(download_info.value, download_dir, doc_name, index)
        except Exception as exc:
            logger.warning("简易送达: 确认对话框下载也失败: %s", exc)

        return None

    def _save_download(self, download: Any, download_dir: Path, doc_name: str, index: int) -> str:
        """保存下载文件

        Args:
            download: Playwright Download 对象
            download_dir: 下载目录
            doc_name: 文书名称
            index: 文书序号

        Returns:
            保存的文件路径
        """
        suggested = download.suggested_filename or ""
        if doc_name and doc_name.endswith(".pdf"):
            filename = self._safe_filename(doc_name)
        elif suggested:
            filename = self._safe_filename(suggested)
        else:
            filename = f"jysd_doc_{index}_{int(time.time())}.pdf"

        filepath = download_dir / filename
        download.save_as(str(filepath))
        logger.info("简易送达: 下载成功: %s", filepath)
        return str(filepath)

    @staticmethod
    def _safe_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", name).strip()
        return cleaned or f"jysd_{int(time.time())}.pdf"
