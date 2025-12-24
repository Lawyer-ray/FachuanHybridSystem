"""
SMS 下载阶段处理器

负责根据短信中的下载链接创建下载任务，或直接进入匹配阶段。

Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
"""
import logging
from typing import Optional, TYPE_CHECKING

from django_q.tasks import async_task

from apps.automation.models import (
    CourtSMS,
    CourtSMSStatus,
    ScraperTask,
    ScraperTaskType,
)
from .base import BaseSMSStage

if TYPE_CHECKING:
    pass

logger = logging.getLogger("apps.automation")


class SMSDownloadingStage(BaseSMSStage):
    """
    SMS 下载阶段处理器
    
    负责根据短信中的下载链接决定：
    - 有下载链接：创建下载任务，进入 DOWNLOADING 状态
    - 无下载链接：直接进入 MATCHING 状态
    
    Attributes:
        无外部依赖，使用 Django ORM 和 Django Q
    """
    
    def __init__(self):
        """
        初始化下载阶段处理器
        
        此阶段不需要外部服务依赖，直接使用 Django ORM 和 Django Q。
        """
        pass
    
    @property
    def stage_name(self) -> str:
        """阶段名称"""
        return "下载"
    
    def can_process(self, sms: CourtSMS) -> bool:
        """
        检查是否可以处理下载阶段
        
        只有 PARSING 状态的短信才能进入下载阶段。
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            bool: 是否可以处理
        """
        return sms.status == CourtSMSStatus.PARSING
    
    def process(self, sms: CourtSMS) -> CourtSMS:
        """
        处理下载阶段
        
        根据是否有下载链接决定进入下载或匹配阶段：
        - 有下载链接：创建下载任务，状态变为 DOWNLOADING
        - 无下载链接：直接进入 MATCHING 状态
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            CourtSMS: 处理后的 SMS 实例
        """
        self._log_start(sms)
        
        try:
            if sms.download_links:
                # 有下载链接，创建下载任务
                logger.info(f"短信 {sms.id} 有下载链接，创建下载任务")
                
                scraper_task = self._create_download_task(sms)
                if scraper_task:
                    sms.scraper_task = scraper_task
                    sms.status = CourtSMSStatus.DOWNLOADING
                    sms.save()
                    logger.info(
                        f"下载任务创建成功: SMS ID={sms.id}, "
                        f"Task ID={scraper_task.id}"
                    )
                else:
                    # 下载任务创建失败，直接进入匹配
                    logger.warning(
                        f"下载任务创建失败，直接进入匹配: SMS ID={sms.id}"
                    )
                    sms.status = CourtSMSStatus.MATCHING
                    sms.save()
            else:
                # 无下载链接，直接进入匹配
                logger.info(f"短信 {sms.id} 无下载链接，直接进入匹配")
                sms.status = CourtSMSStatus.MATCHING
                sms.save()
            
            self._log_complete(sms)
            return sms
            
        except Exception as e:
            self._log_error(sms, e)
            raise
    
    def _create_download_task(self, sms: CourtSMS) -> Optional[ScraperTask]:
        """
        创建下载任务并关联到短信记录，然后提交到 Django Q 队列执行
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            ScraperTask: 创建的下载任务，失败返回 None
        """
        if not sms.download_links:
            return None
        
        try:
            # 使用第一个下载链接创建任务
            download_url = sms.download_links[0]
            
            # 创建 ScraperTask
            task = ScraperTask.objects.create(
                task_type=ScraperTaskType.COURT_DOCUMENT,
                url=download_url,
                case=sms.case,
                config={
                    'court_sms_id': sms.id,
                    'auto_download': True,
                    'source': 'court_sms'
                }
            )
            
            logger.info(
                f"创建下载任务成功: Task ID={task.id}, URL={download_url}"
            )
            
            # 提交到 Django Q 队列执行
            queue_task_id = async_task(
                'apps.automation.tasks.execute_scraper_task',
                task.id,
                task_name=f"court_document_download_{task.id}"
            )
            
            logger.info(
                f"提交下载任务到队列: Task ID={task.id}, "
                f"Queue Task ID={queue_task_id}"
            )
            
            return task
            
        except Exception as e:
            logger.error(
                f"创建下载任务失败: SMS ID={sms.id}, 错误: {str(e)}"
            )
            return None


def create_sms_downloading_stage() -> SMSDownloadingStage:
    """
    工厂函数：创建 SMS 下载阶段处理器
    
    Returns:
        SMSDownloadingStage: 下载阶段处理器实例
    """
    return SMSDownloadingStage()
