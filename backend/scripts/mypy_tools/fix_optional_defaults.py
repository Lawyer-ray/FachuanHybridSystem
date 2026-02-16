"""修复Dict/List等类型参数默认值为None的问题"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_optional_defaults(backend_path: Path) -> int:
    """修复Incompatible default错误"""

    # 运行mypy找出所有Incompatible default错误
    result = subprocess.run(
        ["mypy", "apps/", "--strict"], capture_output=True, text=True, cwd=backend_path, timeout=300
    )

    # 收集需要修复的文件和行号
    fixes: dict[Path, list[int]] = {}

    lines = result.stdout.split("\n")
    for i, line in enumerate(lines):
        if "Incompatible default for argument" in line:
            # 向前查找文件路径和行号
            for j in range(max(0, i - 5), i + 1):
                if lines[j].startswith("apps/") and ":" in lines[j]:
                    parts = lines[j].split(":")
                    if len(parts) >= 3:
                        file_path_str = parts[0]
                        try:
                            line_num = int(parts[1])
                            file_path = backend_path / file_path_str
                            if file_path.exists():
                                if file_path not in fixes:
                                    fixes[file_path] = []
                                fixes[file_path].append(line_num)
                                break
                        except ValueError:
                            continue

    logger.info(f"找到{len(fixes)}个文件需要修复")

    fixed_count = 0
    for file_path, line_nums in sorted(fixes.items()):
        content = file_path.read_text(encoding="utf-8")
        lines_list = content.split("\n")

        modified = False
        for line_num in sorted(set(line_nums), reverse=True):  # 从后往前修复,避免行号变化
            if line_num <= 0 or line_num > len(lines_list):
                continue

            line_idx = line_num - 1
            line = lines_list[line_idx]

            # 查找需要修复的模式: Type = None
            # 常见模式: Dict[str, Any] = None, List[str] = None等
            patterns = [
                (r"(\w+:\s*)(Dict\[[\w\s,\[\]]+\])(\s*=\s*None)", r"\1Optional[\2]\3"),
                (r"(\w+:\s*)(List\[[\w\s,\[\]]+\])(\s*=\s*None)", r"\1Optional[\2]\3"),
                (r"(\w+:\s*)(Set\[[\w\s,\[\]]+\])(\s*=\s*None)", r"\1Optional[\2]\3"),
                (r"(\w+:\s*)(Tuple\[[\w\s,\[\]]+\])(\s*=\s*None)", r"\1Optional[\2]\3"),
                (r"(\w+:\s*)(dict\[[\w\s,\[\]]+\])(\s*=\s*None)", r"\1Optional[\2]\3"),
                (r"(\w+:\s*)(list\[[\w\s,\[\]]+\])(\s*=\s*None)", r"\1Optional[\2]\3"),
            ]

            for pattern, replacement in patterns:
                new_line = re.sub(pattern, replacement, line)
                if new_line != line:
                    lines_list[line_idx] = new_line
                    modified = True
                    fixed_count += 1
                    logger.info(f"修复 {file_path.relative_to(backend_path)}:{line_num}")
                    break

        if modified:
            file_path.write_text("\n".join(lines_list), encoding="utf-8")

    return fixed_count


def main() -> None:
    backend_path = Path(__file__).parent.parent.parent

    logger.info("=" * 60)
    logger.info("修复Optional默认值问题")
    logger.info("=" * 60)

    fixed = fix_optional_defaults(backend_path)

    logger.info("=" * 60)
    logger.info(f"修复完成,共修复{fixed}处")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
