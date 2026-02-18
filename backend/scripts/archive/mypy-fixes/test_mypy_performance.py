#!/usr/bin/env python3
"""
测试 mypy 性能

测量全量检查和增量检查的时间，确保满足性能要求：
- 全量检查 < 5 分钟
- 增量检查比全量检查快至少 50%
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path


def measure_full_check() -> float:
    """测量全量检查时间"""
    print("=" * 60)
    print("测试 1: 全量检查性能")
    print("=" * 60)

    # 清除 mypy 缓存以测量真正的全量检查时间
    backend_path = Path(__file__).parent.parent
    cache_dir = backend_path / ".mypy_cache"
    if cache_dir.exists():
        print(f"清除 mypy 缓存: {cache_dir}")
        shutil.rmtree(cache_dir)
        print()

    print("运行: mypy apps/ --strict (无缓存)")
    print()

    start = time.time()
    result = subprocess.run(["mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=backend_path)
    duration = time.time() - start

    print(f"✓ 全量检查完成")
    print(f"  时间: {duration:.2f} 秒 ({duration/60:.2f} 分钟)")
    print(f"  返回码: {result.returncode}")

    if result.returncode == 0:
        print(f"  状态: ✓ 无类型错误")
    else:
        # 统计错误数
        error_lines = [line for line in result.stdout.split("\n") if "error:" in line]
        print(f"  状态: ✗ 发现 {len(error_lines)} 个错误")

    print()
    return duration


def measure_incremental_check() -> float:
    """测量增量检查时间"""
    print("=" * 60)
    print("测试 2: 增量检查性能")
    print("=" * 60)
    print("运行: mypy apps/ --strict (使用缓存)")
    print()

    backend_path = Path(__file__).parent.parent

    start = time.time()
    result = subprocess.run(["mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=backend_path)
    duration = time.time() - start

    print(f"✓ 增量检查完成")
    print(f"  时间: {duration:.2f} 秒 ({duration/60:.2f} 分钟)")
    print(f"  返回码: {result.returncode}")

    if result.returncode == 0:
        print(f"  状态: ✓ 无类型错误")
    else:
        error_lines = [line for line in result.stdout.split("\n") if "error:" in line]
        print(f"  状态: ✗ 发现 {len(error_lines)} 个错误")

    print()
    return duration


def main():
    print("\n" + "=" * 60)
    print("Mypy 性能测试")
    print("=" * 60)
    print()

    # 测量全量检查时间
    full_duration = measure_full_check()

    # 测量增量检查时间（第二次运行，使用缓存）
    incremental_duration = measure_incremental_check()

    # 性能分析
    print("=" * 60)
    print("性能分析")
    print("=" * 60)

    # 检查全量检查是否 < 5 分钟
    full_check_limit = 300  # 5 分钟 = 300 秒
    if full_duration < full_check_limit:
        print(f"✓ 全量检查时间: {full_duration:.2f}s < {full_check_limit}s (5分钟)")
        print(f"  满足性能要求")
    else:
        print(f"✗ 全量检查时间: {full_duration:.2f}s >= {full_check_limit}s (5分钟)")
        print(f"  不满足性能要求")

    print()

    # 检查增量检查是否比全量检查快至少 50%
    speedup = (full_duration - incremental_duration) / full_duration * 100
    if speedup >= 50:
        print(f"✓ 增量检查加速: {speedup:.1f}% >= 50%")
        print(f"  满足性能要求")
    else:
        print(f"✗ 增量检查加速: {speedup:.1f}% < 50%")
        print(f"  不满足性能要求")

    print()
    print("=" * 60)
    print("性能总结")
    print("=" * 60)
    print(f"全量检查时间: {full_duration:.2f}s ({full_duration/60:.2f}分钟)")
    print(f"增量检查时间: {incremental_duration:.2f}s ({incremental_duration/60:.2f}分钟)")
    print(f"加速比例: {speedup:.1f}%")
    print()

    # 返回状态码
    if full_duration < full_check_limit and speedup >= 50:
        print("✓ 所有性能测试通过")
        return 0
    else:
        print("✗ 部分性能测试未通过")
        return 1


if __name__ == "__main__":
    sys.exit(main())
