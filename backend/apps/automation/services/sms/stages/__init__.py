"""
SMS 处理阶段模块

包含各个处理阶段的实现：
- SMSParsingStage - 解析阶段
- SMSDownloadingStage - 下载阶段
- SMSMatchingStage - 匹配阶段
- SMSRenamingStage - 重命名阶段
- SMSNotifyingStage - 通知阶段
"""

from .base import ISMSStage, BaseSMSStage
from .sms_parsing_stage import SMSParsingStage, create_sms_parsing_stage
from .sms_downloading_stage import SMSDownloadingStage, create_sms_downloading_stage
from .sms_matching_stage import SMSMatchingStage, create_sms_matching_stage
from .sms_renaming_stage import SMSRenamingStage, create_sms_renaming_stage
from .sms_notifying_stage import SMSNotifyingStage, create_sms_notifying_stage

__all__ = [
    # 接口和基类
    "ISMSStage",
    "BaseSMSStage",
    # 解析阶段
    "SMSParsingStage",
    "create_sms_parsing_stage",
    # 下载阶段
    "SMSDownloadingStage",
    "create_sms_downloading_stage",
    # 匹配阶段
    "SMSMatchingStage",
    "create_sms_matching_stage",
    # 重命名阶段
    "SMSRenamingStage",
    "create_sms_renaming_stage",
    # 通知阶段
    "SMSNotifyingStage",
    "create_sms_notifying_stage",
]
