"""
Model层 save() 方法分析器

解析Django Model的save()方法AST，将方法体中的每条语句分类为：
- business_logic: 创建关联对象、调用外部服务、复杂计算、信号类操作
- data_validation: 字段验证、clean()调用、简单字段转换、约束检查
- super_call: super().save() 调用
- field_assignment: 简单的 self.field = value 预保存默认值赋值

分析结果包含分类后的代码块列表、业务逻辑摘要和提取建议。
"""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger

logger = get_logger("save_method_analyzer")


# ── 代码块类型常量 ──────────────────────────────────────────

BLOCK_BUSINESS_LOGIC: str = "business_logic"
BLOCK_DATA_VALIDATION: str = "data_validation"
BLOCK_SUPER_CALL: str = "super_call"
BLOCK_FIELD_ASSIGNMENT: str = "field_assignment"


# ── 数据模型 ────────────────────────────────────────────────

@dataclass
class SaveMethodBlock:
    """save()方法中的代码块分类"""

    block_type: str  # BLOCK_* 常量之一
    line_start: int
    line_end: int
    code_snippet: str
    description: str
    ast_nodes: list[ast.stmt] = field(default_factory=list)


@dataclass
class SaveMethodAnalysis:
    """save()方法分析结果"""

    model_name: str
    file_path: str
    blocks: list[SaveMethodBlock] = field(default_factory=list)
    has_business_logic: bool = False
    business_logic_summary: list[str] = field(default_factory=list)
    extraction_recommendations: list[str] = field(default_factory=list)


# ── Django Model基类名称 ────────────────────────────────────

_DJANGO_MODEL_BASES: frozenset[str] = frozenset({
    "Model",
    "models.Model",
    "AbstractBaseUser",
    "AbstractUser",
    "PermissionsMixin",
})

# ── 验证相关的方法/属性名 ──────────────────────────────────

_VALIDATION_METHODS: frozenset[str] = frozenset({
    "full_clean",
    "clean",
    "clean_fields",
    "validate_unique",
    "validate_constraints",
})

# ── 外部服务调用的属性名模式 ────────────────────────────────

_EXTERNAL_SERVICE_ATTRS: frozenset[str] = frozenset({
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
})

# ── 算术运算符 ─────────────────────────────────────────────

_ARITHMETIC_OPS: tuple[type, ...] = (
    ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow,
)

# ── 简单内置函数（用于字段赋值判断）──────────────────────────

_SIMPLE_BUILTINS: frozenset[str] = frozenset({
    "str", "int", "float", "bool", "len", "round", "abs",
    "max", "min", "sum", "sorted", "list", "tuple", "dict", "set",
})


