"""模拟庭审流程类型定义."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MockTrialStep(str, Enum):
    """模拟庭审步骤."""

    INIT = "mt_init"
    MODE_SELECT = "mt_mode_select"
    EVIDENCE_LOAD = "mt_evidence_load"
    FOCUS_ANALYSIS = "mt_focus_analysis"
    SIMULATION = "mt_simulation"
    SUMMARY = "mt_summary"
    # 多 Agent 对抗专用步骤
    MODEL_CONFIG = "mt_model_config"
    COURT_OPENING = "mt_court_opening"
    PLAINTIFF_STATEMENT = "mt_plaintiff_statement"
    DEFENDANT_RESPONSE = "mt_defendant_response"
    COURT_INVESTIGATION = "mt_court_investigation"
    COURT_DEBATE = "mt_court_debate"
    COURT_SUMMARY = "mt_court_summary"


@dataclass
class MockTrialContext:
    """模拟庭审流程上下文."""

    session_id: str
    case_id: int
    user_id: int
    current_step: MockTrialStep
    mode: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdversarialConfig:
    """多 Agent 对抗配置."""

    plaintiff_model: str = ""
    defendant_model: str = ""
    judge_model: str = ""
    debate_rounds: int = 10
    user_role: str = "observer"  # plaintiff / defendant / judge / observer
