"""
安全服务 - 敏感信息加密
"""
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
from django.conf import settings

from apps.core.interfaces import ISecurityService

logger = logging.getLogger("apps.automation")


class SecurityService:
    """安全服务"""
    
    def __init__(self):
        """初始化加密密钥"""
        # 从配置获取密钥，如果没有则生成一个
        key = getattr(settings, "SCRAPER_ENCRYPTION_KEY", None)
        
        if not key:
            # 生成新密钥（仅用于开发环境）
            key = Fernet.generate_key()
            logger.warning(
                "未配置 SCRAPER_ENCRYPTION_KEY，使用临时密钥。"
                "生产环境请在 settings.py 中配置固定密钥！"
            )
        
        if isinstance(key, str):
            key = key.encode()
        
        self.cipher = Fernet(key)
    
    def encrypt(self, text: str) -> str:
        """
        加密文本
        
        Args:
            text: 明文
            
        Returns:
            密文（Base64 编码）
        """
        if not text:
            return ""
        
        try:
            encrypted = self.cipher.encrypt(text.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise
    
    def decrypt(self, encrypted_text: str) -> str:
        """
        解密文本
        
        Args:
            encrypted_text: 密文（Base64 编码）
            
        Returns:
            明文
        """
        if not encrypted_text:
            return ""
        
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_text.encode())
            decrypted = self.cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise
    
    @staticmethod
    def mask_sensitive_data(data: dict, keys: list = None) -> dict:
        """
        脱敏敏感数据（用于日志）
        
        Args:
            data: 原始数据
            keys: 需要脱敏的键列表
            
        Returns:
            脱敏后的数据
        """
        if keys is None:
            keys = ["password", "passwd", "pwd", "secret", "token", "key"]
        
        masked = data.copy()
        
        for key in keys:
            if key in masked and masked[key]:
                value = str(masked[key])
                if len(value) > 4:
                    masked[key] = value[:2] + "***" + value[-2:]
                else:
                    masked[key] = "***"
        
        return masked
    
    @staticmethod
    def encrypt_config(config: dict) -> dict:
        """
        加密配置中的敏感字段
        
        Args:
            config: 配置字典
            
        Returns:
            加密后的配置
        """
        service = SecurityService()
        encrypted = config.copy()
        
        sensitive_keys = ["password", "passwd", "pwd"]
        
        for key in sensitive_keys:
            if key in encrypted and encrypted[key]:
                encrypted[key] = service.encrypt(encrypted[key])
                encrypted[f"{key}_encrypted"] = True
        
        return encrypted
    
    @staticmethod
    def decrypt_config(config: dict) -> dict:
        """
        解密配置中的敏感字段
        
        Args:
            config: 加密的配置字典
            
        Returns:
            解密后的配置
        """
        service = SecurityService()
        decrypted = config.copy()
        
        sensitive_keys = ["password", "passwd", "pwd"]
        
        for key in sensitive_keys:
            if f"{key}_encrypted" in decrypted and decrypted.get(f"{key}_encrypted"):
                if key in decrypted and decrypted[key]:
                    decrypted[key] = service.decrypt(decrypted[key])
                del decrypted[f"{key}_encrypted"]
        
        return decrypted


class SecurityServiceAdapter(ISecurityService):
    """
    安全服务适配器
    
    实现 ISecurityService Protocol，将 SecurityService 适配为标准接口
    """
    
    def __init__(self, service: Optional[SecurityService] = None):
        self._service = service
    
    @property
    def service(self) -> SecurityService:
        """延迟加载服务实例"""
        if self._service is None:
            self._service = SecurityService()
        return self._service
    
    def encrypt(self, text: str) -> str:
        """加密文本"""
        return self.service.encrypt(text)
    
    def decrypt(self, encrypted_text: str) -> str:
        """解密文本"""
        return self.service.decrypt(encrypted_text)
    
    def mask_sensitive_data(self, data: dict, keys: list = None) -> dict:
        """脱敏敏感数据"""
        return self.service.mask_sensitive_data(data, keys)
    
    def encrypt_config(self, config: dict) -> dict:
        """加密配置中的敏感字段"""
        return self.service.encrypt_config(config)
    
    def decrypt_config(self, config: dict) -> dict:
        """解密配置中的敏感字段"""
        return self.service.decrypt_config(config)
    
    # 内部方法版本，供其他模块调用
    def encrypt_internal(self, text: str) -> str:
        """加密文本（内部接口，无权限检查）"""
        return self.service.encrypt(text)
    
    def decrypt_internal(self, encrypted_text: str) -> str:
        """解密文本（内部接口，无权限检查）"""
        return self.service.decrypt(encrypted_text)
    
    def mask_sensitive_data_internal(self, data: dict, keys: list = None) -> dict:
        """脱敏敏感数据（内部接口，无权限检查）"""
        return self.service.mask_sensitive_data(data, keys)
    
    def encrypt_config_internal(self, config: dict) -> dict:
        """加密配置中的敏感字段（内部接口，无权限检查）"""
        return self.service.encrypt_config(config)
    
    def decrypt_config_internal(self, config: dict) -> dict:
        """解密配置中的敏感字段（内部接口，无权限检查）"""
        return self.service.decrypt_config(config)


# 注意：不再使用全局单例，请通过 ServiceLocator.get_security_service() 获取服务实例
