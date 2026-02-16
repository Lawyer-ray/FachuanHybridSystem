"""第二轮批量修复常见错误"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_list_type_annotations(backend_path: Path) -> int:
    """为列表变量添加类型注解"""
    fixed = 0
    
    for py_file in backend_path.glob('apps/**/*.py'):
        content = py_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        modified = False
        for i in range(len(lines)):
            line = lines[i]
            
            # 匹配: errors = [] 或 items = [] 等
            match = re.match(r'^(\s+)(errors|warnings|items|results|data|values|keys|names|ids)\s*=\s*\[\]', line)
            if match and ':' not in line.split('=')[0]:
                indent = match.group(1)
                var_name = match.group(2)
                lines[i] = f"{indent}{var_name}: list[Any] = []"
                modified = True
                fixed += 1
        
        if modified:
            py_file.write_text('\n'.join(lines), encoding='utf-8')
    
    return fixed


def fix_none_comparisons(backend_path: Path) -> int:
    """修复None比较"""
    fixed = 0
    
    for py_file in backend_path.glob('apps/**/*.py'):
        content = py_file.read_text(encoding='utf-8')
        original = content
        
        # 修复 == None -> is None
        content = re.sub(r'([^=!])== None\b', r'\1is None', content)
        
        # 修复 != None -> is not None
        content = re.sub(r'([^=!])!= None\b', r'\1is not None', content)
        
        if content != original:
            py_file.write_text(content, encoding='utf-8')
            fixed += 1
    
    return fixed


def fix_empty_dict_annotations(backend_path: Path) -> int:
    """为空字典添加类型注解"""
    fixed = 0
    
    for py_file in backend_path.glob('apps/**/*.py'):
        content = py_file.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        modified = False
        for i in range(len(lines)):
            line = lines[i]
            
            # 匹配: cache = {} 或 mapping = {} 等
            match = re.match(r'^(\s+)(cache|mapping|data|config|params|kwargs|options)\s*=\s*\{\}', line)
            if match and ':' not in line.split('=')[0]:
                indent = match.group(1)
                var_name = match.group(2)
                lines[i] = f"{indent}{var_name}: dict[str, Any] = {{}}"
                modified = True
                fixed += 1
        
        if modified:
            py_file.write_text('\n'.join(lines), encoding='utf-8')
    
    return fixed


def fix_union_none_to_optional(backend_path: Path) -> int:
    """将Union[X, None]转换为Optional[X]"""
    fixed = 0
    
    for py_file in backend_path.glob('apps/**/*.py'):
        content = py_file.read_text(encoding='utf-8')
        original = content
        
        # Union[Type, None] -> Optional[Type]
        # 简单情况: Union[SomeType, None]
        content = re.sub(r'Union\[([A-Za-z_][A-Za-z0-9_\[\], ]*), None\]', r'Optional[\1]', content)
        content = re.sub(r'Union\[None, ([A-Za-z_][A-Za-z0-9_\[\], ]*)\]', r'Optional[\1]', content)
        
        if content != original:
            py_file.write_text(content, encoding='utf-8')
            fixed += 1
    
    return fixed


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent.parent
    
    logger.info("=" * 60)
    logger.info("第二轮批量修复")
    logger.info("=" * 60)
    
    # 统计初始错误数
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    initial_errors = len([line for line in result.stdout.split('\n') if ': error:' in line])
    logger.info(f"初始错误数: {initial_errors}")
    
    # 执行修复
    logger.info("\n1. 修复列表类型注解...")
    fixed1 = fix_list_type_annotations(backend_path)
    logger.info(f"   修复: {fixed1}处")
    
    logger.info("\n2. 修复None比较...")
    fixed2 = fix_none_comparisons(backend_path)
    logger.info(f"   修复: {fixed2}个文件")
    
    logger.info("\n3. 修复空字典类型注解...")
    fixed3 = fix_empty_dict_annotations(backend_path)
    logger.info(f"   修复: {fixed3}处")
    
    logger.info("\n4. 将Union[X, None]转换为Optional[X]...")
    fixed4 = fix_union_none_to_optional(backend_path)
    logger.info(f"   修复: {fixed4}个文件")
    
    # 统计最终错误数
    result = subprocess.run(
        ['mypy', 'apps/', '--strict'],
        capture_output=True,
        text=True,
        cwd=backend_path,
        timeout=300
    )
    final_errors = len([line for line in result.stdout.split('\n') if ': error:' in line])
    
    logger.info("\n" + "=" * 60)
    logger.info(f"修复完成")
    logger.info(f"初始错误: {initial_errors}")
    logger.info(f"最终错误: {final_errors}")
    logger.info(f"修复数量: {initial_errors - final_errors}")
    logger.info(f"操作总数: {fixed1 + fixed2 + fixed3 + fixed4}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
