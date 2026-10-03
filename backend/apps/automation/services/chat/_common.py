"""群聊提供者公共 helper

收敛各 provider / mixin 中的逐行重复实现：
- build_text_message: 文本消息组装（原各 provider 的 _build_text_message 重复实现）
- guess_mime_type: MIME 类型推断（原三个 file mixin 的 _get_mime_type 重复实现）
- load_db_category_config: 从 SystemConfig 加载平台配置（原各 token mixin 的 _load_config_from_db 重复实现）
- normalize_provider_config: TIMEOUT 规范化 + 过滤空值（原各 token mixin 的 _load_config 重复片段）
"""

import logging
import mimetypes
from collections.abc import Mapping
from typing import Any

from apps.core.dto.chat import MessageContent

logger = logging.getLogger(__name__)


def build_text_message(content: MessageContent) -> str:
    """构建文本消息（标题加图标前缀，与正文空行分隔）"""
    message_parts = []
    if content.title:
        message_parts.append(f"📋 {content.title}")
    if content.text:
        message_parts.append(content.text)
    return "\n\n".join(message_parts) if message_parts else "空消息"


def guess_mime_type(file_path: str) -> str:
    """根据文件扩展名确定 MIME 类型"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def load_db_category_config(loader_name: str, key_mapping: Mapping[str, str], platform_label: str) -> dict[str, Any]:
    """从 SystemConfig 加载指定平台的配置并映射为内部键名

    Args:
        loader_name: apps.core.config.utils 中的分类配置加载函数名
        key_mapping: SystemConfig 键 -> 内部键 的映射
        platform_label: 平台中文名（用于日志）

    Returns:
        映射后的配置字典；加载失败时返回空字典（回退到 settings）
    """
    try:
        from apps.core.config import utils as config_utils

        loader = getattr(config_utils, loader_name, None)
        if loader is None:
            raise AttributeError(f"配置加载函数不存在: {loader_name}")

        db_configs = loader()
        if not db_configs:
            return {}
        config = {internal: db_configs[db] for db, internal in key_mapping.items() if db_configs.get(db)}
        logger.debug(f"从 SystemConfig 加载{platform_label}配置: {list(config.keys())}")
        return config
    except Exception as e:
        logger.debug(f"从 SystemConfig 加载配置失败，回退到 settings: {e!s}")
        return {}


def normalize_provider_config(config: dict[str, Any], platform_label: str) -> dict[str, Any]:
    """规范化平台配置：补默认 TIMEOUT、强制 int、过滤空值"""
    config.setdefault("TIMEOUT", 30)
    try:
        config["TIMEOUT"] = int(config["TIMEOUT"])
    except (ValueError, TypeError):
        config["TIMEOUT"] = 30

    filtered_config = {k: v for k, v in config.items() if v is not None and v != ""}
    logger.debug(f"最终{platform_label}配置: {list(filtered_config.keys())}")
    return filtered_config
