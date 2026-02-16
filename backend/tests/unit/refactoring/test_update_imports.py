#!/usr/bin/env python3
"""
导入路径更新脚本的测试

测试 update_imports.py 的核心功能
"""

import re
import sys
from apps.core.path import Path
from typing import List, Tuple

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.refactoring.update_imports import ImportPathUpdater, ImportUpdate


def test_import_pattern_matching():
    """测试导入模式匹配"""
    print("测试导入模式匹配...")
    
    test_cases = [
        # (输入行, 预期是否匹配, 预期新行)
        (
            "from apps.tests.factories import CaseFactory",
            True,
            "from tests.factories import CaseFactory"
        ),
        (
            "from apps.tests.factories.case_factories import CaseFactory",
            True,
            "from tests.factories.case_factories import CaseFactory"
        ),
        (
            "import apps.tests.factories",
            True,
            "import tests.factories"
        ),
        (
            "from apps.cases.tests import TestCase",
            True,
            "from tests.unit.cases import TestCase"
        ),
        (
            "from apps.tests.mocks import MockService",
            True,
            "from tests.mocks import MockService"
        ),
        (
            "from apps.core.exceptions import ValidationError",
            False,
            None  # 不应该匹配
        ),
    ]
    
    # 获取导入模式
    updater = ImportPathUpdater(project_root, dry_run=True)
    patterns = updater.import_patterns
    
    passed = 0
    failed = 0
    
    for input_line, should_match, expected_output in test_cases:
        matched = False
        output_line = input_line
        
        for pattern_name, old_pattern, new_pattern in patterns:
            if re.search(old_pattern, input_line):
                matched = True
                output_line = re.sub(old_pattern, new_pattern, input_line)
                break
        
        if matched == should_match:
            if should_match and expected_output:
                if output_line == expected_output:
                    print(f"✓ PASS: {input_line}")
                    passed += 1
                else:
                    print(f"✗ FAIL: {input_line}")
                    print(f"  预期: {expected_output}")
                    print(f"  实际: {output_line}")
                    failed += 1
            else:
                print(f"✓ PASS: {input_line} (不匹配)")
                passed += 1
        else:
            print(f"✗ FAIL: {input_line}")
            print(f"  预期匹配: {should_match}, 实际匹配: {matched}")
            failed += 1
    
    print(f"\n测试结果: {passed} 通过, {failed} 失败")
    return failed == 0


def test_file_scanning():
    """测试文件扫描功能"""
    print("\n测试文件扫描功能...")
    
    updater = ImportPathUpdater(project_root, dry_run=True)
    python_files = updater.scan_python_files()
    
    print(f"找到 {len(python_files)} 个 Python 文件")
    
    # 验证扫描结果
    assert len(python_files) > 0, "应该找到至少一个 Python 文件"
    
    # 验证排除了不需要的目录
    for file_path in python_files:
        assert '__pycache__' not in str(file_path), "不应该包含 __pycache__ 文件"
        assert 'migrations' not in str(file_path), "不应该包含 migrations 文件"
    
    print("✓ 文件扫描测试通过")
    return True


def test_import_analysis():
    """测试导入分析功能"""
    print("\n测试导入分析功能...")
    
    # 创建临时测试文件
    test_file = project_root / "test_temp_imports.py"
    test_content = """
# 测试文件
from apps.tests.factories import CaseFactory
from apps.tests.mocks import MockService
from apps.core.exceptions import ValidationError  # 不应该匹配
import apps.tests.factories

def test_function():
    pass
"""
    
    try:
        test_file.write_text(test_content, encoding='utf-8')
        
        updater = ImportPathUpdater(project_root, dry_run=True)
        updates = updater.analyze_file(test_file)
        
        print(f"找到 {len(updates)} 处需要更新的导入")
        
        # 验证结果
        assert len(updates) == 3, f"应该找到 3 处更新，实际找到 {len(updates)} 处"
        
        # 验证更新内容
        expected_patterns = ['factories_imports', 'mocks_imports', 'factories_imports_as']
        actual_patterns = [u.pattern_name for u in updates]
        
        for pattern in expected_patterns:
            assert pattern in actual_patterns, f"应该包含模式 {pattern}"
        
        print("✓ 导入分析测试通过")
        return True
    
    finally:
        # 清理临时文件
        if test_file.exists():
            test_file.unlink()


def test_update_application():
    """测试更新应用功能"""
    print("\n测试更新应用功能...")
    
    # 创建临时测试文件
    test_file = project_root / "test_temp_update.py"
    original_content = """
from apps.tests.factories import CaseFactory
from apps.tests.mocks import MockService
"""
    
    expected_content = """
from tests.factories import CaseFactory
from tests.mocks import MockService
"""
    
    try:
        test_file.write_text(original_content, encoding='utf-8')
        
        # 执行更新（非 dry-run）
        updater = ImportPathUpdater(project_root, dry_run=False)
        updater.scan_all_files()
        updater.apply_updates()
        
        # 验证更新结果
        updated_content = test_file.read_text(encoding='utf-8')
        
        assert updated_content == expected_content, "更新后的内容不正确"
        
        print("✓ 更新应用测试通过")
        return True
    
    finally:
        # 清理临时文件
        if test_file.exists():
            test_file.unlink()


def main():
    """运行所有测试"""
    print("=" * 80)
    print("导入路径更新脚本测试")
    print("=" * 80)
    
    tests = [
        ("导入模式匹配", test_import_pattern_matching),
        ("文件扫描", test_file_scanning),
        ("导入分析", test_import_analysis),
        # ("更新应用", test_update_application),  # 暂时注释，避免修改实际文件
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ 测试失败: {test_name}")
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"测试总结: {passed} 通过, {failed} 失败")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
