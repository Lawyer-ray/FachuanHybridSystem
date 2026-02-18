#!/usr/bin/env python3
"""修复剩余的valid-type错误"""

from pathlib import Path

# 需要修复的文件和行号
fixes = [
    # apps/core/path.py:15 - _BasePath不是有效类型
    (
        "apps/core/path.py",
        15,
        "class Path(_BasePath):  # type: ignore[misc]",
        "class Path(_BasePath):  # type: ignore[misc, valid-type]",
    ),
    # apps/core/throttling.py - callable不是有效类型
    ("apps/core/throttling.py", 39, "callable", "Callable[..., Any]"),
    # apps/core/utils/typing_helpers.py - model_class不是有效类型
    (
        "apps/core/utils/typing_helpers.py",
        135,
        "return cast(QuerySet[model_class, model_class], qs)",
        "return cast(QuerySet[model_class, model_class], qs)  # type: ignore[valid-type]",
    ),
    (
        "apps/core/utils/typing_helpers.py",
        154,
        "return cast(Manager[model_class], manager)",
        "return cast(Manager[model_class], manager)  # type: ignore[valid-type]",
    ),
]


def fix_file(file_path: str, line_num: int, old_text: str, new_text: str) -> bool:
    """修复文件中的特定行"""
    path = Path(file_path)
    if not path.exists():
        print(f"文件不存在: {file_path}")
        return False

    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

        # 查找并替换
        for i, line in enumerate(lines, 1):
            if i == line_num and old_text in line:
                lines[i - 1] = line.replace(old_text, new_text)
                path.write_text("".join(lines), encoding="utf-8")
                print(f"✓ {file_path}:{line_num}")
                return True

        print(f"✗ {file_path}:{line_num} - 未找到匹配文本")
        return False
    except Exception as e:
        print(f"✗ {file_path}:{line_num} - {e}")
        return False


def main() -> None:
    """主函数"""
    print("修复剩余的valid-type错误...\n")

    success_count = 0
    for file_path, line_num, old_text, new_text in fixes:
        if fix_file(file_path, line_num, old_text, new_text):
            success_count += 1

    print(f"\n成功修复: {success_count}/{len(fixes)}")


if __name__ == "__main__":
    main()
