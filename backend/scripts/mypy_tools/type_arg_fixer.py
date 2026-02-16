"""TypeArgFixer - 修复type-arg错误（泛型类型参数缺失）"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .batch_fixer import BatchFixer

if TYPE_CHECKING:
    from .error_analyzer import ErrorRecord
    from .validation_system import FixResult

logger = logging.getLogger(__name__)


class TypeArgFixer(BatchFixer):
    """修复type-arg错误"""
    
    # 内置泛型类型映射到默认类型参数
    BUILTIN_GENERIC_DEFAULTS: dict[str, str] = {
        'dict': 'dict[str, Any]',
        'Dict': 'Dict[str, Any]',
        'list': 'list[Any]',
        'List': 'List[Any]',
        'set': 'set[Any]',
        'Set': 'Set[Any]',
        'frozenset': 'frozenset[Any]',
        'FrozenSet': 'FrozenSet[Any]',
        'tuple': 'tuple[Any, ...]',
        'Tuple': 'Tuple[Any, ...]',
        'defaultdict': 'defaultdict[str, Any]',
        'OrderedDict': 'OrderedDict[str, Any]',
        'Counter': 'Counter[Any]',
        'deque': 'deque[Any]',
    }
    
    def __init__(self, backend_path: Path | None = None) -> None:
        """初始化TypeArgFixer"""
        super().__init__('add_generic_params', backend_path)
        self._future_annotations_added: set[str] = set()
    
    def can_fix(self, error: ErrorRecord) -> bool:
        """判断是否可以修复此错误"""
        return error.error_code == 'type-arg'
    
    def fix_file(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        """修复文件中的type-arg错误"""
        from .validation_system import FixResult
        
        full_path = self.backend_path / file_path
        
        # 解析AST
        tree = self.parse_ast(full_path)
        if tree is None:
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message="AST解析失败"
            )
        
        # 读取源代码用于行号匹配
        source_lines = full_path.read_text(encoding='utf-8').split('\n')
        
        # 修复每个错误
        errors_fixed = 0
        modified = False
        
        for error in errors:
            if not self.can_fix(error):
                continue
            
            # 尝试修复此错误
            if self._fix_type_arg_error(tree, error, source_lines):
                errors_fixed += 1
                modified = True
        
        # 如果有修改，添加future annotations导入
        if modified:
            self._ensure_future_annotations(tree, file_path)
            
            # 写回文件
            if not self.write_source(full_path, tree):
                return FixResult(
                    file_path=file_path,
                    errors_fixed=0,
                    errors_remaining=len(errors),
                    fix_pattern=self.fix_pattern,
                    success=False,
                    error_message="写入文件失败"
                )
        
        success = errors_fixed > 0
        errors_remaining = len(errors) - errors_fixed
        
        logger.info(
            f"修复完成: {file_path}, "
            f"修复了 {errors_fixed}/{len(errors)} 个错误"
        )
        
        return FixResult(
            file_path=file_path,
            errors_fixed=errors_fixed,
            errors_remaining=errors_remaining,
            fix_pattern=self.fix_pattern,
            success=success,
            error_message=None if success else "部分错误无法修复"
        )
    
    def _fix_type_arg_error(
        self, 
        tree: ast.Module, 
        error: ErrorRecord,
        source_lines: list[str]
    ) -> bool:
        """
        修复单个type-arg错误
        
        Args:
            tree: AST树
            error: 错误记录
            source_lines: 源代码行列表
            
        Returns:
            是否修复成功
        """
        # 查找错误所在行的代码
        if error.line <= 0 or error.line > len(source_lines):
            logger.warning(f"行号超出范围: {error.line}")
            return False
        
        error_line = source_lines[error.line - 1]
        
        # 提取泛型类型名称
        generic_type = self._extract_generic_type(error.message)
        if not generic_type:
            logger.warning(f"无法从错误消息中提取泛型类型: {error.message}")
            return False
        
        # 查找并修复AST节点
        visitor = TypeArgVisitor(error.line, generic_type, self.BUILTIN_GENERIC_DEFAULTS)
        visitor.visit(tree)
        
        return visitor.fixed
    
    def _extract_generic_type(self, message: str) -> str | None:
        """
        从错误消息中提取泛型类型名称
        
        例如: '"dict" expects 2 type arguments' -> 'dict'
        """
        import re
        
        # 匹配 "type_name" expects N type arguments
        match = re.search(r'"([^"]+)"\s+expects?\s+\d+\s+type\s+arguments?', message)
        if match:
            return match.group(1)
        
        # 匹配 Missing type parameters for generic type "type_name"
        match = re.search(r'Missing\s+type\s+parameters?\s+for\s+generic\s+type\s+"([^"]+)"', message)
        if match:
            return match.group(1)
        
        return None
    
    def _ensure_future_annotations(self, tree: ast.Module, file_path: str) -> None:
        """确保文件包含 from __future__ import annotations"""
        
        # 检查是否已经有此导入
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.module == '__future__':
                    for alias in node.names:
                        if alias.name == 'annotations':
                            logger.info(f"文件已有future annotations导入: {file_path}")
                            return
        
        # 添加导入（插入到文件开头，在docstring和注释之后）
        import_node = ast.ImportFrom(
            module='__future__',
            names=[ast.alias(name='annotations', asname=None)],
            level=0
        )
        
        # 找到插入位置（在docstring之后）
        insert_pos = 0
        if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
            # 第一个节点是docstring
            insert_pos = 1
        
        tree.body.insert(insert_pos, import_node)
        logger.info(f"添加future annotations导入: {file_path}")


class TypeArgVisitor(ast.NodeTransformer):
    """访问并修复AST中的泛型类型节点"""
    
    def __init__(
        self, 
        target_line: int, 
        generic_type: str,
        defaults: dict[str, str]
    ) -> None:
        """
        初始化访问器
        
        Args:
            target_line: 目标行号
            generic_type: 泛型类型名称
            defaults: 默认类型参数映射
        """
        self.target_line = target_line
        self.generic_type = generic_type
        self.defaults = defaults
        self.fixed = False
    
    def visit_Name(self, node: ast.Name) -> ast.AST:
        """访问Name节点（变量名）"""
        # 检查是否是目标行的目标类型
        if (hasattr(node, 'lineno') and 
            node.lineno == self.target_line and 
            node.id == self.generic_type):
            
            # 获取默认类型参数
            default_type = self.defaults.get(self.generic_type)
            if default_type:
                # 将 dict -> dict[str, Any] 等
                # 这里需要解析default_type并构建Subscript节点
                new_node = self._create_subscript_node(node, default_type)
                if new_node:
                    self.fixed = True
                    logger.info(f"修复泛型类型: {self.generic_type} -> {default_type}")
                    return new_node
        
        return self.generic_visit(node)
    
    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        """访问Attribute节点（属性访问）"""
        # 处理 typing.Dict 等情况
        if (hasattr(node, 'lineno') and 
            node.lineno == self.target_line and 
            node.attr == self.generic_type):
            
            default_type = self.defaults.get(self.generic_type)
            if default_type:
                # 这种情况较复杂，暂时跳过
                logger.warning(f"跳过Attribute节点的修复: {self.generic_type}")
        
        return self.generic_visit(node)
    
    def _create_subscript_node(self, base_node: ast.Name, type_str: str) -> ast.Subscript | None:
        """
        创建Subscript节点（泛型类型）
        
        Args:
            base_node: 基础Name节点
            type_str: 类型字符串，如 "dict[str, Any]"
            
        Returns:
            Subscript节点或None
        """
        try:
            # 解析类型字符串
            # 简化处理：只处理常见的单参数和双参数泛型
            if '[' not in type_str:
                return None
            
            # 提取类型参数
            start = type_str.index('[')
            end = type_str.rindex(']')
            params_str = type_str[start+1:end]
            
            # 分割参数
            params = [p.strip() for p in params_str.split(',')]
            
            # 构建slice节点
            if len(params) == 1:
                # 单参数：list[Any]
                slice_node = self._create_name_node(params[0])
            else:
                # 多参数：dict[str, Any]
                slice_node = ast.Tuple(
                    elts=[self._create_name_node(p) for p in params],
                    ctx=ast.Load()
                )
            
            # 构建Subscript节点
            subscript = ast.Subscript(
                value=base_node,
                slice=slice_node,
                ctx=ast.Load()
            )
            
            # 复制行号信息
            if hasattr(base_node, 'lineno'):
                subscript.lineno = base_node.lineno
                subscript.col_offset = base_node.col_offset
            
            return subscript
            
        except Exception as e:
            logger.error(f"创建Subscript节点失败: {e}")
            return None
    
    def _create_name_node(self, name: str) -> ast.Name:
        """创建Name节点"""
        return ast.Name(id=name, ctx=ast.Load())
