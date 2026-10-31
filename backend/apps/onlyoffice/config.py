"""OnlyOffice Document Server 配置读取。

配置来源（按优先级）：
1. SystemConfig 表（key 前缀 `ONLYOFFICE_`）
2. Django settings 同名大写常量
3. 环境变量

三个必需项：DOCSERVER_URL（浏览器可达）、INTERNAL_URL（DS 容器可达的回源地址）、
JWT_SECRET（DS 容器的 JWT_SECRET，用于签发 config token）。

读取带 60 秒 TTL 缓存：每次打开编辑器都查 3 条 SystemConfig 太浪费；
Admin 改完配置后最长 1 分钟生效，或调用 clear_config_cache() 立即生效。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.utils import InterfaceError, OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

_PREFIX = "ONLYOFFICE_"
_CONFIG_TTL_SECONDS = 60.0

#: 配置 TTL 缓存：(取配置时刻, 配置)；读写均经函数内 ``global``，CodeQL 误报「未使用」，不可删除。
_config_cache: tuple[float, OnlyOfficeConfig] | None = None
_config_cache_lock = threading.Lock()
_weak_secret_warned: set[str] = set()


def _get_config(key: str, default: str = "") -> str:
    """读配置：SystemConfig → settings → 环境变量。"""
    full = _PREFIX + key
    try:
        from apps.core.models.system_config import SystemConfig

        obj = SystemConfig.objects.filter(key=full, is_active=True).first()
        if obj is not None:
            if obj.is_secret:
                from apps.core.security.secret_codec import SecretCodec

                codec = SecretCodec()
                if codec.is_encrypted(obj.value):
                    return codec.decrypt(obj.value) or default
                return obj.value or default
            return obj.value or default
    except (ProgrammingError, OperationalError, InterfaceError):
        # 表未就绪 / 库未连：迁移早期或独立脚本场景，回落 settings/env 是预期降级
        logger.debug("SystemConfig 未就绪，跳过 %s", full)
    except Exception:
        # 解密失败等真实故障：回落默认值会让用户看到「OnlyOffice 未启用」
        # 这种无法解释的结果，必须 warning 留痕（仓库日志规范）
        logger.warning("读取 SystemConfig %s 失败，回落默认值", full, exc_info=True)

    return str(getattr(settings, full, "") or os.environ.get(full, default))


@dataclass(frozen=True)
class OnlyOfficeConfig:
    """Document Server 连接参数（一次性快照）。"""

    docserver_url: str
    internal_url: str
    jwt_secret: str

    @property
    def enabled(self) -> bool:
        return bool(self.docserver_url and self.internal_url and self.jwt_secret)


def _warn_weak_secret(secret: str) -> None:
    """JWT_SECRET 不足 32 字节时告警（每个不同值只报一次，避免每次请求刷屏）。"""
    size = len(secret.encode())
    if secret and size < 32 and secret not in _weak_secret_warned:
        _weak_secret_warned.add(secret)
        logger.warning("ONLYOFFICE_JWT_SECRET 长度 %d 字节（建议 ≥32），存在被暴力破解风险", size)


def clear_config_cache() -> None:
    """立即失效配置缓存（Admin 改配置后 / 测试 fixture 换值时调用）。"""
    global _config_cache
    with _config_cache_lock:
        _config_cache = None


def _load_config() -> OnlyOfficeConfig:
    return OnlyOfficeConfig(
        docserver_url=_get_config("DOCSERVER_URL").rstrip("/"),
        internal_url=_get_config("INTERNAL_URL").rstrip("/"),
        jwt_secret=_get_config("JWT_SECRET"),
    )


def _cached_config() -> OnlyOfficeConfig:
    global _config_cache
    now = time.monotonic()
    with _config_cache_lock:
        if _config_cache is not None and now - _config_cache[0] < _CONFIG_TTL_SECONDS:
            return _config_cache[1]
    cfg = _load_config()
    _warn_weak_secret(cfg.jwt_secret)
    with _config_cache_lock:
        _config_cache = (now, cfg)
    return cfg


def get_config() -> OnlyOfficeConfig:
    """同步读取配置（带 TTL 缓存）。"""
    return _cached_config()


async def aget_config() -> OnlyOfficeConfig:
    """异步读取配置（API 层用；缓存命中时不再触库）。"""
    return await sync_to_async(_cached_config)()


def build_file_url(internal_url: str, file_url_path: str) -> str:
    """把站内下载路径拼成 DS 容器可达的绝对 URL。

    file_url_path 形如 `/api/v1/onlyoffice/file?src=...&sig=...`，
    查询串（签名参数）原样保留；路径里可能含中文文件名，逐段编码、斜杠保留。
    """
    path, _, query = file_url_path.partition("?")
    safe_path = "/".join(quote(seg, safe="") for seg in path.split("/"))
    url = f"{internal_url}{safe_path}"
    return f"{url}?{query}" if query else url