class SaveMethodAnalyzer:
    """
    save()方法分析器

    解析Django Model的save()方法，将方法体中的每条语句分类，
    识别业务逻辑与数据验证，生成提取建议。

    分类规则：
    - super_call: super().save(...) 调用
    - field_assignment: self.field = <简单表达式> 的预保存默认值
    - data_validation: 包含 raise ValidationError / clean() 调用 / 简单约束检查
    - business_logic: 创建关联对象、调用外部服务、复杂计算等
    """

    # ── 公开 API ────────────────────────────────────────────

    def analyze_file(self, file_path: Path) -> list[SaveMethodAnalysis]:
        """
        分析单个文件中所有Django Model的save()方法。

        Args:
            file_path: Python源文件路径

        Returns:
            每个包含save()覆写的Model对应一个SaveMethodAnalysis
        """
        file_path = Path(file_path)
        source = self._read_source(file_path)
        if source is None:
            return []

        tree = self._parse_ast(source, file_path)
        if tree is None:
            return []

        results: list[SaveMethodAnalysis] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_django_model(node):
                continue

            save_node = self._find_save_method(node)
            if save_node is None:
                continue

            analysis = self._analyze_save_method(
                save_node=save_node,
                model_name=node.name,
                source=source,
                file_path=file_path,
            )
            results.append(analysis)

        if results:
            logger.info(
                "文件 %s 中分析了 %d 个save()方法",
                file_path,
                len(results),
            )
        return results

    def analyze_source(
        self,
        source: str,
        file_path: str = "<string>",
    ) -> list[SaveMethodAnalysis]:
        """
        分析源代码字符串中所有Django Model的save()方法。

        便于测试和动态分析场景使用。

        Args:
            source: Python源代码文本
            file_path: 虚拟文件路径（用于结果标识）

        Returns:
            每个包含save()覆写的Model对应一个SaveMethodAnalysis
        """
        tree = self._parse_ast(source, Path(file_path))
        if tree is None:
            return []

        results: list[SaveMethodAnalysis] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_django_model(node):
                continue

            save_node = self._find_save_method(node)
            if save_node is None:
                continue

            analysis = self._analyze_save_method(
                save_node=save_node,
                model_name=node.name,
                source=source,
                file_path=Path(file_path),
            )
            results.append(analysis)

        return results

    # ── 核心分析逻辑 ────────────────────────────────────────

    def _analyze_save_method(
        self,
        save_node: ast.FunctionDef | ast.AsyncFunctionDef,
        model_name: str,
        source: str,
        file_path: Path,
    ) -> SaveMethodAnalysis:
        """
        分析单个save()方法，对方法体中的每条语句进行分类。

        Args:
            save_node: save()方法的AST节点
            model_name: 所属Model类名
            source: 源代码文本
            file_path: 文件路径

        Returns:
            SaveMethodAnalysis 分析结果
        """
        blocks: list[SaveMethodBlock] = []

        for stmt in save_node.body:
            # 跳过文档字符串
            if _is_docstring(stmt):
                continue

            block = self._classify_statement(stmt, model_name, source)
            blocks.append(block)

        # 汇总业务逻辑信息
        biz_blocks = [b for b in blocks if b.block_type == BLOCK_BUSINESS_LOGIC]
        has_business_logic = len(biz_blocks) > 0
        business_logic_summary = [b.description for b in biz_blocks]
        extraction_recommendations = self._generate_recommendations(
            blocks, model_name,
        )

        analysis = SaveMethodAnalysis(
            model_name=model_name,
            file_path=str(file_path),
            blocks=blocks,
            has_business_logic=has_business_logic,
            business_logic_summary=business_logic_summary,
            extraction_recommendations=extraction_recommendations,
        )

        logger.info(
            "%s.save(): %d个代码块, 业务逻辑=%s, 摘要=%s",
            model_name,
            len(blocks),
            has_business_logic,
            business_logic_summary,
        )
        return analysis

    def _classify_statement(
        self,
        stmt: ast.stmt,
        model_name: str,
        source: str,
    ) -> SaveMethodBlock:
        """
        对save()方法体中的单条语句进行分类。

        分类优先级：
        1. super().save() → super_call
        2. 包含验证模式 → data_validation
        3. 简单 self.field = value → field_assignment
        4. 包含业务逻辑模式 → business_logic
        5. 默认 → field_assignment（保守策略）

        Args:
            stmt: AST语句节点
            model_name: 所属Model类名
            source: 源代码文本

        Returns:
            SaveMethodBlock 分类结果
        """
        line_start = stmt.lineno
        line_end = stmt.end_lineno or stmt.lineno
        code_snippet = _extract_source_lines(source, line_start, line_end)

        # 1. super().save() 调用
        if _is_super_save_call(stmt):
            return SaveMethodBlock(
                block_type=BLOCK_SUPER_CALL,
                line_start=line_start,
                line_end=line_end,
                code_snippet=code_snippet,
                description="super().save() 调用",
                ast_nodes=[stmt],
            )

        # 2. 数据验证模式
        validation_desc = _detect_validation_pattern(stmt)
        if validation_desc is not None:
            return SaveMethodBlock(
                block_type=BLOCK_DATA_VALIDATION,
                line_start=line_start,
                line_end=line_end,
                code_snippet=code_snippet,
                description=validation_desc,
                ast_nodes=[stmt],
            )

        # 3. 简单字段赋值: self.field = <简单表达式>
        assignment_desc = _detect_field_assignment(stmt)
        if assignment_desc is not None:
            # 进一步检查赋值右侧是否包含业务逻辑
            if not _rhs_contains_business_logic(stmt, model_name):
                return SaveMethodBlock(
                    block_type=BLOCK_FIELD_ASSIGNMENT,
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=code_snippet,
                    description=assignment_desc,
                    ast_nodes=[stmt],
                )

        # 4. 业务逻辑模式
        biz_desc = _detect_business_logic_pattern(stmt, model_name)
        if biz_desc is not None:
            return SaveMethodBlock(
                block_type=BLOCK_BUSINESS_LOGIC,
                line_start=line_start,
                line_end=line_end,
                code_snippet=code_snippet,
                description=biz_desc,
                ast_nodes=[stmt],
            )

        # 5. 对于 if 语句，递归检查分支内容
        if isinstance(stmt, ast.If):
            inner_desc = _detect_if_business_logic(stmt, model_name)
            if inner_desc is not None:
                return SaveMethodBlock(
                    block_type=BLOCK_BUSINESS_LOGIC,
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=code_snippet,
                    description=inner_desc,
                    ast_nodes=[stmt],
                )

        # 6. 默认: 保守地归为字段赋值
        return SaveMethodBlock(
            block_type=BLOCK_FIELD_ASSIGNMENT,
            line_start=line_start,
            line_end=line_end,
            code_snippet=code_snippet,
            description="其他语句",
            ast_nodes=[stmt],
        )

    # ── 提取建议生成 ────────────────────────────────────────

    @staticmethod
    def _generate_recommendations(
        blocks: list[SaveMethodBlock],
        model_name: str,
    ) -> list[str]:
        """
        根据分类结果生成业务逻辑提取建议。

        Args:
            blocks: 分类后的代码块列表
            model_name: Model类名

        Returns:
            提取建议列表
        """
        recommendations: list[str] = []
        biz_blocks = [b for b in blocks if b.block_type == BLOCK_BUSINESS_LOGIC]

        if not biz_blocks:
            return recommendations

        service_name = f"{model_name}Service"
        recommendations.append(
            f"将 {len(biz_blocks)} 个业务逻辑块提取到 {service_name}"
        )

        for block in biz_blocks:
            recommendations.append(
                f"  - 行 {block.line_start}-{block.line_end}: {block.description}"
            )

        val_blocks = [b for b in blocks if b.block_type == BLOCK_DATA_VALIDATION]
        if val_blocks:
            recommendations.append(
                f"保留 {len(val_blocks)} 个数据验证块在 {model_name}.clean() 中"
            )

        return recommendations

    # ── save() 方法查找 ─────────────────────────────────────

    @staticmethod
    def _find_save_method(
        class_node: ast.ClassDef,
    ) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
        """
        在类定义中查找save()方法。

        Args:
            class_node: 类定义AST节点

        Returns:
            save()方法节点，未找到时返回None
        """
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == "save":
                    return item
        return None

    # ── 辅助方法 ────────────────────────────────────────────

    @staticmethod
    def _read_source(file_path: Path) -> Optional[str]:
        """
        读取源文件内容。

        Args:
            file_path: 文件路径

        Returns:
            源代码文本，读取失败时返回None
        """
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("无法读取文件 %s: %s", file_path, exc)
            return None

    @staticmethod
    def _parse_ast(source: str, file_path: Path) -> Optional[ast.Module]:
        """
        将源代码解析为AST。

        Args:
            source: 源代码文本
            file_path: 文件路径（用于错误消息）

        Returns:
            AST模块节点，解析失败时返回None
        """
        try:
            return ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            logger.warning(
                "语法错误 %s (行 %s): %s",
                file_path,
                exc.lineno,
                exc.msg,
            )
            return None


