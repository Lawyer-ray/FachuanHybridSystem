"""AttrDefinedFixer - 修复attr-defined错误"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .batch_fixer import BatchFixer

if TYPE_CHECKING:
    from .error_analyzer import ErrorRecord
    from .validation_system import FixResult

logger = logging.getLogger(__name__)


class AttrDefinedFixer(BatchFixer):
    """修复attr-defined错误"""

    # Django Model 常见动态属性
    DJANGO_MODEL_ATTRS = {"id", "pk", "objects", "DoesNotExist", "MultipleObjectsReturned", "_meta", "_state"}

    # 需要手动修复的复杂模式
    MANUAL_FIX_PATTERNS = [
        'has no attribute "_',  # 私有属性通常需要手动检查
        "maybe",  # mypy建议的属性名，需要人工判断
    ]

    def __init__(self, backend_path: Path | None = None) -> None:
        """初始化AttrDefinedFixer"""
        super().__init__(fix_pattern="attr-defined", backend_path=backend_path)
        self._django_models: set[str] = set()
        self._load_django_models()

    def _load_django_models(self) -> None:
        """加载Django Model类名列表"""
        logger.info("开始加载Django Model类名...")

        apps_dir = self.backend_path / "apps"
        if not apps_dir.exists():
            logger.warning(f"apps目录不存在: {apps_dir}")
            return

        # 遍历所有models.py文件
        for models_file in apps_dir.rglob("models.py"):
            try:
                tree = self.parse_ast(models_file)
                if tree is None:
                    continue

                # 查找继承自models.Model的类
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        for base in node.bases:
                            base_name = self._get_base_name(base)
                            if base_name in ("Model", "models.Model"):
                                self._django_models.add(node.name)
                                logger.debug(f"发现Django Model: {node.name}")

            except Exception as e:
                logger.warning(f"加载models文件失败 {models_file}: {e}")

        logger.info(f"加载完成，共发现 {len(self._django_models)} 个Django Model")

    def _get_base_name(self, base: ast.expr) -> str:
        """获取基类名称"""
        if isinstance(base, ast.Name):
            return base.id
        elif isinstance(base, ast.Attribute):
            return f"{self._get_base_name(base.value)}.{base.attr}"
        return ""

    def can_fix(self, error: ErrorRecord) -> bool:
        """
        判断是否可以修复此错误

        Args:
            error: 错误记录

        Returns:
            是否可以修复
        """
        if error.error_code != "attr-defined":
            return False

        # 检查是否是需要手动修复的复杂情况
        for pattern in self.MANUAL_FIX_PATTERNS:
            if pattern in error.message:
                logger.debug(f"需要手动修复: {error.message}")
                return False

        # 检查是否是Django Model动态属性
        if self._is_django_model_attr_error(error):
            return True

        # 其他情况暂时标记为需要手动修复
        logger.debug(f"暂不支持自动修复: {error.message}")
        return False

    def _is_django_model_attr_error(self, error: ErrorRecord) -> bool:
        """判断是否是Django Model动态属性错误"""
        # 提取属性名
        attr_match = re.search(r'has no attribute "(\w+)"', error.message)
        if not attr_match:
            return False

        attr_name = attr_match.group(1)

        # 检查是否是Django Model常见动态属性
        if attr_name in self.DJANGO_MODEL_ATTRS:
            # 提取类名
            class_match = re.search(r'"(\w+)" has no attribute', error.message)
            if class_match:
                class_name = class_match.group(1)
                # 检查是否是已知的Django Model
                if class_name in self._django_models:
                    return True

        return False

    def fix_file(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        """
        修复文件中的错误

        Args:
            file_path: 文件路径
            errors: 该文件中的错误列表

        Returns:
            修复结果
        """
        from .validation_system import FixResult

        full_path = self.backend_path / file_path

        if not full_path.exists():
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message=f"文件不存在: {file_path}",
            )

        # 解析AST
        tree = self.parse_ast(full_path)
        if tree is None:
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=False,
                error_message="AST解析失败",
            )

        # 收集需要添加类型注解的Django Model类
        models_to_fix: dict[str, set[str]] = {}

        for error in errors:
            if not self.can_fix(error):
                continue

            # 提取类名和属性名
            class_match = re.search(r'"(\w+)" has no attribute', error.message)
            attr_match = re.search(r'has no attribute "(\w+)"', error.message)

            if class_match and attr_match:
                class_name = class_match.group(1)
                attr_name = attr_match.group(1)

                if class_name not in models_to_fix:
                    models_to_fix[class_name] = set()
                models_to_fix[class_name].add(attr_name)

        if not models_to_fix:
            logger.info(f"文件 {file_path} 中没有可自动修复的错误")
            return FixResult(
                file_path=file_path,
                errors_fixed=0,
                errors_remaining=len(errors),
                fix_pattern=self.fix_pattern,
                success=True,
                error_message=None,
            )

        # 修改AST，添加类型注解
        errors_fixed = 0
        transformer = DjangoModelAnnotationAdder(models_to_fix)
        modified_tree = transformer.visit(tree)

        if transformer.modified:
            # 写回文件
            if self.write_source(full_path, modified_tree):
                errors_fixed = transformer.annotations_added
                logger.info(f"成功修复文件 {file_path}，" f"添加了 {errors_fixed} 个类型注解")
            else:
                return FixResult(
                    file_path=file_path,
                    errors_fixed=0,
                    errors_remaining=len(errors),
                    fix_pattern=self.fix_pattern,
                    success=False,
                    error_message="写入文件失败",
                )

        return FixResult(
            file_path=file_path,
            errors_fixed=errors_fixed,
            errors_remaining=len(errors) - errors_fixed,
            fix_pattern=self.fix_pattern,
            success=True,
            error_message=None,
        )


class DjangoModelAnnotationAdder(ast.NodeTransformer):
    """为Django Model添加类型注解的AST转换器"""

    # Django Model动态属性的类型映射
    ATTR_TYPE_MAP = {
        "id": "int",
        "pk": "int",
        "objects": "models.Manager[Self]",
        "DoesNotExist": "type[Exception]",
        "MultipleObjectsReturned": "type[Exception]",
    }

    def __init__(self, models_to_fix: dict[str, set[str]]) -> None:
        """
        初始化转换器

        Args:
            models_to_fix: {类名: {属性名集合}}
        """
        self.models_to_fix = models_to_fix
        self.modified = False
        self.annotations_added = 0

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        """访问类定义节点"""
        # 检查是否是需要修复的Model类
        if node.name not in self.models_to_fix:
            return node

        attrs_to_add = self.models_to_fix[node.name]

        # 获取已有的类型注解
        existing_annotations = set()
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                existing_annotations.add(item.target.id)

        # 添加缺失的类型注解
        new_annotations: list[ast.AnnAssign] = []

        for attr_name in attrs_to_add:
            if attr_name in existing_annotations:
                logger.debug(f"类 {node.name} 已有属性 {attr_name} 的注解，跳过")
                continue

            # 获取属性类型
            attr_type = self.ATTR_TYPE_MAP.get(attr_name)
            if attr_type is None:
                logger.warning(f"未知的Django Model属性类型: {attr_name}")
                continue

            # 创建类型注解节点
            annotation = self._create_annotation(attr_type)
            ann_assign = ast.AnnAssign(target=ast.Name(id=attr_name, ctx=ast.Store()), annotation=annotation, simple=1)

            new_annotations.append(ann_assign)
            self.annotations_added += 1
            logger.info(f"为类 {node.name} 添加属性注解: {attr_name}: {attr_type}")

        # 将新注解插入到类体的开头（在docstring之后）
        if new_annotations:
            insert_pos = 0

            # 如果第一个语句是docstring，插入到它后面
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                insert_pos = 1

            node.body[insert_pos:insert_pos] = new_annotations
            self.modified = True

        return node

    def _create_annotation(self, type_str: str) -> ast.expr:
        """
        创建类型注解AST节点

        Args:
            type_str: 类型字符串，如 'int', 'models.Manager[Self]'

        Returns:
            类型注解AST节点
        """
        # 简单类型
        if type_str in ("int", "str", "bool", "float"):
            return ast.Name(id=type_str, ctx=ast.Load())

        # 处理泛型类型，如 models.Manager[Self]
        if "[" in type_str:
            base_type, param_type = type_str.split("[", 1)
            param_type = param_type.rstrip("]")

            base_node = self._create_annotation(base_type)
            param_node = self._create_annotation(param_type)

            return ast.Subscript(value=base_node, slice=param_node, ctx=ast.Load())

        # 处理属性访问，如 models.Manager
        if "." in type_str:
            parts = type_str.split(".")
            node: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
            for part in parts[1:]:
                node = ast.Attribute(value=node, attr=part, ctx=ast.Load())
            return node

        # 其他情况，作为简单名称
        return ast.Name(id=type_str, ctx=ast.Load())
