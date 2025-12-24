"""
群聊审计日志器

本模块实现群聊创建和群主设置的完整审计日志功能。
支持结构化日志记录和JSON格式存储，便于后续查询和分析。

主要功能：
- 记录群聊创建的完整过程
- 记录群主设置和验证结果
- 记录错误和重试信息
- 支持结构化日志格式
- 集成Django日志系统

Requirements: 5.1, 5.2
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ChatAuditLogger:
    """群聊审计日志器
    
    负责记录群聊创建和群主设置的完整审计信息。
    支持结构化日志和JSON格式存储。
    
    使用方法:
        audit_logger = ChatAuditLogger()
        audit_logger.log_chat_creation_start(case_id=123, chat_name="案件群聊", owner_id="ou_abc123")
        audit_logger.log_chat_creation_success(case_id=123, chat_id="oc_def456", owner_info={...})
    """
    
    def __init__(self):
        """初始化审计日志器"""
        self.logger = logging.getLogger(f"{__name__}.ChatAuditLogger")
        self.audit_enabled = self._is_audit_enabled()
        
        if not self.audit_enabled:
            self.logger.info("群聊审计日志功能已禁用")
    
    def _is_audit_enabled(self) -> bool:
        """检查审计日志是否启用
        
        Returns:
            bool: 审计日志是否启用
        """
        feishu_config = getattr(settings, 'FEISHU', {})
        return feishu_config.get('AUDIT_ENABLED', True)
    
    def _get_audit_level(self) -> str:
        """获取审计日志级别
        
        Returns:
            str: 日志级别（INFO, DEBUG, WARNING等）
        """
        feishu_config = getattr(settings, 'FEISHU', {})
        return feishu_config.get('AUDIT_LEVEL', 'INFO')
    
    def _create_audit_entry(
        self, 
        action: str, 
        case_id: Optional[int] = None,
        chat_id: Optional[str] = None,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建审计日志条目
        
        Args:
            action: 操作类型
            case_id: 案件ID
            chat_id: 群聊ID
            success: 操作是否成功
            details: 操作详情
            error_message: 错误信息
            
        Returns:
            Dict[str, Any]: 审计日志条目
        """
        entry = {
            'timestamp': timezone.now().isoformat(),
            'action': action,
            'success': success,
            'case_id': case_id,
            'chat_id': chat_id,
            'details': details or {},
            'error_message': error_message,
            'audit_version': '1.0'
        }
        
        return entry
    
    def _log_audit_entry(self, entry: Dict[str, Any], level: str = 'INFO'):
        """记录审计日志条目
        
        Args:
            entry: 审计日志条目
            level: 日志级别
        """
        if not self.audit_enabled:
            return
        
        # 格式化日志消息
        action = entry.get('action', 'UNKNOWN')
        success = entry.get('success', True)
        case_id = entry.get('case_id')
        chat_id = entry.get('chat_id')
        
        # 构建日志消息
        message_parts = [f"[AUDIT] {action}"]
        
        if case_id:
            message_parts.append(f"Case:{case_id}")
        
        if chat_id:
            message_parts.append(f"Chat:{chat_id}")
        
        if not success:
            message_parts.append("FAILED")
            error_msg = entry.get('error_message', '未知错误')
            message_parts.append(f"Error:{error_msg}")
        else:
            message_parts.append("SUCCESS")
        
        log_message = " | ".join(message_parts)
        
        # 添加结构化数据
        extra_data = {
            'audit_entry': entry,
            'audit_action': action,
            'audit_success': success,
            'audit_case_id': case_id,
            'audit_chat_id': chat_id
        }
        
        # 根据级别记录日志
        log_level = level.upper()
        if log_level == 'DEBUG':
            self.logger.debug(log_message, extra=extra_data)
        elif log_level == 'WARNING':
            self.logger.warning(log_message, extra=extra_data)
        elif log_level == 'ERROR':
            self.logger.error(log_message, extra=extra_data)
        else:
            self.logger.info(log_message, extra=extra_data)
    
    def log_chat_creation_start(
        self, 
        case_id: int, 
        chat_name: str, 
        owner_id: Optional[str] = None,
        platform: str = "feishu",
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录群聊创建开始
        
        Args:
            case_id: 案件ID
            chat_name: 群聊名称
            owner_id: 指定的群主ID
            platform: 群聊平台
            additional_details: 额外的详细信息
        """
        details = {
            'chat_name': chat_name,
            'platform': platform,
            'specified_owner_id': owner_id,
            'start_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='CREATE_START',
            case_id=case_id,
            success=True,
            details=details
        )
        
        self._log_audit_entry(entry, level=self._get_audit_level())
        
        self.logger.info(f"开始创建群聊: 案件{case_id}, 群聊名称: {chat_name}, 指定群主: {owner_id}")
    
    def log_chat_creation_success(
        self, 
        case_id: int, 
        chat_id: str, 
        owner_info: Dict[str, Any],
        chat_name: Optional[str] = None,
        platform: str = "feishu",
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录群聊创建成功
        
        Args:
            case_id: 案件ID
            chat_id: 群聊ID
            owner_info: 群主信息
            chat_name: 群聊名称
            platform: 群聊平台
            additional_details: 额外的详细信息
        """
        details = {
            'chat_name': chat_name,
            'platform': platform,
            'owner_info': owner_info,
            'success_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='CREATE_SUCCESS',
            case_id=case_id,
            chat_id=chat_id,
            success=True,
            details=details
        )
        
        self._log_audit_entry(entry, level=self._get_audit_level())
        
        effective_owner_id = owner_info.get('effective_owner_id', '未知')
        self.logger.info(f"群聊创建成功: 案件{case_id}, 群聊ID: {chat_id}, 群主: {effective_owner_id}")
    
    def log_chat_creation_failure(
        self, 
        case_id: int, 
        error: str,
        chat_name: Optional[str] = None,
        owner_id: Optional[str] = None,
        platform: str = "feishu",
        error_code: Optional[str] = None,
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录群聊创建失败
        
        Args:
            case_id: 案件ID
            error: 错误信息
            chat_name: 群聊名称
            owner_id: 指定的群主ID
            platform: 群聊平台
            error_code: 错误代码
            additional_details: 额外的详细信息
        """
        details = {
            'chat_name': chat_name,
            'platform': platform,
            'specified_owner_id': owner_id,
            'error_code': error_code,
            'failure_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='CREATE_FAILED',
            case_id=case_id,
            success=False,
            details=details,
            error_message=error
        )
        
        self._log_audit_entry(entry, level='ERROR')
        
        self.logger.error(f"群聊创建失败: 案件{case_id}, 群聊名称: {chat_name}, 错误: {error}")
    
    def log_owner_setting_failure(
        self, 
        chat_id: str, 
        owner_id: str, 
        error: str, 
        retry_count: int = 0,
        case_id: Optional[int] = None,
        error_code: Optional[str] = None,
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录群主设置失败
        
        Args:
            chat_id: 群聊ID
            owner_id: 群主ID
            error: 错误信息
            retry_count: 重试次数
            case_id: 案件ID
            error_code: 错误代码
            additional_details: 额外的详细信息
        """
        details = {
            'owner_id': owner_id,
            'retry_count': retry_count,
            'error_code': error_code,
            'failure_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='OWNER_SET_FAILED',
            case_id=case_id,
            chat_id=chat_id,
            success=False,
            details=details,
            error_message=error
        )
        
        self._log_audit_entry(entry, level='ERROR')
        
        self.logger.error(f"群主设置失败: 群聊{chat_id}, 群主: {owner_id}, 重试次数: {retry_count}, 错误: {error}")
    
    def log_owner_verification(
        self, 
        chat_id: str, 
        expected_owner: str, 
        actual_owner: Optional[str], 
        success: bool,
        case_id: Optional[int] = None,
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录群主验证结果
        
        Args:
            chat_id: 群聊ID
            expected_owner: 期望的群主ID
            actual_owner: 实际的群主ID
            success: 验证是否成功
            case_id: 案件ID
            additional_details: 额外的详细信息
        """
        details = {
            'expected_owner_id': expected_owner,
            'actual_owner_id': actual_owner,
            'verification_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='OWNER_VERIFY',
            case_id=case_id,
            chat_id=chat_id,
            success=success,
            details=details,
            error_message=None if success else f"群主不匹配: 期望{expected_owner}, 实际{actual_owner}"
        )
        
        level = self._get_audit_level() if success else 'WARNING'
        self._log_audit_entry(entry, level=level)
        
        if success:
            self.logger.info(f"群主验证成功: 群聊{chat_id}, 群主: {actual_owner}")
        else:
            self.logger.warning(f"群主验证失败: 群聊{chat_id}, 期望: {expected_owner}, 实际: {actual_owner}")
    
    def log_owner_retry_attempt(
        self, 
        chat_id: str, 
        owner_id: str, 
        attempt: int, 
        max_attempts: int,
        delay: float = 0.0,
        case_id: Optional[int] = None,
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录群主设置重试尝试
        
        Args:
            chat_id: 群聊ID
            owner_id: 群主ID
            attempt: 当前尝试次数
            max_attempts: 最大尝试次数
            delay: 延迟时间（秒）
            case_id: 案件ID
            additional_details: 额外的详细信息
        """
        details = {
            'owner_id': owner_id,
            'attempt': attempt,
            'max_attempts': max_attempts,
            'delay_seconds': delay,
            'retry_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='OWNER_RETRY',
            case_id=case_id,
            chat_id=chat_id,
            success=True,
            details=details
        )
        
        self._log_audit_entry(entry, level='DEBUG')
        
        self.logger.debug(f"群主设置重试: 群聊{chat_id}, 群主: {owner_id}, 尝试{attempt}/{max_attempts}")
    
    def log_configuration_error(
        self, 
        error: str, 
        missing_config: Optional[str] = None,
        platform: str = "feishu",
        additional_details: Optional[Dict[str, Any]] = None
    ):
        """记录配置错误
        
        Args:
            error: 错误信息
            missing_config: 缺失的配置项
            platform: 平台名称
            additional_details: 额外的详细信息
        """
        details = {
            'platform': platform,
            'missing_config': missing_config,
            'error_time': timezone.now().isoformat()
        }
        
        if additional_details:
            details.update(additional_details)
        
        entry = self._create_audit_entry(
            action='CONFIG_ERROR',
            success=False,
            details=details,
            error_message=error
        )
        
        self._log_audit_entry(entry, level='ERROR')
        
        self.logger.error(f"配置错误: {error}, 缺失配置: {missing_config}")
    
    def get_audit_summary(
        self, 
        case_id: Optional[int] = None, 
        chat_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """获取审计日志摘要
        
        注意：这个方法返回内存中的摘要信息，不查询数据库。
        实际的审计日志查询应该通过数据库模型进行。
        
        Args:
            case_id: 案件ID过滤
            chat_id: 群聊ID过滤
            start_time: 开始时间过滤
            end_time: 结束时间过滤
            
        Returns:
            Dict[str, Any]: 审计日志摘要
        """
        summary = {
            'audit_enabled': self.audit_enabled,
            'audit_level': self._get_audit_level(),
            'filter_criteria': {
                'case_id': case_id,
                'chat_id': chat_id,
                'start_time': start_time.isoformat() if start_time else None,
                'end_time': end_time.isoformat() if end_time else None
            },
            'note': '实际审计日志数据请通过ChatAuditLog模型查询'
        }
        
        return summary
    
    def export_audit_logs(
        self, 
        case_id: Optional[int] = None, 
        chat_id: Optional[str] = None,
        format: str = 'json'
    ) -> str:
        """导出审计日志
        
        注意：这个方法返回格式说明，实际导出需要查询数据库。
        
        Args:
            case_id: 案件ID过滤
            chat_id: 群聊ID过滤
            format: 导出格式（json, csv等）
            
        Returns:
            str: 导出说明
        """
        export_info = {
            'message': '审计日志导出功能需要通过ChatAuditLog模型实现',
            'suggested_query': 'ChatAuditLog.objects.filter(...)',
            'filter_criteria': {
                'case_id': case_id,
                'chat_id': chat_id,
                'format': format
            }
        }
        
        return json.dumps(export_info, ensure_ascii=False, indent=2)