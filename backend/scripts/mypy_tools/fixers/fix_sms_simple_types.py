#!/usr/bin/env python3
"""批量修复 SMS 模块的简单类型错误"""

import re
from pathlib import Path
from typing import Any


def fix_implicit_optional(content: str) -> str:
    """修复 implicit Optional 参数"""
    # 修复 = None 的参数，添加 | None
    patterns = [
        # dict[str, Any] = None -> dict[str, Any] | None = None
        (r"(\w+):\s*dict\[str,\s*Any\]\s*=\s*None", r"\1: dict[str, Any] | None = None"),
        # str = None -> str | None = None
        (r"(\w+):\s*str\s*=\s*None", r"\1: str | None = None"),
        # int = None -> int | None = None
        (r"(\w+):\s*int\s*=\s*None", r"\1: int | None = None"),
        # bool = None -> bool | None = None
        (r"(\w+):\s*bool\s*=\s*None", r"\1: bool | None = None"),
        # list[Any] = None -> list[Any] | None = None
        (r"(\w+):\s*list\[Any\]\s*=\s*None", r"\1: list[Any] | None = None"),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    return content


def fix_optional_syntax(content: str) -> str:
    """修复 Optional[...] 语法为 | None"""
    # Optional[str] -> str | None
    content = re.sub(r"Optional\[([^\]]+)\]", r"\1 | None", content)

    # 移除不必要的 Optional 导入
    if "Optional" not in content or content.count("Optional") == 0:
        content = re.sub(r",\s*Optional", "", content)
        content = re.sub(r"Optional,\s*", "", content)
        content = re.sub(r"from typing import Optional\n", "", content)

    return content


def add_return_type_annotations(file_path: Path) -> int:
    """为缺少返回类型的函数添加 -> None"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 简单模式：def function_name(...): 后面没有 ->
    # 只处理明显的 setter/helper 方法
    lines = content.split("\n")
    modified = False

    for i, line in enumerate(lines):
        # 跳过已有返回类型的
        if "->" in line:
            continue

        # 匹配函数定义
        if re.match(r"\s*def\s+\w+\s*\([^)]*\)\s*:", line):
            # 添加 -> None
            lines[i] = line.replace("):", ") -> None:")
            modified = True

    if modified:
        content = "\n".join(lines)
        file_path.write_text(content, encoding="utf-8")
        return 1

    return 0


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
            original = content

            # 应用修复
            content = fix_implicit_optional(content)
            content = fix_optional_syntax(content)

            if content != original:
                py_file.write_text(content, encoding="utf-8")
                fixed_files += 1
                print(f"✓ {py_file.relative_to(backend_path)}")

        except Exception as e:
            print(f"✗ {py_file.relative_to(backend_path)}: {e}")

    print(f"\n修复了 {fixed_files} 个文件")


if __name__ == "__main__":
    main()
