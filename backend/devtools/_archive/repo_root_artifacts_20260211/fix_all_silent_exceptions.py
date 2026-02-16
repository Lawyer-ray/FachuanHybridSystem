#!/usr/bin/env python3
"""
批量修复所有静默异常
"""
import ast
import re
from pathlib import Path
from typing import List, Set, Tuple

# 应该保持静默的场景（文件操作等）
SILENT_OK_KEYWORDS = ["rmdir", "delete", "unlink", "remove", "prune", "field_file", "file_path", "Path(", "resolve()"]


class ExceptionFixer(ast.NodeVisitor):
    def __init__(self, filepath: str, content: str):
        self.filepath = filepath
        self.content = content
        self.lines = content.split("\n")
        self.fixes: List[Tuple[int, str, bool]] = []  # (lineno, fix_type, needs_logger)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # 只处理 except Exception
        if node.type and isinstance(node.type, ast.Name) and node.type.id == "Exception":
            has_logger = False
            has_raise = False

            # 检查 body 中是否有 logger 或 raise
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Raise):
                    has_raise = True
                elif isinstance(stmt, ast.Call):
                    if isinstance(stmt.func, ast.Attribute):
                        if isinstance(stmt.func.value, ast.Name) and stmt.func.value.id == "logger":
                            has_logger = True

            # 如果既没有 logger 也没有 raise，需要修复
            if not has_logger and not has_raise:
                # 获取上下文判断是否应该静默
                context_start = max(0, node.lineno - 5)
                context_end = min(len(self.lines), node.lineno + 5)
                context = "\n".join(self.lines[context_start:context_end])

                should_stay_silent = any(kw in context for kw in SILENT_OK_KEYWORDS)
                self.fixes.append((node.lineno, "silent" if should_stay_silent else "log", not should_stay_silent))

        self.generic_visit(node)


def has_logger_import(content: str) -> bool:
    """检查是否已有 logger"""
    return bool(re.search(r"logger\s*=\s*logging\.getLogger", content))


def add_logger_to_file(lines: List[str]) -> List[str]:
    """添加 logger 导入"""
    # 找到最后一个 import
    last_import = -1
    for i, line in enumerate(lines):
        if line.strip().startswith(("import ", "from ")) and "from __future__" not in line:
            last_import = i

    insert_pos = last_import + 1 if last_import >= 0 else 0

    # 检查是否已有 logging import
    has_logging = any("import logging" in line for line in lines[: insert_pos + 10])

    if not has_logging:
        lines.insert(insert_pos, "import logging")
        insert_pos += 1

    lines.insert(insert_pos, "")
    lines.insert(insert_pos + 1, "logger = logging.getLogger(__name__)")

    return lines


def fix_exception_at_line(lines: List[str], lineno: int, fix_type: str) -> List[str]:
    """在指定行修复异常"""
    idx = lineno - 1  # 转为 0-based
    if idx >= len(lines):
        return lines

    # 找到 except 行的缩进
    except_line = lines[idx]
    base_indent = len(except_line) - len(except_line.lstrip())
    body_indent = " " * (base_indent + 4)

    # 找到 except body 的第一行
    body_idx = idx + 1
    while body_idx < len(lines) and lines[body_idx].strip() == "":
        body_idx += 1

    if fix_type == "silent":
        # 添加注释
        comment = body_indent + "# 静默处理：文件操作失败不影响主流程"
        lines.insert(body_idx, comment)
    else:
        # 添加 logger.exception()
        logger_line = body_indent + 'logger.exception("操作失败")'
        lines.insert(body_idx, logger_line)

    return lines


def process_file(filepath: Path) -> Tuple[bool, str]:
    """处理单个文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 AST
        try:
            tree = ast.parse(content, filename=str(filepath))
        except SyntaxError:
            return False, "语法错误"

        # 查找需要修复的异常
        fixer = ExceptionFixer(str(filepath), content)
        fixer.visit(tree)

        if not fixer.fixes:
            return False, "无需修复"

        # 应用修复（从后往前，避免行号变化）
        lines = content.split("\n")
        needs_logger = any(needs for _, _, needs in fixer.fixes)

        for lineno, fix_type, _ in sorted(fixer.fixes, reverse=True):
            lines = fix_exception_at_line(lines, lineno, fix_type)

        # 添加 logger 导入
        if needs_logger and not has_logger_import(content):
            lines = add_logger_to_file(lines)

        # 写回文件
        new_content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        return True, f"修复 {len(fixer.fixes)} 处"

    except Exception as e:
        return False, f"错误: {e}"


def main():
    backend_dir = Path("backend/apps")

    fixed_files = []
    error_files = []

    for py_file in backend_dir.rglob("*.py"):
        if "migrations" in py_file.parts:
            continue

        success, msg = process_file(py_file)
        if success:
            fixed_files.append((py_file, msg))
            print(f"✓ {py_file.relative_to('backend')}: {msg}")
        elif "错误" in msg:
            error_files.append((py_file, msg))

    print(f"\n总计：")
    print(f"  已修复: {len(fixed_files)} 个文件")
    print(f"  错误: {len(error_files)} 个文件")

    if error_files:
        print(f"\n错误文件：")
        for f, msg in error_files[:10]:
            print(f"  {f}: {msg}")


if __name__ == "__main__":
    main()
