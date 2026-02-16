"""
进度跟踪和报告模块

提供重构过程的实时进度跟踪、阶段性报告生成和详细日志记录。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from .logging_config import get_logger
from .models import RefactoringResult, Violation

logger = get_logger("progress_tracker")


@dataclass
class PhaseReport:
    """阶段报告"""

    phase_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    violations_processed: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def duration_seconds(self) -> float:
        """阶段耗时（秒）"""
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return {
            "phase_name": self.phase_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": round(self.duration_seconds, 2),
            "violations_processed": self.violations_processed,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
        }


@dataclass
class ProgressReport:
    """进度报告"""

    total: int
    processed: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    current_phase: Optional[str] = None
    phases: list[PhaseReport] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        """完成百分比"""
        if self.total == 0:
            return 100.0
        return round((self.processed / self.total) * 100, 1)

    @property
    def remaining(self) -> int:
        """剩余未处理数量"""
        return max(0, self.total - self.processed)

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return {
            "total": self.total,
            "processed": self.processed,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
            "percentage": self.percentage,
            "remaining": self.remaining,
            "current_phase": self.current_phase,
            "phases": [p.to_dict() for p in self.phases],
        }


# 进度回调类型
ProgressCallback = Callable[[ProgressReport], None]


class ProgressTracker:
    """
    重构进度跟踪器

    跟踪重构进度（已处理/总数/成功/失败/跳过），
    生成阶段性报告，记录详细日志，支持进度回调。
    """

    def __init__(
        self,
        total_violations: int,
        callback: Optional[ProgressCallback] = None,
    ) -> None:
        self._total = total_violations
        self._processed = 0
        self._successful = 0
        self._failed = 0
        self._skipped = 0
        self._callback = callback
        self._phases: list[PhaseReport] = []
        self._current_phase: Optional[PhaseReport] = None
        self._start_time = time.monotonic()
        logger.info("进度跟踪器已初始化: 共 %d 个违规待处理", total_violations)

    def start_phase(self, phase_name: str) -> None:
        """开始新阶段。"""
        if self._current_phase is not None:
            self.complete_phase()
        self._current_phase = PhaseReport(
            phase_name=phase_name,
            started_at=datetime.now(),
        )
        logger.info("开始阶段: %s", phase_name)

    def complete_phase(self) -> Optional[PhaseReport]:
        """完成当前阶段。"""
        if self._current_phase is None:
            return None
        phase = self._current_phase
        phase.completed_at = datetime.now()
        self._phases.append(phase)
        self._current_phase = None
        logger.info(
            "阶段完成: %s — 处理 %d, 成功 %d, 失败 %d, 跳过 %d, 耗时 %.2f 秒",
            phase.phase_name,
            phase.violations_processed,
            phase.successful,
            phase.failed,
            phase.skipped,
            phase.duration_seconds,
        )
        return phase

    def record_result(self, violation: Violation, result: RefactoringResult) -> None:
        """记录单个违规的处理结果。"""
        self._processed += 1
        is_skipped = not result.success and result.error_message is not None and "跳过" in result.error_message
        if result.success:
            self._successful += 1
            status_label = "成功"
        elif is_skipped:
            self._skipped += 1
            status_label = "跳过"
        else:
            self._failed += 1
            status_label = "失败"

        if self._current_phase is not None:
            self._current_phase.violations_processed += 1
            if result.success:
                self._current_phase.successful += 1
            elif is_skipped:
                self._current_phase.skipped += 1
            else:
                self._current_phase.failed += 1

        logger.info(
            "[%d/%d] %s — %s:%d (%s) %s",
            self._processed,
            self._total,
            status_label,
            violation.file_path,
            violation.line_number,
            violation.violation_type,
            result.error_message or "",
        )
        if self._callback is not None:
            self._callback(self.get_progress())

    def get_progress(self) -> ProgressReport:
        """获取当前进度报告。"""
        return ProgressReport(
            total=self._total,
            processed=self._processed,
            successful=self._successful,
            failed=self._failed,
            skipped=self._skipped,
            current_phase=(self._current_phase.phase_name if self._current_phase else None),
            phases=list(self._phases),
        )

    def get_summary(self) -> dict[str, object]:
        """获取最终汇总。"""
        elapsed = time.monotonic() - self._start_time
        progress = self.get_progress()
        return {
            "total_violations": self._total,
            "processed": self._processed,
            "successful": self._successful,
            "failed": self._failed,
            "skipped": self._skipped,
            "completion_percentage": progress.percentage,
            "total_elapsed_seconds": round(elapsed, 2),
            "phases": [p.to_dict() for p in self._phases],
        }
