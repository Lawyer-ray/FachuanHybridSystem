#!/usr/bin/env python3
"""
修复错误最多的前20个文件
"""

import re
import subprocess
from pathlib import Path


def get_top_error_files(n=20):
    """获取错误最多的前N个文件"""
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"], capture_output=True, text=True
    )

    # 统计每个文件的错误数
    file_errors = {}
    for line in result.stdout.split("\n"):
        if "error:" in line:
            match = re.match(r"(.+?):\d+:", line)
            if match:
                file_path = match.group(1)
                file_errors[file_path] = file_errors.get(file_path, 0) + 1

    # 排序并返回前N个
    sorted_files = sorted(file_errors.items(), key=lambda x: -x[1])
    return sorted_files[:n]


def fix_file(file_path: Path) -> int:
    """修复单个文件,返回修改数"""
    try:
        content = file_path.read_text()
        lines = content.split("\n")
        modified_count = 0

        for i, line in enumerate(lines):
            original = line

            # 修复 Type = None -> Type | None = None
            # 但要避免已经有 Optional 或 | None 的
            if " = None" in line and "Optional[" not in line and "| None" not in line:
                # 模式1: param: SomeType = None
                line = re.sub(r"(\w+):\s*([A-Z]\w+)\s*=\s*None", r"\1: \2 | None = None", line)

                # 模式2: param: dict = None
                line = re.sub(r"(\w+):\s*dict\s*=\s*None", r"\1: dict | None = None", line)

                # 模式3: param: list = None
                line = re.sub(r"(\w+):\s*list\s*=\s*None", r"\1: list | None = None", line)

                # 模式4: param: str = None
                line = re.sub(r"(\w+):\s*str\s*=\s*None", r"\1: str | None = None", line)

                # 模式5: param: int = None
                line = re.sub(r"(\w+):\s*int\s*=\s*None", r"\1: int | None = None", line)

            if line != original:
                lines[i] = line
                modified_count += 1

        if modified_count > 0:
            file_path.write_text("\n".join(lines))

        return modified_count

    except Exception as e:
        print(f"❌ {file_path}: {e}")
        return 0


def main():
    print("🔍 获取错误最多的文件...")
    top_files = get_top_error_files(20)

    print("\n📊 错误最多的20个文件:")
    for file_path, error_count in top_files:
        print(f"  {error_count:3d} errors: {file_path}")

    print("\n🔧 开始修复...")
    total_modified = 0
    fixed_files = 0

    for file_path_str, error_count in top_files:
        file_path = Path(file_path_str)
        if not file_path.exists():
            continue

        modified = fix_file(file_path)
        if modified > 0:
            fixed_files += 1
            total_modified += modified
            print(f"✅ {file_path}: 修改了 {modified} 行")

    print(f"\n✅ 修复了 {fixed_files} 个文件, 共 {total_modified} 处修改")

    # 重新检查
    print("\n🔍 重新检查...")
    result = subprocess.run(
        ["python", "-m", "mypy", "--config-file", "mypy.ini", "apps/"], capture_output=True, text=True
    )

    for line in result.stdout.split("\n"):
        if "Found" in line and "error" in line:
            print(f"📊 {line}")
            break


if __name__ == "__main__":
    main()
