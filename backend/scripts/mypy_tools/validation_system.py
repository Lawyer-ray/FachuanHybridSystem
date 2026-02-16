"""ValidationSystem - 验证修复效果"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .error_analyzer import ErrorRecord

logger = logging.getLogger(__name__)


@dataclass
class FixResult:
    """修复结果数据类"""

    file_path: str
    errors_fixed: int
    errors_remaining: int
    fix_pattern: str
    success: bool
    error_message: str | None


@dataclass
class ValidationReport:
    """验证报告数据类"""

    total_errors_before: int
    total_errors_after: int
    errors_fixed: int
    new_errors: int
    tests_passed: bool
    regression_detected: bool


class ValidationSystem:
    """验证修复效果"""

    def __init__(self, backend_path: Path | None = None) -> None:
        """
        初始化ValidationSystem

        Args:
            backend_path: backend目录路径，默认为当前文件的父目录的父目录
        """
        if backend_path is None:
            # 默认路径：scripts/mypy_tools -> scripts -> backend
            self.backend_path = Path(__file__).parent.parent.parent
        else:
            self.backend_path = backend_path

        logger.info(f"ValidationSystem初始化，backend路径: {self.backend_path}")

    def run_mypy(self) -> tuple[int, str]:
        """
        运行mypy检查，返回错误数和输出

        Returns:
            (错误数量, mypy输出文本)
        """
        logger.info("开始运行mypy检查...")

        try:
            result = subprocess.run(
                ["mypy", "apps/", "--strict"],
                capture_output=True,
                text=True,
                cwd=self.backend_path,
                timeout=300,  # 5分钟超时
            )

            output = result.stdout + result.stderr

            # 从输出中提取错误数量
            error_count = self._count_errors_in_output(output)

            logger.info(f"mypy检查完成，发现 {error_count} 个错误")
            return error_count, output

        except subprocess.TimeoutExpired:
            logger.error("mypy检查超时")
            return -1, "mypy检查超时"
        except FileNotFoundError:
            logger.error("未找到mypy命令，请确保已安装mypy")
            return -1, "未找到mypy命令"
        except Exception as e:
            logger.error(f"运行mypy时发生错误: {e}")
            return -1, str(e)

    def run_tests(self, test_path: str = "tests/") -> bool:
        """
        运行单元测试

        Args:
            test_path: 测试目录路径

        Returns:
            测试是否全部通过
        """
        logger.info(f"开始运行测试: {test_path}")

        try:
            result = subprocess.run(
                ["pytest", test_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=self.backend_path,
                timeout=600,  # 10分钟超时
            )

            passed = result.returncode == 0

            if passed:
                logger.info("所有测试通过")
            else:
                logger.warning(f"测试失败，返回码: {result.returncode}")
                logger.warning(f"测试输出: {result.stdout[-500:]}")  # 只记录最后500字符

            return passed

        except subprocess.TimeoutExpired:
            logger.error("测试运行超时")
            return False
        except FileNotFoundError:
            logger.error("未找到pytest命令，请确保已安装pytest")
            return False
        except Exception as e:
            logger.error(f"运行测试时发生错误: {e}")
            return False

    def compare_errors(self, before: list[ErrorRecord], after: list[ErrorRecord]) -> ValidationReport:
        """
        对比修复前后的错误

        Args:
            before: 修复前的错误列表
            after: 修复后的错误列表

        Returns:
            验证报告
        """
        total_before = len(before)
        total_after = len(after)
        errors_fixed = max(0, total_before - total_after)

        # 检测新错误
        before_set = {(e.file_path, e.line, e.error_code) for e in before}
        after_set = {(e.file_path, e.line, e.error_code) for e in after}
        new_error_set = after_set - before_set
        new_errors = len(new_error_set)

        regression_detected = new_errors > 0

        if regression_detected:
            logger.warning(f"检测到 {new_errors} 个新错误（回归）")

        report = ValidationReport(
            total_errors_before=total_before,
            total_errors_after=total_after,
            errors_fixed=errors_fixed,
            new_errors=new_errors,
            tests_passed=False,  # 需要单独调用run_tests设置
            regression_detected=regression_detected,
        )

        logger.info(
            f"对比完成: 修复前 {total_before} 个错误，"
            f"修复后 {total_after} 个错误，"
            f"修复了 {errors_fixed} 个，"
            f"新增 {new_errors} 个"
        )

        return report

    def detect_regression(self, before: list[ErrorRecord], after: list[ErrorRecord]) -> list[ErrorRecord]:
        """
        检测新引入的错误

        Args:
            before: 修复前的错误列表
            after: 修复后的错误列表

        Returns:
            新引入的错误列表
        """
        # 使用(文件路径, 行号, 错误代码)作为唯一标识
        before_set = {(e.file_path, e.line, e.error_code) for e in before}

        new_errors = [e for e in after if (e.file_path, e.line, e.error_code) not in before_set]

        if new_errors:
            logger.warning(f"检测到 {len(new_errors)} 个新错误")
            for error in new_errors[:5]:  # 只记录前5个
                logger.warning(f"  新错误: {error.file_path}:{error.line} " f"[{error.error_code}] {error.message}")
        else:
            logger.info("未检测到新错误")

        return new_errors

    def _count_errors_in_output(self, output: str) -> int:
        """从mypy输出中统计错误数量"""
        # 统计包含"error:"的行数
        error_lines = [line for line in output.split("\n") if "error:" in line.lower()]
        return len(error_lines)
