"""documents 裁判文书提取器的 contracts 出口。

contracts 侧只暴露构造入口，实现细节（正则 + LLM 兜底）留在 documents。
延迟 import：契约模块不持有对 documents 的模块级引用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor


def build_judgment_pdf_extractor() -> JudgmentPdfExtractor:
    """构造裁判文书 PDF 提取器（判决书/调解书/程序性文书共用）。"""
    from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor

    return JudgmentPdfExtractor()
