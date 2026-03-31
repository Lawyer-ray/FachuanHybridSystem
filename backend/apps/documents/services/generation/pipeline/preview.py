"""docx 模板预览服务 — 提取模板占位符并匹配上下文值"""

from __future__ import annotations

import re
import zipfile
from typing import Any

from apps.core.utils.path import Path


class DocxPreviewService:
    """从 docx 模板提取占位符，与上下文匹配后返回键值对预览"""

    def preview(self, template_path: str | Path, context: dict[str, Any]) -> list[dict[str, str]]:
        """
        按模板中出现顺序提取占位符，返回键值对预览。

        Args:
            template_path: docx 模板文件路径
            context: 占位符上下文字典

        Returns:
            [{key, value, status}] — status: ok / empty
        """
        ordered_vars = self._extract_ordered_vars(str(template_path))

        rows: list[dict[str, str]] = []
        for var in ordered_vars:
            val = context.get(var)
            if val:
                rows.append({"key": var, "value": str(val).replace("\a", "\n"), "status": "ok"})
            else:
                rows.append({"key": var, "value": "", "status": "empty"})
        return rows

    @staticmethod
    def _extract_ordered_vars(path: str) -> list[str]:
        """从 docx XML 中按出现顺序提取 jinja2 变量，去重"""
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode()
        clean = re.sub(r"<[^>]+>", "", xml)
        seen: set[str] = set()
        ordered: list[str] = []
        for m in re.findall(r"\{\{\s*(\w+)\s*\}\}", clean):
            if m not in seen:
                seen.add(m)
                ordered.append(m)
        return ordered
