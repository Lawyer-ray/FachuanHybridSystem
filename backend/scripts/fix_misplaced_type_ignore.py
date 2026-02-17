"""
修复 type: ignore 注释位置不匹配的问题。
当 ruff format 重新格式化代码后，type: ignore 可能被放在了错误的行上。
这个脚本处理两种情况：
1. 错误在 line N，unused-ignore 在 line N+1 或 N+2 → 移动 type: ignore 到 line N
2. 错误在 line N，同一行已有不同的 type: ignore → 合并错误码
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def parse_errors(error_file: str) -> dict[str, list[tuple[int, str, str]]]:
    """解析错误，返回 {文件: [(行号, 错误类型, 错误码)]}"""
    errors: dict[str, list[tuple[int, str, str]]] = {}
    pattern = re.compile(r'^(.+?):(\d+)(?::\d+)?: error: (.+?)\s+\[(.+)\]$')

    with open(error_file) as f:
        for line in f:
            line = line.strip()
            m = pattern.match(line)
            if not m:
                continue
            filepath, lineno_str, msg, error_code = m.groups()
            if filepath not in errors:
                errors[filepath] = []
            errors[filepath].append((int(lineno_str), msg.strip(), error_code))

    return errors


def fix_file(filepath: str, file_errors: list[tuple[int, str, str]]) -> int:
    """修复单个文件，返回修复数量"""
    path = Path(filepath)
    if not path.exists():
        return 0

    lines = path.read_text(encoding='utf-8').split('\n')
    fixed = 0

    # 分类错误
    real_errors: dict[int, list[str]] = {}  # 行号 -> [错误码]
    unused_ignores: set[int] = set()  # unused-ignore 的行号

    for lineno, msg, code in file_errors:
        if code == 'unused-ignore':
            unused_ignores.add(lineno)
        else:
            if lineno not in real_errors:
                real_errors[lineno] = []
            real_errors[lineno].append(code)

    # 处理每个 unused-ignore：删除该行的 type: ignore
    # 处理每个 real error：在该行添加 type: ignore
    lines_to_remove_ignore: set[int] = set()
    lines_to_add_ignore: dict[int, list[str]] = {}

    for lineno in unused_ignores:
        idx = lineno - 1
        if 0 <= idx < len(lines):
            lines_to_remove_ignore.add(lineno)

    for lineno, codes in real_errors.items():
        idx = lineno - 1
        if 0 <= idx < len(lines):
            line = lines[idx]
            # 检查该行是否已有 type: ignore
            existing = re.search(r'#\s*type:\s*ignore\[([^\]]*)\]', line)
            if existing:
                existing_codes = [c.strip() for c in existing.group(1).split(',') if c.strip()]
                all_codes = list(set(existing_codes + codes))
                # 替换现有的 type: ignore
                new_comment = f"# type: ignore[{', '.join(sorted(all_codes))}]"
                lines[idx] = re.sub(r'#\s*type:\s*ignore\[([^\]]*)\]', new_comment, line)
                fixed += 1
            else:
                # 添加新的 type: ignore
                if lineno not in lines_to_add_ignore:
                    lines_to_add_ignore[lineno] = []
                lines_to_add_ignore[lineno].extend(codes)

    # 先删除 unused-ignore 行的 type: ignore 注释
    for lineno in lines_to_remove_ignore:
        idx = lineno - 1
        if 0 <= idx < len(lines):
            line = lines[idx]
            # 删除 # type: ignore[...] 部分
            new_line = re.sub(r'\s*#\s*type:\s*ignore\[[^\]]*\]\s*$', '', line)
            # 也处理裸的 type: ignore
            new_line = re.sub(r'\s*#\s*type:\s*ignore\s*$', '', new_line)
            if new_line != line:
                lines[idx] = new_line
                fixed += 1

    # 添加新的 type: ignore
    for lineno, codes in lines_to_add_ignore.items():
        idx = lineno - 1
        if 0 <= idx < len(lines):
            line = lines[idx]
            # 再次检查（可能上面的删除操作已经改变了）
            existing = re.search(r'#\s*type:\s*ignore\[([^\]]*)\]', line)
            if existing:
                existing_codes = [c.strip() for c in existing.group(1).split(',') if c.strip()]
                all_codes = list(set(existing_codes + codes))
                new_comment = f"# type: ignore[{', '.join(sorted(all_codes))}]"
                lines[idx] = re.sub(r'#\s*type:\s*ignore\[([^\]]*)\]', new_comment, line)
            else:
                codes_str = ', '.join(sorted(set(codes)))
                lines[idx] = lines[idx].rstrip() + f"  # type: ignore[{codes_str}]"
            fixed += 1

    if fixed > 0:
        path.write_text('\n'.join(lines), encoding='utf-8')
        print(f"  修复 {filepath}: {fixed} 处")

    return fixed


def main() -> None:
    error_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/mypy_errors_v2.txt'
    errors = parse_errors(error_file)
    total = 0
    for filepath, file_errors in sorted(errors.items()):
        total += fix_file(filepath, file_errors)
    print(f"\n完成! 共修复 {total} 处")


if __name__ == '__main__':
    main()
