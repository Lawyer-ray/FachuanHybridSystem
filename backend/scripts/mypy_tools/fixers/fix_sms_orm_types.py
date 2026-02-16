"""修复 SMS 模块的 Django ORM 类型错误"""

import re
from pathlib import Path
from typing import Any


def fix_attr_defined_errors(file_path: Path) -> int:
    """修复 [attr-defined] 错误 - 为 Django ORM 动态属性使用 cast()"""
    content = file_path.read_text(encoding="utf-8")
    original = content
    fixed_count = 0

    # 确保导入 cast
    if "from typing import cast" not in content and "cast(" not in content:
        # 在 typing 导入区域添加 cast
        if "from typing import" in content:
            content = re.sub(r"(from typing import [^)]+)", r"\1, cast", content, count=1)
        else:
            # 在第一个 import 后添加
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    lines.insert(i + 1, "from typing import cast")
                    break
            content = "\n".join(lines)

    # 修复常见的 Django ORM 动态属性访问
    # 1. sms.id, case.id, task.id 等
    patterns = [
        # CourtSMS.id
        (r"(\bsms)\.id\b", r"cast(int, \1.id)"),
        # ScraperTask.id
        (r"(\btask)\.id\b", r"cast(int, \1.id)"),
        # case.id
        (r"(\bcase)\.id\b", r"cast(int, \1.id)"),
        # case_log.id
        (r"(\bcase_log)\.id\b", r"cast(int, \1.id)"),
        # scraper_task.id
        (r"(\bscraper_task)\.id\b", r"cast(int, \1.id)"),
        # .case_id
        (r"(\w+)\.case_id\b", r"cast(int | None, \1.case_id)"),
        # .case_log_id
        (r"(\w+)\.case_log_id\b", r"cast(int | None, \1.case_log_id)"),
        # .scraper_task_id
        (r"(\w+)\.scraper_task_id\b", r"cast(int | None, \1.scraper_task_id)"),
        # .pk
        (r"(\w+)\.pk\b", r"cast(int, \1.pk)"),
        # .result (ScraperTask)
        (r"(\bscraper_task)\.result\b", r"cast(dict[str, Any] | None, \1.result)"),
        (r"(\btask)\.result\b", r"cast(dict[str, Any] | None, \1.result)"),
        # .documents (ScraperTask)
        (r"(\bscraper_task)\.documents\b", r"cast(Any, \1.documents)"),
        (r"(\btask)\.documents\b", r"cast(Any, \1.documents)"),
        # .name (Document, Case, etc)
        (r"(\bdocument)\.name\b", r"cast(str, \1.name)"),
        (r"(\bcase)\.name\b", r"cast(str, \1.name)"),
    ]

    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            fixed_count += 1
            content = new_content

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return fixed_count

    return 0


def fix_queryset_generic_types(file_path: Path) -> int:
    """为 QuerySet 添加泛型参数"""
    content = file_path.read_text(encoding="utf-8")
    original = content
    fixed_count = 0

    # QuerySet[CourtSMS]
    patterns = [
        (r": QuerySet\s*=", r": QuerySet[CourtSMS] ="),
        (r"-> QuerySet:", r"-> QuerySet[CourtSMS]:"),
        (r"-> QuerySet\s*\n", r"-> QuerySet[CourtSMS]\n"),
    ]

    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            fixed_count += 1
            content = new_content

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return fixed_count

    return 0


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    sms_path = backend_path / "apps" / "automation" / "services" / "sms"

    if not sms_path.exists():
        print(f"SMS 路径不存在: {sms_path}")
        return

    total_fixed = 0
    files_fixed = 0

    for py_file in sms_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        fixed = fix_attr_defined_errors(py_file)
        fixed += fix_queryset_generic_types(py_file)

        if fixed > 0:
            files_fixed += 1
            total_fixed += fixed
            print(f"修复: {py_file.relative_to(backend_path)} ({fixed} 处)")

    print(f"\n总计修复 {files_fixed} 个文件，{total_fixed} 处错误")


if __name__ == "__main__":
    main()
