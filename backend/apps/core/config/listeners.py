"""
配置变更监听器

提供配置变更的日志记录和验证功能
"""

import logging
from typing import Any
from .manager import ConfigChangeListener

logger = logging.getLogger(__name__)


class ConfigChangeLogger(ConfigChangeListener):
    """配置变更日志监听器"""
    
    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """
        记录配置变更
        
        Args:
            key: 配置键
            old_value: 旧值
            new_value: 新值
        """
        # 对敏感配置进行脱敏
        if self._is_sensitive_key(key):
            old_display = self._mask_value(old_value)
            new_display = self._mask_value(new_value)
        else:
            old_display = old_value
            new_display = new_value
        
        logger.info(f"配置变更: {key} = {old_display} -> {new_display}")
    
    def on_config_added(self, key: str, value: Any) -> None:
        """
        记录配置添加
        
        Args:
            key: 配置键
            value: 配置值
        """
        display_value = self._mask_value(value) if self._is_sensitive_key(key) else value
        logger.info(f"配置添加: {key} = {display_value}")
    
    def on_config_removed(self, key: str, old_value: Any) -> None:
        """
        记录配置移除
        
        Args:
            key: 配置键
            old_value: 旧值
        """
        display_value = self._mask_value(old_value) if self._is_sensitive_key(key) else old_value
        logger.info(f"配置移除: {key} (原值: {display_value})")
    
    def on_config_reloaded(self) -> None:
        """记录配置重载"""
        logger.info("配置重载完成")
    
    def _is_sensitive_key(self, key: str) -> bool:
        """
        检查是否为敏感配置键
        
        Args:
            key: 配置键
            
        Returns:
            bool: 是否为敏感配置
        """
        sensitive_keywords = [
            'password', 'secret', 'key', 'token', 'credential',
            'private', 'auth', 'api_key', 'access_key'
        ]
        
        key_lower = key.lower()
        return any(keyword in key_lower for keyword in sensitive_keywords)
    
    def _mask_value(self, value: Any) -> str:
        """
        对敏感值进行脱敏
        
        Args:
            value: 原始值
            
        Returns:
            str: 脱敏后的值
        """
        if value is None:
            return "None"
        
        str_value = str(value)
        if len(str_value) <= 4:
            return "***"
        elif len(str_value) <= 8:
            return str_value[:2] + "***" + str_value[-1:]
        else:
            return str_value[:3] + "***" + str_value[-2:]


class ConfigValidationListener(ConfigChangeListener):
    """配置验证监听器"""
    
    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """
        验证配置变更
        
        Args:
            key: 配置键
            old_value: 旧值
            new_value: 新值
        """
        try:
            self._validate_config_change(key, new_value)
        except Exception as e:
            logger.error(f"配置变更验证失败 ({key}): {e}")
    
    def on_config_added(self, key: str, value: Any) -> None:
        """
        验证新增配置
        
        Args:
            key: 配置键
            value: 配置值
        """
        try:
            self._validate_config_change(key, value)
        except Exception as e:
            logger.error(f"新增配置验证失败 ({key}): {e}")
    
    def _validate_config_change(self, key: str, value: Any) -> None:
        """
        验证配置变更
        
        Args:
            key: 配置键
            value: 配置值
            
        Raises:
            ValueError: 配置值无效
        """
        # 验证关键配置项
        if key == 'django.debug':
            if not isinstance(value, bool):
                raise ValueError(f"DEBUG 配置必须是布尔值，当前值: {value}")
        
        elif key == 'django.secret_key':
            if not value or len(str(value)) < 20:
                raise ValueError("SECRET_KEY 配置不能为空且长度不能少于20个字符")
        
        elif key.endswith('.timeout'):
            if not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"超时配置必须是正数，当前值: {value}")
        
        elif key.endswith('.max_retries'):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"重试次数配置必须是非负整数，当前值: {value}")
        
        elif key.endswith('.port'):
            if not isinstance(value, int) or not (1 <= value <= 65535):
                raise ValueError(f"端口配置必须是1-65535之间的整数，当前值: {value}")


class ConfigSecurityListener(ConfigChangeListener):
    """配置安全监听器"""
    
    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """
        监控敏感配置变更
        
        Args:
            key: 配置键
            old_value: 旧值
            new_value: 新值
        """
        if self._is_security_critical(key):
            logger.warning(f"安全关键配置变更: {key}")
            
            # 在生产环境中，记录安全审计日志
            from django.conf import settings
            if not getattr(settings, 'DEBUG', True):
                self._log_security_audit(key, 'modified')
    
    def on_config_added(self, key: str, value: Any) -> None:
        """
        监控敏感配置添加
        
        Args:
            key: 配置键
            value: 配置值
        """
        if self._is_security_critical(key):
            logger.warning(f"安全关键配置添加: {key}")
            
            from django.conf import settings
            if not getattr(settings, 'DEBUG', True):
                self._log_security_audit(key, 'added')
    
    def on_config_removed(self, key: str, old_value: Any) -> None:
        """
        监控敏感配置移除
        
        Args:
            key: 配置键
            old_value: 旧值
        """
        if self._is_security_critical(key):
            logger.error(f"安全关键配置被移除: {key}")
            
            from django.conf import settings
            if not getattr(settings, 'DEBUG', True):
                self._log_security_audit(key, 'removed')
    
    def _is_security_critical(self, key: str) -> bool:
        """
        检查是否为安全关键配置
        
        Args:
            key: 配置键
            
        Returns:
            bool: 是否为安全关键配置
        """
        security_critical_keys = [
            'django.secret_key',
            'django.debug',
            'django.allowed_hosts',
            'database.password',
            'permissions.open_access',
        ]
        
        return key in security_critical_keys or 'secret' in key.lower() or 'password' in key.lower()
    
    def _log_security_audit(self, key: str, action: str) -> None:
        """
        记录安全审计日志
        
        Args:
            key: 配置键
            action: 操作类型
        """
        import datetime
        audit_logger = logging.getLogger('security.config')
        audit_logger.critical(f"[SECURITY AUDIT] {datetime.datetime.now().isoformat()} - "
                            f"配置安全事件: {action} - {key}")