#!/usr/bin/env python3
"""
扫描 automation 模块剩余子模块的类型错误
"""
import subprocess
from collections import defaultdict
from pathlib import Path


def run_mypy_on_path(path: Path) -> tuple[int, str]:
    """对指定路径运行 mypy 并返回错误数和输出"""
    result = subprocess.run(
        ["mypy", str(path), "--strict"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
    )

    # 统计错误数
    lines = result.stdout.strip().split("\n")
    error_count = 0
    for line in lines:
        if line.startswith("Found "):
            # 解析 "Found X errors in Y files"
            parts = line.split()
            if len(parts) >= 2:
                try:
                    error_count = int(parts[1])
                except ValueError:
                    pass

    return error_count, result.stdout


def main():
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / "apps" / "automation"

    # 定义所有需要扫描的子模块
    submodules = {
        # 顶层文件
        "root_files": automation_path,
        # services 子模块（排除已修复的）
        "services/admin": automation_path / "services" / "admin",
        "services/ai": automation_path / "services" / "ai",
        "services/captcha": automation_path / "services" / "captcha",
        "services/chat": automation_path / "services" / "chat",
        "services/court_document_recognition": automation_path / "services" / "court_document_recognition",
        "services/document": automation_path / "services" / "document",
        "services/fee_notice": automation_path / "services" / "fee_notice",
        "services/image_rotation": automation_path / "services" / "image_rotation",
        "services/insurance": automation_path / "services" / "insurance",
        "services/litigation": automation_path / "services" / "litigation",
        "services/ocr": automation_path / "services" / "ocr",
        "services/preservation_date": automation_path / "services" / "preservation_date",
        "services/token": automation_path / "services" / "token",
        "services/root_files": automation_path / "services",
        # 其他子模块
        "admin": automation_path / "admin",
        "api": automation_path / "api",
        "integrations": automation_path / "integrations",
        "models": automation_path / "models",
        "schemas": automation_path / "schemas",
        "tasking": automation_path / "tasking",
        "tasks_impl": automation_path / "tasks_impl",
        "usecases": automation_path / "usecases",
        "utils": automation_path / "utils",
        "workers": automation_path / "workers",
    }

    # 扫描每个子模块
    results = {}
    total_errors = 0

    print("=" * 80)
    print("扫描 automation 模块剩余子模块的类型错误")
    print("=" * 80)
    print()

    for name, path in sorted(submodules.items()):
        if not path.exists():
            print(f"⚠️  {name}: 路径不存在")
            continue

        # 对于 root_files，只扫描直接的 .py 文件
        if name.endswith("root_files"):
            py_files = list(path.glob("*.py"))
            if not py_files:
                continue

            # 分别扫描每个文件并汇总
            error_count = 0
            for py_file in py_files:
                count, _ = run_mypy_on_path(py_file)
                error_count += count

            results[name] = error_count
            total_errors += error_count
            print(f"📊 {name:50s}: {error_count:4d} 个错误")
        else:
            error_count, output = run_mypy_on_path(path)
            results[name] = error_count
            total_errors += error_count

            if error_count > 0:
                print(f"❌ {name:50s}: {error_count:4d} 个错误")
            else:
                print(f"✅ {name:50s}: {error_count:4d} 个错误")

    print()
    print("=" * 80)
    print(f"总计: {total_errors} 个错误")
    print("=" * 80)
    print()

    # 按错误数排序
    print("按错误数排序（降序）:")
    print("-" * 80)
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    for name, count in sorted_results:
        if count > 0:
            print(f"  {name:50s}: {count:4d} 个错误")

    print()
    print("建议修复顺序（从小到大）:")
    print("-" * 80)
    sorted_asc = sorted(results.items(), key=lambda x: x[1])
    for name, count in sorted_asc:
        if count > 0:
            print(f"  {name:50s}: {count:4d} 个错误")


if __name__ == "__main__":
    main()
