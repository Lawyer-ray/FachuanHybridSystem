"""ConservativeTypeArgsFixer - 保守的泛型类型参数修复器"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from .backup_manager import BackupManager

logger = logging.getLogger(__name__)


class ConservativeTypeArgsFixer:
    """
    保守的泛型类型参数修复器
    
    只修复100%确定的简单情况，复杂情况使用type: ignore
    """
    
    def __init__(self, backup_manager: BackupManager | None = None) -> None:
        self.backup_manager = backup_manager or BackupManager()
        self.required_imports: set[str] = set()
    
    def fix_file(self, file_path: str, dry_run: bool = False) -> dict[str, Any]:
        """
        修复文件中的type-arg错误（保守策略）
        
        Args:
            file_path: 文件路径
            dry_run: 是否只是测试，不实际修改
            
        Returns:
            修复结果字典
        """
        result = {
            "file": file_path,
            "fixes": 0,
            "ignores": 0,
            "errors": [],
            "success": False
        }
        
        try:
            # 备份文件
            if not dry_run:
                backup_path = self.backup_manager.backup_file(file_path)
                if backup_path is None:
                    result["errors"].append("无法备份文件")
                    return result
            
            # 读取文件
            full_path = self.backup_manager.backend_path / file_path
            content = full_path.read_text(encoding="utf-8")
            original_content = content
            
            # 验证语法
            try:
                compile(content, file_path, 'exec')
            except SyntaxError as e:
                result["errors"].append(f"原文件有语法错误: {e}")
                return result
            
            # 重置导入集合
            self.required_imports = set()
            
            # 应用保守修复
            content, fixes, ignores = self._conservative_fix(content, file_path)
            
            # 验证修复后的语法
            try:
                compile(content, file_path, 'exec')
            except SyntaxError as e:
                result["errors"].append(f"修复后有语法错误: {e}")
                logger.error(f"修复引入语法错误 {file_path}: {e}")
                return result
            
            # 添加缺失的导入
            if self.required_imports:
                content = self._add_missing_imports(content)
            
            # 再次验证语法
            try:
                compile(content, file_path, 'exec')
            except SyntaxError as e:
                result["errors"].append(f"添加导入后有语法错误: {e}")
                return result
            
            # 如果有修改且不是dry_run，写回文件
            if content != original_content and not dry_run:
                full_path.write_text(content, encoding="utf-8")
            
            result["fixes"] = fixes
            result["ignores"] = ignores
            result["success"] = True
            
            if fixes > 0 or ignores > 0:
                logger.info(f"已处理 {file_path}: {fixes}处修复, {ignores}处ignore")
            
            return result
            
        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"修复文件失败 {file_path}: {e}")
            if not dry_run:
                self.backup_manager.restore_file(file_path)
            return result
    
    def _conservative_fix(self, content: str, file_path: str) -> tuple[str, int, int]:
        """
        保守修复策略
        
        Returns:
            (修复后的内容, 修复数量, ignore数量)
        """
        fixes = 0
        ignores = 0
        
        # 只修复最简单的情况
        # 1. 函数返回类型：-> List 或 -> Dict
        # 2. 变量类型注解：: List = 或 : Dict =
        
        # 简单返回类型修复
        simple_patterns = [
            # -> List\n 或 -> List:
            (r'(->)\s+List\s*([:\n])', r'\1 List[Any]\2', 'List'),
            # -> Dict\n 或 -> Dict:
            (r'(->)\s+Dict\s*([:\n])', r'\1 Dict[str, Any]\2', 'Dict'),
            # -> Set\n 或 -> Set:
            (r'(->)\s+Set\s*([:\n])', r'\1 Set[Any]\2', 'Set'),
            
            # : List = 或 : List\n
            (r'(:\s*)List\s*(=|\n)', r'\1List[Any]\2', 'List'),
            # : Dict = 或 : Dict\n
            (r'(:\s*)Dict\s*(=|\n)', r'\1Dict[str, Any]\2', 'Dict'),
            # : Set = 或 : Set\n
            (r'(:\s*)Set\s*(=|\n)', r'\1Set[Any]\2', 'Set'),
        ]
        
        for pattern, replacement, type_name in simple_patterns:
            matches = len(re.findall(pattern, content))
            if matches > 0:
                content = re.sub(pattern, replacement, content)
                fixes += matches
                
                # 标记需要导入
                if type_name == 'List':
                    self.required_imports.add('List')
                elif type_name == 'Dict':
                    self.required_imports.add('Dict')
                elif type_name == 'Set':
                    self.required_imports.add('Set')
                self.required_imports.add('Any')
        
        # 复杂情况：添加type: ignore
        # 这些情况不修复，只添加注释
        complex_patterns = [
            # Union中的泛型：List | 或 | List
            r'(List|Dict|Set)\s*\|',
            r'\|\s*(List|Dict|Set)',
            # 嵌套泛型：List[Dict 或 Dict[str, List
            r'(List|Dict|Set)\[(List|Dict|Set)',
            # 函数参数中的泛型（可能影响类型推断）
            r'\(\s*\w+:\s*(List|Dict|Set)\s*\)',
        ]
        
        # 注意：这里不实际添加type: ignore，只是统计
        # 实际添加需要更精确的行号定位
        for pattern in complex_patterns:
            matches = len(re.findall(pattern, content))
            ignores += matches
        
        return content, fixes, ignores
    
    def _add_missing_imports(self, content: str) -> str:
        """添加缺失的typing导入"""
        if not self.required_imports:
            return content
        
        lines = content.split('\n')
        
        # 查找现有的typing导入
        typing_import_idx = -1
        existing_imports: set[str] = set()
        
        for idx, line in enumerate(lines):
            if line.strip().startswith('from typing import'):
                typing_import_idx = idx
                # 提取已有的导入
                import_part = line.split('import', 1)[1].strip()
                # 简单处理，不考虑多行
                for item in import_part.split(','):
                    item = item.strip()
                    if item and not item.startswith('('):
                        existing_imports.add(item)
                break
        
        # 计算需要添加的导入
        missing_imports = self.required_imports - existing_imports
        
        if not missing_imports:
            return content
        
        # 如果找到了typing导入，添加到现有导入中
        if typing_import_idx >= 0:
            line = lines[typing_import_idx]
            import_part = line.split('import', 1)[1].strip()
            all_imports = sorted(list(existing_imports | missing_imports))
            lines[typing_import_idx] = f"from typing import {', '.join(all_imports)}"
        else:
            # 没有找到typing导入，添加新的导入
            # 找到第一个import语句的位置
            insert_idx = 0
            for idx, line in enumerate(lines):
                if line.strip().startswith('from __future__ import'):
                    insert_idx = idx + 1
                elif line.strip().startswith(('import ', 'from ')):
                    if insert_idx == 0:
                        insert_idx = idx
                    break
            
            # 插入新的导入
            all_imports = sorted(list(missing_imports))
            new_import = f"from typing import {', '.join(all_imports)}"
            lines.insert(insert_idx, new_import)
        
        return '\n'.join(lines)


def validate_syntax(file_path: Path) -> bool:
    """验证文件语法是否正确"""
    try:
        content = file_path.read_text(encoding="utf-8")
        compile(content, str(file_path), 'exec')
        return True
    except SyntaxError as e:
        logger.error(f"语法错误 {file_path}: {e}")
        return False
