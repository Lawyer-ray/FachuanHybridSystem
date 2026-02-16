#!/usr/bin/env python3
"""全面修复未闭合的列表和字典"""
import re
from pathlib import Path


def fix_file(file_path: Path) -> bool:
    try:
        content = file_path.read_text(encoding="utf-8")
        original = content
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # 查找 : list[Any] = [ 或 : dict[str, Any] = {
            # 且该行以 [ 或 { 结尾
            if re.search(r":\s*list\[Any\]\s*=\s*\[$", line.rstrip()):
                # 检查下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 如果下一行不是列表元素或闭合括号
                    if (
                        next_line
                        and not next_line.startswith(("]", "'", '"', "(", "[", "#"))
                        and not next_line[0].isdigit()
                    ):
                        # 闭合列表
                        lines[i] = line.rstrip()[:-1] + "[]"

            elif re.search(r":\s*dict\[str,\s*Any\]\s*=\s*\{$", line.rstrip()):
                # 检查下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 如果下一行不是字典元素或闭合括号
                    if next_line and not next_line.startswith(("}", "'", '"', "#")) and ":" not in next_line[:30]:
                        # 闭合字典
                        lines[i] = line.rstrip()[:-1] + "{}"

            i += 1

        new_content = "\n".join(lines)

        # 再次修复双括号
        new_content = new_content.replace("[]]", "[]")
        new_content = new_content.replace("{}}", "{}")

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
