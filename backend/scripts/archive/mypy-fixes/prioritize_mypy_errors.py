#!/usr/bin/env python3
"""
mypy 错误优先级分析脚本

根据模块重要性和错误类型，对 mypy 错误进行优先级排序，并生成修复建议。

用法:
    # 从 stdin 读取 mypy 输出
    mypy apps/ --strict 2>&1 | python scripts/prioritize_mypy_errors.py

    # 从文件读取
    python scripts/prioritize_mypy_errors.py < mypy_output.txt

    # 直接运行（会自动执行 mypy）
    python scripts/prioritize_mypy_errors.py --run

    # 生成 JSON 格式输出
    python scripts/prioritize_mypy_errors.py --run --json > priorities.json
"""

import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypedDict


class ErrorConfig(TypedDict):
    """错误类型配置"""

    priority: int
    label: str
    suggestion: str


@dataclass
class ErrorPriority:
    """错误优先级信息"""

    file: str
    line: int
    col: int
    code: str
    message: str
    priority: int  # 1=Critical, 2=High, 3=Medium, 4=Low
    priority_label: str
    module: str
    fix_suggestion: str


# 模块优先级配置（数字越小优先级越高）
MODULE_PRIORITY = {
    "core": 1,  # 核心基础设施
    "litigation_ai": 2,  # AI 核心功能
    "cases": 2,  # 业务核心
    "documents": 2,  # 业务核心
    "contracts": 2,  # 业务核心
    "clients": 3,  # 业务支持
    "automation": 4,  # 自动化模块
}

# 错误类型优先级和修复建议
ERROR_TYPE_CONFIG: dict[str, ErrorConfig] = {
    # Critical - 代码错误，可能导致运行时崩溃
    "name-defined": {
        "priority": 1,
        "label": "Critical",
        "suggestion": "变量未定义，检查是否缺少导入或变量声明。可能是重构遗留问题，需要补充定义或删除无效代码。",
    },
    "attr-defined": {
        "priority": 1,
        "label": "Critical",
        "suggestion": "属性不存在。对于 Django Model 动态属性（如 model.id），使用 cast() 或创建类型存根文件。",
    },
    "call-arg": {
        "priority": 1,
        "label": "Critical",
        "suggestion": "函数调用参数错误，检查参数数量和类型是否匹配函数签名。",
    },
    "index": {
        "priority": 1,
        "label": "Critical",
        "suggestion": "索引类型错误，确保使用正确的索引类型（通常是 int 或 str）。",
    },
    # High - 类型安全问题，应尽快修复
    "no-untyped-def": {
        "priority": 2,
        "label": "High",
        "suggestion": "函数缺少类型注解。为所有参数和返回值添加类型注解，如 def func(x: str) -> int: ...",
    },
    "no-untyped-call": {
        "priority": 2,
        "label": "High",
        "suggestion": "调用了无类型注解的函数。为被调用函数添加类型注解，或使用 # type: ignore[no-untyped-call]。",
    },
    "arg-type": {
        "priority": 2,
        "label": "High",
        "suggestion": "参数类型不匹配。检查传入参数的类型是否符合函数签名，可能需要类型转换。",
    },
    "return-value": {
        "priority": 2,
        "label": "High",
        "suggestion": "返回值类型不匹配。检查返回值类型是否符合函数签名，可能需要调整返回类型注解。",
    },
    "assignment": {
        "priority": 2,
        "label": "High",
        "suggestion": "赋值类型不兼容。检查赋值两侧的类型是否匹配，可能需要类型转换或调整类型注解。",
    },
    # Medium - 类型注解不完整
    "type-arg": {
        "priority": 3,
        "label": "Medium",
        "suggestion": "泛型类型参数缺失。将 dict 改为 dict[str, Any]，list 改为 list[Any] 或具体类型。",
    },
    "no-any-return": {
        "priority": 3,
        "label": "Medium",
        "suggestion": "函数返回 Any 类型。明确指定返回类型，或使用 cast() 转换为具体类型。",
    },
    "return": {
        "priority": 3,
        "label": "Medium",
        "suggestion": "返回语句问题。检查是否在应该返回值的函数中缺少 return，或在 -> None 函数中返回了值。",
    },
    "var-annotated": {
        "priority": 3,
        "label": "Medium",
        "suggestion": "变量需要类型注解。为变量添加类型注解，如 result: dict[str, Any] = {}。",
    },
    # Low - 其他类型问题
    "misc": {"priority": 4, "label": "Low", "suggestion": "其他类型问题，查看具体错误信息进行修复。"},
    "override": {"priority": 4, "label": "Low", "suggestion": "方法重写签名不匹配。确保子类方法签名与父类一致。"},
    "union-attr": {
        "priority": 4,
        "label": "Low",
        "suggestion": "Union 类型属性访问问题。使用 isinstance() 检查或类型收窄。",
    },
}


