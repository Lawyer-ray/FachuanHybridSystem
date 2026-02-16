"""TypeArgsFixer单元测试"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from .backup_manager import BackupManager
from .type_args_fixer import TypeArgsFixer


class TestTypeArgsFixer:
    """测试TypeArgsFixer类"""

    @pytest.fixture
    def temp_backend(self, tmp_path: Path) -> Path:
        """创建临时backend目录"""
        backend_path = tmp_path / "backend"
        backend_path.mkdir()
        return backend_path

    @pytest.fixture
    def fixer(self, temp_backend: Path) -> TypeArgsFixer:
        """创建TypeArgsFixer实例"""
        backup_manager = BackupManager(backend_path=temp_backend)
        return TypeArgsFixer(backup_manager=backup_manager)

    def test_fix_list_return_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复List返回类型"""
        input_code = "def foo() -> List:\n    return []"
        expected = "def foo() -> List[Any]:\n    return []"

        result = fixer.fix_list_types(input_code)

        assert result == expected
        assert "List" in fixer.required_imports
        assert "Any" in fixer.required_imports

    def test_fix_list_variable_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复List变量类型"""
        input_code = "items: List = []"
        expected = "items: List[Any] = []"

        result = fixer.fix_list_types(input_code)

        assert result == expected

    def test_fix_list_in_union(self, fixer: TypeArgsFixer) -> None:
        """测试修复Union中的List"""
        input_code = "def foo() -> List | None:\n    pass"
        expected = "def foo() -> List[Any] | None:\n    pass"

        result = fixer.fix_list_types(input_code)

        assert result == expected

    def test_fix_lowercase_list(self, fixer: TypeArgsFixer) -> None:
        """测试修复小写list"""
        input_code = "def foo() -> list:\n    return []"
        expected = "def foo() -> List[Any]:\n    return []"

        result = fixer.fix_list_types(input_code)

        assert result == expected

    def test_fix_dict_return_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复Dict返回类型"""
        input_code = "def foo() -> Dict:\n    return {}"
        expected = "def foo() -> Dict[str, Any]:\n    return {}"

        result = fixer.fix_dict_types(input_code)

        assert result == expected
        assert "Dict" in fixer.required_imports
        assert "Any" in fixer.required_imports

    def test_fix_dict_variable_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复Dict变量类型"""
        input_code = "config: Dict = {}"
        expected = "config: Dict[str, Any] = {}"

        result = fixer.fix_dict_types(input_code)

        assert result == expected

    def test_fix_lowercase_dict(self, fixer: TypeArgsFixer) -> None:
        """测试修复小写dict"""
        input_code = "def foo() -> dict:\n    return {}"
        expected = "def foo() -> Dict[str, Any]:\n    return {}"

        result = fixer.fix_dict_types(input_code)

        assert result == expected

    def test_fix_set_return_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复Set返回类型"""
        input_code = "def foo() -> Set:\n    return set()"
        expected = "def foo() -> Set[Any]:\n    return set()"

        result = fixer.fix_set_types(input_code)

        assert result == expected
        assert "Set" in fixer.required_imports
        assert "Any" in fixer.required_imports

    def test_fix_set_variable_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复Set变量类型"""
        input_code = "items: Set = set()"
        expected = "items: Set[Any] = set()"

        result = fixer.fix_set_types(input_code)

        assert result == expected

    def test_fix_tuple_return_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复Tuple返回类型"""
        input_code = "def foo() -> Tuple:\n    return ()"
        expected = "def foo() -> Tuple[Any, ...]:\n    return ()"

        result = fixer.fix_tuple_types(input_code)

        assert result == expected
        assert "Tuple" in fixer.required_imports
        assert "Any" in fixer.required_imports

    def test_fix_tuple_variable_type(self, fixer: TypeArgsFixer) -> None:
        """测试修复Tuple变量类型"""
        input_code = "items: Tuple = ()"
        expected = "items: Tuple[Any, ...] = ()"

        result = fixer.fix_tuple_types(input_code)

        assert result == expected

    def test_add_missing_imports_no_existing(self, fixer: TypeArgsFixer) -> None:
        """测试添加导入（无现有导入）"""
        content = "def foo() -> List[Any]:\n    return []"
        fixer.required_imports = {"List", "Any"}

        result = fixer._add_missing_imports(content)

        assert "from typing import" in result
        assert "List" in result
        assert "Any" in result

    def test_add_missing_imports_with_existing(self, fixer: TypeArgsFixer) -> None:
        """测试添加导入（有现有导入）"""
        content = "from typing import Optional\n\ndef foo() -> List[Any]:\n    return []"
        fixer.required_imports = {"List", "Any"}

        result = fixer._add_missing_imports(content)

        assert "from typing import" in result
        assert "List" in result
        assert "Any" in result
        assert "Optional" in result

    def test_add_missing_imports_already_exists(self, fixer: TypeArgsFixer) -> None:
        """测试添加导入（导入已存在）"""
        content = "from typing import List, Any\n\ndef foo() -> List[Any]:\n    return []"
        fixer.required_imports = {"List", "Any"}

        result = fixer._add_missing_imports(content)

        # 内容应该不变
        assert result == content

    def test_count_fixes(self, fixer: TypeArgsFixer) -> None:
        """测试统计修复数量"""
        original = "def foo() -> List:\n    return []"
        fixed = "def foo() -> List[Any]:\n    return []"

        count = fixer._count_fixes(original, fixed)

        assert count == 1

    def test_count_multiple_fixes(self, fixer: TypeArgsFixer) -> None:
        """测试统计多个修复"""
        original = "def foo() -> List:\n    items: Dict = {}\n    return []"
        fixed = "def foo() -> List[Any]:\n    items: Dict[str, Any] = {}\n    return []"

        count = fixer._count_fixes(original, fixed)

        assert count == 2

    def test_fix_file_integration(self, fixer: TypeArgsFixer, temp_backend: Path) -> None:
        """集成测试：修复文件"""
        # 创建测试文件
        test_file = temp_backend / "test.py"
        test_file.write_text("def foo() -> List:\n" "    items: Dict = {}\n" "    return []", encoding="utf-8")

        # 修复文件
        fixes_count = fixer.fix_file("test.py")

        # 验证修复
        assert fixes_count == 2

        # 验证文件内容
        content = test_file.read_text(encoding="utf-8")
        assert "List[Any]" in content
        assert "Dict[str, Any]" in content
        assert "from typing import" in content

    def test_fix_file_with_backup(self, fixer: TypeArgsFixer, temp_backend: Path) -> None:
        """测试修复文件时创建备份"""
        # 创建测试文件
        test_file = temp_backend / "test.py"
        original_content = "def foo() -> List:\n    return []"
        test_file.write_text(original_content, encoding="utf-8")

        # 修复文件
        fixer.fix_file("test.py")

        # 验证备份存在
        backups = fixer.backup_manager.list_backups()
        assert "test.py" in backups

    def test_fix_file_preserves_existing_types(self, fixer: TypeArgsFixer, temp_backend: Path) -> None:
        """测试修复文件时保留已有的类型参数"""
        # 创建测试文件
        test_file = temp_backend / "test.py"
        test_file.write_text("def foo() -> List[str]:\n" "    items: List = []\n" "    return items", encoding="utf-8")

        # 修复文件
        fixer.fix_file("test.py")

        # 验证文件内容
        content = test_file.read_text(encoding="utf-8")
        assert "List[str]" in content  # 保留原有的类型参数
        assert content.count("List[Any]") == 1  # 只修复了一个
