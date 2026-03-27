"""短信文书提取与重命名 Mixin"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from apps.automation.models import CourtSMS, CourtSMSStatus

if TYPE_CHECKING:
    from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.matching.case_number_extractor_service import CaseNumberExtractorService
    from apps.automation.services.sms.matching.document_attachment_service import DocumentAttachmentService

logger = logging.getLogger("apps.automation")


class SMSDocumentMixin:
    """负责文书信息提取和重命名流程"""

    @property
    def case_number_extractor(self) -> "CaseNumberExtractorService":
        raise NotImplementedError

    @property
    def document_attachment(self) -> "DocumentAttachmentService":
        raise NotImplementedError

    @property
    def matcher(self) -> "CaseMatcher":
        raise NotImplementedError

    @property
    def case_folder_archive(self) -> "CaseFolderArchiveService":
        raise NotImplementedError

    def _extract_and_update_sms_from_documents(self, sms: CourtSMS) -> None:
        """从文书中提取案号和当事人，并回写到 CourtSMS 记录"""
        if not sms.scraper_task:
            logger.info(f"短信 {sms.id} 没有下载任务，跳过文书信息提取")
            return

        document_paths = self._get_document_paths_for_extraction(sms)
        if not document_paths:
            logger.info(f"短信 {sms.id} 没有已下载的文书，跳过文书信息提取")
            return

        logger.info(f"开始从 {len(document_paths)} 个文书中提取案号和当事人: SMS ID={sms.id}")

        case_numbers = list(sms.case_numbers) if sms.case_numbers else []
        party_names = list(sms.party_names) if sms.party_names else []
        has_updates = False

        for doc_path in document_paths:
            updated = self._extract_from_single_document(doc_path, case_numbers, party_names)
            if updated:
                has_updates = True
            if case_numbers and party_names:
                break

        if has_updates:
            sms.case_numbers = list(dict.fromkeys(case_numbers))
            sms.party_names = list(dict.fromkeys(party_names))
            sms.save()
            logger.info(
                f"已更新短信记录的案号和当事人: SMS ID={sms.id}, 案号={sms.case_numbers}, 当事人={sms.party_names}"
            )

    def _extract_from_single_document(self, doc_path: str, case_numbers: list[str], party_names: list[str]) -> bool:
        """从单个文书中提取案号和当事人，返回是否有更新"""
        updated = False
        try:
            if not case_numbers:
                nums = self.case_number_extractor.extract_from_document(doc_path)
                if nums:
                    case_numbers.extend(nums)
                    logger.info(f"从文书 {doc_path} 提取到案号: {nums}")
                    updated = True

            if not party_names:
                names = self.matcher.extract_parties_from_document(doc_path)
                if names:
                    party_names.extend(names)
                    logger.info(f"从文书 {doc_path} 提取到当事人: {names}")
                    updated = True
        except Exception as e:
            logger.warning(f"从文书提取信息失败: {doc_path}, 错误: {e!s}")
        return updated

    def _get_document_paths_for_extraction(self, sms: CourtSMS) -> list[Any]:
        """获取用于提取信息的文书路径列表"""
        document_paths = []

        try:
            if sms.scraper_task and hasattr(sms.scraper_task, "documents"):
                documents = sms.scraper_task.documents.filter(download_status="success")
                for doc in documents:
                    if doc.local_file_path and Path(doc.local_file_path).exists():
                        document_paths.append(doc.local_file_path)

            if not document_paths and sms.scraper_task:
                result = sms.scraper_task.result
                if result and isinstance(result, dict):
                    files = result.get("files", [])
                    for file_path in files:
                        if file_path and Path(file_path).exists():
                            document_paths.append(file_path)

        except Exception as e:
            logger.warning(f"获取文书路径失败: SMS ID={sms.id}, 错误: {e!s}")

        return document_paths

    def _process_renaming(self, sms: CourtSMS) -> CourtSMS:
        """处理文书重命名阶段"""
        logger.info(f"开始重命名文书: SMS ID={sms.id}")

        try:
            sms.status = CourtSMSStatus.RENAMING
            sms.save()

            if not sms.scraper_task:
                logger.info(f"短信 {sms.id} 无下载任务，跳过重命名")
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                return sms

            document_paths = self.document_attachment.get_paths_for_renaming(sms)
            if not document_paths:
                logger.info(f"短信 {sms.id} 无可重命名的文书，跳过重命名")
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                return sms

            logger.info(f"短信 {sms.id} 找到 {len(document_paths)} 个文书待重命名")
            renamed_paths = self.document_attachment.rename_documents(sms, document_paths)

            self._save_renamed_paths(sms, renamed_paths)
            self._attach_to_case_log(sms, renamed_paths)
            self._archive_to_case_folder(sms, renamed_paths)
            self._sync_case_numbers_from_documents(sms, renamed_paths)
            self._sync_party_names_from_documents(sms, renamed_paths)

            logger.info(f"文书重命名阶段完成: SMS ID={sms.id}, 成功重命名 {len(renamed_paths)} 个文书")
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms

        except Exception as e:
            logger.error(f"文书重命名阶段失败: SMS ID={sms.id}, 错误: {e!s}")
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms

    def _save_renamed_paths(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """保存重命名后的文件路径到 scraper_task.result"""
        if not renamed_paths or not sms.scraper_task:
            return
        result = sms.scraper_task.result or {}
        if not isinstance(result, dict):
            result = {}
        result["renamed_files"] = renamed_paths
        sms.scraper_task.result = result
        sms.scraper_task.save()
        logger.info(f"保存重命名后的文件路径到任务结果: {len(renamed_paths)} 个文件")

    def _attach_to_case_log(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """将文书附件添加到案件日志"""
        if not renamed_paths:
            return
        if sms.case_log:
            self.document_attachment.add_to_case_log(sms, renamed_paths)
        elif sms.case:
            logger.info(f"短信 {sms.id} 没有案件日志，先创建案件日志")
            success = self._create_case_binding(sms)
            if success and sms.case_log:
                self.document_attachment.add_to_case_log(sms, renamed_paths)
            else:
                logger.warning(f"短信 {sms.id} 创建案件日志失败，无法添加文书附件")

    def _sync_case_numbers_from_documents(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """从文书中提取案号并同步到案件"""
        if not sms.case or not renamed_paths:
            return

        logger.info(f"开始从文书中提取案号: SMS ID={sms.id}")
        case_numbers_to_sync = list(sms.case_numbers) if sms.case_numbers else []
        extracted_from_document = False

        if not case_numbers_to_sync:
            for file_path in renamed_paths:
                try:
                    extracted = self.case_number_extractor.extract_from_document(file_path)
                    if extracted:
                        case_numbers_to_sync.extend(extracted)
                        extracted_from_document = True
                        logger.info(f"从文书 {file_path} 提取到案号: {extracted}")
                        break
                except Exception as e:
                    logger.warning(f"从文书提取案号失败: {file_path}, 错误: {e!s}")

        if extracted_from_document and case_numbers_to_sync:
            sms.case_numbers = list(dict.fromkeys(case_numbers_to_sync))
            sms.save()
            logger.info(f"已将提取的案号回写到短信记录: SMS ID={sms.id}, 案号={sms.case_numbers}")

        if case_numbers_to_sync:
            count = self.case_number_extractor.sync_to_case(
                case_id=sms.case.id,
                case_numbers=case_numbers_to_sync,
                sms_id=sms.id,
            )
            logger.info(f"案号同步完成: SMS ID={sms.id}, 写入 {count} 个新案号")

    def _archive_to_case_folder(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """将短信和文书归档到案件绑定目录（非阻塞）"""
        if not sms.case_id or not renamed_paths:
            return
        try:
            archived = self.case_folder_archive.archive_sms_documents(sms, renamed_paths)
            if archived:
                logger.info(f"短信 {sms.id} 已归档到案件绑定目录")
        except Exception as e:
            logger.warning(f"短信 {sms.id} 归档到案件绑定目录失败，不影响主流程: {e!s}")

    def _sync_party_names_from_documents(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """从文书中提取当事人并回写到 CourtSMS"""
        if not renamed_paths or sms.party_names:
            return
        logger.info(f"开始从文书中提取当事人: SMS ID={sms.id}")
        for file_path in renamed_paths:
            try:
                parties = self.matcher.extract_parties_from_document(file_path)
                if parties:
                    sms.party_names = list(dict.fromkeys(parties))
                    sms.save()
                    logger.info(f"已将提取的当事人回写到短信记录: SMS ID={sms.id}, 当事人={sms.party_names}")
                    break
            except Exception as e:
                logger.warning(f"从文书提取当事人失败: {file_path}, 错误: {e!s}")
