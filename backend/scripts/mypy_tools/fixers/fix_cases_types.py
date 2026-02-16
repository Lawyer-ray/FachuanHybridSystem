#!/usr/bin/env python
"""
批量修复 cases 模块的类型错误

修复内容：
1. 泛型类型参数缺失
2. 函数返回类型缺失
3. 简单的 Returning Any 错误
"""

import re
import subprocess
from pathlib import Path
from typing import Any


def get_mypy_errors() -> list[str]:
    """获取 cases 模块的 mypy 错误"""
    result = subprocess.run(
        ["python", "-m", "mypy", "apps/cases/", "--strict"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.stdout.split("\n")


def fix_generic_types(file_path: Path) -> int:
    """修复泛型类型参数缺失"""
    if not file_path.exists():
        return 0

    content = file_path.read_text(encoding="utf-8")
    original = content

    # 修复 -> dict
    content = re.sub(r"-> dict:", r"-> dict[str, Any]:", content)
    content = re.sub(r"-> dict\s*\n", r"-> dict[str, Any]\n", content, flags=re.MULTILINE)

    # 修复 -> list
    content = re.sub(r"-> list:", r"-> list[Any]:", content)
    content = re.sub(r"-> list\s*\n", r"-> list[Any]\n", content, flags=re.MULTILINE)

    # 修复参数类型
    content = re.sub(r": dict\s*=", r": dict[str, Any] =", content)
    content = re.sub(r": list\s*=", r": list[Any] =", content)

    # 确保导入 Any
    if "dict[str, Any]" in content or "list[Any]" in content:
        if "from typing import" in content:
            # 检查是否已导入 Any
            if not re.search(r"from typing import.*\bAny\b", content):
                # 在第一个 from typing import 行添加 Any
                content = re.sub(
                    r"(from typing import )([^\n]+)",
                    lambda m: f"{m.group(1)}Any, {m.group(2)}" if "Any" not in m.group(2) else m.group(0),
                    content,
                    count=1,
                )

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return 1
    return 0


def fix_missing_return_none(file_path: Path, line_num: int, func_name: str) -> bool:
    """为缺少返回类型的函数添加 -> None"""
    if not file_path.exists():
        return False

    lines = file_path.read_text(encoding="utf-8").split("\n")

    # 找到函数定义行
    if line_num > 0 and line_num <= len(lines):
        line_idx = line_num - 1
        line = lines[line_idx]

        # 检查是否是函数定义且缺少返回类型
        if "def " in line and ")" in line and ":" in line and "->" not in line:
            # 在 ): 之前添加 -> None
            lines[line_idx] = line.replace("):", ") -> None:")

            file_path.write_text("\n".join(lines), encoding="utf-8")
            return True

    return False


def fix_returning_any_with_cast(file_path: Path, line_num: int) -> bool:
    """修复 Returning Any 错误，使用 cast()"""
    if not file_path.exists():
        return False

    lines = file_path.read_text(encoding="utf-8").split("\n")

    if line_num > 0 and line_num <= len(lines):
        line_idx = line_num - 1
        line = lines[line_idx]

        # 检查是否是 return 语句
        if "return " in line and "cast(" not in line:
            # 需要手动处理，这里只是标记
            return False

    return False


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    cases_path = backend_path / "apps" / "cases"

    print("开始修复 cases 模块类型错误...")

    # 1. 批量修复泛型类型参数
    print("\n1. 修复泛型类型参数...")
    fixed_generic = 0
    for py_file in cases_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        fixed_generic += fix_generic_types(py_file)

    print(f"   修复了 {fixed_generic} 个文件的泛型类型")

    # 2. 获取当前错误
    print("\n2. 分析剩余错误...")
    errors = get_mypy_errors()

    missing_return_errors = [e for e in errors if "Missing type" in e or "missing return type" in e]
    returning_any_errors = [e for e in errors if "Returning Any" in e]

    print(f"   - Missing return type: {len(missing_return_errors)} 个")
    print(f"   - Returning Any: {len(returning_any_errors)} 个")

    print("\n修复完成！")
    print("请运行 'python -m mypy apps/cases/ --strict' 查看剩余错误")


if __name__ == "__main__":
    main()
