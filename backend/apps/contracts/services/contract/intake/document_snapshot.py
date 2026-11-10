"""合同文档快照：把上传的合同文件转成可供 LLM 消费的纯文本。

纯确定性模块（无 IO 之外的副作用、不调用 AI），便于单测。

为什么必须抽表格：合同签署页（甲乙方盖章、签约日期）几乎总在 ``<w:tbl>`` 里，
``python-docx`` 的 ``paragraphs`` 不包含表格单元格文字——只取段落会丢掉落款，
而落款正是「签约日期」这一字段的唯一来源（实测本仓库样例合同即如此）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 支持的合同文件扩展名 → 归一化后的类型标签
SUPPORTED_SUFFIXES: dict[str, str] = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
}

#: 单份合同送给 LLM 的正文最大字符数。超长时优先保留头部与「关键词段」。
#: 8 万字符约 4-6 万 token，主流 128k 上下文模型足够，且留出输出空间。
MAX_PROMPT_CHARS = 80_000

#: 命中这些关键词的段落即使超出长度上限也优先保留（收费/期限/当事人/签署语义所在）
_CRITICAL_KEYWORDS: tuple[str, ...] = (
    "律师费",
    "费用",
    "收费",
    "支付",
    "金额",
    "人民币",
    "元整",
    "甲方",
    "乙方",
    "委托人",
    "受托人",
    "当事人",
    "委托事项",
    "服务事",
    "指派",
    "主办律师",
    "承办律师",
    "签字",
    "盖章",
    "签约",
    "签署",
    "生效",
    "期限",
    "期间",
    "起止",
    "年月日",
    "争议",
    "仲裁",
    "法院",
    "案号",
    "通知书",
)

#: 表格单元格多行文本压成单行的分隔符
_CELL_JOINER = " / "


class DocumentSnapshotError(Exception):
    """文档无法提取文本（格式不支持 / 加密 / 空文档 / 解析失败）。"""


@dataclass
class DocumentSnapshot:
    """一份合同文档的可消费文本快照。"""

    filename: str
    suffix: str
    text: str
    paragraph_count: int = 0
    table_count: int = 0
    page_count: int = 0
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text)


def detect_suffix(filename: str) -> str:
    """返回归一化扩展名（含点，小写）；不支持时抛错。"""
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = "、".join(sorted(SUPPORTED_SUFFIXES))
        raise DocumentSnapshotError(f"不支持的文件类型「{suffix or '无扩展名'}」，仅支持 {supported}")
    return suffix


def _clean_line(raw: str) -> str:
    """压缩空白：保留中文全角空格语义上的分隔，但去掉零宽字符与多余空格。"""
    text = str(raw or "")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\xa0", " ")
    # 连续空白压成单个空格；制表符同理
    text = re.sub(r"[ \t\u3000]+", " ", text)
    return text.strip()


def extract_docx_text(path: Path) -> tuple[list[str], int, int]:
    """提取 docx 的段落与表格文本。

    Returns:
        ``(lines, paragraph_count, table_count)``；表格行以 ``表格N | 列1 / 列2`` 形式落行。
    """
    from docx import Document  # 延迟导入：仅在实际解析时载入

    try:
        document = Document(str(path))
    except Exception as exc:  # python-docx 对损坏/加密文件抛多种异常
        raise DocumentSnapshotError(f"无法读取 Word 文档：{exc}") from exc

    lines: list[str] = []
    for paragraph in document.paragraphs:
        cleaned = _clean_line(paragraph.text)
        if cleaned:
            lines.append(cleaned)

    tables = list(document.tables)
    for index, table in enumerate(tables, start=1):
        lines.append(f"【签署/信息表格 {index}】")
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                # 单元格内多段文本用 / 连接，空单元格跳过以免产生大量分隔符
                inner = _CELL_JOINER.join(filter(None, (_clean_line(p.text) for p in cell.paragraphs)))
                if inner:
                    cells.append(inner)
            if cells:
                lines.append(" | ".join(cells))

    return lines, len(document.paragraphs), len(tables)


def extract_pdf_text(path: Path) -> tuple[list[str], int]:
    """提取 PDF 文本层。

    Returns:
        ``(lines, page_count)``。扫描件（无文本层）返回空 lines，由调用方提示用户。
    """
    import pymupdf  # PyMuPDF

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        raise DocumentSnapshotError(f"无法读取 PDF：{exc}") from exc

    try:
        if getattr(document, "needs_pass", False):
            raise DocumentSnapshotError("PDF 已加密，请先解除密码后再导入")
        lines: list[str] = []
        # 按索引逐页取：PyMuPDF 的 stubs 未声明 Document.__iter__，mypy 会报不可迭代
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            for raw_line in str(page.get_text() or "").splitlines():
                cleaned = _clean_line(raw_line)
                if cleaned:
                    lines.append(cleaned)
        return lines, int(document.page_count or 0)
    finally:
        document.close()


def extract_text_file(path: Path) -> tuple[list[str], int]:
    """读取纯文本文件（txt/md），按行切分。"""
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            content = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise DocumentSnapshotError("文本编码无法识别（已尝试 UTF-8 / GB18030）")

    lines = [_clean_line(line) for line in content.splitlines()]
    return [line for line in lines if line], 0


def select_for_prompt(lines: list[str], *, max_chars: int = MAX_PROMPT_CHARS) -> tuple[str, bool]:
    """在长度上限内挑出最有价值的行，返回 ``(text, truncated)``。

    策略：未超限直接全文返回；超限时按「头部保留 + 关键词行 + 表格行」优先级选取，
    保证收费条款、当事人信息与签署表格不会被截掉。
    """
    full = "\n".join(lines)
    if len(full) <= max_chars:
        return full, False

    # 头部保留：合同标题、编号、当事人首段通常在前 25% 预算内
    head_budget = max_chars // 4
    selected: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > head_budget:
            break
        selected.append(line)
        used += len(line) + 1

    head_consumed = len(selected)
    for line in lines[head_consumed:]:
        is_critical = any(keyword in line for keyword in _CRITICAL_KEYWORDS)
        if not is_critical:
            continue
        if used + len(line) + 1 > max_chars:
            continue
        selected.append(line)
        used += len(line) + 1

    logger.info(
        "合同正文超长已裁剪: 原文 %d 字符，送入 %d 字符，保留 %d/%d 行",
        len(full),
        used,
        len(selected),
        len(lines),
    )
    return "\n".join(selected), True


def build_snapshot(*, path: Path, filename: str) -> DocumentSnapshot:
    """把磁盘上的合同文件转成 :class:`DocumentSnapshot`。"""
    suffix = detect_suffix(filename)
    kind = SUPPORTED_SUFFIXES[suffix]
    warnings: list[str] = []
    paragraph_count = 0
    table_count = 0
    page_count = 0

    if kind == "docx":
        lines, paragraph_count, table_count = extract_docx_text(path)
    elif kind == "pdf":
        lines, page_count = extract_pdf_text(path)
        if not lines:
            raise DocumentSnapshotError("PDF 没有可提取的文字层（疑似扫描件），请改用 Word 版或先做 OCR")
    else:
        lines, _ = extract_text_file(path)

    if not lines:
        raise DocumentSnapshotError("文档中未提取到任何文字")

    text, truncated = select_for_prompt(lines)
    if truncated:
        warnings.append("合同正文较长，已按关键条款优先裁剪后送模型分析，请重点核对未展示部分")

    if kind == "docx" and table_count == 0 and not any("签约日期" in line for line in lines):
        warnings.append("未在文档中找到签署表格，签约日期等落款信息可能缺失")

    return DocumentSnapshot(
        filename=filename,
        suffix=suffix,
        text=text,
        paragraph_count=paragraph_count,
        table_count=table_count,
        page_count=page_count,
        truncated=truncated,
        warnings=warnings,
    )


def snapshot_to_dict(snapshot: DocumentSnapshot) -> dict[str, Any]:
    """调试/日志用摘要（不含全文，避免把合同正文写进日志）。"""
    return {
        "filename": snapshot.filename,
        "suffix": snapshot.suffix,
        "char_count": snapshot.char_count,
        "paragraph_count": snapshot.paragraph_count,
        "table_count": snapshot.table_count,
        "page_count": snapshot.page_count,
        "truncated": snapshot.truncated,
        "warnings": list(snapshot.warnings),
    }
