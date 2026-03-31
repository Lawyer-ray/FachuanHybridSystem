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
    # 一审/二审共用
    COURT_OPENING = "mt_court_opening"          # 庭前准备+宣布开庭
    IDENTITY_CHECK = "mt_identity_check"        # 核实当事人身份
    RIGHTS_NOTICE = "mt_rights_notice"          # 告知权利义务+询问回避
    # 二审特有
    APPEAL_STATEMENT = "mt_appeal_statement"    # 上诉请求与答辩
    # 一审/二审共用
    PLAINTIFF_STATEMENT = "mt_plaintiff_statement"  # 原告陈述（一审）
    DEFENDANT_RESPONSE = "mt_defendant_response"    # 被告答辩（一审）
    COURT_INVESTIGATION = "mt_court_investigation"  # 法庭调查（举证质证）
    COURT_DEBATE = "mt_court_debate"                # 法庭辩论
    FINAL_STATEMENT = "mt_final_statement"          # 最后陈述
    MEDIATION = "mt_mediation"                      # 法庭调解
    COURT_SUMMARY = "mt_court_summary"              # 法官总结/宣判


class TrialLevel(str, Enum):
    """审级."""

    FIRST = "first"    # 一审
    SECOND = "second"  # 二审


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
    trial_level: str = "first"  # first / second
