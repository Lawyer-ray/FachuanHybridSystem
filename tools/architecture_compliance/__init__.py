"""
架构合规性检查和重构工具

用于扫描和修复backend项目中违反四层架构规范的代码。
"""

from __future__ import annotations

from .api_file_updater import ApiFileUpdater
from .api_refactoring_engine import ApiRefactoringEngine
from .api_scanner import ApiLayerScanner
from .business_logic_extractor import (
    BusinessLogicExtractor,
    ExtractedServiceMethod,
    SaveMethodRefactoring,
    format_service_method_template,
)
from .call_site_updater import CallSite, CallSiteUpdate, CallSiteUpdater, CallSiteUpdateReport, FileCallSiteReport
from .errors import CircularDependencyError, RefactoringError, RefactoringSyntaxError, TestFailureError
from .model_save_call_updater import (
    FileModelSaveReport,
    ModelSaveCallSite,
    ModelSaveCallUpdate,
    ModelSaveCallUpdater,
    ModelSaveUpdateReport,
)
from .model_scanner import ModelLayerScanner
from .models import (
    ApiViolation,
    BatchResult,
    ModelViolation,
    RefactoringResult,
    ServiceViolation,
    Violation,
    ViolationReport,
)
from .progress_tracker import PhaseReport, ProgressCallback, ProgressReport, ProgressTracker
from .refactoring_orchestrator import RefactoringOrchestrator
from .report_generator import ReportGenerator
from .rollback import Checkpoint, RollbackManager
from .save_method_analyzer import SaveMethodAnalysis, SaveMethodAnalyzer, SaveMethodBlock
from .scan_pilot_module import scan_module
from .scanner import ViolationScanner
from .service_method_extractor import ServiceMethodExtractor
from .service_refactoring_engine import ServiceRefactoringEngine
from .service_scanner import ServiceLayerScanner
from .static_method_analyzer import (
    ConversionReason,
    StaticMethodAnalysisReport,
    StaticMethodAnalyzer,
    StaticMethodClassification,
    StaticMethodInfo,
)
from .static_method_converter import DependencyInfo, FileConversionPlan, MethodConversionPlan, StaticMethodConverter

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
