"""
Service层静态方法分析器

使用Python AST分析Service类中的@staticmethod装饰方法，
通过启发式规则判断每个静态方法是否应该转换为实例方法。

分类规则：
- **convert**: 方法体包含import语句、调用类自身其他方法、访问Model.objects、
  实例化自身类等 → 需要依赖注入 → 应转换为实例方法
- **keep**: 纯工具函数（字符串处理、数学运算、返回常量等）→ 保留为静态方法
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .scanner import ViolationScanner

logger = get_logger("static_method_analyzer")


class StaticMethodClassification(Enum):
    """静态方法分类"""

    CONVERT = "convert"  # 应转换为实例方法
    KEEP = "keep"  # 保留为静态方法


@dataclass
class ConversionReason:
    """转换/保留的原因"""

    rule: str  # 规则名称
    detail: str  # 详细说明


@dataclass
class StaticMethodInfo:
    """单个静态方法的分析结果"""

    class_name: str
    method_name: str
    file_path: str
    line_number: int
    classification: StaticMethodClassification
    reasons: list[ConversionReason] = field(default_factory=list)
    code_snippet: str = ""

    @property
    def should_convert(self) -> bool:
        """是否应该转换为实例方法"""
        return self.classification == StaticMethodClassification.CONVERT


@dataclass
class StaticMethodAnalysisReport:
    """静态方法分析报告"""

    total: int = 0
    convert_count: int = 0
    keep_count: int = 0
    methods: list[StaticMethodInfo] = field(default_factory=list)

    @property
    def convert_methods(self) -> list[StaticMethodInfo]:
        """需要转换的方法列表"""
        return [m for m in self.methods if m.should_convert]

    @property
    def keep_methods(self) -> list[StaticMethodInfo]:
        """保留为静态方法的列表"""
        return [m for m in self.methods if not m.should_convert]


# ── 启发式规则名称常量 ──────────────────────────────────────

_RULE_IMPORT_IN_BODY = "import_in_body"
_RULE_CALLS_CLASS_METHOD = "calls_class_method"
_RULE_MODEL_OBJECTS_ACCESS = "model_objects_access"
_RULE_INSTANTIATES_SELF = "instantiates_self_class"
_RULE_PURE_STRING_MATH = "pure_string_math"
_RULE_RETURNS_CONSTANT = "returns_constant"
_RULE_ACCESSES_SETTINGS = "accesses_settings"
_RULE_CALLS_EXTERNAL_SERVICE = "calls_external_service"

# 工具类后缀 — 这些类中的静态方法不参与分析
_UTILITY_CLASS_SUFFIXES: tuple[str, ...] = (
    "Utils",
    "Util",
    "Helper",
    "Helpers",
    "Tool",
    "Tools",
    "Mixin",
    "Detection",
)


class StaticMethodAnalyzer:
    """
    Service层静态方法分析器

    扫描Service类中的@staticmethod装饰方法，使用启发式规则判断
    每个方法是否应该转换为实例方法。

    启发式规则（convert）：
    - 方法体包含 import 语句 → 需要依赖
    - 方法体调用同类其他方法（ClassName.xxx） → 可用 self
    - 方法体访问 Model.objects → 需要服务注入
    - 方法体实例化自身类 → 应该用 self
    - 方法体访问 django settings → 可通过构造函数注入
    - 方法体调用外部服务类 → 需要依赖注入

    启发式规则（keep）：
    - 仅做字符串/数学运算 → 纯工具函数
    - 仅返回常量 → 纯工具函数
    """

    def __init__(self) -> None:
        self._scanner = ViolationScanner.__subclasses__()  # 不直接使用

    # ── 公开 API ────────────────────────────────────────────

    def analyze_directory(self, root: Path) -> StaticMethodAnalysisReport:
        """
        扫描目录下所有Service文件中的静态方法并分析。

        Args:
            root: 要扫描的根目录（通常是 backend/apps）

        Returns:
            静态方法分析报告
        """
        root = Path(root)
        if not root.is_dir():
            logger.warning("路径不是目录，跳过: %s", root)
            return StaticMethodAnalysisReport()

        report = StaticMethodAnalysisReport()
        py_files = self._collect_service_files(root)
        logger.info("找到 %d 个Service层Python文件: %s", len(py_files), root)

        for py_file in py_files:
            methods = self.analyze_file(py_file)
            report.methods.extend(methods)

        report.total = len(report.methods)
        report.convert_count = len(report.convert_methods)
        report.keep_count = len(report.keep_methods)

        logger.info(
            "静态方法分析完成: 共 %d 个, 建议转换 %d 个, 建议保留 %d 个",
            report.total,
            report.convert_count,
            report.keep_count,
        )
        return report

    def analyze_file(self, file_path: Path) -> list[StaticMethodInfo]:
        """
        分析单个文件中的所有静态方法。

        Args:
            file_path: Python源文件路径

        Returns:
            该文件中所有静态方法的分析结果
        """
        file_path = Path(file_path)
        source = self._read_source(file_path)
        if source is None:
            return []

        tree = self._parse_ast(source, file_path)
        if tree is None:
            return []

        results: list[StaticMethodInfo] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # 跳过工具类
            if node.name.endswith(_UTILITY_CLASS_SUFFIXES):
                logger.info("跳过工具类: %s", node.name)
                continue

            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not self._has_staticmethod_decorator(item):
                    continue

                info = self._analyze_single_method(
                    class_node=node,
                    method_node=item,
                    source=source,
                    file_path=file_path,
                )
                results.append(info)

        if results:
            logger.info(
                "文件 %s 中发现 %d 个静态方法",
                file_path,
                len(results),
            )
        return results

    # ── 核心分析逻辑 ────────────────────────────────────────

    def _analyze_single_method(
        self,
        class_node: ast.ClassDef,
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: str,
        file_path: Path,
    ) -> StaticMethodInfo:
        """
        分析单个静态方法，判断是否应该转换。

        依次应用所有启发式规则，收集 convert/keep 原因，
        最终根据是否存在 convert 原因来决定分类。

        Args:
            class_node: 所属类的AST节点
            method_node: 方法的AST节点
            source: 源代码文本
            file_path: 文件路径

        Returns:
            StaticMethodInfo 分析结果
        """
        class_name = class_node.name
        method_name = method_node.name
        line_number = method_node.lineno
        code_snippet = self._get_source_line(source, line_number)

        convert_reasons: list[ConversionReason] = []
        keep_reasons: list[ConversionReason] = []

        # ── 应用 convert 规则 ──

        # 规则1: 方法体包含 import 语句
        import_reason = self._check_import_in_body(method_node)
        if import_reason is not None:
            convert_reasons.append(import_reason)

        # 规则2: 调用同类其他方法
        class_call_reason = self._check_calls_class_method(
            method_node,
            class_name,
        )
        if class_call_reason is not None:
            convert_reasons.append(class_call_reason)

        # 规则3: 访问 Model.objects
        model_reason = self._check_model_objects_access(method_node)
        if model_reason is not None:
            convert_reasons.append(model_reason)

        # 规则4: 实例化自身类
        self_inst_reason = self._check_instantiates_self_class(
            method_node,
            class_name,
        )
        if self_inst_reason is not None:
            convert_reasons.append(self_inst_reason)

        # 规则5: 访问 django settings
        settings_reason = self._check_accesses_settings(method_node)
        if settings_reason is not None:
            convert_reasons.append(settings_reason)

        # 规则6: 调用外部服务类
        ext_service_reason = self._check_calls_external_service(method_node)
        if ext_service_reason is not None:
            convert_reasons.append(ext_service_reason)

        # ── 应用 keep 规则 ──

        # 规则7: 纯字符串/数学运算
        pure_reason = self._check_pure_string_math(method_node)
        if pure_reason is not None:
            keep_reasons.append(pure_reason)

        # 规则8: 仅返回常量
        const_reason = self._check_returns_constant(method_node)
        if const_reason is not None:
            keep_reasons.append(const_reason)

        # ── 决定分类 ──
        # 只要有任何一个 convert 原因，就建议转换
        if convert_reasons:
            classification = StaticMethodClassification.CONVERT
            reasons = convert_reasons
        elif keep_reasons:
            classification = StaticMethodClassification.KEEP
            reasons = keep_reasons
        else:
            # 没有明确信号时，默认保留
            classification = StaticMethodClassification.KEEP
            reasons = [
                ConversionReason(
                    rule="no_signal",
                    detail="未检测到需要依赖的模式，默认保留为静态方法",
                ),
            ]

        info = StaticMethodInfo(
            class_name=class_name,
            method_name=method_name,
            file_path=str(file_path),
            line_number=line_number,
            classification=classification,
            reasons=reasons,
            code_snippet=code_snippet,
        )

        logger.info(
            "%s.%s → %s (%s)",
            class_name,
            method_name,
            classification.value,
            ", ".join(r.rule for r in reasons),
        )
        return info

    # ── Convert 规则实现 ─────────────────────────────────────

    @staticmethod
    def _check_import_in_body(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法体包含 import 语句。

        如果方法内部有 ``import xxx`` 或 ``from xxx import yyy``，
        说明该方法依赖外部模块，适合通过构造函数注入。

        Args:
            method_node: 方法AST节点

        Returns:
            ConversionReason 或 None
        """
        for node in ast.walk(method_node):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name = ""
                if isinstance(node, ast.ImportFrom) and node.module:
                    module_name = node.module
                elif isinstance(node, ast.Import) and node.names:
                    module_name = node.names[0].name
                return ConversionReason(
                    rule=_RULE_IMPORT_IN_BODY,
                    detail=f"方法体包含import语句: {module_name}",
                )
        return None

    @staticmethod
    def _check_calls_class_method(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法体调用同类其他方法（ClassName.xxx()）。

        如果方法通过 ``ClassName.method()`` 调用同类方法，
        说明可以改用 ``self.method()``，应转换为实例方法。

        Args:
            method_node: 方法AST节点
            class_name: 所属类名

        Returns:
            ConversionReason 或 None
        """
        for node in ast.walk(method_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # 匹配 ClassName.method_name(...)
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == class_name:
                return ConversionReason(
                    rule=_RULE_CALLS_CLASS_METHOD,
                    detail=f"调用同类方法: {class_name}.{func.attr}()",
                )
        return None

    @staticmethod
    def _check_model_objects_access(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法体访问 Model.objects。

        如果方法中出现 ``SomeModel.objects`` 模式，
        说明需要数据库访问，应通过服务注入。

        Args:
            method_node: 方法AST节点

        Returns:
            ConversionReason 或 None
        """
        for node in ast.walk(method_node):
            if not isinstance(node, ast.Attribute):
                continue
            # 匹配 XXX.objects
            if node.attr == "objects" and isinstance(node.value, ast.Name):
                model_name = node.value.id
                return ConversionReason(
                    rule=_RULE_MODEL_OBJECTS_ACCESS,
                    detail=f"访问 {model_name}.objects，需要服务注入",
                )
        return None

    @staticmethod
    def _check_instantiates_self_class(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法体实例化自身类。

        如果方法中出现 ``ClassName()``，说明方法依赖自身类实例，
        应该直接使用 self。

        Args:
            method_node: 方法AST节点
            class_name: 所属类名

        Returns:
            ConversionReason 或 None
        """
        for node in ast.walk(method_node):
            if not isinstance(node, ast.Call):
                continue
            # 匹配 ClassName()
            if isinstance(node.func, ast.Name) and node.func.id == class_name:
                return ConversionReason(
                    rule=_RULE_INSTANTIATES_SELF,
                    detail=f"方法体实例化自身类: {class_name}()",
                )
        return None

    @staticmethod
    def _check_accesses_settings(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法体访问 django settings。

        如果方法中出现 ``settings.XXX``，说明依赖配置，
        可通过构造函数注入配置值。

        Args:
            method_node: 方法AST节点

        Returns:
            ConversionReason 或 None
        """
        for node in ast.walk(method_node):
            if not isinstance(node, ast.Attribute):
                continue
            if isinstance(node.value, ast.Name) and node.value.id == "settings":
                return ConversionReason(
                    rule=_RULE_ACCESSES_SETTINGS,
                    detail=f"访问 settings.{node.attr}，可通过构造函数注入",
                )
        return None

    @staticmethod
    def _check_calls_external_service(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法体调用外部服务类。

        如果方法中实例化了以 ``Service`` 结尾的类（排除自身类），
        说明依赖外部服务，应通过依赖注入。

        Args:
            method_node: 方法AST节点

        Returns:
            ConversionReason 或 None
        """
        for node in ast.walk(method_node):
            if not isinstance(node, ast.Call):
                continue
            # 匹配 XxxService() 调用
            if isinstance(node.func, ast.Name) and node.func.id.endswith("Service"):
                return ConversionReason(
                    rule=_RULE_CALLS_EXTERNAL_SERVICE,
                    detail=f"调用外部服务: {node.func.id}()",
                )
        return None

    # ── Keep 规则实现 ────────────────────────────────────────

    @staticmethod
    def _check_pure_string_math(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法仅做字符串/数学运算。

        检查方法体是否只包含简单操作：赋值、return、字符串方法调用、
        数学运算等，不包含任何外部依赖调用。

        判断标准：方法体中没有 import、没有 Call 到非内置函数、
        没有属性访问到 .objects 等。

        Args:
            method_node: 方法AST节点

        Returns:
            ConversionReason 或 None
        """
        has_complex_call = False

        for node in ast.walk(method_node):
            # 有 import → 不是纯工具函数
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return None

            if isinstance(node, ast.Call):
                func = node.func
                # 允许: str方法调用 (xxx.replace, xxx.lower 等)
                if isinstance(func, ast.Attribute):
                    # 不允许: ClassName.method() 或 xxx.objects
                    if isinstance(func.value, ast.Name):
                        name = func.value.id
                        # 如果是大写开头的名称调用属性方法，可能是类方法调用
                        if name[0:1].isupper() and func.attr != "join":
                            has_complex_call = True
                            break
                # 允许: 内置函数 (len, str, int, tuple, list, dict, set, bool, isinstance)
                elif isinstance(func, ast.Name):
                    _BUILTIN_NAMES = frozenset(
                        {
                            "len",
                            "str",
                            "int",
                            "float",
                            "bool",
                            "tuple",
                            "list",
                            "dict",
                            "set",
                            "isinstance",
                            "type",
                            "range",
                            "enumerate",
                            "zip",
                            "map",
                            "filter",
                            "sorted",
                            "reversed",
                            "min",
                            "max",
                            "sum",
                            "abs",
                            "round",
                            "repr",
                            "hash",
                            "id",
                            "ord",
                            "chr",
                        }
                    )
                    if func.id not in _BUILTIN_NAMES:
                        has_complex_call = True
                        break

        if not has_complex_call:
            return ConversionReason(
                rule=_RULE_PURE_STRING_MATH,
                detail="方法仅包含字符串/数学运算，是纯工具函数",
            )
        return None

    @staticmethod
    def _check_returns_constant(
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Optional[ConversionReason]:
        """
        规则: 方法仅返回常量值。

        如果方法体只有一条 return 语句，且返回值是常量
        （字符串、数字、元组、空字符串等），则视为常量返回。

        Args:
            method_node: 方法AST节点

        Returns:
            ConversionReason 或 None
        """
        # 过滤掉文档字符串，只看实际语句
        body = [
            stmt
            for stmt in method_node.body
            if not (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            )
        ]

        if len(body) != 1:
            return None

        stmt = body[0]
        if not isinstance(stmt, ast.Return):
            return None

        if stmt.value is None:
            return ConversionReason(
                rule=_RULE_RETURNS_CONSTANT,
                detail="方法仅返回 None",
            )

        # 检查返回值是否为常量
        if isinstance(stmt.value, ast.Constant):
            return ConversionReason(
                rule=_RULE_RETURNS_CONSTANT,
                detail=f"方法仅返回常量: {stmt.value.value!r}",
            )

        # 检查返回值是否为 tuple(...常量...)
        if isinstance(stmt.value, ast.Tuple):
            all_const = all(isinstance(elt, ast.Constant) for elt in stmt.value.elts)
            if all_const:
                return ConversionReason(
                    rule=_RULE_RETURNS_CONSTANT,
                    detail="方法仅返回常量元组",
                )

        return None

    # ── 辅助方法 ────────────────────────────────────────────

    @staticmethod
    def _has_staticmethod_decorator(
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> bool:
        """
        判断函数是否有 @staticmethod 装饰器。

        Args:
            func_node: 函数定义节点

        Returns:
            True 表示有 @staticmethod 装饰器
        """
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "staticmethod":
                return True
        return False

    @staticmethod
    def _collect_service_files(root: Path) -> list[Path]:
        """
        收集 services/ 目录下的Python文件。

        排除 __pycache__、migrations、venv 等目录。

        Args:
            root: 根目录

        Returns:
            排序后的文件路径列表
        """
        _EXCLUDE_DIRS: frozenset[str] = frozenset(
            {
                "__pycache__",
                ".git",
                ".tox",
                ".mypy_cache",
                ".pytest_cache",
                "node_modules",
                "migrations",
                "venv",
                ".venv",
                "venv312",
            }
        )

        py_files: list[Path] = []
        for path in sorted(root.rglob("*.py")):
            if any(part in _EXCLUDE_DIRS for part in path.parts):
                continue
            if "services" not in path.parts:
                continue
            py_files.append(path)
        return py_files

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
        将源代码解析为AST。

        Args:
            source: 源代码文本
            file_path: 文件路径（用于错误消息）

        Returns:
            AST模块节点，解析失败时返回 None
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

    @staticmethod
    def _get_source_line(source: str, line_number: int) -> str:
        """
        从源代码中提取指定行。

        Args:
            source: 完整源代码
            line_number: 行号（1-based）

        Returns:
            该行文本（去除首尾空白），行号无效时返回空字符串
        """
        lines = source.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""
