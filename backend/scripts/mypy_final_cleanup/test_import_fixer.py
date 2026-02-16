"""ImportFixer单元测试"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .import_fixer import ImportFixer
from .backup_manager import BackupManager


def test_detect_missing_imports_basic() -> None:
    """测试基本的缺失导入检测"""
    content = """
def foo(x: Any) -> Optional[str]:
    return None
"""
    
    fixer = ImportFixer()
    missing = fixer.detect_missing_imports(content)
    
    assert 'Any' in missing
    assert 'Optional' in missing


def test_detect_missing_imports_with_existing() -> None:
    """测试已有导入时的检测"""
    content = """
from typing import Any

def foo(x: Any) -> Optional[str]:
    return None
"""
    
    fixer = ImportFixer()
    missing = fixer.detect_missing_imports(content)
    
    assert 'Any' not in missing
    assert 'Optional' in missing


def test_add_imports_new() -> None:
    """测试添加新的导入"""
    content = """
def foo(x: Any) -> None:
    pass
"""
    
    fixer = ImportFixer()
    result = fixer.add_imports(content, {'Any'})
    
    assert 'from typing import Any' in result


def test_add_imports_update_existing() -> None:
    """测试更新现有导入"""
    content = """from typing import Any

def foo(x: Any) -> Optional[str]:
    return None
"""
    
    fixer = ImportFixer()
    result = fixer.add_imports(content, {'Optional'})
    
    assert 'from typing import Any, Optional' in result


def test_fix_file_integration() -> None:
    """集成测试：修复文件中的缺失导入"""
    # 创建临时目录和文件
    with tempfile.TemporaryDirectory() as tmpdir:
        backend_path = Path(tmpdir)
        test_file = backend_path / "test.py"
        
        # 写入测试内容
        content = """
def foo(x: Any) -> Optional[str]:
    return None
"""
        test_file.write_text(content, encoding="utf-8")
        
        # 创建备份管理器和修复器
        backup_manager = BackupManager(backend_path)
        fixer = ImportFixer(backup_manager)
        
        # 修复文件
        fixes_count = fixer.fix_file("test.py")
        
        # 验证修复结果
        assert fixes_count > 0
        
        # 读取修复后的内容
        fixed_content = test_file.read_text(encoding="utf-8")
        assert 'from typing import' in fixed_content
        assert 'Any' in fixed_content
        assert 'Optional' in fixed_content


def test_import_insert_position_after_future() -> None:
    """测试在__future__导入之后插入"""
    content = """from __future__ import annotations

def foo() -> None:
    pass
"""
    
    fixer = ImportFixer()
    result = fixer.add_imports(content, {'Any'})
    
    lines = result.split('\n')
    assert lines[0].startswith('from __future__')
    assert 'from typing import Any' in lines[1]


def test_detect_used_types_in_annotations() -> None:
    """测试检测类型注解中使用的类型"""
    content = """
def foo(x: List[str], y: Dict[str, Any]) -> Optional[int]:
    z: Set[str] = set()
    return None
"""
    
    fixer = ImportFixer()
    used = fixer._detect_used_types(content)
    
    assert 'List' in used
    assert 'Dict' in used
    assert 'Any' in used
    assert 'Optional' in used
    assert 'Set' in used


if __name__ == '__main__':
    # 运行测试
    test_detect_missing_imports_basic()
    test_detect_missing_imports_with_existing()
    test_add_imports_new()
    test_add_imports_update_existing()
    test_fix_file_integration()
    test_import_insert_position_after_future()
    test_detect_used_types_in_annotations()
    
    print("所有测试通过！")
