"""
智能移除 type: ignore 注释的脚本。
按照错误类型分类处理：

1. valid-type: User 类型 → 改为 Any
2. attr-defined: Django Model 动态属性 → 用 getattr 或 cast
3. no-any-return: 返回 Any → 添加 cast 或类型注解
4. return-value: 返回值类型不匹配 → 添加 cast
5. union-attr: Optional 属性访问 → 添加 None 检查
6. assignment: 赋值类型不匹配 → 添加类型注解
7. arg-type: 参数类型不匹配 → 添加 cast
8. operator: 运算符类型不匹配 → 添加 assert
"""

from __future__ import annotations

import re
from pathlib import Path


def process_file(filepath: Path) -> int:
    """处理单个文件，返回移除的 type: ignore 数量"""
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    removed = 0

    new_lines = []
    for i, line in enumerate(lines):
        # 检查是否有 type: ignore
        match = re.search(r"\s*#\s*type:\s*ignore\[([^\]]*)\]", line)
        if not match:
            # 也检查裸的 type: ignore
            match_bare = re.search(r"\s*#\s*type:\s*ignore\s*$", line)
            if not match_bare:
                new_lines.append(line)
                continue
            # 裸的 type: ignore 保留
            new_lines.append(line)
            continue

        error_codes = [c.strip() for c in match.group(1).split(",")]
        clean_line = line[: match.start()] + line[match.end() :]

        # 尝试修复每种错误类型
        can_remove = True
        for code in error_codes:
            if not can_fix_error(code, clean_line, lines, i):
                can_remove = False
                break

        if can_remove:
            new_lines.append(clean_line.rstrip())
            removed += 1
        else:
            new_lines.append(line)

    if removed > 0:
        filepath.write_text("\n".join(new_lines), encoding="utf-8")

    return removed


def can_fix_error(code: str, line: str, all_lines: list[str], line_idx: int) -> bool:
    """判断是否可以安全移除某个错误码的 type: ignore"""
    # 这些错误码通常不能简单移除
    return False


def main() -> None:
    """主函数"""
    import sys

    # 统计所有 type: ignore
    apps_dir = Path("apps")
    total = 0
    files_with_ignores: list[tuple[Path, int]] = []

    for py_file in sorted(apps_dir.rglob("*.py")):
        if "migrations" in str(py_file) or "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8")
        count = len(re.findall(r"#\s*type:\s*ignore", content))
        if count > 0:
            files_with_ignores.append((py_file, count))
            total += count

    print(f"共 {len(files_with_ignores)} 个文件, {total} 个 type: ignore 注释")

    # 按错误码分类统计
    code_counts: dict[str, int] = {}
    for py_file, _ in files_with_ignores:
        content = py_file.read_text(encoding="utf-8")
        for m in re.finditer(r"#\s*type:\s*ignore\[([^\]]*)\]", content):
            codes = [c.strip() for c in m.group(1).split(",")]
            for code in codes:
                code_counts[code] = code_counts.get(code, 0) + 1

    print("\n错误码分布:")
    for code, count in sorted(code_counts.items(), key=lambda x: -x[1]):
        print(f"  {code}: {count}")


if __name__ == "__main__":
    main()