# ── 模块级辅助函数 ──────────────────────────────────────────


def _is_django_model(class_node: ast.ClassDef) -> bool:
    """
    判断类是否继承自Django Model。

    Args:
        class_node: 类定义AST节点

    Returns:
        True 表示该类是Django Model子类
    """
    for base in class_node.bases:
        if isinstance(base, ast.Name) and base.id in _DJANGO_MODEL_BASES:
            return True
        if isinstance(base, ast.Attribute):
            full_name = _get_attribute_full_name(base)
            if full_name in _DJANGO_MODEL_BASES:
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


def _is_docstring(stmt: ast.stmt) -> bool:
    """
    判断语句是否为文档字符串。

    Args:
        stmt: AST语句节点

    Returns:
        True 表示是文档字符串
    """
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_super_save_call(stmt: ast.stmt) -> bool:
    """
    判断语句是否为 super().save(...) 调用。

    匹配模式:
    - ``super().save(...)``
    - ``super(ClassName, self).save(...)``

    Args:
        stmt: AST语句节点

    Returns:
        True 表示是 super().save() 调用
    """
    if not isinstance(stmt, ast.Expr):
        return False
    if not isinstance(stmt.value, ast.Call):
        return False

    func = stmt.value.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "save":
        return False

    # 检查调用者是 super() 或 super(Cls, self)
    caller = func.value
    if isinstance(caller, ast.Call):
        if isinstance(caller.func, ast.Name) and caller.func.id == "super":
            return True
    return False


