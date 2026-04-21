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
                # 优先使用 plain_text 属性（如 _ArchiveMaterialsRichText），否则用 str()
                display_val = getattr(val, "plain_text", None)
                if display_val is None:
                    if isinstance(val, list):
                        # 列表类型：格式化每项的字典为可读文本
                        lines: list[str] = []
                        for item in val:
                            if isinstance(item, dict):
                                lines.append(" | ".join(f"{k}: {v}" for k, v in item.items()))
                            else:
                                lines.append(str(item))
                        display_val = "\n".join(lines)
                    else:
                        display_val = str(val).replace("\a", "\n")
                rows.append({"key": var, "value": display_val, "status": "ok"})
            else:
                rows.append({"key": var, "value": "", "status": "empty"})
        return rows

    @staticmethod
    def _extract_ordered_vars(path: str) -> list[str]:
        """从 docx XML 中按出现顺序提取 jinja2 变量，去重

        提取两种类型的变量：
        1. {{ 变量名 }} — 支持中文变量名和点号属性访问
        2. {% for item in 变量名 %} / {%tr for item in 变量名 %} — for 循环的列表变量
        """
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode()
        clean = re.sub(r"<[^>]+>", "", xml)
        seen: set[str] = set()
        ordered: list[str] = []

        # 按位置顺序扫描，统一处理 {{ }} 和 {% %} 中的变量
        # 匹配 {{ xxx }} 或 {% xxx %}
        loop_iter_vars: set[str] = set()  # 记录 for 循环的迭代变量名，跳过它们
        for m in re.finditer(r"\{\{([^}]+?)\}\}|\{%([^%]+?)%\}", clean):
            simple_var = m.group(1)  # {{ xxx }} 中的内容
            block_tag = m.group(2)  # {% xxx %} 中的内容

            if simple_var is not None:
                # {{ item.序号 }} → 取首段 item; {{ 合同名称 }} → 合同名称
                var_name = simple_var.strip().split(".")[0].strip()
                # 跳过 for 循环迭代变量（如 item）
                if var_name and var_name not in seen and var_name not in loop_iter_vars:
                    seen.add(var_name)
                    ordered.append(var_name)
            elif block_tag is not None:
                # {%tr for item in 卷内目录 %} → 提取 item 和 卷内目录
                for_match = re.match(r"tr?\s+for\s+(\w+)\s+in\s+(\S+)", block_tag.strip())
                if for_match:
                    iter_var = for_match.group(1).strip()
                    list_var = for_match.group(2).strip()
                    loop_iter_vars.add(iter_var)  # 标记迭代变量，后续跳过
                    if list_var and list_var not in seen:
                        seen.add(list_var)
                        ordered.append(list_var)

        return ordered
