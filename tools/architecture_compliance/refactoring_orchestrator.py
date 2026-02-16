"""
重构协调器

协调各个重构引擎（API层、Service层、Model层），实现批量重构逻辑，
集成 RollbackManager 进行回滚管理，每个违规重构后进行语法验证。
"""

from __future__ import annotations

import ast
import time
import uuid
from pathlib import Path
from typing import Optional

from .api_refactoring_engine import ApiRefactoringEngine
from .api_scanner import ApiLayerScanner
from .errors import RefactoringError
from .logging_config import get_logger
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
from .progress_tracker import ProgressCallback, ProgressTracker
from .report_generator import ReportGenerator
from .rollback import RollbackManager
from .service_refactoring_engine import ServiceRefactoringEngine
from .service_scanner import ServiceLayerScanner

logger = get_logger("refactoring_orchestrator")

# 违规类型 → 严重程度排序权重（越小越优先）
_SEVERITY_ORDER: dict[str, int] = {
    "high": 0,
    "medium": 1,
    "low": 2,
}

# 违规类型 → 处理优先级（越小越优先）
_TYPE_PRIORITY: dict[str, int] = {
    "api_direct_orm_access": 0,
    "service_cross_module_import": 1,
    "service_static_method_abuse": 2,
    "model_business_logic_in_save": 3,
}


def _sort_key(violation: Violation) -> tuple[int, int, str, int]:
    """
    生成违规排序键：按类型优先级、严重程度、文件路径、行号排序。

    Args:
        violation: 违规对象

    Returns:
        排序元组
    """
    type_priority = _TYPE_PRIORITY.get(violation.violation_type, 99)
    severity_priority = _SEVERITY_ORDER.get(violation.severity, 99)
    return (type_priority, severity_priority, violation.file_path, violation.line_number)