def _detect_validation_pattern(stmt: ast.stmt) -> Optional[str]:
    """
    检测语句是否为数据验证模式。

    匹配模式:
    - raise ValidationError(...)
    - self.full_clean() / self.clean() 等验证方法调用
    - if <condition>: raise ValidationError(...)

    Args:
        stmt: AST语句节点

    Returns:
        验证描述字符串，非验证模式时返回None
    """
    # 直接 raise ValidationError
    if isinstance(stmt, ast.Raise):
        if _is_validation_error_raise(stmt):
            return "raise ValidationError 数据验证"

    # self.clean() / self.full_clean() 等调用
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        if isinstance(call.func, ast.Attribute):
            if call.func.attr in _VALIDATION_METHODS:
                return f"调用验证方法: {call.func.attr}()"

    # if <condition>: raise ValidationError
    if isinstance(stmt, ast.If):
        if _if_only_raises_validation_error(stmt):
            return "条件验证: if ... raise ValidationError"

    return None


def _is_validation_error_raise(raise_node: ast.Raise) -> bool:
    """
    判断 raise 语句是否抛出 ValidationError。

    Args:
        raise_node: ast.Raise 节点

    Returns:
        True 表示抛出 ValidationError
    """
    exc = raise_node.exc
    if exc is None:
        return False
    # raise ValidationError(...)
    if isinstance(exc, ast.Call):
        func = exc.func
        if isinstance(func, ast.Name) and func.id == "ValidationError":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "ValidationError":
            return True
    # raise ValidationError (无括号，罕见但合法)
    if isinstance(exc, ast.Name) and exc.id == "ValidationError":
        return True
    return False


def _if_only_raises_validation_error(if_node: ast.If) -> bool:
    """
    判断 if 语句是否仅包含 raise ValidationError。

    检查 if 的 body 和 orelse 中是否只有 raise ValidationError
    或简单赋值（用于验证消息构建）。

    Args:
        if_node: ast.If 节点

    Returns:
        True 表示该 if 仅用于数据验证
    """
    for child_stmt in if_node.body:
        if isinstance(child_stmt, ast.Raise):
            if _is_validation_error_raise(child_stmt):
                return True
    # 嵌套 if 中的 raise
    for child_stmt in if_node.body:
        if isinstance(child_stmt, ast.If):
            if _if_only_raises_validation_error(child_stmt):
                return True
    return False


def _detect_field_assignment(stmt: ast.stmt) -> Optional[str]:
    """
    检测语句是否为简单字段赋值: self.field = <value>。

    仅匹配直接赋值语句（非增量赋值），且目标为 self 的属性。

    Args:
        stmt: AST语句节点

    Returns:
        赋值描述字符串，非字段赋值时返回None
    """
    if not isinstance(stmt, ast.Assign):
        return None
    if len(stmt.targets) != 1:
        return None

    target = stmt.targets[0]
    if not isinstance(target, ast.Attribute):
        return None
    if not isinstance(target.value, ast.Name):
        return None
    if target.value.id != "self":
        return None

    field_name: str = target.attr
    return f"字段赋值: self.{field_name}"


def _rhs_contains_business_logic(
    stmt: ast.stmt,
    model_name: str,
) -> bool:
    """
    检查赋值语句右侧是否包含业务逻辑。

    业务逻辑标志：
    - 调用其他Model的ORM方法
    - 调用外部服务
    - 复杂计算（3+个算术运算）

    Args:
        stmt: 赋值语句AST节点
        model_name: 当前Model类名

    Returns:
        True 表示右侧包含业务逻辑
    """
    if not isinstance(stmt, ast.Assign):
        return False

    value = stmt.value

    # 检查是否调用了其他Model的ORM方法
    for node in ast.walk(value):
        if _is_other_model_orm_call(node, model_name):
            return True
        if _is_external_service_call(node):
            return True

    # 检查复杂计算
    arith_count = sum(
        1 for node in ast.walk(value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITHMETIC_OPS)
    )
    if arith_count >= 3:
        return True

    return False


