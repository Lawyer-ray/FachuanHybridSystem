"""DocSpace 配置读取 — 从 SystemConfig 获取连接参数。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 运行时缓存自动发现的 folder_id（进程生命周期内有效）
_discovered_folder_id: int | None = None


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
    """默认上传文件夹 ID（自动从 DocSpace API 获取当前用户的「我的文档」）。"""
    global _discovered_folder_id  # noqa: PLW0603

    if _discovered_folder_id is not None:
        return _discovered_folder_id

    _discovered_folder_id = _discover_my_folder_id()
    return _discovered_folder_id


def _discover_my_folder_id() -> int:
    """调用 DocSpace API 获取当前用户的「我的文档」文件夹 ID。"""
    portal = get_portal_url()
    token = get_api_token()
    if not portal or not token:
        return 0

    try:
        import httpx

        resp = httpx.get(
            f"{portal}/api/2.0/files/@my",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        folder_id = resp.json().get("response", {}).get("current", {}).get("id", 0)
        if folder_id:
            logger.info("DocSpace 自动发现「我的文档」folder_id=%s", folder_id)
        return int(folder_id)
    except Exception as e:
        logger.warning("DocSpace 自动发现 folder_id 失败: %s", e)
        return 0


def is_configured() -> bool:
    """检查 DocSpace 是否已配置完成。"""
    return bool(get_portal_url() and get_api_token())
