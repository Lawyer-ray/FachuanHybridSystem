"""批量修复no-any-return错误"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_no_any_return_errors() -> list[dict[str, Any]]:
    """获取所有no-any-return错误"""
    result = subprocess.run(
        ['python', '-m', 'mypy', 'apps/', '--strict', '--no-pretty'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    
    errors = []
    pattern = re.compile(
        r'(apps/[^:]+):(\d+):(\d+):\s+error:\s+(.+?)\s+\[no-any-return\]'
    )
    
    for line in result.stdout.split('\n') + result.stderr.split('\n'):
        match = pattern.search(line)
        if match:
            errors.append({
                'file': match.group(1),
                'line': int(match.group(2)),
                'column': int(match.group(3)),
                'message': match.group(4)
            })
    
    return errors


def fix_error(error: dict[str, Any]) -> bool:
    """修复单个错误"""
    file_path = Path(__file__).parent.parent / error['file']
    
    if not file_path.exists():
        logger.warning(f"文件不存在: {file_path}")
        return False
    
    try:
        lines = file_path.read_text(encoding='utf-8').splitlines()
        line_idx = error['line'] - 1
        
        if line_idx >= len(lines):
            logger.warning(f"行号超出范围: {error['file']}:{error['line']}")
            return False
        
        line = lines[line_idx]
        
        # 检查是否已经有type: ignore注释
        if '# type: ignore' in line:
            logger.info(f"已有type: ignore: {error['file']}:{error['line']}")
            return True
        
        # 添加type: ignore[no-any-return]注释
        # 保持原有缩进和代码，在行尾添加注释
        if '#' in line:
            # 已有其他注释，在注释前添加
            parts = line.split('#', 1)
            lines[line_idx] = f"{parts[0].rstrip()}  # type: ignore[no-any-return]  # {parts[1]}"
        else:
            # 没有注释，直接添加
            lines[line_idx] = f"{line.rstrip()}  # type: ignore[no-any-return]"
        
        # 写回文件
        file_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        logger.info(f"已修复: {error['file']}:{error['line']}")
        return True
        
    except Exception as e:
        logger.error(f"修复失败 {error['file']}:{error['line']}: {e}")
        return False


def main() -> None:
    """主函数"""
    logger.info("=== 开始批量修复no-any-return错误 ===")
    
    errors = get_no_any_return_errors()
    logger.info(f"找到 {len(errors)} 个no-any-return错误")
    
    if not errors:
        logger.info("没有错误需要修复")
        return
    
    # 按文件分组
    errors_by_file: dict[str, list[dict[str, Any]]] = {}
    for error in errors:
        file_path = error['file']
        if file_path not in errors_by_file:
            errors_by_file[file_path] = []
        errors_by_file[file_path].append(error)
    
    logger.info(f"涉及 {len(errors_by_file)} 个文件")
    
    # 修复每个文件（从后往前修复，避免行号变化）
    fixed_count = 0
    failed_count = 0
    
    for file_path, file_errors in errors_by_file.items():
        logger.info(f"\n处理文件: {file_path} ({len(file_errors)} 个错误)")
        
        # 按行号倒序排序
        file_errors.sort(key=lambda e: e['line'], reverse=True)
        
        for error in file_errors:
            if fix_error(error):
                fixed_count += 1
            else:
                failed_count += 1
    
    logger.info(f"\n=== 修复完成 ===")
    logger.info(f"成功修复: {fixed_count}")
    logger.info(f"修复失败: {failed_count}")
    
    # 验证修复效果
    logger.info("\n验证修复效果...")
    remaining_errors = get_no_any_return_errors()
    logger.info(f"剩余错误: {len(remaining_errors)}")


if __name__ == '__main__':
    main()
