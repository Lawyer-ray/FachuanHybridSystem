"""
飞书消息构建器

本模块提供飞书消息构建功能,包括文本消息和富文本消息的构建.
作为 FeishuChatProvider 的 Mixin 使用.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import MessageContent

logger = logging.getLogger(__name__)


class FeishuMessageBuilderMixin:
    """飞书消息构建器 Mixin

    提供消息构建相关的方法,包括:
    - 简单文本消息构建
    - 富文本消息构建
    - 文件类型和MIME类型判断
    """

    def _build_simple_text_message(self, content: "MessageContent") -> str:
        """构建简单的文本消息

        将MessageContent转换为简单的文本格式,避免复杂的富文本格式问题.

        Args:
            content: 消息内容

        Returns:
            str: 格式化的文本消息
        """
        message_parts: list[Any] = []

        # 添加标题(如果存在)
        if content.title:
            message_parts.append(f"📋 {content.title}")

        # 添加正文
        if content.text:
            message_parts.append(content.text)

        # 用换行符连接各部分
        return "\n\n".join(message_parts) if message_parts else "空消息"

    def _build_rich_text_message(self, content: "MessageContent") -> dict[str, Any]:
        """构建飞书富文本消息格式

        将MessageContent转换为飞书支持的富文本消息格式.
        注意:此方法保留用于未来可能的富文本需求.

        Args:
            content: 消息内容

        Returns:
            Dict[str, Any]: 飞书富文本消息格式
        """
        # 构建富文本元素
        elements: list[Any] = []

        # 添加标题(如果存在)
        if content.title:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{content.title}**"}})

        # 添加正文
        if content.text:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content.text}})

        # 添加分隔线(如果有标题和正文)
        if content.title and content.text:
            elements.insert(1, {"tag": "hr"})

        # 构建完整的富文本消息
        rich_text_content: dict[str, Any] = {"zh_cn": {"title": "", "content": elements}}

        return rich_text_content

    def _get_file_type(self, file_path: str) -> str:
        """根据文件扩展名确定飞书文件类型

        Args:
            file_path: 文件路径

        Returns:
            str: 飞书文件类型
        """
        from apps.core.path import Path

        ext = Path(file_path).ext.lower()

        # 飞书支持的文件类型映射
        file_type_mapping = {
            ".pdf": "pdf",
            ".doc": "doc",
            ".docx": "docx",
            ".xls": "xls",
            ".xlsx": "xlsx",
            ".ppt": "ppt",
            ".pptx": "pptx",
            ".txt": "txt",
            ".jpg": "image",
            ".jpeg": "image",
            ".png": "image",
            ".gif": "image",
            ".mp4": "video",
            ".avi": "video",
            ".mov": "video",
            ".mp3": "audio",
            ".wav": "audio",
            ".zip": "zip",
            ".rar": "rar",
        }

        return file_type_mapping.get(ext, "file")

    def _get_mime_type(self, file_path: str) -> str:
        """根据文件扩展名确定MIME类型

        Args:
            file_path: 文件路径

        Returns:
            str: MIME类型
        """
        import mimetypes

        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"

    def _build_file_content(self, file_key: str) -> str:
        """构建文件消息内容

        根据飞书官方API文档,发送文件消息时 content 中只需要 file_key.

        Args:
            file_key: 飞书文件key

        Returns:
            str: JSON格式的文件消息内容
        """
        content: dict[str, str] = {"file_key": file_key}
        return json.dumps(content, ensure_ascii=False)

    def _build_text_content(self, text: str) -> str:
        """构建文本消息内容

        Args:
            text: 文本内容

        Returns:
            str: JSON格式的文本消息内容
        """
        return json.dumps({"text": text})
