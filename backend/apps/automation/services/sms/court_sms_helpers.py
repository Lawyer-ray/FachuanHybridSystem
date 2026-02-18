"""Business logic services."""

from __future__ import annotations

"""
法院短信辅助方法 Mixin

负责短信处理的辅助功能,包括:
- 下载任务创建
- 下载等待检查
- 案件绑定创建
- 文书信息提取

作为 CourtSMSService 的 Mixin 使用.
"""

import logging
from typing import TYPE_CHECKING, Any, Protocol

from apps.automation.models import CourtSMS, ScraperTask, ScraperTaskStatus, ScraperTaskType
from apps.automation.utils.logging_mixins.common import sanitize_url
from apps.core.path import Path

if TYPE_CHECKING:
    from apps.core.protocols import ICaseService, ILawyerService

    class _SMSHelperHost(Protocol):
        @property
        def lawyer_service(self) -> ILawyerService: ...
        @property
        def case_service(self) -> ICaseService: ...
        @property
        def caselog_service(self) -> Any: ...
        @property
        def task_queue(self) -> Any: ...
        @property
        def case_number_extractor(self) -> Any: ...
        @property
        def matcher(self) -> Any: ...


logger = logging.getLogger("apps.automation")


def _filter_valid_case_numbers(case_numbers: list[Any]) -> list[Any]:
    """过滤掉明显不是案号的内容(如日期)"""
    import re

    valid: list[Any] = []
    for num in case_numbers:
        if (
            "年" in num
            and "月" in num
            and ("日" in num or num.endswith("号"))
            and re.match(r"^\d{4}年\d{1,2}月\d{1,2}[日号]?$", num)
        ):
            continue
        valid.append(num)
    return valid


