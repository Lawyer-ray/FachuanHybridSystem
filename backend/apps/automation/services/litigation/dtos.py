"""诉讼态势识别的结构化输出模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CourtPleadingSignals(BaseModel):
    """案件诉讼文书态势信号。

    由 LLM 从法院文书名称列表识别的结构化结果，字段与
    ``apps.core.dto.litigation.CourtPleadingSignalsDTO`` 保持一致。
    """

    has_complaint: bool = Field(default=False, description="是否出现起诉状")
    has_defense: bool = Field(default=False, description="是否出现答辩状")
    has_counterclaim: bool = Field(default=False, description="是否出现反诉状")
    has_counterclaim_defense: bool = Field(default=False, description="是否出现反诉答辩状")
    notes: str = Field(default="", description="判断依据或补充说明")
