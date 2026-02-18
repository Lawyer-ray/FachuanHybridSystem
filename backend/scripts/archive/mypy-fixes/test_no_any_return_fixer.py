"""测试NoAnyReturnFixer"""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

from mypy_tools.error_analyzer import ErrorRecord
from mypy_tools.no_any_return_fixer import NoAnyReturnFixer


def test_can_fix() -> None:
    """测试can_fix方法"""
    fixer = NoAnyReturnFixer()

    # 可以修复的错误
    error1 = ErrorRecord(
        file_path="test.py",
        line=10,
        column=0,
        error_code="no-any-return",
        message="Returning Any from function",
        severity="medium",
        fixable=False,
        fix_pattern=None,
    )
    assert fixer.can_fix(error1) is True

    # 不能修复的错误（包含Protocol）
    error2 = ErrorRecord(
        file_path="test.py",
        line=20,
        column=0,
        error_code="no-any-return",
        message="Returning Any from function with Protocol",
        severity="medium",
        fixable=False,
        fix_pattern=None,
    )
    assert fixer.can_fix(error2) is False

    # 错误类型不匹配
    error3 = ErrorRecord(
        file_path="test.py",
        line=30,
        column=0,
        error_code="attr-defined",
        message="Attribute not defined",
        severity="critical",
        fixable=False,
        fix_pattern=None,
    )
    assert fixer.can_fix(error3) is False

    print("✓ test_can_fix 通过")


def test_infer_simple_return_types() -> None:
    """测试简单返回类型推断"""
    from mypy_tools.no_any_return_fixer import ReturnTypeReplacer

    # 测试代码
    code = """
def get_number() -> Any:
    return 42

def get_string() -> Any:
    return "hello"

def get_bool() -> Any:
    return True

def get_none() -> Any:
    return None
"""

    tree = ast.parse(code)

    # 创建错误记录
    functions_to_fix = {
        2: ErrorRecord("test.py", 2, 0, "no-any-return", "", "medium", False, None),
        5: ErrorRecord("test.py", 5, 0, "no-any-return", "", "medium", False, None),
        8: ErrorRecord("test.py", 8, 0, "no-any-return", "", "medium", False, None),
        11: ErrorRecord("test.py", 11, 0, "no-any-return", "", "medium", False, None),
    }

    transformer = ReturnTypeReplacer(functions_to_fix)
    modified_tree = transformer.visit(tree)

    assert transformer.modified is True
    assert transformer.functions_fixed == 4

    # 检查推断的类型
    func_defs = [node for node in ast.walk(modified_tree) if isinstance(node, ast.FunctionDef)]

    # get_number应该返回int
    assert func_defs[0].name == "get_number"
    assert isinstance(func_defs[0].returns, ast.Name)
    assert func_defs[0].returns.id == "int"

    # get_string应该返回str
    assert func_defs[1].name == "get_string"
    assert isinstance(func_defs[1].returns, ast.Name)
    assert func_defs[1].returns.id == "str"

    # get_bool应该返回bool
    assert func_defs[2].name == "get_bool"
    assert isinstance(func_defs[2].returns, ast.Name)
    assert func_defs[2].returns.id == "bool"

    # get_none应该返回None
    assert func_defs[3].name == "get_none"
    assert isinstance(func_defs[3].returns, ast.Constant)
    assert func_defs[3].returns.value is None

    print("✓ test_infer_simple_return_types 通过")


def test_infer_container_types() -> None:
    """测试容器类型推断"""
    from mypy_tools.no_any_return_fixer import ReturnTypeReplacer

    code = """
def get_list() -> Any:
    return [1, 2, 3]

def get_dict() -> Any:
    return {"key": "value"}

def get_set() -> Any:
    return {1, 2, 3}
"""

    tree = ast.parse(code)

    functions_to_fix = {
        2: ErrorRecord("test.py", 2, 0, "no-any-return", "", "medium", False, None),
        5: ErrorRecord("test.py", 5, 0, "no-any-return", "", "medium", False, None),
        8: ErrorRecord("test.py", 8, 0, "no-any-return", "", "medium", False, None),
    }

    transformer = ReturnTypeReplacer(functions_to_fix)
    modified_tree = transformer.visit(tree)

    assert transformer.modified is True
    assert transformer.functions_fixed == 3

    func_defs = [node for node in ast.walk(modified_tree) if isinstance(node, ast.FunctionDef)]

    # get_list应该返回list[int]
    assert func_defs[0].name == "get_list"
    assert isinstance(func_defs[0].returns, ast.Subscript)

    # get_dict应该返回dict[str, str]
    assert func_defs[1].name == "get_dict"
    assert isinstance(func_defs[1].returns, ast.Subscript)

    # get_set应该返回set[int]
    assert func_defs[2].name == "get_set"
    assert isinstance(func_defs[2].returns, ast.Subscript)

    print("✓ test_infer_container_types 通过")


def test_infer_union_types() -> None:
    """测试Union类型推断"""
    from mypy_tools.no_any_return_fixer import ReturnTypeReplacer

    code = """
def get_value(flag: bool) -> Any:
    if flag:
        return 42
    else:
        return "hello"

def get_optional(flag: bool) -> Any:
    if flag:
        return 42
    return None
"""

    tree = ast.parse(code)

    functions_to_fix = {
        2: ErrorRecord("test.py", 2, 0, "no-any-return", "", "medium", False, None),
        8: ErrorRecord("test.py", 8, 0, "no-any-return", "", "medium", False, None),
    }

    transformer = ReturnTypeReplacer(functions_to_fix)
    modified_tree = transformer.visit(tree)

    assert transformer.modified is True
    assert transformer.functions_fixed == 2

    func_defs = [node for node in ast.walk(modified_tree) if isinstance(node, ast.FunctionDef)]

    # get_value应该返回int | str
    assert func_defs[0].name == "get_value"
    assert isinstance(func_defs[0].returns, ast.BinOp)

    # get_optional应该返回int | None
    assert func_defs[1].name == "get_optional"
    assert isinstance(func_defs[1].returns, ast.BinOp)

    print("✓ test_infer_union_types 通过")


def test_fix_file() -> None:
    """测试fix_file方法"""
    # 创建临时目录和文件
    with tempfile.TemporaryDirectory() as tmpdir:
        backend_path = Path(tmpdir)
        test_file = backend_path / "test.py"

        # 写入测试代码
        test_code = """from typing import Any

def get_number() -> Any:
    return 42

def get_string() -> Any:
    return "hello"
"""
        test_file.write_text(test_code)

        # 创建fixer
        fixer = NoAnyReturnFixer(backend_path=backend_path)

        # 创建错误记录
        errors = [
            ErrorRecord("test.py", 3, 0, "no-any-return", "Returning Any", "medium", False, None),
            ErrorRecord("test.py", 6, 0, "no-any-return", "Returning Any", "medium", False, None),
        ]

        # 修复文件
        result = fixer.fix_file("test.py", errors)

        assert result.success is True
        assert result.errors_fixed == 2
        assert result.errors_remaining == 0

        # 检查修复后的代码
        fixed_code = test_file.read_text()
        assert "def get_number() -> int:" in fixed_code
        assert "def get_string() -> str:" in fixed_code

        print("✓ test_fix_file 通过")


if __name__ == "__main__":
    test_can_fix()
    test_infer_simple_return_types()
    test_infer_container_types()
    test_infer_union_types()
    test_fix_file()

    print("\n所有测试通过！✓")
