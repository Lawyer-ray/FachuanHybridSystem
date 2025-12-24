"""
SMS 处理阶段基类和接口定义

定义所有 SMS 处理阶段的通用接口和基类。
"""
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.automation")


class ISMSStage(ABC):
    """
    SMS 处理阶段接口
    
    所有 SMS 处理阶段都必须实现此接口。
    """
    
    @abstractmethod
    def process(self, sms: "CourtSMS") -> "CourtSMS":
        """
        处理当前阶段
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            CourtSMS: 处理后的 SMS 实例
            
        Raises:
            ValidationException: 处理失败
        """
        pass
    
    @abstractmethod
    def can_process(self, sms: "CourtSMS") -> bool:
        """
        检查是否可以处理
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            bool: 是否可以处理
        """
        pass
    
    @property
    @abstractmethod
    def stage_name(self) -> str:
        """
        阶段名称
        
        Returns:
            str: 阶段名称
        """
        pass


class BaseSMSStage(ISMSStage):
    """
    SMS 处理阶段基类
    
    提供通用的日志记录和错误处理功能。
    """
    
    def _log_start(self, sms: "CourtSMS") -> None:
        """记录阶段开始日志"""
        logger.info(f"开始 {self.stage_name} 阶段: SMS ID={sms.id}")
    
    def _log_complete(self, sms: "CourtSMS") -> None:
        """记录阶段完成日志"""
        logger.info(f"{self.stage_name} 阶段完成: SMS ID={sms.id}, 状态={sms.status}")
    
    def _log_error(self, sms: "CourtSMS", error: Exception) -> None:
        """记录阶段错误日志"""
        logger.error(f"{self.stage_name} 阶段失败: SMS ID={sms.id}, 错误: {str(error)}")
