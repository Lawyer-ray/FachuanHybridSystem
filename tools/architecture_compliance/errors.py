"""
架构合规性工具的异常定义
"""

from __future__ import annotations


class RefactoringError(Exception):
    """重构错误基类"""

    def __init__(self, message: str, file_path: str = "") -> None:
        self.file_path = file_path
        super().__init__(message)


class TestFailureError(RefactoringError):
    """重构后测试失败"""

    def __init__(self, test_name: str, error_message: str, file_path: str = "") -> None:
        self.test_name = test_name
        self.error_message = error_message
        super().__init__(
            f"Test '{test_name}' failed: {error_message}",
            file_path=file_path,
        )


class RefactoringSyntaxError(RefactoringError):
    """重构产生的语法错误"""

    def __init__(self, message: str, file_path: str = "", line_number: int = 0) -> None:
        self.line_number = line_number
        super().__init__(message, file_path=file_path)


class CircularDependencyError(RefactoringError):
    """循环依赖错误"""

    def __init__(self, modules: list[str], file_path: str = "") -> None:
        self.modules = modules
        cycle = " -> ".join(modules)
        super().__init__(
            f"Circular dependency detected: {cycle}",
            file_path=file_path,
        )
