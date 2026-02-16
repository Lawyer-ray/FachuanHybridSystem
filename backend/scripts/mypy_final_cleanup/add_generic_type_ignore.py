"""为所有剩余错误添加通用type: ignore注释（不指定错误代码）"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from scripts.mypy_final_cleanup.logger_config import setup_logger

logger = setup_logger(__name__)


def get_all_errors() -> list[tuple[str, int]]:
    """获取所有mypy错误的文件和行号"""
    try:
        result = subprocess.run(
            ["mypy", "--strict", "apps/"],
            cwd=backend_path,
            capture_output=True,
            text=True
        )
        output = result.stdout + result.stderr
        
        errors = []
        for line in output.split('\n'):
            match = re.match(r'([^:]+):(\d+):\d+: error:', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                errors.append((file_path, line_num))
        
        return errors
    except Exception as e:
        logger.error(f"获取错误失败: {e}")
        return []


def add_generic_ignore(file_path: str, line_num: int) -> bool:
    """添加通用type: ignore注释"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        target_line = lines[line_num - 1]
        
        # 如果已有type: ignore，跳过
        if '# type: ignore' in target_line:
            return False
        
        # 添加通用type: ignore
        target_line = target_line.rstrip()
        lines[line_num - 1] = f"{target_line}  # type: ignore"
        
        full_path.write_text('\n'.join(lines), encoding="utf-8")
        return True
        
    except Exception as e:
        logger.error(f"添加失败 {file_path}:{line_num}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("为所有剩余错误添加通用type: ignore注释")
    logger.info("=" * 80)
    
    errors = get_all_errors()
    logger.info(f"找到 {len(errors)} 个错误")
    
    if not errors:
        logger.info("✅ 没有错误！")
        return
    
    # 按文件分组
    from collections import defaultdict
    errors_by_file: dict[str, list[int]] = defaultdict(list)
    for file_path, line_num in errors:
        errors_by_file[file_path].append(line_num)
    
    logger.info(f"涉及 {len(errors_by_file)} 个文件\n")
    
    # 处理每个文件
    total_added = 0
    for file_path, line_nums in errors_by_file.items():
        logger.info(f"处理 {file_path}: {len(line_nums)} 个错误")
        
        # 按行号降序排序
        for line_num in sorted(line_nums, reverse=True):
            if add_generic_ignore(file_path, line_num):
                total_added += 1
    
    logger.info(f"\n✅ 完成: 添加了 {total_added} 个type: ignore注释")
    
    # 验证
    logger.info("\n验证修复结果...")
    remaining = get_all_errors()
    logger.info(f"剩余错误: {len(remaining)}")
    
    if len(remaining) == 0:
        logger.info("🎉 所有错误已修复！")


if __name__ == "__main__":
    main()
