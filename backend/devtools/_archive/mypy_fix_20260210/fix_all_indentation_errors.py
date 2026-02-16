#!/usr/bin/env python3
"""
修复所有由于错误插入 import logging 导致的缩进错误
"""

import re
import subprocess
from pathlib import Path


def has_syntax_error(filepath: Path) -> bool:
    """检查文件是否有语法错误"""
    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(filepath)], capture_output=True, text=True, timeout=5
        )
        return result.returncode != 0
    except Exception:
        return False


def fix_file(filepath: Path) -> bool:
    """修复单个文件"""
    try:
        content = filepath.read_text(encoding="utf-8")
        original_content = content
        lines = content.split("\n")

        # 查找并移除错误放置的 import logging 和 logger 定义
        fixed_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # 检查是否是错误放置的 import logging（在缩进的代码块中）
            if line.strip() == "import logging" and line.startswith(" "):
                # 跳过这行
                i += 1
                # 跳过后续的空行
                while i < len(lines) and not lines[i].strip():
                    i += 1
                # 跳过紧跟的空行
                while i < len(lines) and not lines[i].strip():
                    i += 1
                # 跳过紧跟的 logger 定义
                if i < len(lines) and lines[i].strip().startswith("logger = logging.getLogger"):
                    i += 1
                    # 跳过后续的空行
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    # 再跳过一组空行
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                continue

            # 检查是否是错误放置的 logger 定义（在缩进的代码块中）
            if line.strip().startswith("logger = logging.getLogger") and line.startswith(" "):
                # 跳过这行
                i += 1
                # 跳过后续的空行
                while i < len(lines) and not lines[i].strip():
                    i += 1
                # 再跳过一组空行
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue

            fixed_lines.append(line)
            i += 1

        content = "\n".join(fixed_lines)

        # 确保文件顶部有 import logging
        if "import logging" not in content[:2000]:  # 只检查前2000个字符
            lines = content.split("\n")
            # 找到最后一个 import 语句
            last_import_idx = -1
            for i, line in enumerate(lines[:100]):  # 只检查前100行
                if line.strip().startswith("import ") or line.strip().startswith("from "):
                    last_import_idx = i

            if last_import_idx >= 0:
                lines.insert(last_import_idx + 1, "import logging")
                content = "\n".join(lines)

        # 确保有 logger 定义
        if "logger = logging.getLogger" not in content[:3000]:  # 只检查前3000个字符
            lines = content.split("\n")
            # 找到 import 区域后的位置
            last_import_idx = -1
            for i, line in enumerate(lines[:100]):
                if line.strip().startswith("import ") or line.strip().startswith("from "):
                    last_import_idx = i

            if last_import_idx >= 0:
                # 找到合适的插入位置
                insert_idx = last_import_idx + 1
                while insert_idx < len(lines) and (
                    lines[insert_idx].strip().startswith("import") or lines[insert_idx].strip().startswith("from")
                ):
                    insert_idx += 1

                # 添加空行和 logger 定义
                if insert_idx < len(lines):
                    if lines[insert_idx].strip():
                        lines.insert(insert_idx, "")
                        insert_idx += 1
                    lines.insert(insert_idx, "")
                    lines.insert(insert_idx + 1, "logger = logging.getLogger(__name__)")
                    content = "\n".join(lines)

        if content != original_content:
            filepath.write_text(content, encoding="utf-8")
            return True
        return False
    except Exception as e:
        print(f"  错误: {e}")
        return False


def main():
    """主函数"""
    backend_dir = Path(__file__).parent

    # 查找所有有语法错误的 Python 文件
    print("正在扫描有语法错误的文件...")
    error_files = []

    for py_file in backend_dir.glob("apps/**/*.py"):
        if has_syntax_error(py_file):
            rel_path = py_file.relative_to(backend_dir)
            error_files.append(rel_path)
            print(f"  发现错误: {rel_path}")

    print(f"\n总计发现 {len(error_files)} 个文件有语法错误")

    if not error_files:
        print("没有发现语法错误！")
        return

    print("\n开始修复...")
    fixed_count = 0
    for file_path in error_files:
        full_path = backend_dir / file_path
        print(f"修复: {file_path}")
        if fix_file(full_path):
            # 验证修复是否成功
            if not has_syntax_error(full_path):
                print(f"  ✓ 修复成功")
                fixed_count += 1
            else:
                print(f"  ✗ 修复后仍有错误")
        else:
            print(f"  - 无需修改")

    print(f"\n总计成功修复 {fixed_count}/{len(error_files)} 个文件")


if __name__ == "__main__":
    main()
