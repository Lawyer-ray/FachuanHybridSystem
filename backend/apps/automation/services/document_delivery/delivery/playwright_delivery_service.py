"""
Playwright 方式文书投递服务

负责通过浏览器自动化方式获取和下载文书.
"""

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Page


from ..data_classes import DocumentDeliveryRecord

if TYPE_CHECKING:
    pass

logger = logging.getLogger("apps.automation")


class PlaywrightDeliveryService:
    """Playwright 方式文书投递服务"""

    # 页面 URL
    DELIVERY_PAGE_URL = "https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/common/wssd/index"

    # 选择器常量 (使用精确 xpath)
    PENDING_TAB_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[1]/uni-view/uni-view[1]/uni-view/uni-text"
    REVIEWED_TAB_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[1]/uni-view/uni-view[2]/uni-view/uni-text"
    CASE_NUMBER_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view/uni-form/span/uni-view[1]/uni-view"
    SEND_TIME_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view/uni-form/span/uni-view[3]/uni-view"
    DOWNLOAD_BUTTON_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-scroll-view/div/div/div/uni-view/uni-view/uni-view[2]/uni-text[2]"
    NEXT_PAGE_SELECTOR = "xpath=/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view[2]/uni-view/uni-view/uni-view/uni-view[4]"

    # 页面加载等待时间(毫秒)
    PAGE_LOAD_WAIT = 3000

    def __init__(self) -> None:
        """初始化 Playwright 投递服务"""
        logger.debug("PlaywrightDeliveryService 初始化完成")

    def navigate_to_delivery_page(self, page: Page, tab: str) -> None:
        """
        导航到文书送达页面

        Args:
            page: Playwright 页面实例
            tab: 标签页类型 ("pending" 或 "reviewed")
        """
        logger.info(f"导航到文书送达页面: {self.DELIVERY_PAGE_URL}")

        # 访问文书送达页面
        page.goto(self.DELIVERY_PAGE_URL)
        page.wait_for_load_state("networkidle")

        # 等待页面完全加载
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

    def extract_document_entries(self, page: Page) -> list[DocumentDeliveryRecord]:
        """
        从页面提取文书条目 - 使用精确 XPath 遍历

        Args:
            page: Playwright 页面实例

        Returns:
            文书条目列表
        """
        logger.info("开始提取文书条目")

        entries: list[Any] = []

        try:
            # 等待页面加载
            page.wait_for_timeout(2000)

            # 使用精确 XPath 获取所有案号
            case_number_elements = page.locator(self.CASE_NUMBER_SELECTOR).all()
            logger.info(f"找到 {len(case_number_elements)} 个案号元素")

            # 使用精确 XPath 获取所有发送时间
            send_time_elements = page.locator(self.SEND_TIME_SELECTOR).all()
            logger.info(f"找到 {len(send_time_elements)} 个时间元素")

            # 确保案号和时间数量一致
            if len(case_number_elements) != len(send_time_elements):
                logger.warning(f"案号数量({len(case_number_elements)})与时间数量({len(send_time_elements)})不匹配")
                count = min(len(case_number_elements), len(send_time_elements))
            else:
                count = len(case_number_elements)

            logger.info(f"将处理 {count} 个文书条目")

            # 遍历提取每个文书条目
            for index in range(count):
                try:
                    # 提取案号
                    case_number = None
                    if index < len(case_number_elements):
                        case_number_text = case_number_elements[index].inner_text()
                        case_number = case_number_text.strip() if case_number_text else None
                        logger.info(f"条目 {index} 案号: {case_number}")

                        # 过滤掉标签文本
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

                        # 过滤掉标签文本,只处理实际的时间格式
                        if send_time_str and send_time_str != "发送时间":
                            # 检查是否符合时间格式 2025-12-16 10:58:52
                            time_pattern = r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"
                            if re.match(time_pattern, send_time_str):
                                try:
                                    # 解析时间并添加时区信息
                                    naive_time = datetime.strptime(send_time_str, "%Y-%m-%d %H:%M:%S")
                                    from django.utils import timezone

                                    send_time = timezone.make_aware(naive_time)
                                    logger.info(f"条目 {index} 时间解析成功: {send_time_str} -> {send_time}")
                                except ValueError as e:
                                    logger.warning(f"条目 {index} 时间解析失败: {send_time_str}, 错误: {e!s}")
                            else:
                                logger.debug(f"条目 {index} 时间格式不匹配: {send_time_str}")
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

    def should_process_entry(self, record: DocumentDeliveryRecord, cutoff_time: datetime, credential_id: int) -> bool:
        """
        判断是否需要处理该文书

        注意:此方法在 Playwright 上下文中调用,ORM 操作需要在独立线程中执行

        Args:
            record: 文书记录
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID

        Returns:
            是否需要处理
        """
        # 检查时间过滤
        if record.send_time and record.send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {record.send_time} 早于截止时间 {cutoff_time},跳过")
            return False

        # 在独立线程中检查是否已经处理过
        return self._check_not_processed_in_thread(credential_id, record)

    def _check_not_processed_in_thread(self, credential_id: int, record: DocumentDeliveryRecord) -> bool:
        """
        在独立线程中检查文书是否已成功处理完成,避免异步上下文问题

        检查逻辑:
        1. 如果有查询历史记录,检查对应的 CourtSMS 是否已成功完成
        2. 如果 CourtSMS 状态为 COMPLETED,则跳过
        3. 如果 CourtSMS 状态为其他(失败、待处理等),则重新处理

        Args:
            credential_id: 账号凭证 ID
            record: 文书记录

        Returns:
            是否需要处理
        """
        import queue
        import threading

        result_queue: queue.Queue[bool] = queue.Queue()

        def do_check() -> None:
            try:
                from django.db import connection

                from apps.automation.models import CourtSMS, CourtSMSStatus, DocumentQueryHistory

                connection.ensure_connection()

                # 检查是否有已成功完成的 CourtSMS 记录
                case_numbers_list: list[Any] = [record.case_number]
                completed_sms = CourtSMS.objects.filter(
                    case_numbers__contains=case_numbers_list, status=CourtSMSStatus.COMPLETED
                ).first()

                if completed_sms:
                    logger.info(
                        f"🔄 文书已成功处理完成: {record.case_number} - {record.send_time}, SMS ID={completed_sms.id}"
                    )
                    result_queue.put(False)
                else:
                    # 检查是否有未完成的记录,如果有则删除重新处理
                    existing_history = DocumentQueryHistory.objects.filter(
                        credential_id=credential_id, case_number=record.case_number, send_time=record.send_time
                    ).first()

                    if existing_history:
                        logger.info(f"🔄 文书有历史记录但未成功完成,重新处理: {record.case_number}")
                        existing_history.delete()

                    logger.info(f"🆕 文书符合处理条件: {record.case_number} - {record.send_time}")
                    result_queue.put(True)

            except Exception as e:
                logger.warning(f"检查文书处理历史失败: {e!s}")
                result_queue.put(True)

        thread = threading.Thread(target=do_check)
        thread.start()
        thread.join(timeout=10)

        if not result_queue.empty():
            return result_queue.get()

        logger.warning("检查文书处理历史超时,默认处理")
        return True

    def download_document(self, page: Page, entry: DocumentDeliveryRecord) -> str | None:
        """
        点击下载按钮下载文书 - 使用精确 XPath

        Args:
            page: Playwright 页面实例
            entry: 文书条目

        Returns:
            下载的文件路径
        """
        logger.info(f"开始下载文书: {entry.case_number}")

        try:
            # 使用精确 XPath 获取所有下载按钮
            download_buttons = page.locator(self.DOWNLOAD_BUTTON_SELECTOR).all()
            logger.info(f"找到 {len(download_buttons)} 个下载按钮")

            if entry.element_index >= len(download_buttons):
                logger.error(f"下载按钮索引超出范围: {entry.element_index} >= {len(download_buttons)}")
                return None

            # 获取对应的下载按钮
            download_button = download_buttons[entry.element_index]

            if not download_button.is_visible():
                logger.error(f"下载按钮不可见: {entry.case_number}")
                return None

            logger.info(f"点击第 {entry.element_index} 个下载按钮")

            # 设置下载监听
            with page.expect_download() as download_info:
                download_button.click()

            download = download_info.value

            # 保存文件
            import tempfile
            from pathlib import Path

            # 创建临时目录
            temp_dir = tempfile.mkdtemp(prefix="court_document_")
            file_path = Path(temp_dir) / (download.suggested_filename or f"{entry.case_number}.pdf")

            download.save_as(str(file_path))

            logger.info(f"文书下载成功: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"下载文书失败: {e!s}")
            return None

    def has_next_page(self, page: Page) -> bool:
        """
        检查是否有下一页

        Args:
            page: Playwright 页面实例

        Returns:
            是否有下一页
        """
        try:
            next_button = page.locator(self.NEXT_PAGE_SELECTOR)
            return bool(next_button.is_visible() and next_button.is_enabled())
        except Exception as e:
            logger.warning(f"检查下一页失败: {e!s}")
            return False

    def go_to_next_page(self, page: Page) -> None:
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
