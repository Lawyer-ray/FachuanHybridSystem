"""Office 文档解析后端（python-docx / openpyxl / xlrd）

为什么不用 OnlyOffice 做这件事——这是本模块存在的第一个理由，写清楚免得后人
又绕回去：

OnlyOffice Document Server（DS）是**编辑器画布**：它把 docx 渲染成人能看的界面，
按 key 拉文件、保存时回调。它不作为文本抽取服务使用，理由有三：
  ① DS 在独立容器里，取文件要经过 /onlyoffice/file 签名回源，抽个文本要多绕
     两跳网络 + 一次容器内转换，比本地读 OOXML 慢一到两个数量级；
  ② 它返回的是**渲染结果**（图片/pdf），拿文字还得再 OCR 一遍——本来 Word 里
     的文字是结构化的，OCR 反而把可靠的字变成可能认错的东西；
  ③ 大文件要整份传给 DS（1GB 卷宗场景），纯属浪费。
所以：**OnlyOffice 负责"给人看和改"，本后端负责"给机器读"**，两者不重叠。

坐标系说明（"识别定位"用的）：
  · Word / Excel 没有 PDF 那种"像素坐标"，但有稳定的**结构定位**：
    Word 用 (段落序 / 表格 行列)，Excel 用 (工作表 / 行 / 列)。
  · 为了让前端能复用 PDF 那套"归一化矩形 + 绿框"的交互，这里额外给出
    **近似归一化矩形**：按文档流顺序在页面上均分高度。它只是**近似**——
    Word 的精确分页只有排版引擎知道（我们不做排版）。
    因此矩形带 ``approx=True`` 标记，前端据此决定要不要画绿框：
    结构定位（段落/行列）永远可用，视觉矩形只在单页文档上才准。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.core.exceptions import ValidationException
from apps.document_parsing.protocols.document_parser_protocol import (
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    BLOCK_TYPE_TITLE,
    ParsedDocument,
    TextExtractionResult,
)
from apps.document_parsing.services.block_builder import attach_blocks

logger = logging.getLogger(__name__)

#: 把文档流按"逻辑页"切分的参考行数。Word 没有可靠分页（见模块注释），
#: 这里只用于给前端一个分页直觉与归一化矩形，不声称与打印分页一致。
_WORD_LINES_PER_LOGICAL_PAGE = 40
#: Excel 每个逻辑页最多放多少行（用于给前端分页展示，不改变数据完整性）
_EXCEL_ROWS_PER_LOGICAL_PAGE = 60


class OfficeBackend:
    """Word / Excel 本地解析后端（纯文本 + 结构定位，不渲染）"""

    provider_type: str = "office"

    # 本地解析无网络 I/O，同步返回即可
    requires_async_execution: bool = False

    _WORD_SUFFIXES = frozenset({".docx"})
    _EXCEL_SUFFIXES = frozenset({".xlsx", ".xls"})

    def get_supported_formats(self) -> list[str]:
        return ["docx", "xlsx", "xls"]

    # ------------------------------------------------------------------
    # 统一入口
    # ------------------------------------------------------------------

    def parse_document(
        self,
        file_path: str,
        file_type: str = "docx",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = path.suffix.lower()
        if suffix in self._WORD_SUFFIXES:
            parsed = self._parse_docx(path)
        elif suffix in self._EXCEL_SUFFIXES:
            parsed = self._parse_excel(path)
        else:
            raise ValidationException(
                f"Office 后端不支持该格式: {suffix or '(无扩展名)'}",
                code="UNSUPPORTED_OFFICE_FORMAT",
                errors={"file": f"支持: {', '.join(self.get_supported_formats())}"},
            )
        return attach_blocks(parsed)

    def extract_text(self, file_path: str, max_length: int | None = None, **kwargs: Any) -> TextExtractionResult:
        try:
            parsed = self.parse_document(file_path=file_path, return_markdown=False, **kwargs)
        except Exception as exc:  # 与云端后端同款：抽取失败不抛，返回 success=False
            logger.error("Office 文本提取失败: %s - %s", file_path, exc)
            return TextExtractionResult(text="", success=False, method="office", metadata={"error": str(exc)})
        text = parsed.text
        if max_length and len(text) > max_length:
            text = text[:max_length]
        return TextExtractionResult(
            text=text,
            success=True,
            method=parsed.parse_method,
            page_count=int((parsed.metadata or {}).get("page_count") or 0),
            metadata=parsed.metadata,
        )

    # ------------------------------------------------------------------
    # Word
    # ------------------------------------------------------------------

    def _parse_docx(self, path: Path) -> ParsedDocument:
        """docx → 文本 + Markdown + 结构定位块。

        按 ``document.element.body`` 的子元素顺序遍历，而不是先读 paragraphs
        再读 tables：Word 里正文与表格是**交错**的，分开读会把「当事人要素表」
        整块挪到文末，Markdown 顺序就错了。
        """
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = docx.Document(str(path))
        body = document.element.body

        blocks: list[dict[str, Any]] = []
        md_lines: list[str] = []
        text_lines: list[str] = []
        para_no = 0
        table_no = 0

        for child in body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                para = Paragraph(child, document)
                raw = (para.text or "").strip()
                if not raw:
                    continue
                level = _heading_level(para)
                block_type = BLOCK_TYPE_TITLE if level else BLOCK_TYPE_TEXT
                blocks.append(
                    {
                        "type": block_type,
                        "text": raw,
                        # 结构定位：Word 的第几个非空段落（1 起）。比"第几页"可靠得多，
                        # 因为它不依赖排版引擎。
                        "locator": {"kind": "paragraph", "paragraph_no": para_no + 1, "heading_level": level},
                    }
                )
                md_lines.append(f"{'#' * level} {raw}" if level else raw)
                text_lines.append(raw)
                para_no += 1
            elif tag == "tbl":
                table = Table(child, document)
                rows = [[(cell.text or "").strip() for cell in row.cells] for row in table.rows]
                if not any(any(c for c in row) for row in rows):
                    continue
                md_table = _rows_to_markdown(rows)
                blocks.append(
                    {
                        "type": BLOCK_TYPE_TABLE,
                        "text": "\n".join("\t".join(r) for r in rows if any(r)),
                        "table_body": md_table,
                        "locator": {"kind": "table", "table_no": table_no + 1, "rows": len(rows)},
                    }
                )
                md_lines.append(md_table)
                # 表格进纯文本时逐行铺开：下游分段/当事人识别按行扫，铺平才扫得到
                text_lines.extend(" ".join(c for c in row if c) for row in rows if any(row))
                table_no += 1

        pages = _paginate_blocks(blocks, text_lines)
        return ParsedDocument(
            text="\n".join(text_lines),
            markdown="\n\n".join(md_lines) if md_lines else None,
            metadata={
                "page_count": len(pages),
                "paragraph_count": para_no,
                "table_count": table_no,
                "office_kind": "word",
                # 分页是"逻辑页"（按块数切），不是排版分页——见模块注释
                "pagination": "logical",
            },
            parse_method="office_docx",
            layout={"page_count": len(pages), "pages": pages, "bbox_unit": "normalized", "bbox_approx": True},
        )

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    def _parse_excel(self, path: Path) -> ParsedDocument:
        """Excel → 每行一条文本 + 逐 sheet 的 Markdown 表格。"""
        rows_by_sheet = self._read_excel_rows(path)
        blocks: list[dict[str, Any]] = []
        md_lines: list[str] = []
        text_lines: list[str] = []

        for sheet_name, rows in rows_by_sheet:
            if not rows:
                continue
            md_lines.append(f"## {sheet_name}")
            md_lines.append(_rows_to_markdown(rows))
            for row_no, row in enumerate(rows, start=1):
                joined = " ".join(c for c in row if c)
                if not joined:
                    continue
                text_lines.append(joined)
                blocks.append(
                    {
                        "type": BLOCK_TYPE_TEXT,
                        "text": joined,
                        "locator": {"kind": "cell_row", "sheet": sheet_name, "row": row_no},
                    }
                )
            md_lines.append("")

        pages = _paginate_blocks(blocks, text_lines, per_page=_EXCEL_ROWS_PER_LOGICAL_PAGE)
        return ParsedDocument(
            text="\n".join(text_lines),
            markdown="\n".join(md_lines).strip() or None,
            metadata={
                "page_count": len(pages),
                "sheet_count": len(rows_by_sheet),
                "office_kind": "excel",
                "pagination": "logical",
            },
            parse_method="office_excel",
            layout={"page_count": len(pages), "pages": pages, "bbox_unit": "normalized", "bbox_approx": True},
        )

    def _read_excel_rows(self, path: Path) -> list[tuple[str, list[list[str]]]]:
        """读全部工作表 → [(sheet 名, 行列表)]。xlsx 用 openpyxl，xls 用 xlrd。"""
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            import openpyxl

            # read_only + data_only：大表不至于整本进内存；取公式的**计算结果**
            # 而不是 "=SUM(...)" 字符串——下游要的是数据本身。
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            try:
                out: list[tuple[str, list[list[str]]]] = []
                for ws in wb.worksheets:
                    rows = [
                        ["" if v is None else str(v).strip() for v in row] for row in ws.iter_rows(values_only=True)
                    ]
                    while rows and not any(rows[-1]):
                        rows.pop()
                    out.append((str(ws.title), rows))
                return out
            finally:
                wb.close()

        import xlrd

        book = xlrd.open_workbook(str(path))
        out = []
        for sheet in book.sheets():
            rows = [["" if c is None else str(c).strip() for c in sheet.row_values(i)] for i in range(sheet.nrows)]
            while rows and not any(rows[-1]):
                rows.pop()
            out.append((str(sheet.name), rows))
        return out


# ----------------------------------------------------------------------
# 纯函数（模块级）
#
# 四层架构规范：Service 层禁用静态方法，纯函数一律下沉到模块级
# （见 tests/ci/structure/test_four_layer_architecture.py 的棘轮）。
# 下面三个函数都不读实例/类状态，故不挂在 OfficeBackend 上。
# ----------------------------------------------------------------------


def display_width_digits(name: str) -> int:
    """从样式名里取末尾的层级数字（"Heading 2" / "标题 2" → 2），取不到返回 0。"""
    digits = ""
    for ch in reversed(name):
        if ch.isdigit():
            digits = ch + digits
        elif digits:
            break
    return int(digits) if digits.isdigit() else 0


def _heading_level(para: Any) -> int:
    """取标题层级（1-6），非标题返回 0。

    先认样式名（``Heading 1`` / ``标题 1``，中英两套写法都见过），
    再看大纲级别——WPS 生成的文档常把标题做成普通样式 + 大纲级别。
    """
    name = str(getattr(getattr(para, "style", None), "name", "") or "")
    for token in ("heading", "标题"):
        if name.lower().startswith(token):
            digits = display_width_digits(name)
            if digits:
                return max(1, min(digits, 6))
    # 大纲级别只能从 XML 读：python-docx 的 ParagraphFormat **没有**
    # outline_level 属性（直接访问会 AttributeError），它存在 pPr/w:outlineLvl。
    # 注意 w:outlineLvl 是 0 起的（0 = 一级标题）。
    try:
        from docx.oxml.ns import qn

        pPr = para._p.pPr
        node = pPr.find(qn("w:outlineLvl")) if pPr is not None else None
        raw = node.get(qn("w:val")) if node is not None else None
        if raw is not None and str(raw).isdigit():
            level = int(raw)
            if 0 <= level < 6:
                return level + 1
    except (AttributeError, ValueError, TypeError):
        # 段落没有 pPr / 没有 w:outlineLvl / val 不是数字，都等价于「没声明大纲级别」，
        # 由下面的 return 0 统一处理（文体样式判定已经先行尝试过）。此处不吞异常
        # 之外的任何状态，段落对象始终可用。
        pass
    return 0


def _rows_to_markdown(rows: list[list[str]]) -> str:
    """行列表 → GFM 表格（首行当表头；列宽取最长行）。"""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [list(r) + [""] * (width - len(r)) for r in rows]
    header, *body = norm
    esc = [[c.replace("|", "\\|").replace("\n", " ") for c in r] for r in (header, *body)]
    head = esc[0]
    rest = esc[1:]
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * width]
    lines.extend("| " + " | ".join(r) + " |" for r in rest)
    return "\n".join(lines)


def _paginate_blocks(
    blocks: list[dict[str, Any]],
    text_lines: list[str],
    per_page: int = _WORD_LINES_PER_LOGICAL_PAGE,
) -> list[dict[str, Any]]:
    """把**真实块**按顺序切成"逻辑页"（不能只按文本行切，否则丢掉块结构）。

    以前这里只把 text_lines 按行数和成一个大块，结果每页只有 1 个块，
    而 ``attach_blocks`` 要求 ≥2 个文本块才认为"块结构可用"，于是
    Office 文档明明有段落和表格，却被判成 ``coverage.has_blocks=False``、
    拿不到任何块级定位。现在保留原始块，只做分组。

    矩形为什么是"整页"：Office 没有像素坐标，逐块估算纵坐标只会给出一个
    **看起来精确、实际是编的**框。宁可给整页框并标 ``bbox_approx=True``，
    让前端知道"能定位到这一页，但框不代表具体位置"，也不给假精度。
    真正的精确定位走 ``locator``（段落序 / 行列），那是结构给出的确定信息。
    """
    pages: list[dict[str, Any]] = []
    if not blocks:
        return pages
    for start in range(0, len(blocks), per_page):
        chunk = blocks[start : start + per_page]
        page_no = len(pages) + 1
        page_blocks = [
            {
                "type": b.get("type") or BLOCK_TYPE_TEXT,
                "text": b.get("text") or "",
                "table_body": b.get("table_body"),
                # 整页矩形 + 结构 locator 同时下发：前者给"看得到"的锚点，
                # 后者给"定位得到"的确定答案
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "locator": b.get("locator"),
            }
            for b in chunk
        ]
        pages.append(
            {
                "page_no": page_no,
                "text": "\n".join(str(pb["text"]) for pb in page_blocks if pb["text"]),
                "blocks": page_blocks,
            }
        )
    return pages


__all__ = ["OfficeBackend", "display_width_digits"]
