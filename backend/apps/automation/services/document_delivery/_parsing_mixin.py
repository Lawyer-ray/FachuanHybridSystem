"""文书送达解析 Mixin — 页面导航、条目提取、时间解析"""

import logging
import re
from datetime import datetime
from typing import Any

from playwright.sync_api import Page

from .data_classes import DocumentDeliveryRecord

logger = logging.getLogger("apps.automation")


class DocumentDeliveryParsingMixin:
    """页面解析相关方法"""

    # 子类需提供这些属性（由 DocumentDeliveryService 定义）
    DELIVERY_PAGE_URL: str
    PENDING_TAB_SELECTOR: str
    REVIEWED_TAB_SELECTOR: str
    CASE_NUMBER_SELECTOR: str
    SEND_TIME_SELECTOR: str
    NEXT_PAGE_SELECTOR: str
    PAGE_LOAD_WAIT: int

    def _navigate_to_delivery_page(self, page: Page, tab: str) -> None:
        """导航到文书送达页面"""
        logger.info(f"导航到文书送达页面: {self.DELIVERY_PAGE_URL}")
        page.goto(self.DELIVERY_PAGE_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(self.PAGE_LOAD_WAIT)

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

    def _parse_send_time_str(self, send_time_str: str, index: int) -> Any:
        """解析发送时间字符串"""
        if not send_time_str or send_time_str == "发送时间":
            return None
        time_pattern = r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"
        if not re.match(time_pattern, send_time_str):
            logger.debug(f"条目 {index} 时间格式不匹配: {send_time_str}")
            return None
        try:
            from django.utils import timezone
            naive_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")
            send_time = timezone.make_aware(naive_time)
            logger.info(f"条目 {index} 时间解析成功: {send_time_str} -> {send_time}")
            return send_time
        except ValueError as e:
            logger.warning(f"条目 {index} 时间解析失败: {send_time_str}, 错误: {e!s}")
            return None

    def _extract_single_doc_entry(
        self,
        index: int,
        case_number_elements: list[Any],
        send_time_elements: list[Any],
    ) -> Any:
        """提取单个文书条目"""
        case_number = None
        if index < len(case_number_elements):
            text = case_number_elements[index].inner_text()
            case_number = text.strip() if text else None
            if case_number in ("案号", "案件编号"):
                case_number = None

        send_time = None
        send_time_str = None
        if index < len(send_time_elements):
            text = send_time_elements[index].inner_text()
            send_time_str = text.strip() if text else None
            if send_time_str:
                send_time = self._parse_send_time_str(send_time_str, index)

        if case_number and send_time:
            entry = DocumentDeliveryRecord(
                case_number=case_number, send_time=send_time, element_index=index
            )
            logger.info(f"✅ 提取文书条目: {entry.case_number} - {entry.send_time}")
            return entry
        logger.debug(f"❌ 条目 {index} 数据不完整: 案号={case_number}, 时间={send_time_str}")
        return None

    def _extract_document_entries(self, page: Page) -> list[DocumentDeliveryRecord]:
        """从页面提取文书条目"""
        logger.info("开始提取文书条目")
        entries: list[Any] = []
        try:
            page.wait_for_timeout(2000)
            case_number_elements = page.locator(self.CASE_NUMBER_SELECTOR).all()
            send_time_elements = page.locator(self.SEND_TIME_SELECTOR).all()
            logger.info(
                f"找到 {len(case_number_elements)} 个案号元素, {len(send_time_elements)} 个时间元素"
            )
            if len(case_number_elements) != len(send_time_elements):
                logger.warning(
                    f"案号数量({len(case_number_elements)})与时间数量({len(send_time_elements)})不匹配"
                )
            count = min(len(case_number_elements), len(send_time_elements))
            for index in range(count):
                try:
                    entry = self._extract_single_doc_entry(
                        index, case_number_elements, send_time_elements
                    )
                    if entry:
                        entries.append(entry)
                except Exception as e:
                    logger.warning(f"提取第 {index} 个文书条目失败: {e!s}")
        except Exception as e:
            logger.error(f"提取文书条目失败: {e!s}")
        logger.info(f"成功提取 {len(entries)} 个文书条目")
        return entries

    def _parse_document_text(self, text: str) -> tuple[Any, ...]:
        """从文书条目文本中解析案号和时间"""
        case_number = None
        send_time = None
        case_patterns = [
            r"\(?\d{4}\)?[^\d\s]+\d+号",
            r"[\(（]\d{4}[\)）][^\d\s]+\d+号",
        ]
        for pattern in case_patterns:
            match = re.search(pattern, text)
            if match:
                case_number = match.group()
                break
        time_patterns = [
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

    def _has_next_page(self, page: Page) -> bool:
        """检查是否有下一页"""
        try:
            next_button = page.locator(self.NEXT_PAGE_SELECTOR)
            return next_button.is_visible() and next_button.is_enabled()
        except Exception as e:
            logger.warning(f"检查下一页失败: {e!s}")
            return False

    def _go_to_next_page(self, page: Page) -> None:
        """翻到下一页"""
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