class CourtSMSHelpersMixin:
    """法院短信辅助方法 Mixin

    提供短信处理的辅助功能,包括:
    - 下载任务创建
    - 下载等待检查
    - 案件绑定创建
    - 文书信息提取
    """

    def _create_download_task(self: _SMSHelperHost, sms: CourtSMS) -> ScraperTask | None:
        """
        创建下载任务并关联到短信记录,然后提交到 Django Q 队列执行
        """
        if not sms.download_links:
            return None

        try:
            download_url = sms.download_links[0]

            task = ScraperTask.objects.create(
                task_type=ScraperTaskType.COURT_DOCUMENT, url=download_url, case=sms.case, config={}
            )

            task_id = task.pk
            logger.info(f"创建下载任务成功: Task ID={task_id}, URL={sanitize_url(download_url)}")

            from apps.automation.tasks import execute_scraper_task

            queue_task_id = self.task_queue.enqueue(
                execute_scraper_task,
                task_id,
                task_name=f"court_document_download_{task_id}",
            )

            logger.info(f"提交下载任务到队列: Task ID={task_id}, Queue Task ID={queue_task_id}")

            return task

        except Exception as e:
            logger.error(f"创建下载任务失败: SMS ID={sms.pk}, 错误: {e!s}")
            return None

    def _should_wait_for_document_download(self: _SMSHelperHost, sms: CourtSMS) -> bool:
        """检查是否需要等待文书下载完成后再进行匹配"""
        try:
            if sms.party_names:
                return False
            if not sms.download_links or not sms.scraper_task:
                return False

            if not self._refresh_scraper_task_status(sms):  # type: ignore[attr-defined]
                return False

            task = sms.scraper_task
            if task is None:
                return False
            if task.status in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
                logger.info(f"短信 {sms.pk} 的下载任务已完成(状态: {task.status}),不再等待")
                return False

            return self._check_documents_need_wait(sms)

        except Exception as e:
            logger.error(f"检查下载状态失败: SMS ID={sms.pk}, 错误: {e!s}")
            return False

    def _refresh_scraper_task_status(self, sms: CourtSMS) -> bool:
        """刷新 ScraperTask 状态,返回任务是否存在"""
        try:
            if sms.scraper_task is None:
                logger.warning(f"短信 {sms.pk} 的下载任务不存在,无需等待")
                return False
            scraper_task = sms.scraper_task
            fresh_task = ScraperTask.objects.get(id=scraper_task.pk)
            sms.scraper_task = fresh_task
            return True
        except ScraperTask.DoesNotExist:
            logger.warning(f"短信 {sms.pk} 的下载任务不存在,无需等待")
            return False

    def _check_documents_need_wait(self, sms: CourtSMS) -> bool:
        """检查文书下载状态,返回是否需要等待"""
        task = sms.scraper_task
        if task is None:
            return False
        task_in_progress = task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]

        if not hasattr(task, "documents"):
            return task_in_progress

        all_documents = task.documents.all()
        if not all_documents.exists():
            return task_in_progress

        successful = all_documents.filter(download_status="success")
        if successful.exists():
            return False

        pending = all_documents.filter(download_status="pending")
        downloading = all_documents.filter(download_status="downloading")

        if not pending.exists() and not downloading.exists():
            return False

        return task_in_progress or pending.exists() or downloading.exists()

    def _create_case_binding(self: _SMSHelperHost, sms: CourtSMS) -> bool:
        """
        创建案件绑定和日志

        注意:
        1. 此方法只创建案件日志,不添加附件.附件会在 _process_renaming 阶段完成重命名后添加.
        2. 如果短信提取到案号,但案件中还没有该案号,则自动写入案件的 case_numbers 字段.
        """
        if not sms.case:
            return False

        try:
            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer_internal()
            if not admin_lawyer_dto:
                logger.error("未找到管理员用户,无法创建案件日志")
                return False

            system_user = self.lawyer_service.get_admin_lawyer_internal()

            if sms.case_numbers:
                self._add_case_numbers_to_case(sms)  # type: ignore[attr-defined]

            case = sms.case
            case_id = case.pk  # type: ignore[attr-defined]
            case_log = self.caselog_service.create_log(
                case_id=case_id, content=f"收到法院短信:{sms.content}", user=system_user
            )

            sms.case_log = case_log
            sms.save()

            logger.info(f"案件绑定创建成功: SMS ID={sms.pk}, CaseLog ID={case_log.pk}")
            return True

        except Exception as e:
            logger.error(f"创建案件绑定失败: SMS ID={sms.pk}, 错误: {e!s}")
            return False

    def _add_case_numbers_to_case(self: _SMSHelperHost, sms: CourtSMS) -> None:
        """将短信中提取的案号写入案件(如果不存在)"""
        if not sms.case or not sms.case_numbers:
            return

        try:
            valid_case_numbers = _filter_valid_case_numbers(sms.case_numbers)

            if not valid_case_numbers:
                logger.info(f"短信 {sms.pk} 没有有效的案号需要写入")
                return

            admin_lawyer_dto = self.lawyer_service.get_admin_lawyer_internal()
            user_id = admin_lawyer_dto.id if admin_lawyer_dto else None

            case = sms.case
            case_id = case.pk  # type: ignore[attr-defined]
            added_count = 0
            for case_number in valid_case_numbers:
                success = self.case_service.add_case_number_internal(
                    case_id=case_id, case_number=case_number, user_id=user_id
                )
                if success:
                    added_count += 1

            if added_count > 0:
                logger.info(f"为案件 {case_id} 添加了 {added_count} 个案号: {valid_case_numbers}")

        except Exception as e:
            logger.warning(f"写入案号失败: SMS ID={sms.pk}, 错误: {e!s}")

    def _extract_and_update_sms_from_documents(self: _SMSHelperHost, sms: CourtSMS) -> None:
        """从文书中提取案号和当事人,并回写到 CourtSMS 记录"""
        if not sms.scraper_task:
            return

        document_paths = self._get_document_paths_for_extraction(sms)  # type: ignore
        if not document_paths:
            return

        extracted_case_numbers = list(sms.case_numbers) if sms.case_numbers else []
        extracted_party_names = list(sms.party_names) if sms.party_names else []
        has_updates = False

        for doc_path in document_paths:
            updated = self._extract_from_single_doc(doc_path, extracted_case_numbers, extracted_party_names)  # type: ignore[attr-defined]
            has_updates = has_updates or updated
            if extracted_case_numbers and extracted_party_names:
                break

        if has_updates:
            sms.case_numbers = list(dict.fromkeys(extracted_case_numbers))
            sms.party_names = list(dict.fromkeys(extracted_party_names))
            sms.save()

    def _extract_from_single_doc(
        self: _SMSHelperHost, doc_path: Any, case_numbers: list[Any], party_names: list[Any]
    ) -> bool:
        """从单个文书提取信息,返回是否有更新"""
        updated = False
        try:
            if not case_numbers:
                numbers = self.case_number_extractor.extract_from_document(doc_path)
                if numbers:
                    case_numbers.extend(numbers)
                    updated = True
            if not party_names:
                names = self.matcher.extract_parties_from_document(doc_path)
                if names:
                    party_names.extend(names)
                    updated = True
        except Exception as e:
            logger.warning(f"从文书提取信息失败: {doc_path}, 错误: {e!s}")
        return updated

    def _get_document_paths_for_extraction(self, sms: CourtSMS) -> list[Any]:
        """
        获取用于提取信息的文书路径列表

        Args:
            sms: CourtSMS 实例

        Returns:
            文书路径列表
        """
        document_paths: list[Any] = []

        try:
            if sms.scraper_task and hasattr(sms.scraper_task, "documents"):
                documents = sms.scraper_task.documents.filter(download_status="success")  # type: ignore[attr-defined]
                for doc in documents:
                    abs_path = doc.absolute_file_path
                    if abs_path and Path(abs_path).exists():
                        document_paths.append(abs_path)

            if not document_paths and sms.scraper_task:
                result = sms.scraper_task.result  # type: ignore[attr-defined]
                if result and isinstance(result, dict):
                    files = result.get("files", [])
                    for file_path in files:
                        if file_path and Path(file_path).exists():
                            document_paths.append(file_path)

        except Exception as e:
            logger.warning(f"获取文书路径失败: SMS ID={sms.pk}, 错误: {e!s}")

        return document_paths
