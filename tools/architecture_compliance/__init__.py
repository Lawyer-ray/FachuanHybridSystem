"""
架构合规性检查和重构工具

用于扫描和修复backend项目中违反四层架构规范的代码。
"""
from __future__ import annotations

from .models import (
    Violation,
    ApiViolation,
    ServiceViolation,
    ModelViolation,
    RefactoringResult,
    ViolationReport,
    BatchResult,
)
from .errors import (
    RefactoringError,
    TestFailureError,
    RefactoringSyntaxError,
    CircularDependencyError,
)
from .rollback import RollbackManager, Checkpoint
from .scanner import ViolationScanner
from .api_scanner import ApiLayerScanner
from .service_scanner import ServiceLayerScanner
from .model_scanner import ModelLayerScanner
from .report_generator import ReportGenerator
from .api_refactoring_engine import ApiRefactoringEngine
from .service_refactoring_engine import ServiceRefactoringEngine
from .service_method_extractor import ServiceMethodExtractor
from .api_file_updater import ApiFileUpdater
from .scan_pilot_module import scan_module
from .static_method_analyzer import (
    StaticMethodAnalyzer,
    StaticMethodAnalysisReport,
    StaticMethodClassification,
    StaticMethodInfo,
    ConversionReason,
)
from .static_method_converter import (
    StaticMethodConverter,
    DependencyInfo,
    MethodConversionPlan,
    FileConversionPlan,
)
from .call_site_updater import (
    CallSiteUpdater,
    CallSite,
    CallSiteUpdate,
    CallSiteUpdateReport,
    FileCallSiteReport,
)
from .save_method_analyzer import (
    SaveMethodAnalyzer,
    SaveMethodAnalysis,
    SaveMethodBlock,
)
from .business_logic_extractor import (
    BusinessLogicExtractor,
    ExtractedServiceMethod,
    SaveMethodRefactoring,
    format_service_method_template,
)
from .model_save_call_updater import (
    ModelSaveCallUpdater,
    ModelSaveCallSite,
    ModelSaveCallUpdate,
    ModelSaveUpdateReport,
    FileModelSaveReport,
)
from .refactoring_orchestrator import RefactoringOrchestrator
from .progress_tracker import (
    ProgressTracker,
    ProgressReport,
    PhaseReport,
    ProgressCallback,
)

__all__ = [
    # Data Models
    "Violation",
    "ApiViolation",
    "ServiceViolation",
    "ModelViolation",
    "RefactoringResult",
    "ViolationReport",
    "BatchResult",
    # Errors
    "RefactoringError",
    "TestFailureError",
    "RefactoringSyntaxError",
    "CircularDependencyError",
    # Rollback
    "RollbackManager",
    "Checkpoint",
    # Scanner
    "ViolationScanner",
    "ApiLayerScanner",
    "ServiceLayerScanner",
    "ModelLayerScanner",
    # Report Generator
    "ReportGenerator",
    # Refactoring Engines
    "ApiRefactoringEngine",
    "ServiceRefactoringEngine",
    "ServiceMethodExtractor",
    "ApiFileUpdater",
    # Pilot module scan
    "scan_module",
    # Static method analyzer
    "StaticMethodAnalyzer",
    "StaticMethodAnalysisReport",
    "StaticMethodClassification",
    "StaticMethodInfo",
    "ConversionReason",
    # Static method converter
    "StaticMethodConverter",
    "DependencyInfo",
    "MethodConversionPlan",
    "FileConversionPlan",
    # Call site updater
    "CallSiteUpdater",
    "CallSite",
    "CallSiteUpdate",
    "CallSiteUpdateReport",
    "FileCallSiteReport",
    # Save method analyzer
    "SaveMethodAnalyzer",
    "SaveMethodAnalysis",
    "SaveMethodBlock",
    # Business logic extractor
    "BusinessLogicExtractor",
    "ExtractedServiceMethod",
    "SaveMethodRefactoring",
    "format_service_method_template",
    # Model save call updater
    "ModelSaveCallUpdater",
    "ModelSaveCallSite",
    "ModelSaveCallUpdate",
    "ModelSaveUpdateReport",
    "FileModelSaveReport",
    # Refactoring orchestrator
    "RefactoringOrchestrator",
    # Progress tracker
    "ProgressTracker",
    "ProgressReport",
    "PhaseReport",
    "ProgressCallback",
]
