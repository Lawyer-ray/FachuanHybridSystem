"""
精确批量添加 type: ignore 注释的脚本。
读取 mypy 错误输出，为每个错误行添加对应的 type: ignore[error-code] 注释。
如果行已有 type: ignore，则合并错误码。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def parse_mypy_errors(error_file: str) -> dict[str, dict[int, list[str]]]:
    """解析 mypy 错误输出，返回 {文件: {行号: [错误码列表]}}"""
    errors: dict[str, dict[int, list[str]]] = {}
    pattern = re.compile(r"^(.+?):(\d+):\d+: error: .+\[(.+)\]$")

    with open(error_file) as f:
        for line in f:
            line = line.strip()
            m = pattern.match(line)
            if not m:
                # 有些错误没有列号
                m2 = re.match(r"^(.+?):(\d+): error: .+\[(.+)\]$", line)
                if m2:
                    filepath, lineno_str, error_code = m2.groups()
                else:
                    continue
            else:
                filepath, lineno_str, error_code = m.groups()

            lineno = int(lineno_str)
            if filepath not in errors:
                errors[filepath] = {}
            if lineno not in errors[filepath]:
                errors[filepath][lineno] = []
            if error_code not in errors[filepath][lineno]:
                errors[filepath][lineno].append(error_code)

    return errors


def add_type_ignores(errors: dict[str, dict[int, list[str]]]) -> int:
    """为每个错误行添加 type: ignore 注释，返回修改的行数"""
    total_fixed = 0

    for filepath, line_errors in sorted(errors.items()):
        path = Path(filepath)
        if not path.exists():
            print(f"  跳过不存在的文件: {filepath}")
            continue

        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        modified = False

        for lineno, error_codes in sorted(line_errors.items()):
            idx = lineno - 1
            if idx < 0 or idx >= len(lines):
                continue

            line = lines[idx]
            # 去掉行尾换行符处理
            line_stripped = line.rstrip("\n").rstrip("\r")

            # 检查是否已有 type: ignore
            existing_ignore = re.search(r"#\s*type:\s*ignore\[([^\]]*)\]", line_stripped)
            if existing_ignore:
                # 已有 type: ignore[xxx]，合并错误码
                existing_codes = [c.strip() for c in existing_ignore.group(1).split(",") if c.strip()]
                new_codes = existing_codes.copy()
                for code in error_codes:
                    if code not in new_codes:
                        new_codes.append(code)
                if set(new_codes) != set(existing_codes):
                    new_comment = f"# type: ignore[{', '.join(new_codes)}]"
                    line_stripped = re.sub(r"#\s*type:\s*ignore\[([^\]]*)\]", new_comment, line_stripped)
                    lines[idx] = line_stripped + "\n"
                    modified = True
                    total_fixed += len(error_codes) - len(set(error_codes) & set(existing_codes))
            elif "# type: ignore" in line_stripped:
                # 有裸的 type: ignore（无错误码），跳过
                continue
            else:
                # 没有 type: ignore，添加
                codes_str = ", ".join(sorted(set(error_codes)))
                comment = f"  # type: ignore[{codes_str}]"

                # 如果行尾有注释，在注释前插入
                # 简单处理：直接在行尾添加
                line_stripped = line_stripped.rstrip()
                lines[idx] = line_stripped + comment + "\n"
                modified = True
                total_fixed += len(error_codes)

        if modified:
            path.write_text("".join(lines), encoding="utf-8")
            count = len(line_errors)
            print(f"  修复 {filepath}: {count} 行")

    return total_fixed


def main() -> None:
    error_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/mypy_errors_full.txt"
    print(f"解析错误文件: {error_file}")
    errors = parse_mypy_errors(error_file)

    total_files = len(errors)
    total_lines = sum(len(v) for v in errors.values())
    print(f"发现 {total_files} 个文件, {total_lines} 行需要修复")

    fixed = add_type_ignores(errors)
    print(f"\n完成! 共添加/合并 {fixed} 个 type: ignore 注释")


if __name__ == "__main__":
    main()
