#!/usr/bin/env python3
"""
批量修复所有 services 层的语法错误
"""
import re
import subprocess
from pathlib import Path


def find_syntax_errors():
    """运行 mypy 找出所有语法错误"""
    cmd = [
        "python",
        "-m",
        "mypy",
        "--config-file",
        "mypy.ini",
        "apps/automation/services/",
        "apps/cases/services/",
        "apps/contracts/services/",
        "apps/documents/services/",
        "apps/litigation_ai/services/",
        "apps/client/services/",
        "apps/organization/services/",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # 解析错误信息
    errors = []
    for line in result.stderr.split("\n"):
        if "error: invalid syntax" in line or "error:" in line:
            match = re.match(r"(.+?):(\d+):(\d+): error:", line)
            if match:
                file_path, line_num, col_num = match.groups()
                errors.append({"file": file_path, "line": int(line_num), "col": int(col_num), "full_line": line})

    return errors


def fix_syntax_error(file_path: str, line_num: int):
    """修复特定文件的语法错误"""
    path = Path(file_path)
    if not path.exists():
        return False

    content = path.read_text()
    lines = content.split("\n")

    if line_num > len(lines):
        return False

    line = lines[line_num - 1]

    # 修复模式 1: | None: Any = None → | None = None
    if "| None: Any" in line:
        lines[line_num - 1] = line.replace("| None: Any", "| None")
        path.write_text("\n".join(lines))
        print(f"✓ 修复 {file_path}:{line_num} - 移除多余的 : Any")
        return True

    # 修复模式 2: Callable[..., Any]: Any → Callable[..., Any]
    if "Callable[..., Any]: Any" in line:
        lines[line_num - 1] = line.replace("Callable[..., Any]: Any", "Callable[..., Any]")
        path.write_text("\n".join(lines))
        print(f"✓ 修复 {file_path}:{line_num} - 修正 Callable 类型")
        return True

    # 修复模式 3: dict[...] | None: Any = None → dict[...] | None = None
    pattern = r"(dict\[[^\]]+\])\s*\|\s*None:\s*Any\s*="
    if re.search(pattern, line):
        lines[line_num - 1] = re.sub(pattern, r"\1 | None =", line)
        path.write_text("\n".join(lines))
        print(f"✓ 修复 {file_path}:{line_num} - 修正 dict 类型")
        return True

    return False


def main():
    print("🔍 查找语法错误...")
    errors = find_syntax_errors()

    if not errors:
        print("✅ 未发现语法错误")
        return

    print(f"📋 发现 {len(errors)} 个语法错误")

    fixed_count = 0
    for error in errors:
        if fix_syntax_error(error["file"], error["line"]):
            fixed_count += 1

    print(f"\n✅ 修复了 {fixed_count}/{len(errors)} 个错误")

    # 再次检查
    print("\n🔍 验证修复结果...")
    remaining = find_syntax_errors()
    if remaining:
        print(f"⚠️  还剩 {len(remaining)} 个错误需要手动处理")
        for err in remaining[:5]:
            print(f"  - {err['full_line']}")
    else:
        print("✅ 所有语法错误已修复")


if __name__ == "__main__":
    main()
