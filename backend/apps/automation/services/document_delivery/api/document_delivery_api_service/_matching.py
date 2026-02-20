"""案件匹配、文书重命名、通知发送逻辑"""

import logging
import os
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")

__all__ = ["DocumentMatchingMixin"]


class DocumentMatchingMixin:
    """案件匹配、重命名、通知 Mixin"""

    case_matcher: "CaseMatcher"
    document_renamer: "DocumentRenamer"
    notification_service: "SMSNotificationService"

    def _match_case_by_number(self, case_number: str) -> Any:
        """通过案号匹配案件（Requirements: 3.1）"""
        return self.case_matcher.match_by_case_number([case_number])

    def _match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        """从文书中提取当事人进行案件匹配（Requirements: 3.1）"""
        try:
            from apps.core.enums import CaseStatus

            for doc_path in document_paths:
                logger.info(f"尝试从文书中提取当事人: {doc_path}")

                extracted_parties = self.case_matcher.extract_parties_from_document(doc_path)

                if not extracted_parties:
                    logger.info(f"从文书 {doc_path} 中未能提取到当事人")
                    continue

                logger.info(f"从文书中提取到当事人: {extracted_parties}")

                matched_case = self.case_matcher.match_by_party_names(extracted_parties)

                if matched_case:
                    if matched_case.status == CaseStatus.ACTIVE:
                        logger.info(f"通过文书当事人匹配到在办案件: Case ID={matched_case.id}")
                        return matched_case
                    else:
                        logger.info(f"匹配到案件但状态为 {matched_case.status}，继续尝试")
                        continue
                else:
                    logger.info(f"当事人 {extracted_parties} 未匹配到案件")

            logger.info("所有文书都未能匹配到在办案件")
            return None

        except Exception as e:
            logger.warning(f"从文书提取当事人匹配失败: {e!s}")
            return None

    def _sync_case_number_to_case(self, case_id: int, case_number: str) -> bool:
        """将案号同步到案件"""
        try:
            from apps.core.dependencies.business_case import build_case_number_service

            case_number_service = build_case_number_service()

            existing_numbers = case_number_service.list_numbers(case_id=case_id) # type: ignore

            for num in existing_numbers:
                if num.number == case_number:
                    logger.info(f"案件 {case_id} 已有案号 {case_number}，无需同步")
                    return True

            case_number_service.create_number(case_id=case_id, number=case_number, remarks="文书送达自动下载同步") # type: ignore

            logger.info(f"案号同步成功: Case ID={case_id}, 案号={case_number}")
            return True

        except Exception as e:
            logger.warning(f"案号同步失败: Case ID={case_id}, 案号={case_number}, 错误: {e!s}")
            return False

    def _rename_and_attach_documents(self, sms: Any, case: Any, extracted_files: list[str]) -> tuple[Any, ...]:
        """重命名文书并添加到案件日志"""
        renamed_files: list[str] = []
        case_log_id = None

        try:
            for file_path in extracted_files:
                try:
                    renamed_path = self.document_renamer.rename(
                        document_path=file_path, case_name=case.name, received_date=date.today()
                    )
                    if renamed_path:
                        renamed_files.append(renamed_path)
                        logger.info(f"文书重命名成功: {file_path} -> {renamed_path}")
                    else:
                        renamed_files.append(file_path)
                except Exception as e:
                    logger.warning(f"文书重命名失败: {file_path}, 错误: {e!s}")
                    renamed_files.append(file_path)

            if renamed_files:
                from apps.core.dependencies.business_case import build_case_log_service

                case_log_service = build_case_log_service()
                file_names = [f.split("/")[-1] for f in renamed_files]
                case_log = case_log_service.create_log(
                    case_id=case.id,
                    content=f"文书送达自动下载: {', '.join(file_names)}",
                    user=None,
                )
                if case_log:
                    case_log_id = case_log.id
                    logger.info(f"案件日志创建成功: CaseLog ID={case_log_id}")

                    from django.core.files.uploadedfile import SimpleUploadedFile

                    for file_path in renamed_files:
                        try:
                            if os.path.exists(file_path):
                                with open(file_path, "rb") as f:
                                    file_content = f.read()
                                file_name = os.path.basename(file_path)
                                uploaded_file = SimpleUploadedFile(
                                    name=file_name,
                                    content=file_content,
                                    content_type="application/octet-stream",
                                )
                                case_log_service.upload_attachments(
                                    log_id=case_log.id,
                                    files=[uploaded_file],
                                    user=None,
                                    perm_open_access=True,
                                )
                                logger.info(f"附件上传成功: {file_name}")
                        except Exception as e:
                            logger.warning(f"添加附件失败: {file_path}, 错误: {e!s}")

        except Exception as e:
            logger.error(f"重命名和附件处理失败: {e!s}")

        return renamed_files, case_log_id

    def _send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        """发送通知"""
        try:
            if not sms.case:
                logger.warning(f"SMS {sms.id} 未绑定案件，无法发送通知")
                return False

            return self.notification_service.send_case_chat_notification(sms, document_paths)
        except Exception as e:
            logger.error(f"发送通知失败: {e!s}")
            return False
