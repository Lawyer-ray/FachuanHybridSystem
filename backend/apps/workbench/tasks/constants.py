"""批量分析任务常量、结构化输出模型和系统提示词"""

from __future__ import annotations

import re

from pydantic import BaseModel

# ─── 常量 ────────────────────────────────────────────────────────────────────

PROGRESS_UPDATE_EVERY = 5  # 每 N 个 item 更新一次进度
CANCEL_CHECK_EVERY = 5  # 每 N 个 item 检查一次取消标志
CHUNK_SIZE = 15000  # 长文档分段大小
CHUNK_OVERLAP = 2000  # 分段重叠字符数
CHUNK_THRESHOLD = 20000  # 超过此长度触发分段

# ─── 结构化输出模型 ──────────────────────────────────────────────────────────

class CaseAnalysisResult(BaseModel):
    """LLM 分析结果的结构化输出"""

    case_number: str = "未注明"
    cause: str = "未注明"
    court: str = "未注明"
    judge: str = "未注明"
    clerk: str = "未注明"
    is_relevant: bool = True
    conclusion: str = ""
    analysis: str = ""

# ─── 系统提示词 ──────────────────────────────────────────────────────────────

_ANALYSIS_INSTRUCTIONS = (
    "你是一位专业的法律文档分析专家。请根据用户提供的分析要求，对文档内容进行分析。\n\n"
    "## 分析步骤\n"
    "第一步：判断本案是否与用户的研究问题相关。\n"
    "- 如果无关，is_relevant 设为 false，conclusion 说明无关原因，analysis 简要说明即可。\n"
    "- 如果有关，is_relevant 设为 true，继续下一步。\n\n"
    "第二步（仅相关案例）：\n"
    "1. 分析本案的全部争议焦点和裁判要旨\n"
    "2. 但只详细输出与用户查询问题直接相关的争议焦点和裁判要旨，其他内容简要提及即可\n"
    "3. 给出针对用户查询问题的明确结论\n\n"
    "## 输出格式要求\n"
    "- 如果用户提供了案号、审理法院等元数据，请使用这些信息，不要编造\n"
    "- 使用专业但易懂的语言\n"
    "- 使用清晰的结构化格式\n\n"
    "## 重要\n"
    "- case_number、cause、court、judge、clerk 字段必须从文档中提取，找不到则填「未注明」\n"
    "- conclusion 字段填写针对用户研究问题的结论\n"
    "- analysis 字段填写完整的分析正文（Markdown 格式）"
)

from apps.core.llm.structured_output import json_schema_instructions

_SCHEMA_INSTRUCTIONS = json_schema_instructions(CaseAnalysisResult)

ANALYSIS_SYSTEM_PROMPT = _ANALYSIS_INSTRUCTIONS + "\n\n" + _SCHEMA_INSTRUCTIONS

# ─── 正则 fallback ───────────────────────────────────────────────────────────

METADATA_BLOCK_RE = re.compile(
    r"```[^\n]*\n\s*【案例元数据汇总】\s*\n([\s\S]*?)\n\s*```\s*\Z"
    r"|【案例元数据汇总】\s*\n([\s\S]*?)\Z",
)
METADATA_FIELD_RE = re.compile(r"^(案号|案由|审理法院|法官|书记员|与研究问题相关|结论)\s*[：:]\s*(.+)$", re.MULTILINE)
_CONCLUSION_RE = re.compile(
    r"(?:^|\n)#{1,3}\s*(?:针对.*研究.*结论|结论)\s*\n([\s\S]*?)(?=\n(?:```|【案例元数据汇总】|#{1,3}\s)|\Z)",
    re.MULTILINE,
)
