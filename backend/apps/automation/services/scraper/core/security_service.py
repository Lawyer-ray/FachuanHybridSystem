"""
安全服务 - 敏感信息加密
"""

import base64
import logging
from typing import Any

from cryptography.fernet import Fernet

from apps.core.interfaces import ISecurityService

logger = logging.getLogger("apps.automation")


def get_config(key: str, default: str | None = None) -> str | None:
    """获取系统配置值（可被测试 monkeypatch）"""
    from apps.core.services.system_config_service import SystemConfigService

    return SystemConfigService().get_value(key, default or "")  # type: ignore[return-value]


class SecurityService:
    """安全服务"""

    def __init__(self) -> None:
        """初始化加密密钥"""
        from django.conf import settings

        raw_key = get_config("SCRAPER_ENCRYPTION_KEY")
        key: bytes
        if not raw_key:
            if not getattr(settings, "DEBUG", False):
                raise RuntimeError(
                    "生产环境必须配置 SCRAPER_ENCRYPTION_KEY，请在系统配置中设置固定密钥！"
                )
            key = Fernet.generate_key()
            logger.warning("未配置 SCRAPER_ENCRYPTION_KEY，使用临时密钥。生产环境请在系统配置中设置固定密钥！")
        else:
            key = raw_key.encode() if isinstance(raw_key, str) else raw_key

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

    def mask_sensitive_data(self, data: dict[str, Any], keys: list[Any] | None = None) -> dict[str, Any]:
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
            if masked.get(key):
                value = str(masked[key])
                if len(value) > 4:
                    masked[key] = value[:2] + "***" + value[-2:]
                else:
                    masked[key] = "***"

        return masked

    def encrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        加密配置中的敏感字段

        Args:
            config: 配置字典

        Returns:
            加密后的配置
        """
        encrypted = config.copy()

        sensitive_keys = ["password", "passwd", "pwd"]

        for key in sensitive_keys:
            if encrypted.get(key):
                encrypted[key] = self.encrypt(encrypted[key])
                encrypted[f"{key}_encrypted"] = True

        return encrypted

    def decrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        解密配置中的敏感字段

        Args:
            config: 加密的配置字典

        Returns:
            解密后的配置
        """
        decrypted = config.copy()

        sensitive_keys = ["password", "passwd", "pwd"]

        for key in sensitive_keys:
            if f"{key}_encrypted" in decrypted and decrypted.get(f"{key}_encrypted"):
                if decrypted.get(key):
                    decrypted[key] = self.decrypt(decrypted[key])
                del decrypted[f"{key}_encrypted"]

        return decrypted


class SecurityServiceAdapter(ISecurityService):
    """
    安全服务适配器

    实现 ISecurityService Protocol，将 SecurityService 适配为标准接口
    """

    def __init__(self, service: SecurityService | None = None):
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

    def mask_sensitive_data(self, data: dict[str, Any], keys: list[Any] | None = None) -> dict[str, Any]:
        """脱敏敏感数据"""
        return self.service.mask_sensitive_data(data, keys)

    def encrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """加密配置中的敏感字段"""
        return self.service.encrypt_config(config)

    def decrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """解密配置中的敏感字段"""
        return self.service.decrypt_config(config)

    # 内部方法版本，供其他模块调用
    def encrypt_internal(self, text: str) -> str:
        """加密文本（内部接口，无权限检查）"""
        return self.service.encrypt(text)

    def decrypt_internal(self, encrypted_text: str) -> str:
        """解密文本（内部接口，无权限检查）"""
        return self.service.decrypt(encrypted_text)

    def mask_sensitive_data_internal(self, data: dict[str, Any], keys: list[Any] | None = None) -> dict[str, Any]:
        """脱敏敏感数据（内部接口，无权限检查）"""
        return self.service.mask_sensitive_data(data, keys)

    def encrypt_config_internal(self, config: dict[str, Any]) -> dict[str, Any]:
        """加密配置中的敏感字段（内部接口，无权限检查）"""
        return self.service.encrypt_config(config)

    def decrypt_config_internal(self, config: dict[str, Any]) -> dict[str, Any]:
        """解密配置中的敏感字段（内部接口，无权限检查）"""
        return self.service.decrypt_config(config)


# 注意：不再使用全局单例，请通过 ServiceLocator.get_security_service() 获取服务实例
