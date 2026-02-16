#!/usr/bin/env python3
"""批量修复core/config模块的简单类型错误"""

import re
from pathlib import Path
from typing import List, Tuple


def fix_optional_dict_params(content: str) -> Tuple[str, int]:
    """修复 Dict[str, Any] = None 为 Optional[Dict[str, Any]] = None"""
    count = 0

    # 修复函数参数中的 Dict[str, Any] = None
    pattern = r"(\w+):\s*Dict\[str,\s*Any\]\s*=\s*None"
    matches = list(re.finditer(pattern, content))

    if matches:
        # 确保导入 Optional
        if "from typing import" in content and "Optional" not in content:
            content = content.replace("from typing import", "from typing import Optional,")
        elif "from typing import" not in content:
            # 在文件开头添加导入
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    lines.insert(i, "from typing import Optional, Dict, Any")
                    break
            content = "\n".join(lines)

        # 替换所有匹配
        for match in reversed(matches):
            param_name = match.group(1)
            start, end = match.span()
            content = content[:start] + f"{param_name}: Optional[Dict[str, Any]] = None" + content[end:]
            count += 1

    return content, count


def fix_missing_return_types(content: str) -> Tuple[str, int]:
    """为缺少返回类型的函数添加 -> None"""
    count = 0

    # 匹配 def __post_init__(self): 这样的函数
    pattern = r"(def\s+\w+\([^)]*\)):\s*\n"

    def replace_func(match: re.Match) -> str:
        nonlocal count
        func_def = match.group(1)
        # 检查是否已经有返回类型
        if "->" not in func_def:
            count += 1
            return f"{func_def} -> None:\n"
        return match.group(0)

    content = re.sub(pattern, replace_func, content)
    return content, count


def fix_generic_types(content: str) -> Tuple[str, int]:
    """修复泛型类型参数缺失"""
    count = 0

    # 修复 deque 类型
    pattern = r":\s*deque\s*="
    matches = list(re.finditer(pattern, content))
    for match in reversed(matches):
        start, end = match.span()
        content = content[:start] + ": deque[Any] =" + content[end:]
        count += 1

    # 修复 Callable 类型（无参数）
    pattern = r":\s*Callable\s*\)"
    matches = list(re.finditer(pattern, content))
    for match in reversed(matches):
        start, end = match.span()
        content = content[:start] + ": Callable[..., Any])" + content[end:]
        count += 1

    # 确保导入 Any
    if count > 0 and "from typing import" in content and "Any" not in content:
        content = content.replace("from typing import", "from typing import Any,")

    return content, count


def fix_var_annotations(content: str) -> Tuple[str, int]:
    """修复变量类型注解缺失"""
    count = 0

    # 修复 path = []
    if "path = []" in content and "path: list[" not in content:
        content = content.replace("path = []", "path: list[str] = []")
        count += 1

    # 修复 env_vars = {}
    if "env_vars = {}" in content and "env_vars: dict[" not in content:
        content = content.replace("env_vars = {}", "env_vars: dict[str, Any] = {}")
        count += 1

    # 修复 _analysis_cache = {}
    if "_analysis_cache = {}" in content and "_analysis_cache: dict[" not in content:
        content = content.replace("_analysis_cache = {}", "_analysis_cache: dict[str, Any] = {}")
        count += 1

    # 修复 recent_hits = []
    if "recent_hits = []" in content and "recent_hits: list[" not in content:
        content = content.replace("self.recent_hits = []", "self.recent_hits: list[Any] = []")
        count += 1

    # 修复其他常见的字典和列表初始化
    patterns = [
        (r"(\s+)levels = \{\}", r"\1levels: dict[str, int] = {}"),
        (r"(\s+)metadata_dict = \{\}", r"\1metadata_dict: dict[str, Any] = {}"),
        (r"(\s+)nested = \{\}", r"\1nested: dict[str, Any] = {}"),
        (r"(\s+)snapshots = \[\]", r"\1snapshots: list[Any] = []"),
        (r"(\s+)_cache = \{\}", r"\1_cache: dict[str, Any] = {}"),
        (r"(\s+)_access_times = \{\}", r"\1_access_times: dict[str, float] = {}"),
        (r"(\s+)_metrics = \{\}", r"\1_metrics: dict[str, Any] = {}"),
        (r"(\s+)_dependency_graph = \{\}", r"\1_dependency_graph: dict[str, list[str]] = {}"),
        (r"(\s+)cache_config = ", r"\1cache_config: dict[str, Any] = "),
        (r"(\s+)perf_config = ", r"\1perf_config: dict[str, Any] = "),
        (r"(\s+)dep_config = ", r"\1dep_config: dict[str, Any] = "),
        (r"(\s+)rules_config = ", r"\1rules_config: list[Any] = "),
        (r"(\s+)applicable_specs = \[\]", r"\1applicable_specs: list[str] = []"),
        (r"(\s+)_file_pattern_cache = \{\}", r"\1_file_pattern_cache: dict[str, list[str]] = {}"),
        (r"(\s+)items = \[\]", r"\1items: list[Any] = []"),
        (r"(\s+)result = \{\}", r"\1result: dict[str, Any] = {}"),
        (r"(\s+)template_config = \{\}", r"\1template_config: dict[str, Any] = {}"),
        (r"(\s+)dep_type_counts = ", r"\1dep_type_counts: dict[str, int] = "),
        (r"(\s+)graph_data = \{", r"\1graph_data: dict[str, Any] = {"),
    ]

    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            count += 1
            content = new_content

    return content, count


def process_file(file_path: Path) -> dict[str, int]:
    """处理单个文件"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        stats = {"optional_params": 0, "return_types": 0, "generic_types": 0, "var_annotations": 0}

        # 应用所有修复
        content, count = fix_optional_dict_params(content)
        stats["optional_params"] = count

        content, count = fix_missing_return_types(content)
        stats["return_types"] = count

        content, count = fix_generic_types(content)
        stats["generic_types"] = count

        content, count = fix_var_annotations(content)
        stats["var_annotations"] = count

        # 只有在内容改变时才写入
        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            return stats

        return {}

    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return {}


def main() -> None:
    """主函数"""
    base_path = Path(__file__).parent.parent / "apps" / "core" / "config"

    if not base_path.exists():
        print(f"错误: 路径不存在 {base_path}")
        return

    # 获取所有Python文件
    py_files = list(base_path.rglob("*.py"))

    print(f"找到 {len(py_files)} 个Python文件")

    total_stats = {
        "files_modified": 0,
        "optional_params": 0,
        "return_types": 0,
        "generic_types": 0,
        "var_annotations": 0,
    }

    for py_file in py_files:
        stats = process_file(py_file)
        if stats:
            total_stats["files_modified"] += 1
            for key in ["optional_params", "return_types", "generic_types", "var_annotations"]:
                total_stats[key] += stats.get(key, 0)

            if sum(stats.values()) > 0:
                print(f"✓ {py_file.relative_to(base_path)}: {stats}")

    print("\n修复统计:")
    print(f"  修改文件数: {total_stats['files_modified']}")
    print(f"  Optional参数修复: {total_stats['optional_params']}")
    print(f"  返回类型修复: {total_stats['return_types']}")
    print(f"  泛型类型修复: {total_stats['generic_types']}")
    print(f"  变量注解修复: {total_stats['var_annotations']}")
    print(f"  总修复数: {sum(v for k, v in total_stats.items() if k != 'files_modified')}")


if __name__ == "__main__":
    main()
