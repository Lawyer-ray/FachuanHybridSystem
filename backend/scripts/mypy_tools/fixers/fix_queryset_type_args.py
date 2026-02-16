"""
修复 QuerySet 泛型参数

将 QuerySet[Model] 改为 QuerySet[Model, Model]
Requirements: 3.5
"""

import re
from pathlib import Path
from typing import Any


def fix_queryset_in_file(file_path: Path) -> int:
    """修复单个文件的 QuerySet 泛型参数"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 匹配 QuerySet[ModelName] 但不匹配已经有两个参数的
    # 使用负向前瞻确保后面不是逗号
    pattern = r"QuerySet\[([A-Za-z_][A-Za-z0-9_]*)\](?!\s*,)"

    def replace_func(match: re.Match[str]) -> str:
        model_name = match.group(1)
        return f"QuerySet[{model_name}, {model_name}]"

    content = re.sub(pattern, replace_func, content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return 1
    return 0


def main() -> None:
    backend_path = Path(__file__).parent.parent
    apps_path = backend_path / "apps" / "cases"

    fixed_count = 0
    total_files = 0

    for py_file in apps_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        if "migrations" in py_file.parts:
            continue

        total_files += 1
        if fix_queryset_in_file(py_file):
            fixed_count += 1
            print(f"Fixed: {py_file.relative_to(backend_path)}")

    print(f"\nTotal files scanned: {total_files}")
    print(f"Total files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
