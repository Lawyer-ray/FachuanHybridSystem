"""documents pdf_merge_utils 的 contracts 出口。

⚠️ 这里的写法是**测试 patch 依赖的硬约束**，改动前先读这段说明：

单元测试 patch 的是 documents 侧的源模块属性，例如
``apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf``。
只有「调用发生时做属性查找」，patch 才能命中。所以：

- ✅ 函数体内 ``from ... import pdf_merge_utils`` 后调用 ``pdf_merge_utils.xxx(...)``
- ❌ 顶层 ``from ...pdf_merge_utils import convert_docx_to_pdf``
- ❌ ``from ... import convert_docx_to_pdf as _conv`` 再调用 ``_conv(...)``

后两种写法会在 import 时把函数对象拷贝到本模块命名空间，patch 源模块属性便不再生效，
测试会「绿着挂」：不报错，但真的去启动 LibreOffice 转换，CI 变慢或环境相关偶发失败。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def to_pdf(docx_path: str) -> str | None:
    """docx/doc 文件路径 → PDF 文件路径（临时文件，调用方负责清理）。

    转换失败返回 ``None``（与原调用点 ``if pdf_path_str: ... else None`` 语义一致）；
    不要在这里无条件 ``str()``，那会把 ``None`` 变成字符串 ``"None"`` 静默吞掉失败。
    """
    from apps.documents.services.infrastructure import pdf_merge_utils

    pdf_path = pdf_merge_utils.convert_docx_to_pdf(docx_path)
    return str(pdf_path) if pdf_path else None


def to_temp_pdf(file_path: Path) -> tuple[Path | None, bool]:
    """归档材料 → 可插入的 PDF。

    Returns:
        (pdf_path, is_temporary)；pdf_path 为 None 表示转换失败或格式不支持，
        is_temporary 为 True 时调用方用完需自行删除临时文件。
    """
    from apps.documents.services.infrastructure import pdf_merge_utils

    return pdf_merge_utils.resolve_material_to_temp_pdf(file_path)
