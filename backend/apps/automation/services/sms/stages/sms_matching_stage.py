"""
SMS 匹配阶段处理器

负责将短信与案件进行匹配，包括：
- 检查是否需要等待文书下载完成
- 从文书中提取案号和当事人信息
- 执行案件匹配
- 创建案件绑定

Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
"""
import logging
import os
import re
from typing import Optional, List, TYPE_CHECKING

from apps.automation.models import CourtSMS, CourtSMSStatus, ScraperTaskStatus
from apps.core.interfaces import ServiceLocator
from .base import BaseSMSStage

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.case_number_extractor_service import (
        CaseNumberExtractorService,
    )
    from apps.core.interfaces import ICaseService, ILawyerService

logger = logging.getLogger("apps.automation")


class SMSMatchingStage(BaseSMSStage):
    """
    SMS 匹配阶段处理器
    
    负责将短信与案件进行匹配，创建案件绑定。
    """
    
    def __init__(
        self,
        matcher: Optional["CaseMatcher"] = None,
        case_number_extractor: Optional["CaseNumberExtractorService"] = None,
        case_service: Optional["ICaseService"] = None,
        lawyer_service: Optional["ILawyerService"] = None,
    ):
        self._matcher = matcher
        self._case_number_extractor = case_number_extractor
        self._case_service = case_service
        self._lawyer_service = lawyer_service
    
    @property
    def matcher(self) -> "CaseMatcher":
        if self._matcher is None:
            from apps.automation.services.sms.case_matcher import CaseMatcher
            self._matcher = CaseMatcher()
        return self._matcher
    
    @property
    def case_number_extractor(self) -> "CaseNumberExtractorService":
        if self._case_number_extractor is None:
            from apps.automation.services.sms.case_number_extractor_service import (
                CaseNumberExtractorService,
            )
            self._case_number_extractor = CaseNumberExtractorService()
        return self._case_number_extractor
    
    @property
    def case_service(self) -> "ICaseService":
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service
    
    @property
    def lawyer_service(self) -> "ILawyerService":
        if self._lawyer_service is None:
            self._lawyer_service = ServiceLocator.get_lawyer_service()
        return self._lawyer_service
    
    @property
    def stage_name(self) -> str:
        return "匹配"
    
    def can_process(self, sms: CourtSMS) -> bool:
        return sms.status == CourtSMSStatus.MATCHING
    
    def process(self, sms: CourtSMS) -> CourtSMS:
        """处理案件匹配阶段"""
        self._log_start(sms)
        
        try:
            sms.status = CourtSMSStatus.MATCHING
            sms.save()
            
            # 已手动指定案件，直接绑定
            if sms.case:
                return self._handle_manual_case(sms)
            
            # 检查是否需要等待下载
            if self._should_wait_for_document_download(sms):
                logger.info(f"短信 {sms.id} 等待文书下载完成")
                self._log_complete(sms)
                return sms
            
            # 从文书提取信息
            self._extract_and_update_sms_from_documents(sms)
            
            # 执行匹配
            matched_case = self.matcher.match(sms)
            
            if matched_case:
                sms.case_id = matched_case.id
                sms.save()
                logger.info(f"匹配成功: SMS={sms.id}, Case={matched_case.id}")
                
                if self._create_case_binding(sms):
                    sms.status = CourtSMSStatus.RENAMING
                else:
                    sms.status = CourtSMSStatus.FAILED
                    sms.error_message = "创建案件绑定失败"
            else:
                sms.status = CourtSMSStatus.PENDING_MANUAL
                sms.error_message = "未能匹配到唯一的在办案件，需要人工处理"
            
            sms.save()
            self._log_complete(sms)
            return sms
            
        except Exception as e:
            self._log_error(sms, e)
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = f"案件匹配错误: {str(e)}"
            sms.save()
            raise
    
    def _handle_manual_case(self, sms: CourtSMS) -> CourtSMS:
        """处理已手动指定案件的情况"""
        logger.info(f"短信 {sms.id} 已手动指定案件: {sms.case.id}")
        if self._create_case_binding(sms):
            sms.status = CourtSMSStatus.RENAMING
        else:
            sms.status = CourtSMSStatus.FAILED
            sms.error_message = "创建案件绑定失败"
        sms.save()
        self._log_complete(sms)
        return sms
    
    def _should_wait_for_document_download(self, sms: CourtSMS) -> bool:
        """检查是否需要等待文书下载完成"""
        try:
            # 有当事人或无下载链接/任务，不等待
            if sms.party_names or not sms.download_links or not sms.scraper_task:
                return False
            
            # 刷新任务状态
            from apps.automation.models import ScraperTask
            try:
                sms.scraper_task = ScraperTask.objects.get(id=sms.scraper_task.id)
            except ScraperTask.DoesNotExist:
                return False
            
            # 任务已完成，不等待
            if sms.scraper_task.status in [ScraperTaskStatus.SUCCESS, ScraperTaskStatus.FAILED]:
                return False
            
            # 检查文书状态
            if not hasattr(sms.scraper_task, 'documents'):
                return sms.scraper_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]
            
            docs = sms.scraper_task.documents.all()
            if not docs.exists():
                return sms.scraper_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]
            
            # 有成功的文书，不等待
            if docs.filter(download_status='success').exists():
                return False
            
            # 还有待下载/下载中的文书，等待
            pending = docs.filter(download_status__in=['pending', 'downloading']).exists()
            running = sms.scraper_task.status in [ScraperTaskStatus.PENDING, ScraperTaskStatus.RUNNING]
            return pending or running
            
        except Exception as e:
            logger.error(f"检查下载状态失败: SMS={sms.id}, 错误: {e}")
            return False
    
    def _extract_and_update_sms_from_documents(self, sms: CourtSMS) -> None:
        """从文书中提取案号和当事人并回写"""
        if not sms.scraper_task:
            return
        
        doc_paths = self._get_document_paths_for_extraction(sms)
        if not doc_paths:
            return
        
        case_numbers = list(sms.case_numbers) if sms.case_numbers else []
        party_names = list(sms.party_names) if sms.party_names else []
        updated = False
        
        for path in doc_paths:
            try:
                if not case_numbers:
                    nums = self.case_number_extractor.extract_from_document(path)
                    if nums:
                        case_numbers.extend(nums)
                        updated = True
                
                if not party_names:
                    names = self.matcher.extract_parties_from_document(path)
                    if names:
                        party_names.extend(names)
                        updated = True
                
                if case_numbers and party_names:
                    break
            except Exception as e:
                logger.warning(f"从文书提取失败: {path}, 错误: {e}")
        
        if updated:
            sms.case_numbers = list(dict.fromkeys(case_numbers))
            sms.party_names = list(dict.fromkeys(party_names))
            sms.save()
    
    def _get_document_paths_for_extraction(self, sms: CourtSMS) -> List[str]:
        """获取文书路径列表"""
        paths = []
        try:
            if sms.scraper_task and hasattr(sms.scraper_task, 'documents'):
                for doc in sms.scraper_task.documents.filter(download_status='success'):
                    if doc.local_file_path and os.path.exists(doc.local_file_path):
                        paths.append(doc.local_file_path)
            
            if not paths and sms.scraper_task and sms.scraper_task.result:
                result = sms.scraper_task.result
                if isinstance(result, dict):
                    for f in result.get('files', []):
                        if f and os.path.exists(f):
                            paths.append(f)
        except Exception as e:
            logger.warning(f"获取文书路径失败: SMS={sms.id}, 错误: {e}")
        return paths
    
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
            
            if sms.case_numbers:
                self._add_case_numbers_to_case(sms)
            
            case_log = case_log_service.create_log(
                case_id=sms.case.id,
                content=f"收到法院短信：{sms.content}",
                user=user
            )
            sms.case_log = case_log
            sms.save()
            logger.info(f"案件绑定成功: SMS={sms.id}, CaseLog={case_log.id}")
            return True
        except Exception as e:
            logger.error(f"创建案件绑定失败: SMS={sms.id}, 错误: {e}")
            return False
    
    def _add_case_numbers_to_case(self, sms: CourtSMS) -> None:
        """将案号写入案件"""
        if not sms.case or not sms.case_numbers:
            return
        
        try:
            valid_nums = [
                n for n in sms.case_numbers
                if not (("年" in n and "月" in n and "日" in n) or
                       ("年" in n and "月" in n and n.endswith("号") and
                        re.match(r'^\d{4}年\d{1,2}月\d{1,2}号?$', n)))
            ]
            
            if not valid_nums:
                return
            
            admin = self.lawyer_service.get_admin_lawyer_internal()
            user_id = admin.id if admin else None
            
            for num in valid_nums:
                self.case_service.add_case_number_internal(
                    case_id=sms.case.id, case_number=num, user_id=user_id
                )
        except Exception as e:
            logger.warning(f"写入案号失败: SMS={sms.id}, 错误: {e}")


def create_sms_matching_stage(
    matcher: Optional["CaseMatcher"] = None,
    case_number_extractor: Optional["CaseNumberExtractorService"] = None,
    case_service: Optional["ICaseService"] = None,
    lawyer_service: Optional["ILawyerService"] = None,
) -> SMSMatchingStage:
    """工厂函数：创建 SMS 匹配阶段处理器"""
    return SMSMatchingStage(
        matcher=matcher,
        case_number_extractor=case_number_extractor,
        case_service=case_service,
        lawyer_service=lawyer_service,
    )
