"""
SMS 重命名阶段处理器

负责处理文书重命名和附件添加。
Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
"""
import logging
from typing import Optional, List, TYPE_CHECKING

from apps.automation.models import CourtSMS, CourtSMSStatus
from apps.core.interfaces import ServiceLocator
from .base import BaseSMSStage

if TYPE_CHECKING:
    from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
    from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.core.interfaces import ILawyerService

logger = logging.getLogger("apps.automation")


class SMSRenamingStage(BaseSMSStage):
    """SMS 重命名阶段处理器"""
    
    def __init__(
        self,
        document_attachment: Optional["DocumentAttachmentService"] = None,
        case_number_extractor: Optional["CaseNumberExtractorService"] = None,
        matcher: Optional["CaseMatcher"] = None,
        lawyer_service: Optional["ILawyerService"] = None,
    ):
        self._document_attachment = document_attachment
        self._case_number_extractor = case_number_extractor
        self._matcher = matcher
        self._lawyer_service = lawyer_service
    
    @property
    def document_attachment(self) -> "DocumentAttachmentService":
        if self._document_attachment is None:
            from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
            self._document_attachment = DocumentAttachmentService()
        return self._document_attachment
    
    @property
    def case_number_extractor(self) -> "CaseNumberExtractorService":
        if self._case_number_extractor is None:
            from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
            self._case_number_extractor = CaseNumberExtractorService()
        return self._case_number_extractor
    
    @property
    def matcher(self) -> "CaseMatcher":
        if self._matcher is None:
            from apps.automation.services.sms.case_matcher import CaseMatcher
            self._matcher = CaseMatcher()
        return self._matcher
    
    @property
    def lawyer_service(self) -> "ILawyerService":
        if self._lawyer_service is None:
            self._lawyer_service = ServiceLocator.get_lawyer_service()
        return self._lawyer_service
    
    @property
    def stage_name(self) -> str:
        return "重命名"
    
    def can_process(self, sms: CourtSMS) -> bool:
        return sms.status == CourtSMSStatus.RENAMING
    
    def process(self, sms: CourtSMS) -> CourtSMS:
        """处理文书重命名阶段"""
        self._log_start(sms)
        
        try:
            sms.status = CourtSMSStatus.RENAMING
            sms.save()
            
            # 无下载任务，跳过重命名
            if not sms.scraper_task:
                logger.info(f"短信 {sms.id} 无下载任务，跳过重命名")
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                self._log_complete(sms)
                return sms
            
            # 获取待重命名的文书路径
            document_paths = self.document_attachment.get_paths_for_renaming(sms)
            if not document_paths:
                logger.info(f"短信 {sms.id} 无可重命名的文书")
                sms.status = CourtSMSStatus.NOTIFYING
                sms.save()
                self._log_complete(sms)
                return sms
            
            logger.info(f"短信 {sms.id} 找到 {len(document_paths)} 个文书待重命名")
            
            # 重命名文书
            renamed_paths = self.document_attachment.rename_documents(sms, document_paths)
            
            # 保存重命名后的文件路径
            self._save_renamed_paths(sms, renamed_paths)
            
            # 添加附件到案件日志
            if renamed_paths:
                self._add_attachments_to_case_log(sms, renamed_paths)
            
            # 从文书中提取案号并同步到案件
            if sms.case and renamed_paths:
                self._extract_and_sync_case_numbers(sms, renamed_paths)
            
            # 从文书中提取当事人
            if renamed_paths and not sms.party_names:
                self._extract_and_update_party_names(sms, renamed_paths)
            
            logger.info(f"重命名完成: SMS={sms.id}, 文书数={len(renamed_paths)}")
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            self._log_complete(sms)
            return sms
            
        except Exception as e:
            self._log_error(sms, e)
            # 重命名失败不影响整体流程
            sms.status = CourtSMSStatus.NOTIFYING
            sms.save()
            return sms
    
    def _save_renamed_paths(self, sms: CourtSMS, renamed_paths: List[str]) -> None:
        """保存重命名后的文件路径到 scraper_task.result"""
        if not renamed_paths or not sms.scraper_task:
            return
        try:
            result = sms.scraper_task.result or {}
            if not isinstance(result, dict):
                result = {}
            result['renamed_files'] = renamed_paths
            sms.scraper_task.result = result
            sms.scraper_task.save()
        except Exception as e:
            logger.warning(f"保存重命名路径失败: SMS={sms.id}, 错误: {e}")
    
    def _add_attachments_to_case_log(self, sms: CourtSMS, renamed_paths: List[str]) -> None:
        """添加附件到案件日志"""
        if sms.case_log:
            self.document_attachment.add_to_case_log(sms, renamed_paths)
        elif sms.case:
            logger.info(f"短信 {sms.id} 没有案件日志，先创建")
            if self._create_case_binding(sms) and sms.case_log:
                self.document_attachment.add_to_case_log(sms, renamed_paths)
    
    def _create_case_binding(self, sms: CourtSMS) -> bool:
        """创建案件绑定和日志"""
        if not sms.case:
            return False
        try:
            case_log_service = ServiceLocator.get_caselog_service()
            admin = self.lawyer_service.get_admin_lawyer_internal()
            if not admin:
                logger.error("未找到管理员用户")
                return False
            
            user = self.lawyer_service.get_lawyer_internal(admin.id)
            case_log = case_log_service.create_log(
                case_id=sms.case.id,
                content=f"收到法院短信：{sms.content}",
                user=user
            )
            sms.case_log = case_log
            sms.save()
            logger.info(f"案件日志创建成功: SMS={sms.id}, CaseLog={case_log.id}")
            return True
        except Exception as e:
            logger.error(f"创建案件日志失败: SMS={sms.id}, 错误: {e}")
            return False
    
    def _extract_and_sync_case_numbers(self, sms: CourtSMS, renamed_paths: List[str]) -> None:
        """从文书中提取案号并同步到案件"""
        case_numbers = list(sms.case_numbers) if sms.case_numbers else []
        extracted = False
        
        # 如果没有案号，从文书中提取
        if not case_numbers:
            for path in renamed_paths:
                try:
                    nums = self.case_number_extractor.extract_from_document(path)
                    if nums:
                        case_numbers.extend(nums)
                        extracted = True
                        break
                except Exception as e:
                    logger.warning(f"提取案号失败: {path}, 错误: {e}")
        
        # 回写到 CourtSMS
        if extracted and case_numbers:
            sms.case_numbers = list(dict.fromkeys(case_numbers))
            sms.save()
        
        # 同步到案件
        if case_numbers:
            self.case_number_extractor.sync_to_case(
                case_id=sms.case.id, case_numbers=case_numbers, sms_id=sms.id
            )
    
    def _extract_and_update_party_names(self, sms: CourtSMS, renamed_paths: List[str]) -> None:
        """从文书中提取当事人"""
        for path in renamed_paths:
            try:
                parties = self.matcher.extract_parties_from_document(path)
                if parties:
                    sms.party_names = list(dict.fromkeys(parties))
                    sms.save()
                    break
            except Exception as e:
                logger.warning(f"提取当事人失败: {path}, 错误: {e}")


def create_sms_renaming_stage(
    document_attachment: Optional["DocumentAttachmentService"] = None,
    case_number_extractor: Optional["CaseNumberExtractorService"] = None,
    matcher: Optional["CaseMatcher"] = None,
    lawyer_service: Optional["ILawyerService"] = None,
) -> SMSRenamingStage:
    """工厂函数：创建 SMS 重命名阶段处理器"""
    return SMSRenamingStage(
        document_attachment=document_attachment,
        case_number_extractor=case_number_extractor,
        matcher=matcher,
        lawyer_service=lawyer_service,
    )
