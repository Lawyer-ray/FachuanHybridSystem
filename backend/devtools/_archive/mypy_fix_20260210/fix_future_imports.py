#!/usr/bin/env python3
"""修复 from __future__ import annotations 的位置问题"""

from pathlib import Path


def fix_file(file_path: Path) -> bool:
    """修复单个文件的 future import 位置"""
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        # 查找 from __future__ import annotations
        future_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == "from __future__ import annotations":
                future_line_idx = i
                break

        if future_line_idx == -1:
            return False

        # 如果已经在第一行（或注释后），跳过
        if future_line_idx == 0:
            return False

        # 检查前面是否只有注释或空行
        has_code_before = False
        for i in range(future_line_idx):
            line = lines[i].strip()
            if line and not line.startswith("#"):
                has_code_before = True
                break

        if not has_code_before:
            return False

        # 移除 future import 行
        future_line = lines.pop(future_line_idx)

        # 找到插入位置（第一个非注释、非空行之前）
        insert_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                insert_idx = i
                break

        # 插入到正确位置
        lines.insert(insert_idx, future_line)

        # 写回文件
        file_path.write_text("\n".join(lines), encoding="utf-8")
        return True

    except Exception as e:
        print(f"错误处理 {file_path}: {e}")
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("修复 from __future__ import annotations 位置")
    print("=" * 80)

    # 查找所有 Python 文件
    services_dir = Path(__file__).parent / "apps"
    py_files = list(services_dir.rglob("*.py"))

    print(f"\n扫描 {len(py_files)} 个文件...")

    fixed_count = 0
    for file_path in py_files:
        if fix_file(file_path):
            fixed_count += 1
            print(f"✓ {file_path.relative_to(Path(__file__).parent)}")

    print(f"\n{'=' * 80}")
    print(f"修复了 {fixed_count} 个文件")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
