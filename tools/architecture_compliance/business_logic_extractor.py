"""
Model层业务逻辑提取器

从 SaveMethodAnalyzer 的分析结果中提取业务逻辑代码块，
生成对应的 Service 方法模板，并生成清理后的 save() 方法
（仅保留字段赋值、数据验证和 super().save() 调用）。

工作流程：
1. 接收 SaveMethodAnalysis 分析结果
2. 提取所有 business_logic 类型的代码块
3. 为每个业务逻辑块生成 Service 方法模板（方法名、参数、方法体）
4. 生成清理后的 save() 方法（移除业务逻辑块）
5. 可选：将 data_validation 块迁移到 clean() 方法
6. 返回结构化的 SaveMethodRefactoring 结果
"""
from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .save_method_analyzer import (
    BLOCK_BUSINESS_LOGIC,
    BLOCK_DATA_VALIDATION,
    BLOCK_FIELD_ASSIGNMENT,
    BLOCK_SUPER_CALL,
    SaveMethodAnalysis,
    SaveMethodBlock,
)

logger = get_logger("business_logic_extractor")


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class ExtractedServiceMethod:
    """提取的Service方法"""

    method_name: str
    parameters: list[str]  # e.g., ["contract: Contract", "amount: Decimal"]
    body_code: str  # The extracted business logic code
    description: str
    source_lines: tuple[int, int]  # Original line range in save()


@dataclass
class SaveMethodRefactoring:
    """save()方法重构结果"""

    model_name: str
    file_path: str
    service_methods: list[ExtractedServiceMethod]
    cleaned_save_code: str  # The save() method with business logic removed
    clean_method_code: Optional[str]  # Optional clean() method for validation logic
    original_save_code: str



# ── CamelCase → snake_case 转换 ─────────────────────────────

_CAMEL_TO_SNAKE_RE: re.Pattern[str] = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


def _to_snake_case(name: str) -> str:
    """
    将 CamelCase 名称转为 snake_case。

    Args:
        name: CamelCase 名称

    Returns:
        snake_case 名称
    """
    return _CAMEL_TO_SNAKE_RE.sub("_", name).lower()


# ── 业务逻辑描述 → 方法名映射 ──────────────────────────────

# 已知的外部服务调用动词 → 方法名前缀
_SERVICE_VERB_MAP: dict[str, str] = {
    "notify": "notify",
    "send": "send",
    "send_mail": "send_mail",
    "send_email": "send_email",
    "publish": "publish",
    "dispatch": "dispatch",
    "emit": "emit",
}

# ORM 方法 → 方法名动词
_ORM_VERB_MAP: dict[str, str] = {
    "create": "create",
    "filter": "query",
    "get": "get",
    "update": "update",
    "delete": "delete",
    "bulk_create": "bulk_create",
}


def _derive_method_name_from_description(
    description: str,
    model_name: str,
) -> str:
    """
    从业务逻辑描述中推导 Service 方法名。

    策略：
    1. 如果描述包含 OtherModel.objects.create → create_{snake_model}
    2. 如果描述包含外部服务调用 → {verb}_{context}
    3. 如果描述包含 Service 实例化 → call_{service_snake}
    4. 回退 → handle_{model_snake}_business_logic

    Args:
        description: SaveMethodBlock 的 description 字段
        model_name: 当前 Model 类名

    Returns:
        推导出的方法名（snake_case）
    """
    # 模式1: 调用其他Model: OtherModel.objects.create()
    orm_match = re.search(
        r"调用其他Model:\s*(\w+)\.objects\.(\w+)\(\)", description,
    )
    if orm_match:
        target_model = orm_match.group(1)
        orm_method = orm_match.group(2)
        verb = _ORM_VERB_MAP.get(orm_method, orm_method)
        return f"{verb}_{_to_snake_case(target_model)}"

    # 模式2: 外部服务调用: notify()
    svc_match = re.search(r"外部服务调用:\s*(\w+)\(\)", description)
    if svc_match:
        verb = svc_match.group(1)
        model_snake = _to_snake_case(model_name)
        prefix = _SERVICE_VERB_MAP.get(verb, verb)
        return f"{prefix}_{model_snake}_event"

    # 模式3: 实例化服务: SomeService()
    inst_match = re.search(r"实例化服务:\s*(\w+)\(\)", description)
    if inst_match:
        service_name = inst_match.group(1)
        return f"call_{_to_snake_case(service_name)}"

    # 模式4: 条件分支中的业务逻辑（递归提取内部描述）
    inner_match = re.search(r"条件分支中的业务逻辑:\s*(.+)", description)
    if inner_match:
        inner_desc = inner_match.group(1)
        return _derive_method_name_from_description(inner_desc, model_name)

    # 模式5: 复杂计算逻辑
    if "复杂计算" in description:
        return f"calculate_{_to_snake_case(model_name)}_fields"

    # 回退
    model_snake = _to_snake_case(model_name)
    return f"handle_{model_snake}_business_logic"


