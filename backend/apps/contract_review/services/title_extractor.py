from __future__ import annotations

import logging
import re
from datetime import date

from docx import Document

logger = logging.getLogger(__name__)


class TitleExtractor:
    """从合同文档提取标题并生成标准文件名"""

    def extract_title(self, doc: Document) -> str:
        """从文档中提取合同标题，失败时返回空字符串"""
        for para in doc.paragraphs[:10]:
            text = para.text.strip()
            if not text or len(text) > 100:
                continue
            # 标题通常居中且包含"合同"/"协议"
            if "合同" in text or "协议" in text:
                logger.info("提取到合同标题: %s", text)
                return text
        # 退而求其次：取第一个非空段落
        for para in doc.paragraphs[:5]:
            text = para.text.strip()
            if text and len(text) <= 60:
                logger.info("使用首段作为标题: %s", text)
                return text
        logger.warning("未能提取合同标题")
        return ""

    @staticmethod
    def generate_output_filename(title: str, version: int = 1, task_id: str = "") -> str:
        """生成格式：{title}[修订版]V{version}_{date}_{short_id}.docx"""
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title) if title else "合同"
        today = date.today().strftime("%Y%m%d")
        suffix = f"_{task_id[:8]}" if task_id else ""
        return f"{safe_title}[修订版]V{version}_{today}{suffix}.docx"

    @staticmethod
    def parse_title_from_filename(filename: str) -> str:
        """从标准文件名中解析合同标题"""
        match = re.match(r"^(.+?)\[修订版]", filename)
        return match.group(1) if match else ""
