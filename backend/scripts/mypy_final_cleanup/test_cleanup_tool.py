"""CleanupTool单元测试"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from .backup_manager import BackupManager
from .cleanup_tool import CleanupTool


class TestCleanupTool:
    """测试CleanupTool类"""

    def test_remove_simple_redundant_cast(self) -> None:
        """测试移除简单的冗余cast"""
        input_code = 'value = cast(str, "hello")'
        expected = 'value = "hello"'

        tool = CleanupTool()
        result = tool.remove_redundant_casts(input_code)

        assert result == expected

    def test_remove_multiple_redundant_casts(self) -> None:
        """测试移除多个冗余cast"""
        input_code = """
x = cast(int, 42)
y = cast(str, "world")
z = cast(bool, True)
"""
        expected = """
x = 42
y = "world"
z = True
"""

        tool = CleanupTool()
        result = tool.remove_redundant_casts(input_code)

        assert result == expected

    def test_remove_cast_with_variable(self) -> None:
        """测试移除变量的冗余cast"""
        input_code = "result = cast(List[str], my_list)"
        expected = "result = my_list"

        tool = CleanupTool()
        result = tool.remove_redundant_casts(input_code)

        assert result == expected

    def test_remove_unused_ignore_simple(self) -> None:
        """测试移除简单的type: ignore"""
        input_code = "x = some_function()  # type: ignore"
        expected = "x = some_function()"

        tool = CleanupTool()
        result = tool.remove_unused_ignores(input_code)

        assert result == expected

    def test_remove_unused_ignore_with_error_code(self) -> None:
        """测试移除带错误码的type: ignore"""
        input_code = "x = some_function()  # type: ignore[attr-defined]"
        expected = "x = some_function()"

        tool = CleanupTool()
        result = tool.remove_unused_ignores(input_code)

        assert result == expected

    def test_remove_unused_ignore_with_multiple_error_codes(self) -> None:
        """测试移除带多个错误码的type: ignore"""
        input_code = "x = some_function()  # type: ignore[attr-defined, union-attr]"
        expected = "x = some_function()"

        tool = CleanupTool()
        result = tool.remove_unused_ignores(input_code)

        assert result == expected

    def test_remove_multiple_unused_ignores(self) -> None:
        """测试移除多个type: ignore"""
        input_code = """
x = func1()  # type: ignore
y = func2()  # type: ignore[attr-defined]
z = func3()
"""
        expected = """
x = func1()
y = func2()
z = func3()
"""

        tool = CleanupTool()
        result = tool.remove_unused_ignores(input_code)

        assert result == expected

    def test_preserve_code_without_issues(self) -> None:
        """测试保留没有问题的代码"""
        input_code = """
def foo(x: int) -> str:
    return str(x)

result = foo(42)
"""

        tool = CleanupTool()
        result = tool.remove_redundant_casts(input_code)
        result = tool.remove_unused_ignores(result)

        assert result == input_code

    def test_combined_cleanup(self) -> None:
        """测试同时清理cast和ignore"""
        input_code = """
x = cast(str, "hello")  # type: ignore
y = cast(int, 42)
z = some_function()  # type: ignore[attr-defined]
"""
        expected = """
x = "hello"
y = 42
z = some_function()
"""

        tool = CleanupTool()
        result = tool.remove_redundant_casts(input_code)
        result = tool.remove_unused_ignores(result)

        assert result == expected

    def test_count_cleanups(self) -> None:
        """测试清理计数"""
        original = """
x = cast(str, "hello")  # type: ignore
y = cast(int, 42)
z = some_function()  # type: ignore[attr-defined]
"""
        cleaned = """
x = "hello"
y = 42
z = some_function()
"""

        tool = CleanupTool()
        count = tool._count_cleanups(original, cleaned)

        # 2个cast + 2个ignore = 4
        assert count == 4

    def test_fix_file_integration(self) -> None:
        """集成测试：修复实际文件"""
        # 创建临时目录和文件
        with tempfile.TemporaryDirectory() as tmpdir:
            backend_path = Path(tmpdir)
            test_file = backend_path / "test.py"

            # 写入测试内容
            test_content = """
x = cast(str, "hello")  # type: ignore
y = cast(int, 42)
z = some_function()  # type: ignore[attr-defined]
"""
            test_file.write_text(test_content, encoding="utf-8")

            # 创建备份管理器和清理工具
            backup_manager = BackupManager(backend_path=backend_path)
            tool = CleanupTool(backup_manager=backup_manager)

            # 执行清理
            count = tool.fix_file("test.py")

            # 验证结果
            assert count == 4

            # 验证文件内容
            result_content = test_file.read_text(encoding="utf-8")
            expected = """
x = "hello"
y = 42
z = some_function()
"""
            assert result_content == expected
