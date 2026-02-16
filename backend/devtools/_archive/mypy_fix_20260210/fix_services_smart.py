#!/usr/bin/env python3
"""
智能修复 services 层类型错误
重点修复可以自动推断的类型
"""

import re
from pathlib import Path
from typing import List, Tuple


def fix_property_return_types(content: str) -> Tuple[str, List[str]]:
    """修复 @property 方法的返回类型"""
    lines = content.split("\n")
    changes = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # 查找 @property 装饰器
        if line.strip() == "@property":
            # 检查下一行的函数定义
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if "def " in next_line and "-> " not in next_line and ":" in next_line:
                    # 查找 return 语句
                    func_indent = len(next_line) - len(next_line.lstrip())
                    for j in range(i + 2, min(i + 20, len(lines))):
                        check_line = lines[j]
                        if not check_line.strip():
                            continue

                        check_indent = len(check_line) - len(check_line.lstrip())
                        if check_line.strip() and check_indent <= func_indent:
                            break

                        if "return " in check_line:
                            return_part = check_line.split("return", 1)[1].strip()

                            # 推断返回类型
                            return_type = None
                            if "ServiceLocator.get_" in return_part:
                                return_type = "Any"
                            elif return_part.startswith("self._"):
                                return_type = "Any"

                            if return_type:
                                lines[i + 1] = next_line.replace("):", f") -> {return_type}:")
                                changes.append(f"为 @property 添加返回类型: {next_line.strip()[:50]}")
                            break

        i += 1

    return "\n".join(lines), changes


def fix_simple_getters(content: str) -> Tuple[str, List[str]]:
    """修复简单的 getter 方法"""
    lines = content.split("\n")
    changes = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # 查找 get_ 开头的方法
        if "def get_" in line and "-> " not in line and ":" in line:
            # 检查是否返回 None
            func_indent = len(line) - len(line.lstrip())
            returns_none = False
            returns_value = False

            for j in range(i + 1, min(i + 30, len(lines))):
                check_line = lines[j]
                if not check_line.strip():
                    continue

                check_indent = len(check_line) - len(check_line.lstrip())
                if check_line.strip() and check_indent <= func_indent:
                    break

                if check_line.strip() in ["return None", "return"]:
                    returns_none = True
                elif "return " in check_line:
                    returns_value = True

            # 如果既返回值又返回 None，使用 Optional[Any]
            if returns_none and returns_value:
                lines[i] = line.replace("):", ") -> Optional[Any]:")
                changes.append(f"添加 Optional[Any] 返回类型: {line.strip()[:50]}")
            elif returns_value:
                lines[i] = line.replace("):", ") -> Any:")
                changes.append(f"添加 Any 返回类型: {line.strip()[:50]}")

        i += 1

    return "\n".join(lines), changes


def fix_wiring_functions(content: str) -> Tuple[str, List[str]]:
    """修复 wiring.py 中的工厂函数"""
    lines = content.split("\n")
    changes = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # 查找 get_ 开头的函数（通常是工厂函数）
        if line.strip().startswith("def get_") and "-> " not in line and ":" in line:
            # 检查是否有 return ServiceLocator
            has_service_locator = False
            func_indent = len(line) - len(line.lstrip())

            for j in range(i + 1, min(i + 10, len(lines))):
                check_line = lines[j]
                if not check_line.strip():
                    continue

                check_indent = len(check_line) - len(check_line.lstrip())
                if check_line.strip() and check_indent <= func_indent:
                    break

                if "ServiceLocator.get_" in check_line or "return " in check_line:
                    has_service_locator = True
                    break

            if has_service_locator:
                lines[i] = line.replace(" :", " -> Any:")
                changes.append(f"为工厂函数添加 -> Any: {line.strip()[:50]}")

        i += 1

    return "\n".join(lines), changes


def ensure_typing_imports(content: str, needed: set) -> str:
    """确保必要的 typing 导入存在"""
    if not needed:
        return content

    lines = content.split("\n")

    # 查找现有的 typing 导入
    typing_line_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            typing_line_idx = i
            break

    if typing_line_idx >= 0:
        # 添加到现有导入
        existing = lines[typing_line_idx]
        for item in sorted(needed):
            if item not in existing:
                existing = existing.rstrip() + f", {item}"
        lines[typing_line_idx] = existing
    else:
        # 查找 from __future__ import annotations
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__ import"):
                insert_idx = i + 1
                break
            elif line.startswith("import ") or line.startswith("from "):
                insert_idx = i
                break

        if needed:
            lines.insert(insert_idx, f"from typing import {', '.join(sorted(needed))}")

    return "\n".join(lines)


def process_file(file_path: Path) -> Tuple[bool, List[str]]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content
        all_changes = []
        needed_imports = set()

        # 应用各种修复
        content, changes = fix_property_return_types(content)
        all_changes.extend(changes)
        if changes:
            needed_imports.add("Any")

        content, changes = fix_simple_getters(content)
        all_changes.extend(changes)
        if changes:
            needed_imports.update(["Any", "Optional"])

        content, changes = fix_wiring_functions(content)
        all_changes.extend(changes)
        if changes:
            needed_imports.add("Any")

        # 添加必要的导入
        if needed_imports:
            content = ensure_typing_imports(content, needed_imports)

        # 写回文件
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            return True, all_changes

        return False, []

    except Exception as e:
        print(f"错误处理 {file_path}: {e}")
        return False, []


def main():
    """主函数"""
    print("=" * 80)
    print("智能修复 services 层类型错误")
    print("=" * 80)

    # 查找所有 service 文件
    services_dir = Path(__file__).parent / "apps"
    service_files = []

    for app_dir in services_dir.iterdir():
        if app_dir.is_dir() and not app_dir.name.startswith("."):
            services_path = app_dir / "services"
            if services_path.exists():
                for py_file in services_path.rglob("*.py"):
                    service_files.append(py_file)

    print(f"\n找到 {len(service_files)} 个 service 文件\n")

    # 处理文件
    modified_count = 0
    total_changes = 0

    for file_path in sorted(service_files):
        modified, changes = process_file(file_path)

        if modified:
            modified_count += 1
            total_changes += len(changes)
            rel_path = file_path.relative_to(Path(__file__).parent)
            print(f"✓ {rel_path}")
            for change in changes[:2]:
                print(f"  - {change}")
            if len(changes) > 2:
                print(f"  ... 还有 {len(changes) - 2} 处修改")

    print(f"\n{'=' * 80}")
    print(f"总结:")
    print(f"  修改文件数: {modified_count}")
    print(f"  总修改数: {total_changes}")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
