"""
API 方式文书投递服务

负责通过法院 API 直接获取文书列表和下载文书.
"""

import logging
import math
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from apps.automation.services.document_delivery.data_classes import (
    DocumentDeliveryRecord,
    DocumentQueryResult,
    DocumentRecord,
)

if TYPE_CHECKING:
    from apps.automation.services.document_delivery.court_document_api_client import CourtDocumentApiClient

logger = logging.getLogger("apps.automation")


class ApiDeliveryService:
    """API 方式文书投递服务"""

    def __init__(self, api_client: "CourtDocumentApiClient") -> None:
        """
        初始化 API 投递服务

        Args:
            api_client: API 客户端实例
        """
        self.api_client = api_client
        logger.debug("ApiDeliveryService 初始化完成")

    def query_documents(self, token: str, cutoff_time: datetime, credential_id: int) -> DocumentQueryResult:
        """
        通过 API 查询文书

        流程:
        1. 调用 fetch_document_list 获取文书列表
        2. 根据 total 计算分页,遍历所有页
        3. 对每条记录检查 fssj 是否需要处理
        4. 调用处理器处理文书

        Args:
            token: 认证令牌
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID

        Returns:
            DocumentQueryResult: 查询结果

        Requirements: 1.1, 1.4, 3.4, 5.1
        """
        logger.info(f"开始 API 查询文书: cutoff_time={cutoff_time}")

        case_log_ids: tuple[list[Any]] = ([],)
        errors: list[Any] = []

        result = DocumentQueryResult(
            total_found=0,
            processed_count=0,
            skipped_count=0,
            failed_count=0,
            case_log_ids=case_log_ids,
            errors=errors,
        )

        page_size = 20
        page_num = 1

        try:
            # 获取第一页,确定总数
            first_response = self.api_client.fetch_document_list(token=token, page_num=page_num, page_size=page_size)

            total = first_response.total
            result.total_found = total

            logger.info(f"API 查询: 总文书数={total}")

            if total == 0:
                logger.info("没有文书需要处理")
                return result

            # 计算总页数
            total_pages = math.ceil(total / page_size)
            logger.info(f"分页计算: total={total}, page_size={page_size}, total_pages={total_pages}")

            # 返回第一页数据供外部处理
            result.documents = first_response.documents
            result.total_pages = total_pages

        except Exception as e:
            error_msg = f"API 查询失败: {e!s}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            raise

        return result

    def fetch_page(self, token: str, page_num: int, page_size: int = 20) -> list[DocumentRecord]:
        """
        获取指定页的文书列表

        Args:
            token: 认证令牌
            page_num: 页码
            page_size: 每页数量

        Returns:
            文书记录列表
        """
        try:
            response = self.api_client.fetch_document_list(token=token, page_num=page_num, page_size=page_size)
            return cast(list[DocumentRecord], response.documents)
        except Exception as e:
            logger.error(f"获取第 {page_num} 页失败: {e!s}")
            return []

    def should_process_document(self, record: DocumentRecord, cutoff_time: datetime, credential_id: int) -> bool:
        """
        判断是否需要处理该 API 文书记录

        检查:
        1. fssj(发送时间)是否晚于 cutoff_time
        2. 是否已在 DocumentQueryHistory 中记录
        3. 对应的 CourtSMS 是否已 COMPLETED

        Args:
            record: API 文书记录
            cutoff_time: 截止时间
            credential_id: 账号凭证 ID

        Returns:
            是否需要处理

        Requirements: 3.1, 3.2, 3.3
        """
        # 1. 解析 fssj 字符串为 datetime
        send_time = record.parse_fssj()

        if send_time is None:
            logger.warning(f"无法解析发送时间: {record.fssj}, 默认处理")
            return True

        # 2. 比较 fssj 与 cutoff_time
        from django.utils import timezone

        if timezone.is_aware(cutoff_time):
            send_time = timezone.make_aware(send_time)

        if send_time <= cutoff_time:
            logger.info(f"⏰ 文书时间 {send_time} 早于截止时间 {cutoff_time},跳过")
            return False

        # 3. 检查是否已经处理过
        return self._check_not_processed(credential_id, record)

    def _check_not_processed(self, credential_id: int, record: DocumentRecord) -> bool:
        """
        检查 API 文书是否已成功处理完成

        检查逻辑:
        1. 如果有查询历史记录,检查对应的 CourtSMS 是否已成功完成
        2. 如果 CourtSMS 状态为 COMPLETED,则跳过
        3. 如果 CourtSMS 状态为其他(失败、待处理等),则重新处理

        Args:
            credential_id: 账号凭证 ID
            record: API 文书记录

        Returns:
            是否需要处理(True=需要处理,False=已处理完成)
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
                case_numbers_list: list[Any] = [record.ah]
                completed_sms = CourtSMS.objects.filter(
                    case_numbers__contains=case_numbers_list, status=CourtSMSStatus.COMPLETED
                ).first()

                if completed_sms:
                    logger.info(f"🔄 文书已成功处理完成: {record.ah} - {record.fssj}, SMS ID={completed_sms.id}")
                    result_queue.put(False)
                else:
                    # 解析发送时间
                    send_time = record.parse_fssj()
                    if send_time:
                        from django.utils import timezone

                        send_time = timezone.make_aware(send_time)

                    # 检查是否有未完成的记录,如果有则删除重新处理
                    if send_time:
                        existing_history = DocumentQueryHistory.objects.filter(
                            credential_id=credential_id, case_number=record.ah, send_time=send_time
                        ).first()

                        if existing_history:
                            logger.info(f"🔄 文书有历史记录但未成功完成,重新处理: {record.ah}")
                            existing_history.delete()

                    logger.info(f"🆕 文书符合处理条件: {record.ah} - {record.fssj}")
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

    def download_document(self, record: DocumentRecord, token: str) -> tuple[list[str], str] | None:
        """
        通过 API 下载文书

        流程:
        1. 调用 api_client.fetch_document_details 获取下载链接
        2. 遍历文书列表,下载每个文书

        Args:
            record: 文书记录
            token: 认证令牌

        Returns:
            (下载的文件路径列表, 临时目录路径) 或 None

        Requirements: 2.1, 2.2, 2.3
        """
        logger.info(f"开始 API 下载文书: {record.ah}, sdbh={record.sdbh}")

        try:
            # 1. 获取文书详情(下载链接)
            details = self.api_client.fetch_document_details(token=token, sdbh=record.sdbh)

            if not details:
                logger.warning(f"未获取到文书详情: sdbh={record.sdbh}")
                return None

            logger.info(f"获取到 {len(details)} 个文书下载链接")

            # 2. 下载所有文书
            temp_dir = tempfile.mkdtemp(prefix="court_document_api_")
            downloaded_files: list[Any] = []

            for detail in details:
                if not detail.wjlj:
                    logger.warning(f"文书缺少下载链接: {detail.c_wsmc}")
                    continue

                # 构建文件名
                file_ext = detail.c_wjgs or "pdf"
                file_name = f"{detail.c_wsmc}.{file_ext}"
                save_path = Path(temp_dir) / file_name

                # 下载文书
                success = self.api_client.download_document(url=detail.wjlj, save_path=save_path)

                if success:
                    downloaded_files.append(str(save_path))
                    logger.info(f"文书下载成功: {file_name}")
                else:
                    logger.warning(f"文书下载失败: {file_name}")

            if not downloaded_files:
                logger.error("所有文书下载失败")
                return None

            logger.info(f"成功下载 {len(downloaded_files)} 个文书")
            return downloaded_files, temp_dir

        except Exception as e:
            logger.error(f"API 下载文书失败: {e!s}")
            return None

    def create_delivery_record(self, api_record: DocumentRecord) -> DocumentDeliveryRecord:
        """
        从 API 记录创建投递记录

        Args:
            api_record: API 文书记录

        Returns:
            DocumentDeliveryRecord
        """
        send_time = api_record.parse_fssj()
        if send_time:
            from django.utils import timezone

            send_time = timezone.make_aware(send_time)
        else:
            from django.utils import timezone

            send_time = timezone.now()

        return DocumentDeliveryRecord(
            case_number=api_record.ah,
            send_time=send_time,
            element_index=0,  # API 方式不需要元素索引
            document_name=api_record.wsmc,
            court_name=api_record.fymc,
        )
