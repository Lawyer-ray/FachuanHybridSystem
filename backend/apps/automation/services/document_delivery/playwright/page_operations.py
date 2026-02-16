"""Business logic services."""

from __future__ import annotations

"""
文书送达 Playwright 页面操作模块

负责 Playwright 浏览器的页面操作,包括:
- 页面导航
- 元素提取
- 文书下载
- 翻页逻辑

作为 DocumentDeliveryPlaywrightService 的 Mixin 使用.
"""


import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from apps.automation.utils.logging_mixins.common import sanitize_url

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

logger = logging.getLogger("apps.automation")


class PageOperationsMixin:
    """页面操作 Mixin

    提供 Playwright 页面操作相关的方法,包括:
    - 页面导航
    - 文书条目提取
    - 文书下载
    - 翻页操作
    """

    # 页面 URL
    DELIVERY_PAGE_URL = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/common/wssd/index"

    # 选择器常量 (使用精确 xpath)
    _XPATH_BASE = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body"
    _SCROLL_BASE = (
        f"{_XPATH_BASE}/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view"
    )

    PENDING_TAB_SELECTOR = f"{_XPATH_BASE}/uni-view/uni-view/uni-view[1]/uni-view/uni-view[1]/uni-view/uni-text"
    REVIEWED_TAB_SELECTOR = f"{_XPATH_BASE}/uni-view/uni-view/uni-view[1]/uni-view/uni-view[2]/uni-view/uni-text"
    CASE_NUMBER_SELECTOR = f"{_SCROLL_BASE}/uni-form/span/uni-view[1]/uni-view"
    SEND_TIME_SELECTOR = f"{_SCROLL_BASE}/uni-form/span/uni-view[3]/uni-view"
    DOWNLOAD_BUTTON_SELECTOR = (
        f"{_XPATH_BASE}/uni-view/uni-view/uni-view[2]"
        "/uni-view/uni-scroll-view/div/div/div"
        "/uni-view/uni-view/uni-view[2]/uni-text[2]"
    )
    NEXT_PAGE_SELECTOR = f"{_XPATH_BASE}/uni-view/uni-view/uni-view[2]/uni-view/uni-view/uni-view/uni-view[4]"

    # 页面加载等待时间(毫秒)
    PAGE_LOAD_WAIT = 3000

    def _navigate_to_delivery_page(self, page: Page, tab: str) -> None:
        """
        导航到文书送达页面

        Args:
            page: Playwright 页面实例
            tab: 标签页类型,"pending" 或 "reviewed"
        """
        logger.info(f"导航到文书送达页面: {sanitize_url(self.DELIVERY_PAGE_URL)}")

        page.goto(self.DELIVERY_PAGE_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(self.PAGE_LOAD_WAIT)

        # 切换标签页
        tab_selector = self.REVIEWED_TAB_SELECTOR if tab == "reviewed" else self.PENDING_TAB_SELECTOR
        tab_name = "已查阅" if tab == "reviewed" else "待查阅"

        logger.info(f"切换到{tab_name}标签页")
        try:
            tab_element = page.locator(tab_selector)
            tab_element.wait_for(state="visible", timeout=5000)
            tab_element.click()
            page.wait_for_timeout(self.PAGE_LOAD_WAIT)
            logger.info(f"成功点击{tab_name}标签页")
        except Exception as e:
            logger.warning(f"切换到{tab_name}标签页失败: {e!s}")

    def _extract_document_entries(self, page: Page) -> list[DocumentDeliveryRecord]:
        """
        从页面提取文书条目 - 使用精确 XPath 遍历

        Args:
            page: Playwright 页面实例

        Returns:
            文书记录列表
        """
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        logger.info("开始提取文书条目")
        entries: list[Any] = []

        try:
            page.wait_for_timeout(2000)

            case_number_elements = page.locator(self.CASE_NUMBER_SELECTOR).all()
            logger.info(f"找到 {len(case_number_elements)} 个案号元素")

            send_time_elements = page.locator(self.SEND_TIME_SELECTOR).all()
            logger.info(f"找到 {len(send_time_elements)} 个时间元素")

            if len(case_number_elements) != len(send_time_elements):
                logger.warning(f"案号数量({len(case_number_elements)})与时间数量({len(send_time_elements)})不匹配")
                count = min(len(case_number_elements), len(send_time_elements))
            else:
                count = len(case_number_elements)

            logger.info(f"将处理 {count} 个文书条目")

            for index in range(count):
                try:
                    # 提取案号
                    case_number = None
                    if index < len(case_number_elements):
                        case_number_text = case_number_elements[index].inner_text()
                        case_number = case_number_text.strip() if case_number_text else None
                        logger.info(f"条目 {index} 案号: {case_number}")

                        if case_number and case_number in ["案号", "案件编号"]:
                            case_number = None
                            logger.debug(f"条目 {index} 跳过案号标签文本")

                    # 提取发送时间
                    send_time = None
                    send_time_str = None
                    if index < len(send_time_elements):
                        send_time_text = send_time_elements[index].inner_text()
                        send_time_str = send_time_text.strip() if send_time_text else None
                        logger.info(f"条目 {index} 时间文本: {send_time_str}")

                        if send_time_str and send_time_str != "发送时间":
                            send_time = self._parse_send_time(send_time_str, index)
                        else:
                            logger.debug(f"条目 {index} 跳过标签文本: {send_time_str}")

                    # 创建文书记录
                    if case_number and send_time:
                        entry = DocumentDeliveryRecord(
                            case_number=case_number, send_time=send_time, element_index=index
                        )
                        entries.append(entry)
                        logger.info(f"✅ 提取文书条目: {entry.case_number} - {entry.send_time}")
                    else:
                        logger.debug(f"❌ 条目 {index} 数据不完整: 案号={case_number}, 时间={send_time_str}")

                except Exception as e:
                    logger.warning(f"提取第 {index} 个文书条目失败: {e!s}")
                    continue

        except Exception as e:
            logger.error(f"提取文书条目失败: {e!s}")

        logger.info(f"成功提取 {len(entries)} 个文书条目")
        return entries

    def _parse_send_time(self, send_time_str: str, index: int) -> datetime | None | None:
        """
        解析发送时间字符串

        Args:
            send_time_str: 时间字符串
            index: 条目索引(用于日志)

        Returns:
            解析后的 datetime 对象,失败返回 None
        """
        from django.utils import timezone

        time_pattern = r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"
        if re.match(time_pattern, send_time_str):
            try:
                naive_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")
                send_time = timezone.make_aware(naive_time)
                logger.info(f"条目 {index} 时间解析成功: {send_time_str} -> {send_time}")
                return send_time
            except ValueError as e:
                logger.warning(f"条目 {index} 时间解析失败: {send_time_str}, 错误: {e!s}")
        else:
            logger.debug(f"条目 {index} 时间格式不匹配: {send_time_str}")

        return None

    def _parse_document_text(self, text: str) -> tuple[str | None, datetime | None]:
        """
        从文书条目文本中解析案号和时间

        Args:
            text: 文书条目的文本内容

        Returns:
            (case_number, send_time) 元组
        """
        case_number = None
        send_time = None

        # 提取案号
        case_patterns: list[Any] = [
            r"\(?\d{4}\)?[^\d\s]+\d+号",
            r"[\((]\d{4}[\))][^\d\s]+\d+号",
        ]

        for pattern in case_patterns:
            match = re.search(pattern, text)
            if match:
                case_number = match.group()
                break

        # 提取时间
        time_patterns: list[Any] = [
            (r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S"),
            (r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", "%Y-%m-%d %H:%M"),
            (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
            (r"\d{4}/\d{2}/\d{2}", "%Y/%m/%d"),
        ]

        for pattern, fmt in time_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    send_time = datetime.strptime(match.group(), fmt)
                    break
                except ValueError:
                    continue

        return case_number, send_time

    def _download_document(self, page: Page, entry: DocumentDeliveryRecord) -> str | None | None:
        """
        点击下载按钮下载文书 - 使用精确 XPath

        Args:
            page: Playwright 页面实例
            entry: 文书记录

        Returns:
            下载的文件路径,失败返回 None
        """
        logger.info(f"开始下载文书: {entry.case_number}")

        try:
            download_buttons = page.locator(self.DOWNLOAD_BUTTON_SELECTOR).all()
            logger.info(f"找到 {len(download_buttons)} 个下载按钮")

            if entry.element_index >= len(download_buttons):
                logger.error(f"下载按钮索引超出范围: {entry.element_index} >= {len(download_buttons)}")
                return None

            download_button = download_buttons[entry.element_index]

            if not download_button.is_visible():
                logger.error(f"下载按钮不可见: {entry.case_number}")
                return None

            logger.info(f"点击第 {entry.element_index} 个下载按钮")

            with page.expect_download() as download_info:
                download_button.click()

            download = download_info.value

            temp_dir = tempfile.mkdtemp(prefix="court_document_")
            file_path = Path(temp_dir) / (download.suggested_filename or f"{entry.case_number}.pdf")

            download.save_as(file_path)

            logger.info(f"文书下载成功: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"下载文书失败: {e!s}")
            return None

    def _has_next_page(self, page: Page) -> bool:
        """
        检查是否有下一页

        Args:
            page: Playwright 页面实例

        Returns:
            是否有下一页
        """
        try:
            next_button = page.locator(self.NEXT_PAGE_SELECTOR)
            return next_button.is_visible() and next_button.is_enabled()
        except Exception as e:
            logger.warning(f"检查下一页失败: {e!s}")
            return False

    def _go_to_next_page(self, page: Page) -> None:
        """
        翻到下一页

        Args:
            page: Playwright 页面实例
        """
        try:
            next_button = page.locator(self.NEXT_PAGE_SELECTOR)
            if next_button.is_visible() and next_button.is_enabled():
                next_button.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(self.PAGE_LOAD_WAIT)
                logger.info("成功翻到下一页")
            else:
                logger.warning("下一页按钮不可用")
        except Exception as e:
            logger.error(f"翻页失败: {e!s}")
