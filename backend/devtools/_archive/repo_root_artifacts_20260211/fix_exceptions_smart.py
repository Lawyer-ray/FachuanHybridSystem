#!/usr/bin/env python3
"""
智能修复静默异常：
1. 文件操作、清理操作 → 添加注释说明为何静默
2. 数据转换、配置获取 → 添加 logger.exception()
"""
import re
from pathlib import Path
from typing import Dict, List, Tuple

# 应该保持静默的场景（只添加注释）
SILENT_OK_PATTERNS = [
    r"\.rmdir\(\)",
    r"\.delete\(",
    r"field_file",
    r"_delete_",
    r"_prune_",
    r"Path\(",
]


def should_stay_silent(context: str) -> bool:
    """判断是否应该保持静默（文件操作等）"""
    return any(re.search(pattern, context, re.IGNORECASE) for pattern in SILENT_OK_PATTERNS)


def has_logger_import(content: str) -> bool:
    """检查是否已导入 logger"""
    return bool(re.search(r"logger\s*=\s*logging\.getLogger", content))


def add_logger_import(lines: List[str]) -> List[str]:
    """添加 logger 导入"""
    # 找到最后一个 import 语句的位置
    last_import_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and not stripped.startswith("from __future__"):
            last_import_idx = i

    # 在最后一个 import 后插入
    insert_idx = last_import_idx + 1 if last_import_idx >= 0 else 0

    # 检查是否已有 logging import
    has_logging = any("import logging" in line for line in lines[: insert_idx + 5])

    if not has_logging:
        lines.insert(insert_idx, "import logging\n")
        insert_idx += 1

    lines.insert(insert_idx, "\nlogger = logging.getLogger(__name__)\n")
    return lines


def fix_file(filepath: Path) -> Tuple[bool, str]:
    """修复单个文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        modified = False
        needs_logger = False

        # 查找所有 except Exception 块
        i = 0
        while i < len(lines):
            line = lines[i]

            # 找到 except Exception:
            if re.match(r"\s*except Exception\s*:", line):
                indent = len(line) - len(line.lstrip())
                body_indent = indent + 4

                # 获取上下文（前后5行）
                context_start = max(0, i - 5)
                context_end = min(len(lines), i + 10)
                context = "\n".join(lines[context_start:context_end])

                # 检查 except 块的内容
                j = i + 1
                body_lines = []
                while j < len(lines):
                    if lines[j].strip() == "":
                        j += 1
                        continue
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    if current_indent <= indent:
                        break
                    body_lines.append(lines[j])
                    j += 1

                # 检查是否已有 logger 或 raise
                body_text = "\n".join(body_lines)
                has_logger_call = "logger." in body_text
                has_raise = "raise" in body_text

                # 如果既没有 logger 也没有 raise
                if not has_logger_call and not has_raise:
                    # 判断是否应该保持静默
                    if should_stay_silent(context):
                        # 添加注释说明
                        comment = " " * body_indent + "# 静默处理：文件操作失败不影响主流程\n"
                        if body_lines and body_lines[0].strip() == "pass":
                            lines[i + 1] = comment + lines[i + 1]
                        else:
                            lines.insert(i + 1, comment)
                        modified = True
                    else:
                        # 添加 logger.exception()
                        logger_line = " " * body_indent + 'logger.exception("操作失败")\n'
                        lines.insert(i + 1, logger_line)
                        modified = True
                        needs_logger = True

                i = j
            else:
                i += 1

        # 如果需要 logger 但没有导入，添加导入
        if needs_logger and not has_logger_import(content):
            lines = add_logger_import(lines)
            modified = True

        if modified:
            new_content = "\n".join(lines)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True, "已修复"

        return False, "无需修改"

    except Exception as e:
        return False, f"错误: {e}"


def main():
    """批量修复所有文件"""
    backend_dir = Path("backend/apps")

    fixed_count = 0
    skipped_count = 0
    error_count = 0

    for py_file in backend_dir.rglob("*.py"):
        if "migrations" in py_file.parts:
            continue

        success, msg = fix_file(py_file)
        if success:
            fixed_count += 1
            print(f"✓ {py_file}")
        elif "错误" in msg:
            error_count += 1
            print(f"✗ {py_file}: {msg}")
        else:
            skipped_count += 1

    print(f"\n总计：")
    print(f"  已修复: {fixed_count}")
    print(f"  跳过: {skipped_count}")
    print(f"  错误: {error_count}")


if __name__ == "__main__":
    main()
