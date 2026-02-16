"""
Service层静态方法转换器

将 StaticMethodAnalyzer 分类为 "convert" 的静态方法转换为实例方法：

1. 移除 ``@staticmethod`` 装饰器行
2. 在方法签名中添加 ``self`` 作为第一个参数
3. 将方法体中的 ``ClassName.method(...)`` 替换为 ``self.method(...)``
4. 识别需要注入的依赖（Model.objects、外部Service、settings等）
5. 如果类没有 ``__init__``，生成包含依赖注入的构造函数
6. 如果类已有 ``__init__``，将新依赖追加到现有构造函数

采用行级正则替换，不做完整 AST 重写，保持简单可靠。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import RefactoringResult
from .static_method_analyzer import StaticMethodAnalyzer, StaticMethodClassification, StaticMethodInfo

logger = get_logger("static_method_converter")


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class DependencyInfo:
    """需要注入的依赖信息"""

    name: str  # 属性名，如 "case_service"
    source: str  # 来源描述，如 "Model.objects.Case" 或 "settings"
    rule: str  # 触发的规则名


@dataclass
class MethodConversionPlan:
    """单个方法的转换计划"""

    class_name: str
    method_name: str
    line_number: int  # 方法定义行号 (1-based)
    decorator_line: int  # @staticmethod 装饰器行号 (1-based)
    dependencies: list[DependencyInfo] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)


@dataclass
class FileConversionPlan:
    """单个文件的转换计划"""

    file_path: Path
    methods: list[MethodConversionPlan] = field(default_factory=list)
    classes_needing_init: dict[str, list[DependencyInfo]] = field(
        default_factory=dict,
    )
    """class_name -> 需要注入的依赖列表"""
    classes_with_init: set[str] = field(default_factory=set)
    """已有 __init__ 的类"""
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── 正则模式 ────────────────────────────────────────────────

# 匹配 @staticmethod 装饰器行（允许前导空白）
_STATICMETHOD_DECORATOR_RE: re.Pattern[str] = re.compile(r"^(\s*)@staticmethod\s*$")

# 匹配 def method_name(... 的方法签名行
_DEF_SIGNATURE_RE: re.Pattern[str] = re.compile(r"^(\s*)(async\s+)?def\s+(\w+)\s*\(")

# 匹配 ClassName.method_name( 调用模式
_CLASS_METHOD_CALL_RE_TEMPLATE = r"\b{class_name}\.(\w+)\s*\("


# ── StaticMethodConverter ───────────────────────────────────


class StaticMethodConverter:
    """
    Service层静态方法转换器

    接收 StaticMethodAnalyzer 的分析结果，对分类为 "convert" 的方法
    执行以下转换：

    - 移除 ``@staticmethod`` 装饰器
    - 添加 ``self`` 参数
    - 将 ``ClassName.method()`` 替换为 ``self.method()``
    - 识别依赖并更新/生成 ``__init__`` 构造函数

    使用行级正则替换，保持简单可靠。
    """

    def __init__(self) -> None:
        self._analyzer = StaticMethodAnalyzer()

    # ── 公开 API ────────────────────────────────────────────

    def convert_file(
        self,
        file_path: Path,
        methods_to_convert: list[StaticMethodInfo],
        *,
        dry_run: bool = False,
    ) -> RefactoringResult:
        """
        对单个文件执行静态方法转换。

        Args:
            file_path: 目标文件路径
            methods_to_convert: 需要转换的静态方法列表
                （应来自 StaticMethodAnalyzer，且 classification == CONVERT）
            dry_run: 为 True 时不写入文件

        Returns:
            RefactoringResult 包含变更详情
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                error_message=f"文件不存在: {file_path}",
            )

        source = self._read_source(file_path)
        if source is None:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                error_message=f"无法读取文件: {file_path}",
            )

        # 只处理 classification == CONVERT 的方法
        convert_methods = [m for m in methods_to_convert if m.classification == StaticMethodClassification.CONVERT]
        if not convert_methods:
            return RefactoringResult(
                success=True,
                file_path=str(file_path),
                changes_made=["无需转换的静态方法，跳过"],
            )

        # 构建转换计划
        plan = self._build_conversion_plan(file_path, source, convert_methods)

        if plan.errors and not plan.methods:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                error_message="; ".join(plan.errors),
            )

        # 执行转换
        new_source = self._apply_conversion_plan(source, plan)

        # 语法验证
        try:
            ast.parse(new_source)
        except SyntaxError as exc:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                changes_made=plan.changes,
                error_message=f"转换后代码语法错误 (行 {exc.lineno}): {exc.msg}",
            )

        if not dry_run:
            file_path.write_text(new_source, encoding="utf-8")
            logger.info("已写入转换后的文件: %s", file_path)

        return RefactoringResult(
            success=True,
            file_path=str(file_path),
            changes_made=plan.changes,
        )

    def analyze_and_convert_file(
        self,
        file_path: Path,
        *,
        dry_run: bool = False,
    ) -> RefactoringResult:
        """
        分析并转换单个文件中的静态方法（一步到位）。

        先用 StaticMethodAnalyzer 分析，再对 "convert" 方法执行转换。

        Args:
            file_path: 目标文件路径
            dry_run: 为 True 时不写入文件

        Returns:
            RefactoringResult
        """
        file_path = Path(file_path)
        methods = self._analyzer.analyze_file(file_path)
        convert_methods = [m for m in methods if m.classification == StaticMethodClassification.CONVERT]
        if not convert_methods:
            return RefactoringResult(
                success=True,
                file_path=str(file_path),
                changes_made=["无需转换的静态方法"],
            )

        return self.convert_file(file_path, convert_methods, dry_run=dry_run)

    # ── 转换计划构建 ────────────────────────────────────────

    def _build_conversion_plan(
        self,
        file_path: Path,
        source: str,
        methods: list[StaticMethodInfo],
    ) -> FileConversionPlan:
        """
        构建文件的完整转换计划。

        解析 AST 确定每个方法的装饰器行号、是否已有 __init__，
        以及需要注入的依赖。

        Args:
            file_path: 文件路径
            source: 源代码
            methods: 需要转换的方法列表

        Returns:
            FileConversionPlan
        """
        plan = FileConversionPlan(file_path=file_path)
        tree = self._parse_ast(source, file_path)
        if tree is None:
            plan.errors.append(f"无法解析文件 AST: {file_path}")
            return plan

        # 构建 (class_name, method_name) -> StaticMethodInfo 映射
        method_map: dict[tuple[str, str], StaticMethodInfo] = {(m.class_name, m.method_name): m for m in methods}

        # 遍历 AST 收集信息
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            class_name = node.name
            has_init = False
            class_deps: list[DependencyInfo] = []

            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                # 检查是否有 __init__
                if item.name == "__init__":
                    has_init = True

                key = (class_name, item.name)
                if key not in method_map:
                    continue

                info = method_map[key]
                decorator_line = self._find_staticmethod_decorator_line(
                    item,
                    source,
                )
                if decorator_line == 0:
                    plan.errors.append(f"未找到 {class_name}.{item.name} 的 @staticmethod 装饰器")
                    continue

                # 识别依赖
                deps = self._identify_dependencies(item, info)
                class_deps.extend(deps)

                method_plan = MethodConversionPlan(
                    class_name=class_name,
                    method_name=item.name,
                    line_number=item.lineno,
                    decorator_line=decorator_line,
                    dependencies=deps,
                )
                plan.methods.append(method_plan)
                plan.changes.append(f"{class_name}.{item.name}: " f"移除 @staticmethod，添加 self 参数")
                if deps:
                    dep_names = ", ".join(d.name for d in deps)
                    plan.changes.append(f"  识别到依赖: {dep_names}")

            if has_init:
                plan.classes_with_init.add(class_name)

            # 去重依赖
            if class_deps:
                unique_deps = self._deduplicate_dependencies(class_deps)
                plan.classes_needing_init[class_name] = unique_deps

        return plan

    def _find_staticmethod_decorator_line(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: str,
    ) -> int:
        """
        查找方法的 @staticmethod 装饰器所在行号。

        Args:
            func_node: 方法 AST 节点
            source: 源代码

        Returns:
            装饰器行号 (1-based)，未找到返回 0
        """
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                return decorator.lineno
        return 0

    def _identify_dependencies(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        info: StaticMethodInfo,
    ) -> list[DependencyInfo]:
        """
        根据分析结果中的 reasons 识别需要注入的依赖。

        Args:
            func_node: 方法 AST 节点
            info: 静态方法分析信息

        Returns:
            依赖列表
        """
        deps: list[DependencyInfo] = []

        for reason in info.reasons:
            if reason.rule == "model_objects_access":
                # 从 detail 中提取 Model 名称
                model_name = self._extract_model_name_from_reason(reason.detail)
                if model_name:
                    dep_name = self._to_snake_case(model_name) + "_service"
                    deps.append(
                        DependencyInfo(
                            name=dep_name,
                            source=f"{model_name}.objects",
                            rule=reason.rule,
                        )
                    )
            elif reason.rule == "calls_external_service":
                service_name = self._extract_service_name_from_reason(
                    reason.detail,
                )
                if service_name:
                    dep_name = self._to_snake_case(service_name)
                    deps.append(
                        DependencyInfo(
                            name=dep_name,
                            source=service_name,
                            rule=reason.rule,
                        )
                    )
            elif reason.rule == "accesses_settings":
                deps.append(
                    DependencyInfo(
                        name="settings",
                        source="django.conf.settings",
                        rule=reason.rule,
                    )
                )

        return deps

    @staticmethod
    def _deduplicate_dependencies(
        deps: list[DependencyInfo],
    ) -> list[DependencyInfo]:
        """
        去重依赖列表（按 name 去重）。

        Args:
            deps: 原始依赖列表

        Returns:
            去重后的依赖列表
        """
        seen: set[str] = set()
        result: list[DependencyInfo] = []
        for dep in deps:
            if dep.name not in seen:
                seen.add(dep.name)
                result.append(dep)
        return result

    # ── 转换计划应用 ────────────────────────────────────────

    def _apply_conversion_plan(
        self,
        source: str,
        plan: FileConversionPlan,
    ) -> str:
        """
        将转换计划应用到源代码。

        执行顺序（从后往前处理，避免行号偏移）：
        1. 移除 @staticmethod 装饰器行
        2. 在方法签名中添加 self 参数
        3. 替换方法体中的 ClassName.method() → self.method()
        4. 生成或更新 __init__ 构造函数

        Args:
            source: 原始源代码
            plan: 转换计划

        Returns:
            修改后的源代码
        """
        lines = source.splitlines(keepends=True)

        # 按行号倒序处理方法（避免行号偏移）
        sorted_methods = sorted(
            plan.methods,
            key=lambda m: m.line_number,
            reverse=True,
        )

        for method_plan in sorted_methods:
            lines = self._convert_single_method(lines, method_plan)

        # 处理 __init__ 构造函数（也按倒序处理类）
        lines = self._handle_init_methods(lines, plan)

        return "".join(lines)

    def _convert_single_method(
        self,
        lines: list[str],
        method_plan: MethodConversionPlan,
    ) -> list[str]:
        """
        转换单个静态方法。

        1. 移除 @staticmethod 装饰器行
        2. 在 def 签名中添加 self
        3. 替换方法体中 ClassName.method() → self.method()

        Args:
            lines: 源代码行列表（带换行符）
            method_plan: 方法转换计划

        Returns:
            修改后的行列表
        """
        result = list(lines)
        class_name = method_plan.class_name

        # 步骤1: 移除 @staticmethod 装饰器行
        decorator_idx = method_plan.decorator_line - 1  # 转为 0-based
        if 0 <= decorator_idx < len(result):
            line = result[decorator_idx]
            if _STATICMETHOD_DECORATOR_RE.match(line.rstrip("\n\r")):
                result.pop(decorator_idx)
                # 行号偏移：后续行号需要 -1
                method_def_idx = method_plan.line_number - 1 - 1
            else:
                # 装饰器行不匹配，可能有注释等，尝试精确匹配
                logger.warning(
                    "第 %d 行不是纯 @staticmethod 装饰器: %s",
                    method_plan.decorator_line,
                    line.strip(),
                )
                method_def_idx = method_plan.line_number - 1
        else:
            method_def_idx = method_plan.line_number - 1

        # 步骤2: 在 def 签名中添加 self
        if 0 <= method_def_idx < len(result):
            result[method_def_idx] = self._add_self_parameter(
                result[method_def_idx],
            )

        # 步骤3: 替换方法体中 ClassName.method() → self.method()
        # 确定方法体范围
        body_start = method_def_idx + 1
        body_end = self._find_method_body_end(result, method_def_idx)

        class_call_pattern = re.compile(_CLASS_METHOD_CALL_RE_TEMPLATE.format(class_name=re.escape(class_name)))

        for i in range(body_start, min(body_end, len(result))):
            line = result[i]
            if class_call_pattern.search(line):
                result[i] = class_call_pattern.sub(r"self.\1(", line)

        return result

    @staticmethod
    def _add_self_parameter(def_line: str) -> str:
        """
        在方法签名中添加 self 作为第一个参数。

        处理以下情况：
        - ``def method():`` → ``def method(self):``
        - ``def method(a, b):`` → ``def method(self, a, b):``
        - ``async def method(a):`` → ``async def method(self, a):``
        - 多行签名的第一行

        Args:
            def_line: 包含 def 的行

        Returns:
            添加 self 后的行
        """
        match = _DEF_SIGNATURE_RE.match(def_line)
        if match is None:
            return def_line

        # 找到左括号位置
        paren_idx = def_line.index("(", match.start())
        after_paren = def_line[paren_idx + 1 :]

        # 检查括号后是否紧跟 )（无参数）
        stripped_after = after_paren.lstrip()
        if stripped_after.startswith(")"):
            # def method(): → def method(self):
            new_line = def_line[: paren_idx + 1] + "self" + after_paren
        else:
            # def method(a, b): → def method(self, a, b):
            new_line = def_line[: paren_idx + 1] + "self, " + after_paren

        return new_line

    def _find_method_body_end(
        self,
        lines: list[str],
        def_line_idx: int,
    ) -> int:
        """
        查找方法体的结束行索引。

        通过缩进级别判断：方法体内的行缩进应大于 def 行的缩进。
        遇到同级或更低缩进的非空行时，认为方法体结束。

        Args:
            lines: 源代码行列表
            def_line_idx: def 行的索引 (0-based)

        Returns:
            方法体结束行索引 (exclusive, 0-based)
        """
        if def_line_idx >= len(lines):
            return def_line_idx

        def_line = lines[def_line_idx]
        def_indent = len(def_line) - len(def_line.lstrip())

        # 处理多行签名：找到签名结束行
        body_start = def_line_idx + 1
        # 如果 def 行没有 :，说明是多行签名
        if ":" not in def_line.split("#")[0]:
            for i in range(def_line_idx + 1, len(lines)):
                if ":" in lines[i].split("#")[0]:
                    body_start = i + 1
                    break

        for i in range(body_start, len(lines)):
            line = lines[i]
            stripped = line.strip()

            # 跳过空行
            if not stripped:
                continue

            # 跳过注释行
            if stripped.startswith("#"):
                continue

            current_indent = len(line) - len(line.lstrip())
            if current_indent <= def_indent:
                return i

        return len(lines)

    def _handle_init_methods(
        self,
        lines: list[str],
        plan: FileConversionPlan,
    ) -> list[str]:
        """
        处理 __init__ 构造函数：生成新的或更新现有的。

        对于有依赖需要注入的类：
        - 如果类没有 __init__，在类体开头插入新的 __init__
        - 如果类已有 __init__，在其中追加依赖赋值

        Args:
            lines: 源代码行列表
            plan: 文件转换计划

        Returns:
            修改后的行列表
        """
        result = list(lines)

        if not plan.classes_needing_init:
            return result

        # 解析 AST 获取类的位置信息
        source = "".join(result)
        tree = self._parse_ast(source, plan.file_path)
        if tree is None:
            return result

        # 按类在文件中的位置倒序处理
        class_positions: list[tuple[str, int, ast.ClassDef]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in plan.classes_needing_init:
                class_positions.append((node.name, node.lineno, node))

        class_positions.sort(key=lambda x: x[1], reverse=True)

        for class_name, _, class_node in class_positions:
            deps = plan.classes_needing_init[class_name]
            if not deps:
                continue

            if class_name in plan.classes_with_init:
                result = self._update_existing_init(
                    result,
                    class_node,
                    deps,
                )
            else:
                result = self._insert_new_init(
                    result,
                    class_node,
                    deps,
                )

        return result

    def _insert_new_init(
        self,
        lines: list[str],
        class_node: ast.ClassDef,
        deps: list[DependencyInfo],
    ) -> list[str]:
        """
        在类体开头插入新的 __init__ 方法。

        Args:
            lines: 源代码行列表
            class_node: 类 AST 节点
            deps: 需要注入的依赖

        Returns:
            修改后的行列表
        """
        result = list(lines)

        # 确定类体的缩进级别
        class_line = lines[class_node.lineno - 1] if class_node.lineno <= len(lines) else ""
        class_indent = len(class_line) - len(class_line.lstrip())
        body_indent = " " * (class_indent + 4)
        inner_indent = " " * (class_indent + 8)

        # 找到类体的第一个语句位置（跳过文档字符串）
        insert_idx = class_node.lineno  # 0-based: class 行之后
        if class_node.body:
            first_stmt = class_node.body[0]
            # 如果第一个语句是文档字符串，在其后插入
            if (
                isinstance(first_stmt, ast.Expr)
                and isinstance(first_stmt.value, ast.Constant)
                and isinstance(first_stmt.value.value, str)
            ):
                # 文档字符串可能是多行的
                insert_idx = first_stmt.end_lineno or first_stmt.lineno
            else:
                insert_idx = first_stmt.lineno - 1

        # 生成 __init__ 代码
        init_lines: list[str] = []
        init_lines.append(f"{body_indent}def __init__(self) -> None:\n")
        for dep in deps:
            init_lines.append(f"{inner_indent}self.{dep.name} = None" f"  # TODO: 注入 {dep.source}\n")
        init_lines.append("\n")

        # 插入
        for i, init_line in enumerate(init_lines):
            result.insert(insert_idx + i, init_line)

        plan_changes_msg = f"为 {class_node.name} 生成 __init__ 构造函数，" f"包含 {len(deps)} 个依赖"
        logger.info(plan_changes_msg)

        return result

    def _update_existing_init(
        self,
        lines: list[str],
        class_node: ast.ClassDef,
        deps: list[DependencyInfo],
    ) -> list[str]:
        """
        在现有 __init__ 方法末尾追加依赖赋值。

        Args:
            lines: 源代码行列表
            class_node: 类 AST 节点
            deps: 需要注入的依赖

        Returns:
            修改后的行列表
        """
        result = list(lines)

        # 找到 __init__ 方法
        init_node: Optional[ast.FunctionDef] = None
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                init_node = item
                break

        if init_node is None:
            return result

        # 确定 __init__ 方法体的缩进
        init_body_indent = " " * (len(lines[init_node.lineno - 1]) - len(lines[init_node.lineno - 1].lstrip()) + 4)

        # 找到 __init__ 方法体的最后一行
        init_end = init_node.end_lineno or init_node.lineno

        # 检查现有代码中是否已有这些依赖赋值
        existing_source = "".join(result[init_node.lineno - 1 : init_end])

        insert_lines: list[str] = []
        for dep in deps:
            attr_pattern = f"self.{dep.name}"
            if attr_pattern in existing_source:
                continue
            insert_lines.append(f"{init_body_indent}self.{dep.name} = None" f"  # TODO: 注入 {dep.source}\n")

        if insert_lines:
            for i, line in enumerate(insert_lines):
                result.insert(init_end + i, line)
            logger.info(
                "更新 %s.__init__，追加 %d 个依赖",
                class_node.name,
                len(insert_lines),
            )

        return result

    # ── 辅助方法 ────────────────────────────────────────────

    @staticmethod
    def _extract_model_name_from_reason(detail: str) -> str:
        """
        从 reason detail 中提取 Model 名称。

        示例: "访问 Case.objects，需要服务注入" → "Case"

        Args:
            detail: reason 的 detail 字段

        Returns:
            Model 名称，提取失败返回空字符串
        """
        match = re.search(r"访问\s+(\w+)\.objects", detail)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _extract_service_name_from_reason(detail: str) -> str:
        """
        从 reason detail 中提取 Service 名称。

        示例: "调用外部服务: CaseService()" → "CaseService"

        Args:
            detail: reason 的 detail 字段

        Returns:
            Service 名称，提取失败返回空字符串
        """
        match = re.search(r"调用外部服务:\s*(\w+)\(\)", detail)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _to_snake_case(name: str) -> str:
        """
        将 CamelCase 转为 snake_case。

        Args:
            name: CamelCase 名称

        Returns:
            snake_case 名称
        """
        chars: list[str] = []
        for i, ch in enumerate(name):
            if ch.isupper() and i > 0:
                chars.append("_")
            chars.append(ch.lower())
        return "".join(chars)

    @staticmethod
    def _read_source(file_path: Path) -> Optional[str]:
        """
        读取源文件内容。

        Args:
            file_path: 文件路径

        Returns:
            源代码文本，读取失败时返回 None
        """
        try:
            return file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("无法读取文件 %s: %s", file_path, exc)
            return None

    @staticmethod
    def _parse_ast(source: str, file_path: Path) -> Optional[ast.Module]:
        """
        将源代码解析为 AST。

        Args:
            source: 源代码文本
            file_path: 文件路径

        Returns:
            AST 模块节点，解析失败时返回 None
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