def _detect_business_logic_pattern(
    stmt: ast.stmt,
    model_name: str,
) -> Optional[str]:
    """
    检测语句是否包含业务逻辑模式。

    业务逻辑模式：
    - OtherModel.objects.create/filter/get 等ORM调用
    - 外部服务调用（send, notify, publish 等）
    - 复杂计算（3+个算术运算）
    - 实例化其他Service类

    Args:
        stmt: AST语句节点
        model_name: 当前Model类名

    Returns:
        业务逻辑描述字符串，非业务逻辑时返回None
    """
    descriptions: list[str] = []

    for node in ast.walk(stmt):
        # 其他Model的ORM调用
        orm_desc = _describe_other_model_orm_call(node, model_name)
        if orm_desc is not None:
            descriptions.append(orm_desc)

        # 外部服务调用
        svc_desc = _describe_external_service_call(node)
        if svc_desc is not None:
            descriptions.append(svc_desc)

        # Service类实例化
        svc_inst_desc = _describe_service_instantiation(node)
        if svc_inst_desc is not None:
            descriptions.append(svc_inst_desc)

    # 复杂计算
    arith_count = sum(
        1 for node in ast.walk(stmt)
        if isinstance(node, ast.BinOp) and isinstance(node.op, _ARITHMETIC_OPS)
    )
    if arith_count >= 3:
        descriptions.append(f"复杂计算逻辑（{arith_count}个算术运算）")

    if descriptions:
        return "; ".join(descriptions)
    return None


def _detect_if_business_logic(
    if_node: ast.If,
    model_name: str,
) -> Optional[str]:
    """
    检测 if 语句内部是否包含业务逻辑。

    递归检查 if 的 body 和 orelse 中的语句。

    Args:
        if_node: ast.If 节点
        model_name: 当前Model类名

    Returns:
        业务逻辑描述字符串，无业务逻辑时返回None
    """
    all_stmts: list[ast.stmt] = list(if_node.body) + list(if_node.orelse)

    for child_stmt in all_stmts:
        desc = _detect_business_logic_pattern(child_stmt, model_name)
        if desc is not None:
            return f"条件分支中的业务逻辑: {desc}"

        # 嵌套 if
        if isinstance(child_stmt, ast.If):
            nested_desc = _detect_if_business_logic(child_stmt, model_name)
            if nested_desc is not None:
                return nested_desc

    return None


# ── ORM / 服务调用检测辅助函数 ──────────────────────────────


def _is_other_model_orm_call(node: ast.AST, model_name: str) -> bool:
    """
    判断AST节点是否为其他Model的ORM调用。

    匹配模式: OtherModel.objects.<method>(...)

    Args:
        node: AST节点
        model_name: 当前Model类名

    Returns:
        True 表示是其他Model的ORM调用
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    objects_node = func.value
    if not isinstance(objects_node, ast.Attribute):
        return False
    if objects_node.attr != "objects":
        return False
    target = objects_node.value
    if not isinstance(target, ast.Name):
        return False
    return target.id != model_name


def _describe_other_model_orm_call(
    node: ast.AST,
    model_name: str,
) -> Optional[str]:
    """
    描述其他Model的ORM调用。

    Args:
        node: AST节点
        model_name: 当前Model类名

    Returns:
        描述字符串，非ORM调用时返回None
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    objects_node = func.value
    if not isinstance(objects_node, ast.Attribute):
        return None
    if objects_node.attr != "objects":
        return None
    target = objects_node.value
    if not isinstance(target, ast.Name):
        return None
    if target.id == model_name:
        return None
    return f"调用其他Model: {target.id}.objects.{func.attr}()"


def _is_external_service_call(node: ast.AST) -> bool:
    """
    判断AST节点是否为外部服务调用。

    Args:
        node: AST节点

    Returns:
        True 表示是外部服务调用
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in _EXTERNAL_SERVICE_ATTRS


def _describe_external_service_call(node: ast.AST) -> Optional[str]:
    """
    描述外部服务调用。

    Args:
        node: AST节点

    Returns:
        描述字符串，非外部服务调用时返回None
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in _EXTERNAL_SERVICE_ATTRS:
        return None
    return f"外部服务调用: {func.attr}()"


def _describe_service_instantiation(node: ast.AST) -> Optional[str]:
    """
    描述Service类实例化。

    匹配模式: XxxService()

    Args:
        node: AST节点

    Returns:
        描述字符串，非Service实例化时返回None
    """
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Name):
        return None
    name: str = node.func.id
    if name.endswith("Service") and name != "Service":
        return f"实例化服务: {name}()"
    return None


def _extract_source_lines(
    source: str,
    line_start: int,
    line_end: int,
) -> str:
    """
    从源代码中提取指定行范围的文本。

    Args:
        source: 完整源代码
        line_start: 起始行号（1-based）
        line_end: 结束行号（1-based，含）

    Returns:
        提取的代码文本（去除公共缩进）
    """
    lines = source.splitlines()
    start_idx = max(0, line_start - 1)
    end_idx = min(len(lines), line_end)
    selected = lines[start_idx:end_idx]
    if not selected:
        return ""
    return textwrap.dedent("\n".join(selected)).strip()
