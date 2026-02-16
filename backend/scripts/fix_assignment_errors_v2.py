"""修复assignment错误 - Optional默认值问题"""

import re
import subprocess
from pathlib import Path

backend_path = Path(__file__).parent.parent


def get_assignment_errors():
    """获取所有assignment错误"""
    result = subprocess.run(["mypy", "--strict", "apps/"], cwd=backend_path, capture_output=True, text=True)
    output = result.stdout + result.stderr

    errors = []
    lines = output.split("\n")

    for i, line in enumerate(lines):
        # 匹配文件路径和行号
        match = re.match(r"(apps/[^:]+):(\d+):(\d+):", line)
        if match:
            # 检查是否是 Incompatible default 错误
            if "Incompatible default" in line or "default for argument" in line:
                # 检查后续行是否包含 [assignment]
                for j in range(i, min(i + 5, len(lines))):
                    if "[assignment]" in lines[j]:
                        file_path = match.group(1)
                        line_num = int(match.group(2))
                        col_num = int(match.group(3))
                        errors.append((file_path, line_num, col_num))
                        break

    return errors


def fix_assignment(file_path: str, line_num: int, col_num: int) -> bool:
    """修复单个assignment错误"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split("\n")

        if line_num < 1 or line_num > len(lines):
            return False

        target_line = lines[line_num - 1]
        original_line = target_line

        # 修复模式：arg: Type = None -> arg: Type | None = None
        # 支持多种类型

        # 模式1: 参数定义中的 Type = None
        # 匹配: config: dict[str, Any] = None
        pattern1 = r"(\w+):\s*([A-Za-z_][\w\[\], ]*?)\s*=\s*None"

        def replace_func(match):
            param_name = match.group(1)
            type_annotation = match.group(2).strip()
            return f"{param_name}: {type_annotation} | None = None"

        modified = re.sub(pattern1, replace_func, target_line)

        if modified != original_line:
            lines[line_num - 1] = modified
            full_path.write_text("\n".join(lines), encoding="utf-8")
            print(f"✓ 修复 {file_path}:{line_num}")
            print(f"  原: {original_line.strip()}")
            print(f"  新: {modified.strip()}")
            return True

        return False

    except Exception as e:
        print(f"✗ 修复失败 {file_path}:{line_num}: {e}")
        return False


def main():
    print("=" * 80)
    print("修复assignment错误（Optional默认值）")
    print("=" * 80)

    errors = get_assignment_errors()
    print(f"\n找到 {len(errors)} 个assignment错误\n")

    # 去重（同一行可能有多个错误）
    unique_errors = list(set((f, l) for f, l, c in errors))
    print(f"去重后: {len(unique_errors)} 个\n")

    fixed = 0
    for file_path, line_num in unique_errors:
        if fix_assignment(file_path, line_num, 0):
            fixed += 1

    print(f"\n✅ 完成: 修复了 {fixed} 个assignment错误")

    # 验证
    remaining = get_assignment_errors()
    print(f"剩余assignment错误: {len(remaining)}")

    # 检查总错误数
    result = subprocess.run(["mypy", "--strict", "apps/"], cwd=backend_path, capture_output=True, text=True)
    output = result.stdout + result.stderr
    for line in output.split("\n"):
        if "Found" in line and "errors" in line:
            print(f"\n{line}")
            break


if __name__ == "__main__":
    main()
