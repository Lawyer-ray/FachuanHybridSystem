"""
Service 方法提取器

分析 ORM 调用，生成 Service 方法签名和模板。
使用 AST 检查 Service 文件中方法是否已存在，
必要时生成方法模板并更新导入语句。
"""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .api_refactoring_engine import ParsedOrmCall, _build_service_method_name, _to_snake_case
from .logging_config import get_logger

logger = get_logger("service_method_extractor")


@dataclass
class ServiceMethodSignature:
    """Service 方法签名"""

    method_name: str
    model_name: str
    orm_method: str
    return_type: str
    params: list[str] = field(default_factory=list)


@dataclass
class ServiceMethodTemplate:
    """生成的 Service 方法模板"""

    method_name: str
    source_code: str
    model_name: str
    orm_method: str
    return_type: str


@dataclass
class ServiceFileUpdate:
    """Service 文件更新信息"""

    service_file_path: Path
    class_name: str
    method_template: ServiceMethodTemplate
    needs_model_import: bool = False
    model_import_line: str = ""


# ORM 方法到返回类型的映射
_RETURN_TYPE_MAP: dict[str, str] = {
    "filter": "QuerySet",
    "exclude": "QuerySet",
    "all": "QuerySet",
    "annotate": "QuerySet",
    "values": "QuerySet",
    "values_list": "QuerySet",
    "order_by": "QuerySet",
    "get": "{model}",
    "first": "Optional[{model}]",
    "last": "Optional[{model}]",
    "create": "{model}",
    "get_or_create": "tuple[{model}, bool]",
    "update_or_create": "tuple[{model}, bool]",
    "update": "int",
    "delete": "tuple[int, dict[str, int]]",
    "count": "int",
    "exists": "bool",
    "aggregate": "dict[str, Any]",
    "bulk_create": "list[{model}]",
    "bulk_update": "int",
}

# ORM 方法到方法体模板的映射
_METHOD_BODY_MAP: dict[str, str] = {
    "filter": "return {model}.objects.filter(**kwargs)",
    "exclude": "return {model}.objects.exclude(**kwargs)",
    "all": "return {model}.objects.all()",
    "get": "return {model}.objects.get(**kwargs)",
    "first": "return {model}.objects.filter(**kwargs).first()",
    "last": "return {model}.objects.filter(**kwargs).last()",
    "create": "return {model}.objects.create(**kwargs)",
    "update": "return {model}.objects.filter(**kwargs).update(**update_fields)",
    "delete": "return {model}.objects.filter(**kwargs).delete()",
    "count": "return {model}.objects.filter(**kwargs).count()",
    "exists": "return {model}.objects.filter(**kwargs).exists()",
    "aggregate": "return {model}.objects.aggregate(**kwargs)",
    "get_or_create": "return {model}.objects.get_or_create(**kwargs)",
    "update_or_create": "return {model}.objects.update_or_create(**kwargs)",
    "bulk_create": "return {model}.objects.bulk_create(objs, **kwargs)",
    "bulk_update": "return {model}.objects.bulk_update(objs, fields, **kwargs)",
    "values": "return {model}.objects.values(**kwargs)",
    "values_list": "return {model}.objects.values_list(**kwargs)",
    "annotate": "return {model}.objects.annotate(**kwargs)",
    "order_by": "return {model}.objects.order_by(*args)",
}

# ORM 方法到参数签名的映射
_PARAMS_MAP: dict[str, list[str]] = {
    "filter": ["**kwargs: Any"],
    "exclude": ["**kwargs: Any"],
    "all": [],
    "get": ["**kwargs: Any"],
    "first": ["**kwargs: Any"],
    "last": ["**kwargs: Any"],
    "create": ["**kwargs: Any"],
    "update": ["update_fields: dict[str, Any]", "**kwargs: Any"],
    "delete": ["**kwargs: Any"],
    "count": ["**kwargs: Any"],
    "exists": ["**kwargs: Any"],
    "aggregate": ["**kwargs: Any"],
    "get_or_create": ["**kwargs: Any"],
    "update_or_create": ["**kwargs: Any"],
    "bulk_create": ["objs: list[{model}]", "**kwargs: Any"],
    "bulk_update": ["objs: list[{model}]", "fields: list[str]", "**kwargs: Any"],
    "values": ["**kwargs: Any"],
    "values_list": ["**kwargs: Any"],
    "annotate": ["**kwargs: Any"],
    "order_by": ["*args: str"],
}


