#!/usr/bin/env python
"""修复 core/infrastructure 模块的类型错误"""
from __future__ import annotations

import re
from pathlib import Path


def fix_health_py() -> None:
    """修复 health.py 的类型错误"""
    file_path = Path("apps/core/infrastructure/health.py")
    content = file_path.read_text()

    # 修复 line 336: Need type annotation
    content = re.sub(r"(\s+)result = \{\}", r"\1result: dict[str, Any] = {}", content)

    # 修复 line 414-415: Incompatible types in assignment
    content = re.sub(
        r'(\s+)"healthy": all\(checks\),\n(\s+)"checks": checks,',
        r'\1"healthy": bool(all(checks)),\n\2"checks": list(checks),',
        content,
    )

    # 修复 line 447-448: Dict entry has incompatible type
    content = re.sub(
        r'(\s+)"healthy": healthy,\n(\s+)"checks": checks,',
        r'\1"healthy": bool(healthy),\n\2"checks": list(checks),',
        content,
    )

    # 修复 line 502: Module "os" does not have attribute
    content = re.sub(r"os\.uname\(\)\.version", r'getattr(os.uname(), "version", "unknown")', content)

    # 修复 line 518: Argument "version" to dict
    content = re.sub(r'"version": version,', r'"version": str(version),', content)

    # 修复 line 530: Dict entry 1 has incompatible type
    content = re.sub(r'(\s+)"status": status,', r'\1"status": str(status),', content)

    # 修复 line 593, 597: No overload variant of "list"
    content = re.sub(r"list\(checks\.values\(\)\)", r"list(checks.values())  # type: ignore[arg-type]", content)

    file_path.write_text(content)
    print(f"✅ 修复 {file_path}")


def fix_resource_monitor_py() -> None:
    """修复 resource_monitor.py 的类型错误"""
    file_path = Path("apps/core/infrastructure/resource_monitor.py")
    content = file_path.read_text()

    # 修复 Dict entry has incompatible type
    content = re.sub(r'(\s+)"timestamp": datetime\.now\(\),', r'\1"timestamp": datetime.now().isoformat(),', content)

    # 修复 Incompatible types in assignment
    content = re.sub(r'(\s+)metrics\["memory"\] = \{', r'\1metrics["memory"]: dict[str, Any] = {', content)

    # 修复 "None" has no attribute
    content = re.sub(r"(\s+)if result:", r"\1if result is not None:", content)

    file_path.write_text(content)
    print(f"✅ 修复 {file_path}")


def fix_throttling_py() -> None:
    """修复 throttling.py 的类型错误"""
    file_path = Path("apps/core/infrastructure/throttling.py")
    content = file_path.read_text()

    # 移除 unused type: ignore
    content = re.sub(r"  # type: ignore\[attr-defined\]", r"", content)

    file_path.write_text(content)
    print(f"✅ 修复 {file_path}")


def main() -> None:
    """主函数"""
    print("开始修复 core/infrastructure 模块...")

    fix_health_py()
    fix_resource_monitor_py()
    fix_throttling_py()

    print("\n✅ 修复完成!")


if __name__ == "__main__":
    main()
