"""
SMS 解析阶段处理器

负责解析短信内容，提取下载链接、案号、当事人等信息。

Requirements: 2.1, 2.2, 5.1, 5.2, 5.5
"""
import logging
from typing import Optional, TYPE_CHECKING

from apps.automation.models import CourtSMS, CourtSMSStatus
from .base import BaseSMSStage

if TYPE_CHECKING:
    from apps.automation.services.sms.sms_parser_service import SMSParserService

logger = logging.getLogger("apps.automation")


class SMSParsingStage(BaseSMSStage):
    """
    SMS 解析阶段处理器
    
    负责解析短信内容，提取：
    - 短信类型
    - 下载链接
    - 案号
    - 当事人名称
    
    Attributes:
        parser: 短信解析服务实例
    """
    
    def __init__(
        self,
        parser: Optional["SMSParserService"] = None,
    ):
        """
        初始化解析阶段处理器
        
        Args:
            parser: 短信解析服务实例，支持依赖注入
        """
        self._parser = parser
    
    @property
    def parser(self) -> "SMSParserService":
        """
        延迟加载短信解析服务
        
        Returns:
            SMSParserService: 短信解析服务实例
        """
        if self._parser is None:
            from apps.automation.services.sms.sms_parser_service import SMSParserService
            self._parser = SMSParserService()
        return self._parser
    
    @property
    def stage_name(self) -> str:
        """阶段名称"""
        return "解析"
    
    def can_process(self, sms: CourtSMS) -> bool:
        """
        检查是否可以处理解析阶段
        
        只有 PENDING 状态的短信才能进入解析阶段。
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            bool: 是否可以处理
        """
        return sms.status == CourtSMSStatus.PENDING
    
    def process(self, sms: CourtSMS) -> CourtSMS:
        """
        处理解析阶段
        
        解析短信内容，提取下载链接、案号、当事人等信息，
        并更新短信记录的解析结果字段。
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            CourtSMS: 处理后的 SMS 实例（状态更新为 PARSING）
            
        Raises:
            Exception: 解析失败时抛出异常
        """
        self._log_start(sms)
        
        try:
            # 更新状态为解析中
            sms.status = CourtSMSStatus.PARSING
            sms.save()
            
            # 解析短信内容
            parse_result = self.parser.parse(sms.content)
            
            # 更新解析结果
            sms.sms_type = parse_result.sms_type
            sms.download_links = parse_result.download_links
            sms.case_numbers = parse_result.case_numbers
            sms.party_names = parse_result.party_names
            sms.save()
            
            logger.info(
                f"短信解析完成: ID={sms.id}, "
                f"类型={parse_result.sms_type}, "
                f"链接数={len(parse_result.download_links)}, "
                f"案号数={len(parse_result.case_numbers)}, "
                f"当事人数={len(parse_result.party_names)}"
            )
            
            self._log_complete(sms)
            return sms
            
        except Exception as e:
            self._log_error(sms, e)
            raise


def create_sms_parsing_stage(
    parser: Optional["SMSParserService"] = None,
) -> SMSParsingStage:
    """
    工厂函数：创建 SMS 解析阶段处理器
    
    Args:
        parser: 短信解析服务实例（可选）
        
    Returns:
        SMSParsingStage: 解析阶段处理器实例
    """
    return SMSParsingStage(parser=parser)