class ServiceMethodExtractor:
    """
    Service 方法提取器

    从 ParsedOrmCall 分析 ORM 调用，生成 Service 方法签名和模板。
    使用 AST 检查现有 Service 文件中方法是否已存在。
    """

    def generate_signature(self, parsed: ParsedOrmCall) -> ServiceMethodSignature:
        """
        根据 ORM 调用生成 Service 方法签名。

        Args:
            parsed: 解析后的 ORM 调用信息

        Returns:
            ServiceMethodSignature 包含方法名、参数和返回类型
        """
        snake_name = _to_snake_case(parsed.model_name)
        method_name = _build_service_method_name(snake_name, parsed.orm_method)
        return_type = self._resolve_return_type(parsed.model_name, parsed.orm_method)
        params = self._resolve_params(parsed.model_name, parsed.orm_method)

        logger.info(
            "生成方法签名: %s(self, %s) -> %s",
            method_name,
            ", ".join(params),
            return_type,
        )

        return ServiceMethodSignature(
            method_name=method_name,
            model_name=parsed.model_name,
            orm_method=parsed.orm_method,
            return_type=return_type,
            params=params,
        )

    def generate_method_template(
        self,
        signature: ServiceMethodSignature,
    ) -> ServiceMethodTemplate:
        """
        根据方法签名生成完整的方法模板（stub）。

        生成的模板遵循项目架构模式::

            def filter_contracts(self, **kwargs: Any) -> QuerySet:
                return Contract.objects.filter(**kwargs)

        Args:
            signature: Service 方法签名

        Returns:
            ServiceMethodTemplate 包含完整的方法源代码
        """
        params_str = ", ".join(["self"] + signature.params)
        body = self._resolve_method_body(signature.model_name, signature.orm_method)

        source = (
            f"def {signature.method_name}({params_str}) -> {signature.return_type}:\n"
            f"    {body}\n"
        )

        logger.info("生成方法模板: %s", signature.method_name)

        return ServiceMethodTemplate(
            method_name=signature.method_name,
            source_code=source,
            model_name=signature.model_name,
            orm_method=signature.orm_method,
            return_type=signature.return_type,
        )

    def check_method_exists(
        self,
        service_file: Path,
        method_name: str,
    ) -> bool:
        """
        使用 AST 检查 Service 文件中方法是否已存在。

        Args:
            service_file: Service 文件路径
            method_name: 要检查的方法名

        Returns:
            True 如果方法已存在
        """
        if not service_file.exists():
            logger.info("Service 文件不存在: %s", service_file)
            return False

        source = service_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("Service 文件解析失败: %s - %s", service_file, exc)
            return False

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_name:
                    logger.info(
                        "方法已存在: %s 在 %s 第 %d 行",
                        method_name,
                        service_file,
                        node.lineno,
                    )
                    return True

        return False

    def check_service_file_exists(self, service_file: Path) -> bool:
        """
        检查 Service 文件是否存在。

        Args:
            service_file: Service 文件路径

        Returns:
            True 如果文件存在
        """
        exists = service_file.exists()
        if not exists:
            logger.info("Service 文件不存在: %s", service_file)
        return exists

    def find_service_class(
        self,
        service_file: Path,
    ) -> Optional[str]:
        """
        在 Service 文件中查找 Service 类名。

        查找以 ``Service`` 结尾的类定义。

        Args:
            service_file: Service 文件路径

        Returns:
            Service 类名，未找到时返回 None
        """
        if not service_file.exists():
            return None

        source = service_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("Service 文件解析失败: %s - %s", service_file, exc)
            return None

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Service"):
                return node.name

        return None

    def generate_import_line(self, model_name: str, app_label: str) -> str:
        """
        生成 Model 导入语句。

        Args:
            model_name: Model 类名
            app_label: Django app 标签 (如 "contracts")

        Returns:
            导入语句字符串
        """
        return f"from apps.{app_label}.models import {model_name}"

    def plan_service_update(
        self,
        parsed: ParsedOrmCall,
        service_file: Path,
        app_label: str,
    ) -> Optional[ServiceFileUpdate]:
        """
        规划 Service 文件更新。

        综合分析 ORM 调用，检查方法是否已存在，
        生成完整的更新计划。

        Args:
            parsed: 解析后的 ORM 调用信息
            service_file: Service 文件路径
            app_label: Django app 标签

        Returns:
            ServiceFileUpdate 或 None（方法已存在时）
        """
        signature = self.generate_signature(parsed)

        if self.check_method_exists(service_file, signature.method_name):
            logger.info(
                "方法 %s 已存在于 %s，跳过生成",
                signature.method_name,
                service_file,
            )
            return None

        template = self.generate_method_template(signature)
        class_name = self.find_service_class(service_file)
        if class_name is None:
            snake_name = _to_snake_case(parsed.model_name)
            class_name = f"{parsed.model_name}Service"

        needs_import = not self._has_model_import(service_file, parsed.model_name)
        import_line = self.generate_import_line(parsed.model_name, app_label) if needs_import else ""

        logger.info(
            "规划更新: %s.%s 在 %s (需要导入: %s)",
            class_name,
            signature.method_name,
            service_file,
            needs_import,
        )

        return ServiceFileUpdate(
            service_file_path=service_file,
            class_name=class_name,
            method_template=template,
            needs_model_import=needs_import,
            model_import_line=import_line,
        )

    # ── 内部方法 ────────────────────────────────────────────

    def _resolve_return_type(self, model_name: str, orm_method: str) -> str:
        """解析返回类型，将 {model} 占位符替换为实际 Model 名称。"""
        template = _RETURN_TYPE_MAP.get(orm_method, "Any")
        return template.format(model=model_name)

    def _resolve_params(self, model_name: str, orm_method: str) -> list[str]:
        """解析参数列表，将 {model} 占位符替换为实际 Model 名称。"""
        templates = _PARAMS_MAP.get(orm_method, ["**kwargs: Any"])
        return [p.format(model=model_name) for p in templates]

    def _resolve_method_body(self, model_name: str, orm_method: str) -> str:
        """解析方法体，将 {model} 占位符替换为实际 Model 名称。"""
        template = _METHOD_BODY_MAP.get(orm_method, f"return {model_name}.objects.{orm_method}(**kwargs)")
        return template.format(model=model_name)

    def _has_model_import(self, service_file: Path, model_name: str) -> bool:
        """检查 Service 文件是否已导入指定 Model。"""
        if not service_file.exists():
            return False

        source = service_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    if name == model_name:
                        return True

        return False
