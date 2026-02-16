#!/usr/bin/env python3
"""
第二轮批量修复 automation 模块的简单类型错误
专注于修复：
1. 无效类型名称（any → Any）
2. 缺少返回类型注解的简单函数
3. 变量类型注解缺失
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def fix_invalid_type_any(content: str) -> tuple[str, int]:
    """修复无效类型名称 any → Any"""
    fixes = 0

    # : any → : Any (参数类型)
    pattern1 = r"(\w+):\s*any\b"
    matches = list(re.finditer(pattern1, content))
    if matches:
        for match in reversed(matches):  # 从后往前替换，避免位置偏移
            start, end = match.span()
            content = content[:start] + match.group(1) + ": Any" + content[end:]
            fixes += 1

    return content, fixes


def fix_missing_return_annotations(content: str) -> tuple[str, int]:
    """为缺少返回类型注解的简单函数添加 -> None"""
    fixes = 0

    # 匹配 def xxx(): 但没有 -> 的函数
    # 只修复明显是 None 返回的函数（没有 return 语句或只有 return）
    pattern = r"(def\s+\w+\([^)]*\)):\s*\n"

    def should_add_none_annotation(func_def: str, following_lines: str) -> bool:
        """判断是否应该添加 -> None 注解"""
        # 简单启发式：如果函数体很短且没有明显的 return value
        lines = following_lines.split("\n")[:10]  # 只看前10行
        for line in lines:
            if "return " in line and not line.strip().endswith("return"):
                # 有 return 值，不添加
                return False
        return True

    # 这个修复比较复杂，暂时跳过
    return content, fixes


def fix_var_annotated_simple(content: str) -> tuple[str, int]:
    """修复简单的变量类型注解缺失"""
    fixes = 0

    # result_queue = queue.Queue() → result_queue: Any = queue.Queue()
    pattern1 = r"(\s+)(\w+)\s*=\s*queue\.Queue\(\)"

    def repl1(m):
        nonlocal fixes
        fixes += 1
        return f"{m.group(1)}{m.group(2)}: Any = queue.Queue()"

    content = re.sub(pattern1, repl1, content)

    # path = [] → path: list[Any] = []
    pattern2 = r"(\s+)(path)\s*=\s*\[\]"

    def repl2(m):
        nonlocal fixes
        fixes += 1
        return f"{m.group(1)}{m.group(2)}: list[Any] = []"

    content = re.sub(pattern2, repl2, content)

    # env_vars = {} → env_vars: dict[str, Any] = {}
    pattern3 = r"(\s+)(env_vars|role_map)\s*=\s*\{\}"

    def repl3(m):
        nonlocal fixes
        fixes += 1
        return f"{m.group(1)}{m.group(2)}: dict[str, Any] = {{}}"

    content = re.sub(pattern3, repl3, content)

    return content, fixes


def ensure_typing_imports(content: str) -> str:
    """确保必要的 typing 导入存在"""
    lines = content.split("\n")

    # 检查是否需要 Any
    needs_any = ": Any" in content or "list[Any]" in content or "dict[str, Any]" in content

    if not needs_any:
        return content

    # 检查是否已有 from typing import
    has_typing_import = False
    typing_import_line = -1
    imports_any = False

    for i, line in enumerate(lines):
        if line.startswith("from typing import"):
            has_typing_import = True
            typing_import_line = i
            if "Any" in line:
                imports_any = True
            break

    # 如果需要 Any 但没有导入
    if needs_any and not imports_any:
        if has_typing_import:
            # 在现有导入中添加 Any
            line = lines[typing_import_line]
            if "Any" not in line:
                # 简单追加
                line = line.rstrip()
                if line.endswith(")"):
                    line = line[:-1] + ", Any)"
                elif "(" in line:
                    line = line + ", Any"
                else:
                    line = line + ", Any"
                lines[typing_import_line] = line
        else:
            # 添加新的导入行
            # 找到合适的位置（在 from __future__ 之后，在其他导入之前）
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith("from __future__"):
                    insert_pos = i + 1
                    # 跳过空行
                    while insert_pos < len(lines) and not lines[insert_pos].strip():
                        insert_pos += 1
                    break
                elif line.startswith("import ") or line.startswith("from "):
                    insert_pos = i
                    break

            if insert_pos == 0:
                # 没找到任何导入，插入到文件开头（跳过 shebang 和 docstring）
                for i, line in enumerate(lines):
                    if (
                        line.strip()
                        and not line.startswith("#")
                        and not line.startswith('"""')
                        and not line.startswith("'''")
                    ):
                        insert_pos = i
                        break

            lines.insert(insert_pos, "from typing import Any")
            if insert_pos > 0 and lines[insert_pos - 1].strip():
                lines.insert(insert_pos, "")

    return "\n".join(lines)


def process_file(file_path: Path) -> dict[str, Any]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content
        total_fixes = 0

        # 应用修复
        content, n1 = fix_invalid_type_any(content)
        total_fixes += n1

        content, n2 = fix_var_annotated_simple(content)
        total_fixes += n2

        # 如果有修复，确保导入 Any
        if total_fixes > 0:
            content = ensure_typing_imports(content)

        # 只有内容变化时才写入
        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            return {"file": str(file_path), "fixes": total_fixes, "success": True}

        return {"file": str(file_path), "fixes": 0, "success": True}

    except Exception as e:
        return {"file": str(file_path), "fixes": 0, "success": False, "error": str(e)}


def main():
    """主函数"""
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    print("开始第二轮批量修复 automation 模块的简单类型错误...")
    print(f"扫描目录: {automation_path}")

    # 收集所有 Python 文件
    py_files = list(automation_path.rglob("*.py"))
    print(f"找到 {len(py_files)} 个 Python 文件")

    # 处理文件
    results = []
    modified_files = []
    total_fixes = 0

    for py_file in py_files:
        result = process_file(py_file)
        results.append(result)

        if result["success"] and result["fixes"] > 0:
            modified_files.append(py_file)
            total_fixes += result["fixes"]
            rel_path = py_file.relative_to(backend_path)
            print(f"  ✓ {rel_path}: {result['fixes']} 处修复")

    # 输出统计
    print(f"\n修复完成:")
    print(f"  - 修改文件数: {len(modified_files)}")
    print(f"  - 总修复数: {total_fixes}")

    # 输出失败的文件
    failed = [r for r in results if not r["success"]]
    if failed:
        print(f"\n失败文件 ({len(failed)}):")
        for r in failed:
            print(f"  ✗ {r['file']}: {r.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
