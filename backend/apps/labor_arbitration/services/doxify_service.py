"""Doxify 文本清洗服务包装器。

将 ~/.workbuddy/skills/doxify/doxify.py 中的 clean/check 功能集成到项目中，
供解析流程做 OCR 后处理。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)

# 把 doxify.py 所在目录加入 sys.path（项目虚拟环境未安装该包）
_DOXIFY_DIR = Path.home() / ".workbuddy" / "skills" / "doxify"
if str(_DOXIFY_DIR) not in sys.path:
    sys.path.insert(0, str(_DOXIFY_DIR))


def _import_doxify_clean() -> tuple[Any, Any, Any, Any, Any]:
    """延迟导入 doxify 清洗函数，失败时抛出以便调用方降级处理。"""
    try:
        from doxify import (
            _normalize_vlm_latex,
            detect_residual_english,
            merge_broken_paragraphs,
            normalize_footnotes,
            strip_watermarks,
        )

        return (
            strip_watermarks,
            merge_broken_paragraphs,
            normalize_footnotes,
            _normalize_vlm_latex,
            detect_residual_english,
        )
    except ImportError as exc:
        logger.warning("[Doxify] 无法导入 doxify.py: %s", exc)
        raise


def clean_text(text: str) -> tuple[str, dict[str, Any]]:
    """对 OCR 纯文本做 Doxify 清洗。

    处理范围：
    - 去水印（页眉页脚 Barcode/Filed By 等水印尼行）
    - 段落接回（跨分页/分块时被截断的句子）
    - LaTeX 排版符号（$\\underline$ 等）转 HTML 标签

    脚注归一化在纯文本中极少见，暂不做。
    """
    if not text or not text.strip():
        return text, {}

    try:
        (
            strip_watermarks_func,
            merge_broken_paragraphs_func,
            _,
            normalize_vlm_latex_func,
            _,
        ) = _import_doxify_clean()
    except Exception as exc:
        logger.warning("[Doxify] clean_text 降级（原样返回）: %s", exc)
        return text, {"error": str(exc)}

    cleaned = normalize_vlm_latex_func(text)
    cleaned, n_merged = merge_broken_paragraphs_func(cleaned)
    cleaned, n_watermark = strip_watermarks_func(cleaned)

    return cleaned, {
        "paragraphs_merged": n_merged,
        "watermark_lines_removed": n_watermark,
    }


def clean_markdown(md: str) -> tuple[str, dict[str, Any]]:
    """对 Markdown 做完整的 Doxify 清洗。

    按 v2 服务端后处理顺序：
    1. LaTeX 排版符号 → HTML 标签
    2. 跨页/跨块断句接回
    3. 脚注归一化（^N^ / <sup>N</sup> → [^N]，尾注区 → [^N]: 定义）
    4. 去水印
    """
    if not md or not md.strip():
        return md, {}

    try:
        (
            strip_watermarks_func,
            merge_broken_paragraphs_func,
            normalize_footnotes_func,
            normalize_vlm_latex_func,
            _,
        ) = _import_doxify_clean()
    except Exception as exc:
        logger.warning("[Doxify] clean_markdown 降级（原样返回）: %s", exc)
        return md, {"error": str(exc)}

    cleaned = normalize_vlm_latex_func(md)
    cleaned, n_merged = merge_broken_paragraphs_func(cleaned)
    cleaned, n_fn = normalize_footnotes_func(cleaned)
    cleaned, n_watermark = strip_watermarks_func(cleaned)

    return cleaned, {
        "paragraphs_merged": n_merged,
        "footnotes_normalized": n_fn,
        "watermark_lines_removed": n_watermark,
    }


def check_residual_english(text: str) -> list[str]:
    """检查文本中残留的未翻译英文词（白名单会自动过滤）。"""
    if not text or not text.strip():
        return []
    try:
        _, _, _, _, detect_func = _import_doxify_clean()
        return cast(list[str], detect_func(text))
    except Exception as exc:
        logger.warning("[Doxify] check_residual_english 失败: %s", exc)
        return []
