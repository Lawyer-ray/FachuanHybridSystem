"""案件匹配、文书重命名、通知发送逻辑"""

import logging
from abc import abstractmethod
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

logger = logging.getLogger("apps.automation")

__all__ = ["DocumentMatchingMixin"]


class DocumentMatchingMixin:
    """案件匹配、重命名、通知 Mixin"""

    @property
    @abstractmethod
    def case_matcher(self) -> "CaseMatcher": ...

    @property
    @abstractmethod
    def document_renamer(self) -> "DocumentRenamer": ...

    @property
    @abstractmethod
    def notification_service(self) -> "SMSNotificationService": ...

    def _match_case_by_number(self, case_number: str) -> Any:
        """通过案号匹配案件（Requirements: 3.1）"""
        return self.case_matcher.match_by_case_number([case_number])

    def _match_case_by_document_parties(self, document_paths: list[str]) -> Any:
        """从文书中提取当事人进行案件匹配（Requirements: 3.1）"""
        try:
            from apps.core.models.enums import CaseStatus

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

            list_method = getattr(case_number_service, "list_numbers_internal", None)
            if list_method is None:
                list_method = getattr(case_number_service, "list_numbers", None)

            create_method = getattr(case_number_service, "create_number_internal", None)
            if create_method is None:
                create_method = getattr(case_number_service, "create_number", None)

            if list_method is None or create_method is None:
                logger.warning("案号服务不支持查询或创建方法，跳过案号同步")
                return False

            existing_numbers = list_method(case_id=case_id)
            for num in existing_numbers:
                if getattr(num, "number", None) == case_number:
                    logger.info(f"案件 {case_id} 已有案号 {case_number}，无需同步")
                    return True

            create_method(case_id=case_id, number=case_number, remarks="文书送达自动下载同步")

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
                system_user = self._get_system_user()
                if system_user is None:
                    logger.error("未找到系统用户，无法创建案件日志")
                    return renamed_files, case_log_id

                from apps.core.dependencies.business_case import build_case_log_service

                case_log_service = build_case_log_service()
                file_names = [f.split("/")[-1] for f in renamed_files]
                case_log = case_log_service.create_log(
                    case_id=case.id,
                    content=f"文书送达自动下载: {', '.join(file_names)}",
                    user=system_user,
                )
                if case_log:
                    case_log_id = case_log.id
                    logger.info(f"案件日志创建成功: CaseLog ID={case_log_id}")

                    from django.core.files.uploadedfile import SimpleUploadedFile

                    for file_path in renamed_files:
                        try:
                            if Path(file_path).exists():
                                with open(file_path, "rb") as f:
                                    file_content = f.read()
                                file_name = Path(file_path).name
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

    def _get_system_user(self) -> Any | None:
        """获取系统操作用户（管理员律师）"""
        try:
            from apps.core.interfaces import ServiceLocator

            lawyer_service = ServiceLocator.get_lawyer_service()
            admin_lawyer = lawyer_service.get_admin_lawyer()
            if not admin_lawyer:
                return None
            return lawyer_service.get_lawyer_model(admin_lawyer.id)
        except Exception as e:
            logger.warning(f"获取系统用户失败: {e!s}")
            return None

    def _archive_to_case_folder(self, sms: Any, renamed_paths: list[str]) -> None:
        """将文书归档到案件绑定目录（不影响主流程）"""
        if not sms.case_id or not renamed_paths:
            return

        try:
            from apps.automation.services.sms.case_folder_archive_service import CaseFolderArchiveService

            archived = CaseFolderArchiveService().archive_sms_documents(sms, renamed_paths)
            if archived:
                logger.info(f"短信 {sms.id} 已归档到案件绑定目录")
        except Exception as e:
            logger.warning(f"短信 {sms.id} 归档到案件绑定目录失败，不影响主流程: {e!s}")

    def _send_notification(self, sms: Any, document_paths: list[str]) -> bool:
        """发送通知（多平台扇出），同时持久化通知结果"""
        try:
            if not sms.case:
                logger.warning(f"SMS {sms.id} 未绑定案件，无法发送通知")
                sms.notification_results = {"none": {"success": False, "error": "短信未绑定案件"}}
                return False

            result = self.notification_service.send_case_chat_notification(sms, document_paths)
            # 持久化多平台通知结果
            sms.notification_results = result.to_notification_results()
            return result.any_success
        except Exception as e:
            logger.error(f"发送通知失败: {e!s}")
            sms.notification_results = sms.notification_results or {}
            sms.notification_results["_exception"] = {"success": False, "error": str(e)}
            return False
