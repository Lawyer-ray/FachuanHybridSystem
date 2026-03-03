"""
结构指纹计算与缓存匹配服务

基于模板 XML 结构（去除文本内容和样式属性）计算 SHA-256 哈希值，
用于识别相同结构的模板并复用已有映射，避免重复调用 LLM。

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.documents.models.external_template import ExternalTemplate

logger: logging.Logger = logging.getLogger(__name__)

# Word XML 命名空间
_WORD_NS: str = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# 需要忽略的样式相关属性（字体、颜色、大小等）
_STYLE_ATTR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\{[^}]*\}(rFonts|sz|szCs|color|highlight|shd|lang)$"),
    re.compile(r"\{[^}]*\}(b|bCs|i|iCs|u|strike|dstrike|vanish|caps|smallCaps)$"),
    re.compile(r"\{[^}]*\}(spacing|kern|position|vertAlign|em|fitText)$"),
]

# 需要忽略的样式相关元素标签
_STYLE_ELEMENT_TAGS: frozenset[str] = frozenset(
    {
        f"{{{_WORD_NS}}}rFonts",
        f"{{{_WORD_NS}}}sz",
        f"{{{_WORD_NS}}}szCs",
        f"{{{_WORD_NS}}}color",
        f"{{{_WORD_NS}}}highlight",
        f"{{{_WORD_NS}}}shd",
        f"{{{_WORD_NS}}}lang",
        f"{{{_WORD_NS}}}b",
        f"{{{_WORD_NS}}}bCs",
        f"{{{_WORD_NS}}}i",
        f"{{{_WORD_NS}}}iCs",
        f"{{{_WORD_NS}}}u",
        f"{{{_WORD_NS}}}strike",
        f"{{{_WORD_NS}}}dstrike",
        f"{{{_WORD_NS}}}vanish",
        f"{{{_WORD_NS}}}caps",
        f"{{{_WORD_NS}}}smallCaps",
        f"{{{_WORD_NS}}}spacing",
        f"{{{_WORD_NS}}}kern",
        f"{{{_WORD_NS}}}position",
        f"{{{_WORD_NS}}}vertAlign",
        f"{{{_WORD_NS}}}em",
        f"{{{_WORD_NS}}}fitText",
    }
)

# 需要跳过的文件（页眉页脚等）
_SKIP_PARTS: frozenset[str] = frozenset(
    {
        "word/header1.xml",
        "word/header2.xml",
        "word/header3.xml",
        "word/footer1.xml",
        "word/footer2.xml",
        "word/footer3.xml",
    }
)


class FingerprintService:
    """结构指纹计算与缓存匹配"""

    def compute_fingerprint(self, file_path: Path) -> str:
        """
        计算结构指纹：
        1. 解析 .docx 的 XML 结构（word/document.xml）
        2. 去除所有文本内容，仅保留标签和结构属性
        3. 忽略样式属性（字体、颜色等）和页眉页脚页码
        4. 计算 SHA-256 哈希值

        Args:
            file_path: .docx 文件的绝对路径

        Returns:
            64 字符的 SHA-256 十六进制字符串
        """
        logger.info("计算结构指纹: %s", file_path)

        xml_content = self._read_document_xml(file_path)
        stripped = self._strip_text_content(xml_content)
        stripped = self._strip_style_attributes(stripped)

        fingerprint: str = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
        logger.info("指纹计算完成: %s -> %s", file_path.name, fingerprint[:16])
        return fingerprint

    def find_matching_template(self, fingerprint: str, law_firm_id: int) -> ExternalTemplate | None:
        """
        在同一律所范围内查找具有相同指纹的已有模板

        Args:
            fingerprint: SHA-256 结构指纹
            law_firm_id: 律所 ID（数据隔离）

        Returns:
            匹配的 ExternalTemplate 或 None
        """
        from apps.documents.models.external_template import ExternalTemplate

        if not fingerprint:
            return None

        template: ExternalTemplate | None = (
            ExternalTemplate.objects.filter(
                structure_fingerprint=fingerprint,
                law_firm_id=law_firm_id,
                is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )

        if template is not None:
            logger.info(
                "指纹匹配成功: fingerprint=%s, template_id=%d, name=%s",
                fingerprint[:16],
                template.id,
                template.name,
            )
        else:
            logger.info(
                "未找到匹配指纹: fingerprint=%s, law_firm_id=%d",
                fingerprint[:16],
                law_firm_id,
            )

        return template

    def _read_document_xml(self, file_path: Path) -> str:
        """
        从 .docx 文件中读取 word/document.xml 内容

        Args:
            file_path: .docx 文件路径

        Returns:
            document.xml 的文本内容
        """
        with zipfile.ZipFile(file_path, "r") as zf, zf.open("word/document.xml") as f:
            return f.read().decode("utf-8")

    def _strip_text_content(self, xml_content: str) -> str:
        """
        去除 XML 中的文本内容，保留标签和结构

        解析 XML 树，将所有 <w:t> 元素的文本清空，
        同时清除所有元素的 text 和 tail 属性。

        Args:
            xml_content: 原始 XML 字符串

        Returns:
            去除文本内容后的 XML 字符串
        """
        root: ET.Element = ET.fromstring(xml_content)  # noqa: S314

        for elem in root.iter():
            elem.text = None
            elem.tail = None

        return ET.tostring(root, encoding="unicode")

    def _strip_style_attributes(self, xml_content: str) -> str:
        """
        去除样式相关属性和元素

        移除字体、颜色、大小等样式相关的 XML 元素，
        仅保留文档结构信息。

        Args:
            xml_content: XML 字符串

        Returns:
            去除样式属性后的 XML 字符串
        """
        root: ET.Element = ET.fromstring(xml_content)  # noqa: S314

        self._remove_style_elements(root)

        # 移除元素上的样式相关属性
        for elem in root.iter():
            attrs_to_remove: list[str] = []
            for attr_name in elem.attrib:
                for pattern in _STYLE_ATTR_PATTERNS:
                    if pattern.match(attr_name):
                        attrs_to_remove.append(attr_name)
                        break
            for attr_name in attrs_to_remove:
                del elem.attrib[attr_name]

        return ET.tostring(root, encoding="unicode")

    def _remove_style_elements(self, element: ET.Element) -> None:
        """
        递归移除样式相关的子元素

        Args:
            element: 要处理的 XML 元素
        """
        children_to_remove: list[ET.Element] = []
        for child in element:
            if child.tag in _STYLE_ELEMENT_TAGS:
                children_to_remove.append(child)
            else:
                self._remove_style_elements(child)

        for child in children_to_remove:
            element.remove(child)
