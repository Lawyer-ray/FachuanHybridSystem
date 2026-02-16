"""
Model层架构违规扫描器

检测Model层代码中的违规模式：
- save() 方法覆写
- save() 中包含业务逻辑（调用其他Model、复杂计算、外部服务调用等）

仅扫描 models/ 目录下的文件或名为 models.py 的文件。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import ModelViolation, Violation
from .scanner import ViolationScanner

logger = get_logger("model_scanner")

# Django Model基类名称集合，用于识别Model子类
_DJANGO_MODEL_BASES: frozenset[str] = frozenset(
    {
        "Model",
        "models.Model",
        "AbstractBaseUser",
        "AbstractUser",
        "PermissionsMixin",
    }
)

# 表示外部服务调用的属性名模式
_EXTERNAL_SERVICE_ATTRS: frozenset[str] = frozenset(
    {
        "send",
        "send_mail",
        "send_email",
        "notify",
        "publish",
        "dispatch",
        "emit",
        "request",
        "post",
        "put",
        "call",
    }
)

# 调用 delete() 时不算外部服务调用的对象名
_CACHE_LIKE_NAMES: frozenset[str] = frozenset(
    {
        "cache",
        "caches",
        "redis",
        "memcache",
    }
)

# 简单验证相关的方法/属性，不算业务逻辑
_VALIDATION_PATTERNS: frozenset[str] = frozenset(
    {
        "full_clean",
        "clean",
        "clean_fields",
        "validate_unique",
        "validate_constraints",
    }
)

# 算术运算符集合
_ARITHMETIC_OPS: tuple[type, ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)


class ModelLayerScanner(ViolationScanner):
    """
    Model层架构违规扫描器

    扫描 models/ 目录下或名为 models.py 的Python文件，检测：
    1. save() 方法覆写中包含业务逻辑
       - 调用其他Model类（如 OtherModel.objects.create）
       - 复杂计算（多个算术运算）
       - 外部服务调用
       - 超出简单验证的条件逻辑
    """

    # ── public API override ─────────────────────────────────

    def scan_directory(self, root: Path) -> list[Violation]:
        """
        扫描目录，仅处理 models/ 子目录下或名为 models.py 的文件。

        Args:
            root: 要扫描的根目录

        Returns:
            Model层违规列表
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("Path is not a directory, skipping: %s", root)
            return []

        violations: list[Violation] = []
        py_files = self._collect_python_files(root)
        model_files = [f for f in py_files if self._is_model_file(f)]
        logger.info(
            "Found %d Model layer Python files (out of %d total) under %s",
            len(model_files),
            len(py_files),
            root,
        )

        for py_file in model_files:
            file_violations = self.scan_file(py_file)
            violations.extend(file_violations)

        logger.info(
            "Model layer scan complete: %d violation(s) in %d file(s)",
            len(violations),
            len(model_files),
        )
        return violations

    # ── abstract method implementation ──────────────────────

    def _scan_file_ast(
        self,
        tree: ast.Module,
        source: str,
        file_path: Path,
    ) -> list[Violation]:
        """
        对单个文件的AST执行Model层违规检测。

        遍历所有类定义，找到继承Django Model的类，
        检查其 save() 方法是否包含业务逻辑。

        Args:
            tree: 已解析的AST模块节点
            source: 原始源代码文本
            file_path: 文件路径

        Returns:
            检测到的ModelViolation列表
        """
        violations: list[Violation] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            if not self._is_django_model(node):
                continue

            class_violations = self._check_save_method(
                node,
                source,
                file_path,
            )
            violations.extend(class_violations)

        if violations:
            logger.info(
                "Found %d Model violation(s) in %s",
                len(violations),
                file_path,
            )
        return violations

    # ── save() method detection ─────────────────────────────

    def _check_save_method(
        self,
        class_node: ast.ClassDef,
        source: str,
        file_path: Path,
    ) -> list[ModelViolation]:
        """
        检查Django Model类中的 save() 方法覆写。

        找到 save() 方法后，使用启发式规则检测其中的业务逻辑。

        Args:
            class_node: ast.ClassDef 节点
            source: 源代码文本
            file_path: 文件路径

        Returns:
            检测到的ModelViolation列表
        """
        violations: list[ModelViolation] = []

        for node in class_node.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "save":
                continue

            # 找到 save() 覆写，检测业务逻辑
            logic_descriptions = self._detect_business_logic(
                node,
                class_node.name,
            )

            for description in logic_descriptions:
                line_number: int = node.lineno
                code_snippet = self._get_source_line(source, line_number)

                violation = ModelViolation(
                    file_path=str(file_path),
                    line_number=line_number,
                    code_snippet=code_snippet,
                    violation_type="model_business_logic_in_save",
                    severity="high",
                    description=(f"Model {class_node.name}.save() 中包含业务逻辑: " f"{description}"),
                    model_name=class_node.name,
                    method_name="save",
                    business_logic_description=description,
                )
                violations.append(violation)

        return violations

    # ── business logic heuristics ───────────────────────────

    def _detect_business_logic(
        self,
        save_node: ast.FunctionDef | ast.AsyncFunctionDef,
        model_name: str,
    ) -> list[str]:
        """
        使用启发式规则检测 save() 方法中的业务逻辑。

        检测规则：
        1. 调用其他Model类（如 OtherModel.objects.create）
        2. 复杂计算（多个算术运算）
        3. 外部服务调用
        4. 超出简单验证的条件逻辑

        Args:
            save_node: save() 方法的AST节点
            model_name: 所属Model类名

        Returns:
            检测到的业务逻辑描述列表
        """
        descriptions: list[str] = []

        # 规则1: 检测其他Model的ORM调用
        other_model_calls = self._detect_other_model_calls(
            save_node,
            model_name,
        )
        descriptions.extend(other_model_calls)

        # 规则2: 检测复杂计算
        complex_calc = self._detect_complex_calculations(save_node)
        if complex_calc is not None:
            descriptions.append(complex_calc)

        # 规则3: 检测外部服务调用
        service_calls = self._detect_external_service_calls(save_node)
        descriptions.extend(service_calls)

        # 规则4: 检测超出简单验证的条件逻辑
        complex_conditions = self._detect_complex_conditions(save_node)
        if complex_conditions is not None:
            descriptions.append(complex_conditions)

        return descriptions

    def _detect_other_model_calls(
        self,
        save_node: ast.FunctionDef | ast.AsyncFunctionDef,
        model_name: str,
    ) -> list[str]:
        """
        检测 save() 中对其他Model类的ORM调用。

        匹配模式: ``OtherModel.objects.<method>(...)``
        排除对自身Model的调用。

        Args:
            save_node: save() 方法的AST节点
            model_name: 当前Model类名

        Returns:
            检测到的描述列表
        """
        descriptions: list[str] = []

        for node in ast.walk(save_node):
            if not isinstance(node, ast.Call):
                continue

            func = node.func
            if not isinstance(func, ast.Attribute):
                continue

            # 检查 X.objects.<method>() 模式
            objects_node = func.value
            if not isinstance(objects_node, ast.Attribute):
                continue
            if objects_node.attr != "objects":
                continue

            target_model = objects_node.value
            if not isinstance(target_model, ast.Name):
                continue

            other_model_name: str = target_model.id
            if other_model_name == model_name:
                continue

            orm_method: str = func.attr
            descriptions.append(f"调用其他Model: {other_model_name}.objects.{orm_method}()")

        return descriptions

    @staticmethod
    def _detect_complex_calculations(
        save_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[str]:
        """
        检测 save() 中的复杂计算。

        当算术运算符（+, -, *, /, //, %, **）出现3次或以上时，
        视为复杂计算。

        Args:
            save_node: save() 方法的AST节点

        Returns:
            描述字符串，未检测到时返回None
        """
        arithmetic_count: int = 0

        for node in ast.walk(save_node):
            if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITHMETIC_OPS):
                arithmetic_count += 1
            elif isinstance(node, ast.AugAssign) and isinstance(node.op, _ARITHMETIC_OPS):
                arithmetic_count += 1

        if arithmetic_count >= 3:
            return f"复杂计算逻辑（{arithmetic_count}个算术运算）"
        return None

    @staticmethod
    def _detect_external_service_calls(
        save_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> list[str]:
        """
        检测 save() 中的外部服务调用。

        匹配模式:
        - ``self.<service_attr>(...)`` 或 ``<obj>.<service_attr>(...)``
          其中 service_attr 在 _EXTERNAL_SERVICE_ATTRS 中
        - ``<obj>.delete()`` 仅当 obj 不是 cache 等缓存对象时才算违规
        - 排除 super().save() 和验证方法

        Args:
            save_node: save() 方法的AST节点

        Returns:
            检测到的描述列表
        """
        descriptions: list[str] = []

        for node in ast.walk(save_node):
            if not isinstance(node, ast.Call):
                continue

            func = node.func
            if not isinstance(func, ast.Attribute):
                continue

            method_name: str = func.attr
            if method_name in _VALIDATION_PATTERNS:
                continue
            if method_name == "save":
                continue

            # 对 delete() 特殊处理：排除 cache.delete() 等缓存操作
            if method_name == "delete":
                caller_name = _get_caller_name(func.value)
                if caller_name in _CACHE_LIKE_NAMES:
                    continue
                descriptions.append(f"外部服务调用: {method_name}()")
                continue

            if method_name in _EXTERNAL_SERVICE_ATTRS:
                descriptions.append(f"外部服务调用: {method_name}()")

        return descriptions

    @staticmethod
    def _detect_complex_conditions(
        save_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[str]:
        """
        检测 save() 中超出简单验证的条件逻辑。

        当 save() 方法中包含3个或以上的 if/elif 分支时，
        视为超出简单验证的复杂条件逻辑。
        仅计算 save() 方法体中的直接和嵌套 if 语句。

        Args:
            save_node: save() 方法的AST节点

        Returns:
            描述字符串，未检测到时返回None
        """
        if_count: int = 0

        for node in ast.walk(save_node):
            if isinstance(node, ast.If):
                if_count += 1

        if if_count >= 3:
            return f"复杂条件逻辑（{if_count}个if分支）"
        return None

    # ── Django Model detection ──────────────────────────────

    @staticmethod
    def _is_django_model(class_node: ast.ClassDef) -> bool:
        """
        判断类是否继承自Django Model。

        检查类的基类列表中是否包含已知的Django Model基类名。
        支持 ``models.Model`` 和 ``Model`` 两种写法。

        Args:
            class_node: ast.ClassDef 节点

        Returns:
            True 表示该类是Django Model子类
        """
        for base in class_node.bases:
            if isinstance(base, ast.Name) and base.id in _DJANGO_MODEL_BASES:
                return True
            if isinstance(base, ast.Attribute):
                # 处理 models.Model 形式
                full_name = _get_attribute_full_name(base)
                if full_name in _DJANGO_MODEL_BASES:
                    return True
        return False

    # ── path filtering ──────────────────────────────────────

    @staticmethod
    def _is_model_file(file_path: Path) -> bool:
        """
        判断文件是否为Model层文件。

        匹配条件（满足任一即可）：
        1. 文件位于 models/ 目录下
        2. 文件名为 models.py

        Args:
            file_path: 文件路径

        Returns:
            True 表示该文件是Model层文件
        """
        if "models" in file_path.parts:
            return True
        if file_path.name == "models.py":
            return True
        return False


def _get_attribute_full_name(node: ast.Attribute) -> str:
    """
    从 ast.Attribute 节点提取完整的点分名称。

    例如: ``models.Model`` → ``"models.Model"``

    Args:
        node: ast.Attribute 节点

    Returns:
        点分名称字符串
    """
    parts: list[str] = [node.attr]
    current: ast.expr = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return ".".join(parts)


def _get_caller_name(node: ast.expr) -> str:
    """
    从AST表达式节点提取调用者名称。

    例如:
    - ``cache`` (Name节点) → ``"cache"``
    - ``self.cache`` (Attribute节点) → ``"cache"``

    Args:
        node: AST表达式节点

    Returns:
        调用者名称字符串，无法识别时返回空字符串
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
