"""结果解析和文本分段工具函数"""

from __future__ import annotations

import json
import logging
from typing import Any

from .constants import (
    _CONCLUSION_RE,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    METADATA_BLOCK_RE,
    METADATA_FIELD_RE,
    CaseAnalysisResult,
)

logger = logging.getLogger(__name__)

# ─── 文档分段 ────────────────────────────────────────────────────────────────


def chunk_text(text: str, max_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将长文本分成重叠的段落"""
    if len(text) <= max_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_size
        if end < len(text):
            # 尝试在句号、换行处断开
            for sep in ["\n\n", "\n", "。", "；", ".", "\r\n"]:
                pos = text.rfind(sep, start + max_size // 2, end)
                if pos > start:
                    end = pos + len(sep)
                    break
        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else end
    return chunks


# ─── 结果解析 ────────────────────────────────────────────────────────────────


def parse_llm_result(result_text: str, file_name: str) -> dict[str, Any]:
    """解析 LLM 输出，优先 JSON 结构化，fallback 到正则"""
    from apps.core.llm.structured_output import parse_model_content

    # 尝试 JSON 结构化解析
    try:
        parsed = parse_model_content(result_text, CaseAnalysisResult)
        return {
            "case_number": parsed.case_number,
            "cause": parsed.cause,
            "court": parsed.court,
            "judge": parsed.judge,
            "clerk": parsed.clerk,
            "is_relevant": parsed.is_relevant,
            "conclusion": parsed.conclusion,
            "analysis": parsed.analysis,
            "parse_method": "json",
        }
    except Exception:
        logger.debug("JSON 解析失败，回退到正则: %s", file_name)

    # Fallback：正则提取
    fields: dict[str, str] = {}
    block_match = METADATA_BLOCK_RE.search(result_text)
    if block_match:
        block_text = (block_match.group(1) or block_match.group(2) or "").strip()
        for field_match in METADATA_FIELD_RE.finditer(block_text):
            fields[field_match.group(1).strip()] = field_match.group(2).strip()

    conclusion = fields.get("结论", "")
    conclusion_match = _CONCLUSION_RE.search(result_text)
    if conclusion_match:
        full_conclusion = conclusion_match.group(1).strip()
        if full_conclusion:
            conclusion = full_conclusion

    # 去掉元数据块，保留分析正文
    analysis = result_text
    if block_match:
        analysis = result_text[: block_match.start()].strip()

    return {
        "case_number": fields.get("案号", "未注明"),
        "cause": fields.get("案由", "未注明"),
        "court": fields.get("审理法院", "未注明"),
        "judge": fields.get("法官", "未注明"),
        "clerk": fields.get("书记员", "未注明"),
        "is_relevant": fields.get("与研究问题相关", "是") == "是",
        "conclusion": conclusion or "未注明",
        "analysis": analysis,
        "parse_method": "regex",
    }


# ─── 共享分析逻辑 ────────────────────────────────────────────────────────────


def build_case_info(metadata: dict[str, str | None]) -> str:
    """从文档元数据构建案例信息字符串"""
    parts = []
    if metadata.get("case_number"):
        parts.append(f"案号：{metadata['case_number']}")
    if metadata.get("court"):
        parts.append(f"审理法院：{metadata['court']}")
    if metadata.get("cause"):
        parts.append(f"案由：{metadata['cause']}")
    if metadata.get("judge"):
        parts.append(f"法官：{metadata['judge']}")
    if metadata.get("clerk"):
        parts.append(f"书记员：{metadata['clerk']}")
    return "\n".join(parts) + "\n" if parts else ""


def merge_chunk_results(chunk_results: list[str], file_name: str) -> str:
    """合并多个 chunk 的分析结果"""
    if len(chunk_results) == 1:
        return chunk_results[0]

    all_analysis = []
    last_parsed = parse_llm_result(chunk_results[-1], file_name)
    for cr in chunk_results:
        parsed = parse_llm_result(cr, file_name)
        if parsed["analysis"]:
            all_analysis.append(parsed["analysis"])
    last_parsed["analysis"] = "\n\n---\n\n".join(all_analysis)
    return json.dumps(last_parsed, ensure_ascii=False)
