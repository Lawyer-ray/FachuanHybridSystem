#!/usr/bin/env python3
"""为所有Django Model添加id属性的类型注解"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def add_id_annotation_to_model(file_path: Path) -> bool:
    """
    为文件中的Django Model类添加id属性注解
    
    Returns:
        是否修改了文件
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        tree = ast.parse(source)
        
        # 查找继承自models.Model的类
        modified = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            
            # 检查是否继承自models.Model
            is_model = False
            for base in node.bases:
                base_name = get_base_name(base)
                if base_name in ('Model', 'models.Model'):
                    is_model = True
                    break
            
            if not is_model:
                continue
            
            # 检查是否已有id注解
            has_id = False
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == 'id':
                        has_id = True
                        break
            
            if has_id:
                logger.debug(f"  类 {node.name} 已有id注解，跳过")
                continue
            
            # 添加id注解
            logger.info(f"  为类 {node.name} 添加id注解")
            
            # 找到插入位置（在docstring之后）
            insert_pos = 0
            if (node.body and 
                isinstance(node.body[0], ast.Expr) and 
                isinstance(node.body[0].value, ast.Constant) and
                isinstance(node.body[0].value.value, str)):
                insert_pos = 1
            
            # 创建id注解
            id_annotation = ast.AnnAssign(
                target=ast.Name(id='id', ctx=ast.Store()),
                annotation=ast.Name(id='int', ctx=ast.Load()),
                simple=1
            )
            
            node.body.insert(insert_pos, id_annotation)
            modified = True
        
        if modified:
            # 写回文件
            new_source = ast.unparse(tree)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_source)
            return True
        
        return False
    
    except Exception as e:
        logger.error(f"  处理文件失败: {e}")
        return False


def get_base_name(base: ast.expr) -> str:
    """获取基类名称"""
    if isinstance(base, ast.Name):
        return base.id
    elif isinstance(base, ast.Attribute):
        value_name = get_base_name(base.value)
        return f"{value_name}.{base.attr}"
    return ""


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent
    apps_dir = backend_path / 'apps'
    
    logger.info("=" * 80)
    logger.info("开始为Django Model添加id属性注解")
    logger.info("=" * 80)
    
    # 查找所有models.py文件
    models_files = list(apps_dir.rglob('models.py'))
    logger.info(f"\n找到 {len(models_files)} 个models.py文件\n")
    
    modified_count = 0
    
    for models_file in models_files:
        rel_path = models_file.relative_to(backend_path)
        logger.info(f"处理: {rel_path}")
        
        if add_id_annotation_to_model(models_file):
            modified_count += 1
    
    logger.info("\n" + "=" * 80)
    logger.info(f"完成！修改了 {modified_count} 个文件")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