class RefactoringOrchestrator:
    """
    重构协调器

    协调 API、Service、Model 三层重构引擎，提供：
    - 完整扫描（execute_full_scan）
    - 批量重构（execute_refactoring_batch）
    - 按层重构（execute_api_refactoring / execute_service_refactoring / execute_model_refactoring）
    - 语法验证（validate_refactoring）

    每次重构前创建回滚点，失败时自动回滚。
    """

    def __init__(
        self,
        rollback_manager: Optional[RollbackManager] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.api_scanner = ApiLayerScanner()
        self.service_scanner = ServiceLayerScanner()
        self.model_scanner = ModelLayerScanner()
        self.api_engine = ApiRefactoringEngine()
        self.service_engine = ServiceRefactoringEngine()
        self.report_generator = ReportGenerator()
        self.rollback_manager = rollback_manager or RollbackManager()
        self._progress_callback = progress_callback

    # ── 完整扫描 ────────────────────────────────────────────

    def execute_full_scan(self, root: Path) -> ViolationReport:
        """
        对指定目录执行完整的架构违规扫描（API + Service + Model 层）。

        Args:
            root: 要扫描的项目根目录

        Returns:
            包含所有违规的 ViolationReport
        """
        root = Path(root)
        logger.info("开始完整扫描: %s", root)
        start = time.monotonic()

        all_violations: list[Violation] = []

        api_violations = self.api_scanner.scan_directory(root)
        logger.info("API 层扫描完成: %d 个违规", len(api_violations))
        all_violations.extend(api_violations)

        service_violations = self.service_scanner.scan_directory(root)
        logger.info("Service 层扫描完成: %d 个违规", len(service_violations))
        all_violations.extend(service_violations)

        model_violations = self.model_scanner.scan_directory(root)
        logger.info("Model 层扫描完成: %d 个违规", len(model_violations))
        all_violations.extend(model_violations)

        report = self.report_generator.build_report(all_violations)
        elapsed = time.monotonic() - start
        logger.info(
            "完整扫描结束: 共 %d 个违规, 耗时 %.2f 秒",
            report.total_violations,
            elapsed,
        )
        return report

    # ── 批量重构 ────────────────────────────────────────────

    def execute_refactoring_batch(
        self,
        violations: list[Violation],
        batch_size: int = 10,
    ) -> BatchResult:
        """
        执行批量重构。

        流程：
        1. 按优先级和依赖关系排序违规
        2. 分批处理（每批 batch_size 个）
        3. 每个违规：创建回滚点 → 执行重构 → 语法验证 → 失败则回滚
        4. 生成 BatchResult 报告

        Args:
            violations: 待重构的违规列表
            batch_size: 每批处理的违规数量

        Returns:
            BatchResult 包含成功/失败统计和详细结果
        """
        batch_id = uuid.uuid4().hex[:8]
        logger.info(
            "开始批量重构 [%s]: %d 个违规, 批大小 %d",
            batch_id,
            len(violations),
            batch_size,
        )
        start = time.monotonic()

        sorted_violations = sorted(violations, key=_sort_key)

        tracker = ProgressTracker(
            total_violations=len(sorted_violations),
            callback=self._progress_callback,
        )

        results: list[RefactoringResult] = []
        successful = 0
        failed = 0
        skipped = 0

        for i in range(0, len(sorted_violations), batch_size):
            batch = sorted_violations[i : i + batch_size]
            batch_num = i // batch_size + 1
            phase_name = f"批次 {batch_num}"
            tracker.start_phase(phase_name)

            logger.info(
                "处理第 %d 批 (%d 个违规)",
                batch_num,
                len(batch),
            )

            for violation in batch:
                result = self._refactor_single_violation(violation)
                results.append(result)
                tracker.record_result(violation, result)
                if result.success:
                    successful += 1
                elif result.error_message and "跳过" in result.error_message:
                    skipped += 1
                else:
                    failed += 1

            tracker.complete_phase()

        elapsed = time.monotonic() - start
        batch_result = BatchResult(
            batch_id=batch_id,
            total_attempted=len(sorted_violations),
            successful=successful,
            failed=failed,
            skipped=skipped,
            results=results,
            execution_time=elapsed,
        )

        summary = tracker.get_summary()
        logger.info(
            "批量重构完成 [%s]: 成功 %d, 失败 %d, 跳过 %d, 耗时 %.2f 秒",
            batch_id,
            successful,
            failed,
            skipped,
            elapsed,
        )
        logger.info("进度跟踪汇总: %s", summary)
        return batch_result

    # ── 按层重构 ────────────────────────────────────────────

    def execute_api_refactoring(self, root: Path) -> BatchResult:
        """
        扫描并重构 API 层违规。

        Args:
            root: 项目根目录

        Returns:
            BatchResult
        """
        root = Path(root)
        logger.info("开始 API 层重构: %s", root)
        violations = self.api_scanner.scan_directory(root)
        if not violations:
            logger.info("API 层无违规，跳过重构")
            return BatchResult(batch_id=uuid.uuid4().hex[:8])
        return self.execute_refactoring_batch(violations)

    def execute_service_refactoring(self, root: Path) -> BatchResult:
        """
        扫描并重构 Service 层违规。

        Args:
            root: 项目根目录

        Returns:
            BatchResult
        """
        root = Path(root)
        logger.info("开始 Service 层重构: %s", root)
        violations = self.service_scanner.scan_directory(root)
        if not violations:
            logger.info("Service 层无违规，跳过重构")
            return BatchResult(batch_id=uuid.uuid4().hex[:8])
        return self.execute_refactoring_batch(violations)

    def execute_model_refactoring(self, root: Path) -> BatchResult:
        """
        扫描并重构 Model 层违规。

        注意：Model 层重构风险最高，当前仅生成重构建议，
        标记为需要人工审查。

        Args:
            root: 项目根目录

        Returns:
            BatchResult
        """
        root = Path(root)
        logger.info("开始 Model 层重构: %s", root)
        violations = self.model_scanner.scan_directory(root)
        if not violations:
            logger.info("Model 层无违规，跳过重构")
            return BatchResult(batch_id=uuid.uuid4().hex[:8])
        return self.execute_refactoring_batch(violations)

    # ── 语法验证 ────────────────────────────────────────────

    def validate_refactoring(self, file_path: Path) -> bool:
        """
        验证重构后的文件语法正确性（AST 解析检查）。

        Args:
            file_path: 要验证的 Python 文件路径

        Returns:
            True 表示语法正确，False 表示存在语法错误
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning("验证失败: 文件不存在 %s", file_path)
            return False

        try:
            source = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("验证失败: 无法读取文件 %s: %s", file_path, exc)
            return False

        try:
            ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            logger.warning(
                "验证失败: 语法错误 %s (行 %s): %s",
                file_path,
                exc.lineno,
                exc.msg,
            )
            return False

        logger.info("验证通过: %s", file_path)
        return True

    # ── 内部方法 ────────────────────────────────────────────

    def _refactor_single_violation(
        self,
        violation: Violation,
    ) -> RefactoringResult:
        """
        重构单个违规，包含回滚点创建和失败回滚。

        流程：
        1. 创建回滚点
        2. 读取源文件
        3. 根据违规类型分派到对应引擎
        4. 验证重构后的语法
        5. 失败时回滚，成功时提交

        Args:
            violation: 待重构的违规

        Returns:
            RefactoringResult
        """
        file_path = Path(violation.file_path)

        # 读取源文件
        source = self._read_source(file_path)
        if source is None:
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=f"无法读取文件: {violation.file_path}",
            )

        # 创建回滚点
        checkpoint_id: Optional[str] = None
        try:
            checkpoint_id = self.rollback_manager.create_checkpoint(
                violation.file_path,
                message=f"重构前: {violation.description}",
            )
        except (RuntimeError, OSError) as exc:
            logger.warning("创建回滚点失败: %s, 继续重构但无法回滚", exc)

        # 根据违规类型分派
        try:
            result = self._dispatch_refactoring(violation, source)
        except RefactoringError as exc:
            logger.error("重构异常: %s", exc)
            result = RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.error("重构未知异常: %s", exc)
            result = RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=f"未知错误: {exc}",
            )

        # 处理回滚/提交
        if checkpoint_id is not None:
            result.rollback_id = checkpoint_id
            if result.success:
                # 验证语法
                if file_path.exists() and not self.validate_refactoring(file_path):
                    logger.warning(
                        "重构后语法验证失败，回滚: %s",
                        violation.file_path,
                    )
                    try:
                        self.rollback_manager.rollback(checkpoint_id)
                    except (RuntimeError, ValueError) as exc:
                        logger.error("回滚失败: %s", exc)
                    result.success = False
                    result.error_message = "重构后语法验证失败，已回滚"
                else:
                    try:
                        self.rollback_manager.commit_changes(
                            checkpoint_id,
                            message=f"重构完成: {violation.description}",
                        )
                    except (RuntimeError, ValueError) as exc:
                        logger.warning("提交变更失败: %s", exc)
            else:
                # 重构失败，回滚
                try:
                    self.rollback_manager.rollback(checkpoint_id)
                except (RuntimeError, ValueError) as exc:
                    logger.error("回滚失败: %s", exc)

        return result

    def _dispatch_refactoring(
        self,
        violation: Violation,
        source: str,
    ) -> RefactoringResult:
        """
        根据违规类型分派到对应的重构引擎。

        Args:
            violation: 违规对象
            source: 源文件内容

        Returns:
            RefactoringResult
        """
        if isinstance(violation, ApiViolation):
            return self.api_engine.refactor_violation(violation, source)

        if isinstance(violation, ServiceViolation):
            return self.service_engine.refactor_violation(violation, source)

        if isinstance(violation, ModelViolation):
            # Model 层重构风险高，当前标记为需要人工审查
            return RefactoringResult(
                success=False,
                file_path=violation.file_path,
                error_message=(
                    f"跳过: Model 层违规 ({violation.model_name}.{violation.method_name}) "
                    f"需要人工审查 — {violation.business_logic_description}"
                ),
            )

        # 未知违规类型
        return RefactoringResult(
            success=False,
            file_path=violation.file_path,
            error_message=f"跳过: 不支持的违规类型 {violation.violation_type}",
        )

    @staticmethod
    def _read_source(file_path: Path) -> Optional[str]:
        """
        读取源文件内容。

        Args:
            file_path: 文件路径

        Returns:
            源代码文本，读取失败时返回 None
        """
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("无法读取文件 %s: %s", file_path, exc)
            return None
