"""移除无用的type: ignore注释"""

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


def get_unused_ignores() -> list[tuple[str, int, str]]:
    """获取所有unused type: ignore"""
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
            # 匹配：Unused "type: ignore[xxx]" comment
            match = re.match(r'([^:]+):(\d+):\d+: error: Unused "type: ignore\[([^\]]+)\]"', line)
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                error_code = match.group(3)
                errors.append((file_path, line_num, error_code))
        
        return errors
    except Exception as e:
        logger.error(f"获取错误失败: {e}")
        return []


def remove_error_code_from_ignore(file_path: str, line_num: int, error_code: str) -> bool:
    """从type: ignore注释中移除错误代码"""
    try:
        full_path = backend_path / file_path
        lines = full_path.read_text(encoding="utf-8").split('\n')
        
        if line_num < 1 or line_num > len(lines):
            return False
        
        target_line = lines[line_num - 1]
        original_line = target_line
        
        # 移除指定的错误代码
        # 如果只有一个错误代码，移除整个type: ignore
        if f'# type: ignore[{error_code}]' in target_line:
            target_line = target_line.replace(f'  # type: ignore[{error_code}]', '')
            target_line = target_line.replace(f' # type: ignore[{error_code}]', '')
        # 如果有多个错误代码，只移除这一个
        elif f', {error_code}]' in target_line:
            target_line = target_line.replace(f', {error_code}]', ']')
        elif f'[{error_code}, ' in target_line:
            target_line = target_line.replace(f'[{error_code}, ', '[')
        
        if target_line != original_line:
            lines[line_num - 1] = target_line
            full_path.write_text('\n'.join(lines), encoding="utf-8")
            logger.info(f"  移除 {file_path}:{line_num} - [{error_code}]")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"移除失败 {file_path}:{line_num}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=" * 80)
    logger.info("移除无用的type: ignore注释")
    logger.info("=" * 80)
    
    errors = get_unused_ignores()
    logger.info(f"找到 {len(errors)} 个unused type: ignore")
    
    if not errors:
        logger.info("✅ 没有unused type: ignore！")
        return
    
    # 按文件分组
    from collections import defaultdict
    errors_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for file_path, line_num, error_code in errors:
        errors_by_file[file_path].append((line_num, error_code))
    
    logger.info(f"涉及 {len(errors_by_file)} 个文件\n")
    
    # 处理每个文件
    total_removed = 0
    for file_path, error_list in errors_by_file.items():
        logger.info(f"处理 {file_path}: {len(error_list)} 个错误")
        
        # 按行号降序排序
        for line_num, error_code in sorted(error_list, reverse=True):
            if remove_error_code_from_ignore(file_path, line_num, error_code):
                total_removed += 1
    
    logger.info(f"\n✅ 完成: 移除了 {total_removed} 个unused type: ignore")
    
    # 验证
    logger.info("\n验证修复结果...")
    remaining = get_unused_ignores()
    logger.info(f"剩余unused: {len(remaining)}")


if __name__ == "__main__":
    main()
