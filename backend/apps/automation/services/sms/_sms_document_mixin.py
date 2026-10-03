"""短信文书提取与重命名 Mixin"""

import logging
from typing import TYPE_CHECKING, Any

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService
from apps.core.services.storage_service import resolve_media_path

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

    def _extract_and_update_sms_from_documents(self, sms: CourtSMS) -> None:  # pragma: no cover
        """从文书中提取案号和当事人，并回写到 CourtSMS 记录"""
        document_paths = self._get_document_paths_for_extraction(sms)
        if not document_paths:
            logger.info("短信 %s 没有已下载的文书，跳过文书信息提取", sms.id)
            return

        logger.info("开始从 %s 个文书中提取案号和当事人: SMS ID=%s", len(document_paths), sms.id)

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
                "已更新短信记录的案号和当事人: SMS ID=%s, 案号=%s, 当事人=%s", sms.id, sms.case_numbers, sms.party_names
            )

    def _extract_from_single_document(self, doc_path: str, case_numbers: list[str], party_names: list[str]) -> bool:
        """从单个文书中提取案号和当事人，返回是否有更新"""
        updated = False
        try:
            if not case_numbers:
                nums = self.case_number_extractor.extract_from_document(doc_path)
                if nums:
                    case_numbers.extend(nums)
                    logger.info("从文书 %s 提取到案号: %s", doc_path, nums)
                    updated = True

            if not party_names:
                names = self.matcher.extract_parties_from_document(doc_path)
                if names:
                    party_names.extend(names)
                    logger.info("从文书 %s 提取到当事人: %s", doc_path, names)
                    updated = True
        except Exception as e:
            logger.warning("从文书提取信息失败: %s, 错误: %s", doc_path, e)
        return updated

    def _get_document_paths_for_extraction(self, sms: CourtSMS) -> list[Any]:
        """获取用于提取信息的文书路径列表"""
        document_paths = []

        try:
            if isinstance(sms.document_file_paths, list):
                for file_path in sms.document_file_paths:
                    if file_path and resolve_media_path(file_path).exists():
                        document_paths.append(file_path)

            if sms.scraper_task and hasattr(sms.scraper_task, "documents"):
                documents = sms.scraper_task.documents.filter(download_status="success")
                for doc in documents:
                    if doc.local_file_path and resolve_media_path(doc.local_file_path).exists():
                        document_paths.append(doc.local_file_path)

            if not document_paths and sms.scraper_task:
                result = sms.scraper_task.result
                if result and isinstance(result, dict):
                    files = result.get("files", [])
                    for file_path in files:
                        if file_path and resolve_media_path(file_path).exists():
                            document_paths.append(file_path)

        except Exception as e:
            logger.warning("获取文书路径失败: SMS ID=%s, 错误: %s", sms.id, e)

        return list(dict.fromkeys(document_paths))

    def _process_renaming(self, sms: CourtSMS) -> CourtSMS:  # pragma: no cover
        """处理文书重命名阶段"""
        logger.info("开始重命名文书: SMS ID=%s", sms.id)

        try:
            sms.status = CourtSMSStatus.RENAMING
            sms.save()

            # 获取文书路径：优先从 scraper_task，否则从 document_file_paths
            if sms.scraper_task:
                document_paths = self.document_attachment.get_paths_for_renaming(sms)
            elif isinstance(sms.document_file_paths, list) and sms.document_file_paths:
                document_paths = [p for p in sms.document_file_paths if p and resolve_media_path(p).exists()]
                logger.info("短信 %s 无下载任务，使用 document_file_paths: %s 个文件", sms.id, len(document_paths))
            else:
                logger.info("短信 %s 无下载任务且无文书文件，跳过重命名", sms.id)
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                return sms

            if not document_paths:
                logger.info("短信 %s 无可重命名的文书，跳过重命名", sms.id)
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                return sms

            logger.info("短信 %s 找到 %s 个文书待重命名", sms.id, len(document_paths))
            renamed_paths = self.document_attachment.rename_documents(sms, document_paths)
            logger.info("短信 %s 重命名结果: %s 个文件", sms.id, len(renamed_paths))

            self._save_renamed_paths(sms, renamed_paths)
            self._attach_to_case_log(sms, renamed_paths)
            self._archive_to_case_folder(sms, renamed_paths)
            self._sync_case_numbers_from_documents(sms, renamed_paths)
            self._sync_party_names_from_documents(sms, renamed_paths)

            logger.info("文书重命名阶段完成: SMS ID=%s, 成功重命名 %s 个文书", sms.id, len(renamed_paths))
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms

        except Exception as e:
            logger.error("文书重命名阶段失败: SMS ID=%s, 错误: %s", sms.id, e)
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms

    def _save_renamed_paths(self, sms: CourtSMS, renamed_paths: list[str]) -> None:  # pragma: no cover
        """保存重命名后的文件路径到 scraper_task.result"""
        if not renamed_paths or not sms.scraper_task:
            return
        result = sms.scraper_task.result or {}
        if not isinstance(result, dict):
            result = {}
        result["renamed_files"] = renamed_paths
        sms.scraper_task.result = result
        sms.scraper_task.save()
        logger.info("保存重命名后的文件路径到任务结果: %s 个文件", len(renamed_paths))

    def _attach_to_case_log(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """将文书附件添加到案件日志"""
        if not renamed_paths:
            return
        if sms.case_log:
            self.document_attachment.add_to_case_log(sms, renamed_paths)
        elif sms.case:
            logger.info("短信 %s 没有案件日志，先创建案件日志", sms.id)
            success = self._create_case_binding(sms)  # type: ignore[attr-defined]
            if success and sms.case_log:
                self.document_attachment.add_to_case_log(sms, renamed_paths)
            else:
                logger.warning("短信 %s 创建案件日志失败，无法添加文书附件", sms.id)

    def _sync_case_numbers_from_documents(self, sms: CourtSMS, renamed_paths: list[str]) -> None:  # pragma: no cover
        """从文书中提取案号并同步到案件"""
        if not sms.case or not renamed_paths:
            return

        logger.info("开始从文书中提取案号: SMS ID=%s", sms.id)
        case_numbers_to_sync = list(sms.case_numbers) if sms.case_numbers else []
        extracted_from_document = False

        if not case_numbers_to_sync:
            for file_path in renamed_paths:
                try:
                    extracted = self.case_number_extractor.extract_from_document(file_path)
                    if extracted:
                        case_numbers_to_sync.extend(extracted)
                        extracted_from_document = True
                        logger.info("从文书 %s 提取到案号: %s", file_path, extracted)
                        break
                except Exception as e:
                    logger.warning("从文书提取案号失败: %s, 错误: %s", file_path, e)

        if extracted_from_document and case_numbers_to_sync:
            sms.case_numbers = list(dict.fromkeys(case_numbers_to_sync))
            sms.save()
            logger.info("已将提取的案号回写到短信记录: SMS ID=%s, 案号=%s", sms.id, sms.case_numbers)

        if case_numbers_to_sync:
            count = self.case_number_extractor.sync_to_case(
                case_id=sms.case.id,
                case_numbers=case_numbers_to_sync,
                sms_id=sms.id,
            )
            logger.info("案号同步完成: SMS ID=%s, 写入 %s 个新案号", sms.id, count)

    def _archive_to_case_folder(self, sms: CourtSMS, renamed_paths: list[str]) -> None:
        """将短信和文书归档到案件绑定目录（非阻塞）"""
        logger.info("短信 %s 归档检查: case_id=%s, renamed_paths=%s 个", sms.id, sms.case_id, len(renamed_paths))
        if not sms.case_id:
            logger.info("短信 %s 未关联案件，跳过归档", sms.id)
            return
        if not renamed_paths:
            logger.info("短信 %s 无文书文件，跳过归档", sms.id)
            return
        try:
            archived = self.case_folder_archive.archive_sms_documents(sms, renamed_paths)
            if archived:
                logger.info("短信 %s 已归档到案件绑定目录", sms.id)
            else:
                logger.warning("短信 %s 归档返回 False，可能未找到案件绑定目录", sms.id)
        except Exception as e:
            logger.warning("短信 %s 归档到案件绑定目录失败，不影响主流程: %s", sms.id, e)

    def _sync_party_names_from_documents(self, sms: CourtSMS, renamed_paths: list[str]) -> None:  # pragma: no cover
        """从文书中提取当事人并回写到 CourtSMS"""
        if not renamed_paths or sms.party_names:
            return
        logger.info("开始从文书中提取当事人: SMS ID=%s", sms.id)
        for file_path in renamed_paths:
            try:
                parties = self.matcher.extract_parties_from_document(file_path)
                if parties:
                    sms.party_names = list(dict.fromkeys(parties))
                    sms.save()
                    logger.info("已将提取的当事人回写到短信记录: SMS ID=%s, 当事人=%s", sms.id, sms.party_names)
                    break
            except Exception as e:
                logger.warning("从文书提取当事人失败: %s, 错误: %s", file_path, e)
