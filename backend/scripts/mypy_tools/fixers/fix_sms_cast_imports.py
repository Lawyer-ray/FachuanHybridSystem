#!/usr/bin/env python3
"""为 SMS 模块添加缺失的 cast 导入"""

import re
from pathlib import Path


def needs_cast_import(content: str) -> bool:
    """检查是否需要 cast 导入"""
    return "cast(" in content and "from typing import" in content and ", cast" not in content and "cast," not in content


def add_cast_to_typing_import(content: str) -> str:
    """在 typing 导入中添加 cast"""
    # 查找 from typing import ... 行
    pattern = r"from typing import ([^\n]+)"

    def add_cast(match: re.Match[str]) -> str:
        imports = match.group(1)
        if "cast" in imports:
            return match.group(0)
        # 添加 cast
        return f"from typing import {imports}, cast"

    content = re.sub(pattern, add_cast, content, count=1)
    return content


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    sms_path = backend_path / "apps" / "automation" / "services" / "sms"

    if not sms_path.exists():
        print(f"SMS 路径不存在: {sms_path}")
        return

    fixed_files = 0

    for py_file in sms_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        try:
            content = py_file.read_text(encoding="utf-8")

            if needs_cast_import(content):
                original = content
                content = add_cast_to_typing_import(content)

                if content != original:
                    py_file.write_text(content, encoding="utf-8")
                    fixed_files += 1
                    print(f"✓ {py_file.relative_to(backend_path)}")

        except Exception as e:
            print(f"✗ {py_file.relative_to(backend_path)}: {e}")

    print(f"\n修复了 {fixed_files} 个文件")


if __name__ == "__main__":
    main()
