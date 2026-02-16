#!/usr/bin/env python3
"""批量修复列表/字典初始化的缩进错误"""
import re
from pathlib import Path


def fix_list_dict_init(file_path: Path) -> bool:
    """修复 list[X] = [] 和 dict[X, Y] = {} 的缩进问题"""
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        modified = False

        i = 0
        while i < len(lines):
            line = lines[i]

            # 检测模式: variable: list[Type] = [] 后面跟着内容但没有闭合
            if re.search(r":\s*list\[[^\]]+\]\s*=\s*\[\]\s*$", line):
                # 检查下一行是否是列表元素（应该是错误的）
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith("#"):
                        # 可能是误删了 [ 改成了 []
                        # 检查是否应该是列表
                        if next_line.startswith("{") or next_line.startswith('"') or next_line.startswith("'"):
                            # 将 [] 改回 [
                            lines[i] = re.sub(r"=\s*\[\]\s*$", "= [", line)
                            modified = True

            # 检测模式: variable: list[Type] = [ 后面没有内容就换行了
            elif re.search(r":\s*list\[[^\]]+\]\s*=\s*\[\s*$", line):
                # 检查下一行
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 如果下一行不是列表元素，说明应该是空列表
                    if (
                        not next_line
                        or next_line.startswith("#")
                        or not (
                            next_line.startswith("{")
                            or next_line.startswith('"')
                            or next_line.startswith("'")
                            or next_line.startswith("[")
                        )
                    ):
                        lines[i] = re.sub(r"=\s*\[\s*$", "= []", line)
                        modified = True

            # 检测模式: variable: dict[K, V] = { 后面没有内容
            elif re.search(r":\s*dict\[[^\]]+\]\s*=\s*\{\s*$", line):
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if (
                        not next_line
                        or next_line.startswith("#")
                        or not (next_line.startswith('"') or next_line.startswith("'"))
                    ):
                        lines[i] = re.sub(r"=\s*\{\s*$", "= {}", line)
                        modified = True

            i += 1

        if modified:
            file_path.write_text("\n".join(lines), encoding="utf-8")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / "apps"

    fixed_count = 0
    for py_file in apps_path.rglob("*.py"):
        if fix_list_dict_init(py_file):
            fixed_count += 1
            print(f"Fixed: {py_file}")

    print(f"\nTotal fixed: {fixed_count} files")


if __name__ == "__main__":
    main()
