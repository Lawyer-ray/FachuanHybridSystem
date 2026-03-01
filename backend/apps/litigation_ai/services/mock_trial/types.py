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


@dataclass
class MockTrialContext:
    """模拟庭审流程上下文."""

    session_id: str
    case_id: int
    user_id: int
    current_step: MockTrialStep
    mode: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
