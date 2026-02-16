#!/usr/bin/env python3
"""修复被错误闭合的列表 - 检测 = [] 后面紧跟着列表元素的情况"""
import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content
        lines = content.split("\n")

        i = 0
        while i < len(lines) - 1:
            line = lines[i]
            next_line = lines[i + 1]

            # 检测模式: xxx: list[Any] = [] 后面紧跟着看起来像列表元素的行
            if re.search(r":\s*list\[Any\]\s*=\s*\[\]$", line.rstrip()):
                next_stripped = next_line.strip()
                # 如果下一行以 { 或 " 或 ' 或 path( 开头,或者包含 "role": 这样的字典键
                if (
                    next_stripped.startswith(("{", '"', "'", "path("))
                    or '"role":' in next_stripped
                    or "'role':" in next_stripped
                ):
                    # 这应该是一个列表的开始,修复为 = [
                    lines[i] = line.rstrip()[:-1]  # 移除最后的 ]

            # 检测模式: xxx: dict[str, Any] = {} 后面紧跟着看起来像字典元素的行
            elif re.search(r":\s*dict\[str,\s*Any\]\s*=\s*\{\}$", line.rstrip()):
                next_stripped = next_line.strip()
                # 如果下一行以 " 或 ' 开头并包含 :
                if next_stripped.startswith(('"', "'")) and ":" in next_stripped[:50]:
                    # 这应该是一个字典的开始,修复为 = {
                    lines[i] = line.rstrip()[:-1]  # 移除最后的 }

            i += 1

        new_content = "\n".join(lines)

        if new_content != original:
            file_path.write_text(new_content, encoding="utf-8")
            return True
        return False

    except Exception as e:
        print(f"错误: {file_path}: {e}")
        return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    fixed = 0
    for py_file in automation_path.rglob("*.py"):
        if fix_file(py_file):
            fixed += 1
            print(f"✓ {py_file.relative_to(backend_path)}")

    print(f"\n修复了 {fixed} 个文件")


if __name__ == "__main__":
    main()
