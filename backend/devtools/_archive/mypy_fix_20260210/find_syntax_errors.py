#!/usr/bin/env python3
"""查找所有语法错误的文件"""

import py_compile
import sys
from pathlib import Path


def check_file(file_path: Path) -> tuple[bool, str]:
    """检查单个文件的语法"""
    try:
        py_compile.compile(str(file_path), doraise=True)
        return True, ""
    except SyntaxError as e:
        return False, f"{file_path}:{e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"{file_path}: {e}"


def main():
    """主函数"""
    backend_dir = Path(__file__).parent
    apps_dir = backend_dir / "apps"

    errors = []
    for py_file in sorted(apps_dir.rglob("*.py")):
        success, error_msg = check_file(py_file)
        if not success:
            errors.append(error_msg)

    if errors:
        print(f"发现 {len(errors)} 个文件有语法错误:\n")
        for error in errors:
            print(error)
        sys.exit(1)
    else:
        print("✓ 所有文件语法检查通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