def _extract_model_references(block: SaveMethodBlock) -> list[str]:
    """
    从代码块的 AST 节点中提取引用的 Model 名称。

    扫描 AST 查找 SomeModel.objects.* 模式中的 Model 名称。

    Args:
        block: 代码块

    Returns:
        引用的 Model 名称列表（去重）
    """
    models: list[str] = []
    seen: set[str] = set()

    for node in block.ast_nodes:
        for child in ast.walk(node):
            if not isinstance(child, ast.Attribute):
                continue
            if child.attr != "objects":
                continue
            if isinstance(child.value, ast.Name):
                name = child.value.id
                if name not in seen:
                    seen.add(name)
                    models.append(name)

    return models


def _extract_self_field_references(block: SaveMethodBlock) -> list[str]:
    """
    从代码块的 AST 节点中提取引用的 self.field 名称。

    Args:
        block: 代码块

    Returns:
        引用的字段名列表（去重）
    """
    fields: list[str] = []
    seen: set[str] = set()

    for node in block.ast_nodes:
        for child in ast.walk(node):
            if not isinstance(child, ast.Attribute):
                continue
            if not isinstance(child.value, ast.Name):
                continue
            if child.value.id != "self":
                continue
            field_name = child.attr
            if field_name not in seen:
                seen.add(field_name)
                fields.append(field_name)

    return fields


def _build_parameters(
    block: SaveMethodBlock,
    model_name: str,
) -> list[str]:
    """
    根据代码块中的引用构建 Service 方法参数列表。

    规则：
    - 如果引用了 self.field，添加 model_instance 参数
    - 如果引用了其他 Model，不额外添加参数（Service 内部处理）

    Args:
        block: 业务逻辑代码块
        model_name: 当前 Model 类名

    Returns:
        参数列表，如 ["contract: Contract"]
    """
    self_fields = _extract_self_field_references(block)
    model_snake = _to_snake_case(model_name)

    # 业务逻辑块几乎总是需要 model 实例作为参数
    if self_fields:
        return [f"{model_snake}: {model_name}"]

    # 即使没有显式 self.field 引用，也传入实例（保守策略）
    return [f"{model_snake}: {model_name}"]


def _rewrite_self_to_param(
    code: str,
    model_name: str,
) -> str:
    """
    将代码中的 self 引用替换为 model_param。

    同时处理 ``self.field`` 和独立的 ``self``（作为参数传递时）。

    Args:
        code: 原始代码片段
        model_name: Model 类名

    Returns:
        替换后的代码
    """
    param_name = _to_snake_case(model_name)
    # 替换所有 self 单词（包括 self.xxx 和独立的 self）
    return re.sub(r"\bself\b", param_name, code)


# ── BusinessLogicExtractor ──────────────────────────────────