def run_mypy() -> str:
    """运行 mypy 并返回输出"""
    backend_path = Path(__file__).parent.parent
    result = subprocess.run(["mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=backend_path)
    return result.stdout + result.stderr


def parse_mypy_output(lines: list[str]) -> list[dict[str, str]]:
    """解析 mypy 输出，提取错误信息"""
    errors = []
    error_pattern = re.compile(
        r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+"
        r"(?P<severity>\w+):\s+(?P<message>.+?)\s+\[(?P<code>[^\]]+)\]"
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = error_pattern.match(line)
        if match:
            errors.append(match.groupdict())

    return errors


def get_module_from_file(file_path: str) -> str:
    """从文件路径提取模块名"""
    if file_path.startswith("apps/"):
        parts = file_path.split("/")
        if len(parts) >= 2:
            return parts[1]
    return "other"


def calculate_priority(error: dict[str, str]) -> ErrorPriority:
    """计算错误优先级"""
    module = get_module_from_file(error["file"])
    error_code = error["code"]

    # 获取错误类型配置
    error_config: ErrorConfig = ERROR_TYPE_CONFIG.get(
        error_code, {"priority": 4, "label": "Low", "suggestion": "查看具体错误信息进行修复。"}
    )

    # 基础优先级（来自错误类型）
    base_priority: int = error_config["priority"]

    # 模块优先级调整
    module_priority = MODULE_PRIORITY.get(module, 5)

    # 综合优先级：错误类型优先级 + 模块优先级调整
    # 核心模块的错误优先级提升
    if module_priority <= 2:  # core, litigation_ai, cases, documents, contracts
        if base_priority > 1:
            base_priority = max(1, base_priority - 1)  # 提升一级

    # 自动化模块的低优先级错误可以降级
    if module_priority >= 4 and base_priority >= 3:
        base_priority = min(4, base_priority + 1)  # 降低一级

    return ErrorPriority(
        file=error["file"],
        line=int(error["line"]),
        col=int(error["col"]),
        code=error_code,
        message=error["message"],
        priority=base_priority,
        priority_label=error_config["label"],
        module=module,
        fix_suggestion=error_config["suggestion"],
    )


def group_by_priority(priorities: list[ErrorPriority]) -> dict[int, list[ErrorPriority]]:
    """按优先级分组"""
    groups: dict[int, list[ErrorPriority]] = defaultdict(list)
    for p in priorities:
        groups[p.priority].append(p)
    return dict(groups)


def print_priority_report(priorities: list[ErrorPriority], json_output: bool = False) -> None:
    """打印优先级分析报告"""
    if not priorities:
        print("✅ 未检测到 mypy 错误！")
        return

    if json_output:
        # JSON 格式输出
        output = {"total_errors": len(priorities), "priorities": [asdict(p) for p in priorities]}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 文本格式输出
    groups = group_by_priority(priorities)

    print("=" * 80)
    print("MYPY 错误优先级分析报告")
    print("=" * 80)
    print()
    print(f"总错误数: {len(priorities)}")
    print()

    # 优先级统计
    print("-" * 80)
    print("优先级分布")
    print("-" * 80)
    priority_labels = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}
    for priority in sorted(groups.keys()):
        count = len(groups[priority])
        percentage = (count / len(priorities)) * 100
        label = priority_labels.get(priority, "Unknown")
        bar = "█" * int(percentage / 2)
        print(f"{label:10s} (P{priority}) {count:5d} ({percentage:5.1f}%) {bar}")
    print()

    # 按优先级显示错误详情
    for priority in sorted(groups.keys()):
        errors = groups[priority]
        label = priority_labels.get(priority, "Unknown")

        print("-" * 80)
        print(f"{label} 优先级错误 (P{priority}) - {len(errors)} 个")
        print("-" * 80)
        print()

        # 按模块分组统计
        module_counts: dict[str, int] = defaultdict(int)
        for e in errors:
            module_counts[e.module] += 1

        print(
            f"涉及模块: {', '.join(f'{m}({c})' for m, c in sorted(module_counts.items(), key=lambda x: x[1], reverse=True))}"
        )
        print()

        # 按错误类型分组统计
        code_counts: dict[str, int] = defaultdict(int)
        for e in errors:
            code_counts[e.code] += 1

        print("错误类型分布:")
        for code, count in sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {code:30s} {count:4d}")
        print()

        # 显示前 10 个错误示例
        print("错误示例 (前 10 个):")
        for i, error in enumerate(errors[:10], 1):
            print(f"\n{i}. [{error.code}] {error.file}:{error.line}:{error.col}")
            print(f"   模块: {error.module}")
            print(f"   错误: {error.message}")
            print(f"   建议: {error.fix_suggestion}")

        if len(errors) > 10:
            print(f"\n   ... 还有 {len(errors) - 10} 个 {label} 优先级错误")
        print()

    # 修复建议总结
    print("-" * 80)
    print("修复建议总结")
    print("-" * 80)
    print()
    print("1. 优先修复 Critical 和 High 优先级错误")
    print("   - Critical: 可能导致运行时错误，必须立即修复")
    print("   - High: 类型安全问题，应尽快修复")
    print()
    print("2. 按模块优先级修复")
    print("   - 核心模块 (core, litigation_ai): 最高优先级")
    print("   - 业务模块 (cases, documents, contracts): 高优先级")
    print("   - 支持模块 (clients): 中优先级")
    print("   - 自动化模块 (automation): 可以最后处理")
    print()
    print("3. 使用批量修复脚本")
    print("   - fix_logger_imports.py: 修复 logger 未定义")
    print("   - fix_generic_types.py: 修复泛型类型参数缺失")
    print("   - fix_return_types.py: 修复返回类型缺失")
    print()
    print("4. 对于 Django ORM 类型问题")
    print("   - 使用 cast() 处理 Model 动态属性")
    print("   - 创建类型存根文件 (.pyi)")
    print("   - 为 QuerySet 添加泛型参数")
    print()
    print("5. 对于第三方库类型问题")
    print("   - 在 mypy.ini 中配置 ignore_missing_imports")
    print("   - 创建简单的类型存根文件")
    print("   - 使用 # type: ignore 注释（最后手段）")
    print()


def main() -> None:
    """主函数"""
    json_output = "--json" in sys.argv

    # 检查是否使用 --run 参数
    if "--run" in sys.argv:
        if not json_output:
            print("正在运行 mypy apps/ --strict...")
            print()
        output = run_mypy()
        lines = output.split("\n")
    elif sys.stdin.isatty():
        print("用法:")
        print("  mypy apps/ --strict 2>&1 | python scripts/prioritize_mypy_errors.py")
        print("  python scripts/prioritize_mypy_errors.py < mypy_output.txt")
        print("  python scripts/prioritize_mypy_errors.py --run")
        print("  python scripts/prioritize_mypy_errors.py --run --json > priorities.json")
        sys.exit(1)
    else:
        lines = sys.stdin.readlines()

    errors = parse_mypy_output(lines)
    priorities = [calculate_priority(e) for e in errors]

    # 按优先级排序（优先级数字小的在前）
    priorities.sort(key=lambda p: (p.priority, p.module, p.file, p.line))

    print_priority_report(priorities, json_output)


if __name__ == "__main__":
    main()
