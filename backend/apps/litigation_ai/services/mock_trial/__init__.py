"""模拟庭审子模块."""

from __future__ import annotations

from .adversarial_service import AdversarialTrialService
from .agents import DEFENDANT, JUDGE, PLAINTIFF, ROLE_LABELS, Agent
from .export_service import MockTrialExportService
from .mock_trial_flow_service import MockTrialFlowService
from .report_service import MockTrialReportService
from .types import AdversarialConfig, MockTrialContext, MockTrialStep, TrialLevel

__all__ = [
    "DEFENDANT",
    "JUDGE",
    "PLAINTIFF",
    "ROLE_LABELS",
    "AdversarialConfig",
    "AdversarialTrialService",
    "Agent",
    "MockTrialContext",
    "MockTrialExportService",
    "MockTrialFlowService",
    "MockTrialReportService",
    "MockTrialStep",
    "TrialLevel",
]
