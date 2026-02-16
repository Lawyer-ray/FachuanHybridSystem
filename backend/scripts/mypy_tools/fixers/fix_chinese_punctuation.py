#!/usr/bin/env python3
"""修复中文标点符号"""
from pathlib import Path


def fix_chinese_punctuation(file_path: Path) -> bool:
    """修复文件中的中文标点符号"""
    content = file_path.read_text(encoding="utf-8")
    original_content = content

    # 替换中文标点为英文标点
    replacements = {
        "，": ",",
        "。": ".",
        "（": "(",
        "）": ")",
        "：": ":",
        "；": ";",
        "！": "!",
        "？": "?",
    }

    for chinese, english in replacements.items():
        content = content.replace(chinese, english)

    if content != original_content:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    """主函数"""
    apps_dir = Path("apps")
    fixed_count = 0

    for py_file in apps_dir.rglob("*.py"):
        if fix_chinese_punctuation(py_file):
            print(f"修复: {py_file}")
            fixed_count += 1

    print(f"\n总共修复 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
