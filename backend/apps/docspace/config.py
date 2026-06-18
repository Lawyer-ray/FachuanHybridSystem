"""DocSpace 配置读取 — 从 SystemConfig 获取连接参数。"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300  # 5 分钟缓存


def _get_system_config(key: str, default: str = "") -> str:
    """从 SystemConfig 读取配置值。"""
    try:
        from apps.core.models.system_config import SystemConfig

        obj = SystemConfig.objects.filter(key=key, is_active=True).first()
        if obj is None:
            return default
        if obj.is_secret:
            from apps.core.security.secret_codec import SecretCodec

            codec = SecretCodec()
            if codec.is_encrypted(obj.value):
                return codec.decrypt(obj.value) or default
            return obj.value or default
        return obj.value or default
    except Exception:
        logger.debug("SystemConfig 未就绪，跳过读取 key=%s", key)
        return default


def get_portal_url() -> str:
    """DocSpace Portal URL，如 https://fachuan.onlyoffice.com"""
    return _get_system_config("DOCSPACE_PORTAL_URL", "").rstrip("/")


def get_api_token() -> str:
    """DocSpace API Token（Bearer Token）。"""
    return _get_system_config("DOCSPACE_API_TOKEN", "")


def get_root_folder_id() -> int:
    """默认上传文件夹 ID（"我的文档"）。"""
    raw = _get_system_config("DOCSPACE_ROOT_FOLDER_ID", "0")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def is_configured() -> bool:
    """检查 DocSpace 是否已配置完成。"""
    return bool(get_portal_url() and get_api_token())