class BusinessLogicExtractor:
    """
    业务逻辑提取器

    从 SaveMethodAnalysis 结果中提取业务逻辑代码块，
    生成 Service 方法模板和清理后的 save()/clean() 方法。
    """

    # ── 公开 API ────────────────────────────────────────────

    def extract(
        self,
        analysis: SaveMethodAnalysis,
    ) -> SaveMethodRefactoring:
        """
        从 save() 方法分析结果中提取业务逻辑。

        Args:
            analysis: SaveMethodAnalyzer 的分析结果

        Returns:
            SaveMethodRefactoring 包含提取的 Service 方法、
            清理后的 save() 代码和可选的 clean() 方法
        """
        model_name = analysis.model_name

        # 按类型分组代码块
        biz_blocks = [
            b for b in analysis.blocks
            if b.block_type == BLOCK_BUSINESS_LOGIC
        ]
        val_blocks = [
            b for b in analysis.blocks
            if b.block_type == BLOCK_DATA_VALIDATION
        ]
        assign_blocks = [
            b for b in analysis.blocks
            if b.block_type == BLOCK_FIELD_ASSIGNMENT
        ]
        super_blocks = [
            b for b in analysis.blocks
            if b.block_type == BLOCK_SUPER_CALL
        ]

        # 生成 Service 方法模板
        service_methods = self._generate_service_methods(
            biz_blocks, model_name,
        )

        # 生成清理后的 save() 方法
        cleaned_save = self._generate_cleaned_save(
            assign_blocks=assign_blocks,
            super_blocks=super_blocks,
            model_name=model_name,
        )

        # 生成 clean() 方法（如果有验证逻辑）
        clean_method = self._generate_clean_method(
            val_blocks, model_name,
        )

        # 拼接原始 save() 代码
        original_save = self._reconstruct_original_save(
            analysis.blocks, model_name,
        )

        result = SaveMethodRefactoring(
            model_name=model_name,
            file_path=analysis.file_path,
            service_methods=service_methods,
            cleaned_save_code=cleaned_save,
            clean_method_code=clean_method,
            original_save_code=original_save,
        )

        logger.info(
            "%s: 提取了 %d 个 Service 方法, clean()=%s",
            model_name,
            len(service_methods),
            clean_method is not None,
        )

        return result

    def extract_from_file(
        self,
        file_path: Path,
        analyses: list[SaveMethodAnalysis],
    ) -> list[SaveMethodRefactoring]:
        """
        从文件的多个 save() 分析结果中批量提取业务逻辑。

        Args:
            file_path: 源文件路径
            analyses: 该文件中所有 Model 的 save() 分析结果

        Returns:
            每个包含业务逻辑的 Model 对应一个 SaveMethodRefactoring
        """
        results: list[SaveMethodRefactoring] = []

        for analysis in analyses:
            if not analysis.has_business_logic:
                logger.info(
                    "%s: 无业务逻辑，跳过提取",
                    analysis.model_name,
                )
                continue

            refactoring = self.extract(analysis)
            results.append(refactoring)

        if results:
            logger.info(
                "文件 %s: 提取了 %d 个 Model 的业务逻辑",
                file_path,
                len(results),
            )

        return results

    # ── Service 方法生成 ────────────────────────────────────

    def _generate_service_methods(
        self,
        biz_blocks: list[SaveMethodBlock],
        model_name: str,
    ) -> list[ExtractedServiceMethod]:
        """
        为每个业务逻辑块生成 Service 方法模板。

        Args:
            biz_blocks: 业务逻辑代码块列表
            model_name: Model 类名

        Returns:
            ExtractedServiceMethod 列表
        """
        methods: list[ExtractedServiceMethod] = []
        seen_names: set[str] = set()

        for block in biz_blocks:
            method_name = _derive_method_name_from_description(
                block.description, model_name,
            )

            # 去重：如果方法名已存在，添加数字后缀
            original_name = method_name
            counter = 2
            while method_name in seen_names:
                method_name = f"{original_name}_{counter}"
                counter += 1
            seen_names.add(method_name)

            parameters = _build_parameters(block, model_name)
            body_code = self._build_method_body(block, model_name)

            method = ExtractedServiceMethod(
                method_name=method_name,
                parameters=parameters,
                body_code=body_code,
                description=block.description,
                source_lines=(block.line_start, block.line_end),
            )
            methods.append(method)

            logger.info(
                "生成 Service 方法: %s(%s)",
                method_name,
                ", ".join(parameters),
            )

        return methods

    def _build_method_body(
        self,
        block: SaveMethodBlock,
        model_name: str,
    ) -> str:
        """
        构建 Service 方法体代码。

        将原始代码中的 self.xxx 替换为 model_param.xxx。

        Args:
            block: 业务逻辑代码块
            model_name: Model 类名

        Returns:
            方法体代码字符串
        """
        code = block.code_snippet
        return _rewrite_self_to_param(code, model_name)

    # ── 清理后的 save() 方法生成 ────────────────────────────

    def _generate_cleaned_save(
        self,
        assign_blocks: list[SaveMethodBlock],
        super_blocks: list[SaveMethodBlock],
        model_name: str,
    ) -> str:
        """
        生成清理后的 save() 方法。

        仅保留字段赋值和 super().save() 调用，
        移除所有业务逻辑块。数据验证移至 clean()。

        Args:
            assign_blocks: 字段赋值代码块
            super_blocks: super().save() 代码块
            model_name: Model 类名

        Returns:
            清理后的 save() 方法代码
        """
        indent = "        "  # 类方法体内的标准缩进（8空格）
        lines: list[str] = []

        lines.append("    def save(self, *args, **kwargs):")

        # 先放字段赋值
        for block in assign_blocks:
            for code_line in block.code_snippet.splitlines():
                lines.append(f"{indent}{code_line}")

        # 再放 super().save()
        if super_blocks:
            for block in super_blocks:
                for code_line in block.code_snippet.splitlines():
                    lines.append(f"{indent}{code_line}")
        else:
            # 如果原始代码没有显式 super().save()，补上
            lines.append(f"{indent}super().save(*args, **kwargs)")

        # 如果 save() 方法体为空（只有签名），添加 super 调用
        if len(lines) == 1:
            lines.append(f"{indent}super().save(*args, **kwargs)")

        return "\n".join(lines)

    # ── clean() 方法生成 ────────────────────────────────────

    def _generate_clean_method(
        self,
        val_blocks: list[SaveMethodBlock],
        model_name: str,
    ) -> Optional[str]:
        """
        从验证代码块生成 clean() 方法。

        如果没有验证代码块，返回 None。

        Args:
            val_blocks: 数据验证代码块列表
            model_name: Model 类名

        Returns:
            clean() 方法代码字符串，无验证逻辑时返回 None
        """
        if not val_blocks:
            return None

        indent = "        "  # 类方法体内的标准缩进
        lines: list[str] = []

        lines.append("    def clean(self):")

        for block in val_blocks:
            for code_line in block.code_snippet.splitlines():
                lines.append(f"{indent}{code_line}")

        return "\n".join(lines)

    # ── 原始 save() 代码重建 ────────────────────────────────

    @staticmethod
    def _reconstruct_original_save(
        blocks: list[SaveMethodBlock],
        model_name: str,
    ) -> str:
        """
        从分析结果的代码块重建原始 save() 方法代码。

        Args:
            blocks: 所有代码块
            model_name: Model 类名

        Returns:
            原始 save() 方法代码
        """
        indent = "        "
        lines: list[str] = []

        lines.append("    def save(self, *args, **kwargs):")

        for block in blocks:
            for code_line in block.code_snippet.splitlines():
                lines.append(f"{indent}{code_line}")

        return "\n".join(lines)


def format_service_method_template(
    method: ExtractedServiceMethod,
    indent: str = "    ",
) -> str:
    """
    将 ExtractedServiceMethod 格式化为可插入 Service 类的方法代码。

    生成格式::

        def method_name(self, param: Type) -> None:
            \"\"\"description\"\"\"
            <body_code>

    Args:
        method: 提取的 Service 方法
        indent: 方法级缩进（默认4空格，适合类内方法）

    Returns:
        格式化后的方法代码字符串
    """
    inner_indent = indent + "    "

    params_str = ", ".join(["self"] + method.parameters)
    lines: list[str] = []

    lines.append(f"{indent}def {method.method_name}({params_str}) -> None:")
    lines.append(f'{inner_indent}"""{method.description}"""')

    for body_line in method.body_code.splitlines():
        lines.append(f"{inner_indent}{body_line}")

    return "\n".join(lines)
