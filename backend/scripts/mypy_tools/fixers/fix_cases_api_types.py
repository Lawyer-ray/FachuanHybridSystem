#!/usr/bin/env python3
"""修复 cases 模块 API 层的类型注解"""
import re
from pathlib import Path
from typing import Any


def fix_api_function_types(file_path: Path) -> bool:
    """为 API 函数添加类型注解"""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 确保导入 Any 和 HttpRequest
    if "from typing import" in content and "Any" not in content:
        content = re.sub(r"from typing import ([^\n]+)", r"from typing import \1, Any", content, count=1)
    elif "from typing import" not in content:
        # 在第一个 import 后添加
        content = re.sub(r'("""[^"]*""")\n', r"\1\nfrom typing import Any\n", content, count=1)

    # 确保导入 HttpRequest
    if "from django.http import" not in content:
        content = re.sub(r"(from typing import[^\n]+\n)", r"\1from django.http import HttpRequest\n", content, count=1)
    elif "HttpRequest" not in content:
        content = re.sub(
            r"from django.http import ([^\n]+)", r"from django.http import \1, HttpRequest", content, count=1
        )

    # 修复 @router.get/post/put/delete 装饰的函数
    # 模式：def function_name(request, ...):
    # 替换为：def function_name(request: HttpRequest, ...) -> Any:

    # 匹配装饰器后的函数定义
    pattern = r"(@router\.(get|post|put|delete|patch)\([^\)]+\)\n)(def\s+(\w+)\s*\(\s*request\s*,)"

    def add_request_type(match: re.Match[str]) -> str:
        decorator = match.group(1)
        method = match.group(2)
        func_def = match.group(3)
        func_name = match.group(4)
        return f'{decorator}{func_def.replace("request,", "request: HttpRequest,")}'

    content = re.sub(pattern, add_request_type, content)

    # 为没有返回类型的函数添加 -> Any
    # 匹配：def function_name(...):  但不匹配已有 -> 的
    pattern = r"(def\s+\w+\s*\([^)]*\))(\s*:)"

    def add_return_type(match: re.Match[str]) -> str:
        func_sig = match.group(1)
        colon = match.group(2)
        # 检查是否已有返回类型
        if "->" not in func_sig:
            return f"{func_sig} -> Any{colon}"
        return match.group(0)

    content = re.sub(pattern, add_return_type, content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    backend_path = Path(__file__).parent.parent
    api_path = backend_path / "apps" / "cases" / "api"

    if not api_path.exists():
        print(f"路径不存在: {api_path}")
        return

    fixed_count = 0
    for py_file in api_path.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        if fix_api_function_types(py_file):
            fixed_count += 1
            print(f"已修复: {py_file.name}")

    print(f"\n总计修复: {fixed_count} 个文件")


if __name__ == "__main__":
    main()
