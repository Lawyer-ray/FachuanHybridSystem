"""修复name-defined错误（缺少导入）"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent.parent

    logger.info("开始修复name-defined错误...")

    # 运行mypy
    result = subprocess.run(
        ["mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=backend_path, timeout=300
    )

    output = result.stdout + result.stderr

    # 提取name-defined错误
    errors: dict[str, list[tuple[int, str]]] = defaultdict(list)

    for line in output.split("\n"):
        if "name-defined" in line and "error:" in line:
            match = re.match(r"^(apps/[^:]+):(\d+):", line)
            if match:
                file_path = match.group(1)
                line_no = int(match.group(2))

                # 提取未定义的名称
                name_match = re.search(r'Name "([^"]+)" is not defined', line)
                if name_match:
                    name = name_match.group(1)
                    errors[file_path].append((line_no, name))

    logger.info(f"找到 {sum(len(v) for v in errors.values())} 个name-defined错误")
    logger.info(f"涉及 {len(errors)} 个文件")

    # 统计最常见的未定义名称
    name_counts: dict[str, int] = defaultdict(int)
    for file_errors in errors.values():
        for _, name in file_errors:
            name_counts[name] += 1

    logger.info("\n最常见的未定义名称:")
    for name, count in sorted(name_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
        logger.info(f"  {name}: {count}")

    # 常见类型的导入映射
    import_map = {
        "Dict": "from typing import Dict",
        "List": "from typing import List",
        "Set": "from typing import Set",
        "Tuple": "from typing import Tuple",
        "Optional": "from typing import Optional",
        "Union": "from typing import Union",
        "Callable": "from typing import Callable",
        "Type": "from typing import Type",
        "TypeVar": "from typing import TypeVar",
        "Generic": "from typing import Generic",
        "Protocol": "from typing import Protocol",
        "Literal": "from typing import Literal",
        "Final": "from typing import Final",
        "ClassVar": "from typing import ClassVar",
    }

    # 修复文件
    fixed_count = 0
    for file_path, file_errors in errors.items():
        full_path = backend_path / file_path
        if not full_path.exists():
            continue

        # 收集需要导入的名称
        names_to_import = set()
        for _, name in file_errors:
            if name in import_map:
                names_to_import.add(name)

        if not names_to_import:
            continue

        # 读取文件
        content = full_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        # 查找typing导入行
        typing_import_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("from typing import"):
                typing_import_idx = i
                break

        if typing_import_idx >= 0:
            # 已有typing导入，添加缺失的名称
            import_line = lines[typing_import_idx]

            # 解析现有导入
            if "(" in import_line:
                # 多行导入
                end_idx = typing_import_idx
                for j in range(typing_import_idx, len(lines)):
                    if ")" in lines[j]:
                        end_idx = j
                        break

                # 在)之前添加
                for name in sorted(names_to_import):
                    if name not in content:
                        continue
                    lines[end_idx] = lines[end_idx].replace(")", f", {name})")
                    fixed_count += 1
                    logger.info(f"修复 {file_path} - 添加 {name} 导入")
            else:
                # 单行导入
                for name in sorted(names_to_import):
                    if name not in content:
                        continue
                    if name not in import_line:
                        lines[typing_import_idx] += f", {name}"
                        fixed_count += 1
                        logger.info(f"修复 {file_path} - 添加 {name} 导入")

            # 写回文件
            full_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info(f"修复完成，共修复 {fixed_count} 个错误")


if __name__ == "__main__":
    main()
