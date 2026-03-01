"""OA立案相关依赖注入."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.oa_filing.services.browser_automation_service import BrowserAutomationService
    from apps.oa_filing.services.filing_session_service import FilingSessionService
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService
    from apps.oa_filing.services.script_generator_service import ScriptGeneratorService
    from apps.oa_filing.services.step_recorder_service import StepRecorderService


def build_filing_session_service() -> FilingSessionService:
    from apps.oa_filing.services.filing_session_service import FilingSessionService

    return FilingSessionService()


def build_browser_automation_service() -> BrowserAutomationService:
    from apps.oa_filing.services.browser_automation_service import BrowserAutomationService

    return BrowserAutomationService()


def build_step_recorder_service() -> StepRecorderService:
    from apps.oa_filing.services.step_recorder_service import StepRecorderService

    return StepRecorderService()


def build_script_generator_service() -> ScriptGeneratorService:
    from apps.oa_filing.services.script_generator_service import ScriptGeneratorService

    return ScriptGeneratorService()


def build_script_executor_service() -> ScriptExecutorService:
    from apps.oa_filing.services.script_executor_service import ScriptExecutorService

    return ScriptExecutorService()
