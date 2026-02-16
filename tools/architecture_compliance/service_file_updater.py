"""
Service 文件更新器

协调 ServiceRefactoringEngine，对 Service 文件执行完整的重构流程：
1. 移除跨模块 Model 导入行
2. 添加 ``from apps.core.interfaces import ServiceLocator`` 导入
3. 将 ``Model.objects.*`` 替换为 ``ServiceLocator.get_xxx_service().method(...)``
4. 对链式调用和复杂场景添加 ``# TODO: 需要人工审查`` 注释
5. 写回更新后的文件并返回 RefactoringResult
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import RefactoringResult
from .service_refactoring_engine import (
    _MODEL_GETTER_MAP,
    FileRefactoringPlan,
    ReplacementSpec,
    _build_service_method_name,
)

logger = get_logger("service_file_updater")

# ServiceLocator 导入语句
_SERVICE_LOCATOR_IMPORT = "from apps.core.interfaces import ServiceLocator"

# 匹配 from apps.<module>.models import ... 的正则
_MODEL_IMPORT_RE: re.Pattern[str] = re.compile(r"^(\s*)from\s+apps\.\w+\.models\s+import\s+(.+)$")

# 匹配 Model.objects.<method>(...) 的正则（含可选链式调用）
_ORM_CALL_RE: re.Pattern[str] = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\.objects\.(\w+)\(")

# 匹配独立的 Model.objects 访问（不跟方法调用）
_ORM_ACCESS_RE: re.Pattern[str] = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\.objects\b(?!\.\w+\()")


# ── 数据模型 ────────────────────────────────────────────────


@dataclass
class _ImportLineInfo:
    """导入行的解析信息"""

    line_number: int  # 1-based
    module_path: str  # e.g. "apps.cases.models"
    imported_names: list[str]  # e.g. ["Case", "CaseLog"]
    raw_line: str  # 原始行文本


@dataclass
class ServiceFileUpdatePlan:
    """Service 文件的完整更新计划"""

    file_path: Path
    original_source: str
    import_lines_to_remove: list[_ImportLineInfo] = field(default_factory=list)
    import_names_to_keep: dict[int, list[str]] = field(default_factory=dict)
    """line_number -> 该行需要保留的名称（部分移除场景）"""
    needs_service_locator_import: bool = False
    orm_replacements: list[_OrmReplacement] = field(default_factory=list)
    manual_review_lines: list[_ManualReviewLine] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class _OrmReplacement:
    """单个 ORM 调用的替换信息"""

    line_number: int
    model_name: str
    orm_method: str
    getter_method: str
    service_method: str
    original_pattern: str  # 正则匹配到的原始文本
    replacement_text: str  # 替换后的文本


@dataclass
class _ManualReviewLine:
    """需要人工审查的行"""

    line_number: int
    reason: str
    code_snippet: str


# ── ServiceFileUpdater ──────────────────────────────────────


class ServiceFileUpdater:
    """
    Service 文件更新器

    接收一个文件路径和 FileRefactoringPlan，实际修改源代码：

    - 移除跨模块 Model 导入行
    - 添加 ServiceLocator 导入（如果尚未存在）
    - 将 ``Model.objects.get(...)`` 替换为
      ``ServiceLocator.get_xxx_service().get_model_internal(...)``
    - 将 ``Model.objects.filter(...)`` 替换为
      ``ServiceLocator.get_xxx_service().query_models_internal(...)``
    - 对链式调用和复杂模式添加 ``# TODO: 需要人工审查`` 注释
    - 写回文件并返回 RefactoringResult
    """

    # ── public API ──────────────────────────────────────────

    def apply_replacements(
        self,
        file_path: Path,
        plan: FileRefactoringPlan,
        *,
        dry_run: bool = False,
    ) -> RefactoringResult:
        """
        根据 FileRefactoringPlan 对文件执行实际替换。

        Args:
            file_path: 目标文件路径
            plan: ServiceRefactoringEngine.analyze_file() 生成的重构计划
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

        source = file_path.read_text(encoding="utf-8")

        if not plan.cross_module_imports and not plan.replacements:
            return RefactoringResult(
                success=True,
                file_path=str(file_path),
                changes_made=["无需替换，跳过"],
            )

        # 收集需要替换的 Model 名称
        target_models: set[str] = set(plan.models_with_getter)

        update_plan = self._build_update_plan(file_path, source, plan, target_models)

        if update_plan.errors and not update_plan.changes:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                changes_made=update_plan.changes,
                error_message="; ".join(update_plan.errors),
            )

        # 执行替换
        final_source = self._apply_update_plan(source, update_plan)

        # 语法验证
        try:
            ast.parse(final_source)
        except SyntaxError as exc:
            return RefactoringResult(
                success=False,
                file_path=str(file_path),
                changes_made=update_plan.changes,
                error_message=f"重构后代码语法错误 (行 {exc.lineno}): {exc.msg}",
            )

        if not dry_run:
            file_path.write_text(final_source, encoding="utf-8")
            logger.info("已写入更新后的文件: %s", file_path)

        all_changes = update_plan.changes[:]
        if update_plan.manual_review_lines:
            all_changes.append(f"需要人工审查: {len(update_plan.manual_review_lines)} 处")
            for review in update_plan.manual_review_lines:
                all_changes.append(f"  - 第 {review.line_number} 行: {review.reason}")

        return RefactoringResult(
            success=True,
            file_path=str(file_path),
            changes_made=all_changes,
        )

    # ── 更新计划构建 ────────────────────────────────────────

    def _build_update_plan(
        self,
        file_path: Path,
        source: str,
        plan: FileRefactoringPlan,
        target_models: set[str],
    ) -> ServiceFileUpdatePlan:
        """
        构建完整的文件更新计划。

        分析源代码，确定：
        - 哪些导入行需要移除或修改
        - 哪些 ORM 调用需要替换
        - 哪些行需要人工审查

        Args:
            file_path: 文件路径
            source: 源代码
            plan: 重构计划
            target_models: 有 ServiceLocator getter 的 Model 名称集合

        Returns:
            ServiceFileUpdatePlan
        """
        update = ServiceFileUpdatePlan(
            file_path=file_path,
            original_source=source,
        )

        lines = source.splitlines()

        # 步骤1: 分析导入行
        self._analyze_import_lines(lines, plan, target_models, update)

        # 步骤2: 分析 ORM 调用替换
        self._analyze_orm_replacements(lines, plan, target_models, update)

        # 步骤3: 确定是否需要 ServiceLocator 导入
        update.needs_service_locator_import = (
            plan.needs_service_locator_import and _SERVICE_LOCATOR_IMPORT not in source
        )

        return update

    def _analyze_import_lines(
        self,
        lines: list[str],
        plan: FileRefactoringPlan,
        target_models: set[str],
        update: ServiceFileUpdatePlan,
    ) -> None:
        """
        分析跨模块导入行，确定移除或修改策略。

        对于 ``from apps.xxx.models import A, B, C``：
        - 如果 A, B, C 全部在 target_models 中，整行移除
        - 如果只有部分在 target_models 中，保留其余名称
        - 如果 Model 不在 target_models 中（无 getter），保留

        Args:
            lines: 源代码行列表
            plan: 重构计划
            target_models: 目标 Model 集合
            update: 更新计划（输出）
        """
        for cross_import in plan.cross_module_imports:
            names_to_remove: list[str] = []
            names_to_keep: list[str] = []

            for name in cross_import.imported_names:
                if name in target_models:
                    names_to_remove.append(name)
                else:
                    names_to_keep.append(name)

            if not names_to_remove:
                continue

            info = _ImportLineInfo(
                line_number=cross_import.line_number,
                module_path=cross_import.module_path,
                imported_names=names_to_remove,
                raw_line=(lines[cross_import.line_number - 1] if cross_import.line_number <= len(lines) else ""),
            )

            if names_to_keep:
                # 部分移除：保留其余名称
                update.import_names_to_keep[cross_import.line_number] = names_to_keep
                update.changes.append(
                    f"第 {cross_import.line_number} 行: "
                    f"从导入中移除 {', '.join(names_to_remove)}，"
                    f"保留 {', '.join(names_to_keep)}"
                )
            else:
                # 整行移除
                update.changes.append(
                    f"第 {cross_import.line_number} 行: " f"移除跨模块导入 {cross_import.import_statement}"
                )

            update.import_lines_to_remove.append(info)

    def _analyze_orm_replacements(
        self,
        lines: list[str],
        plan: FileRefactoringPlan,
        target_models: set[str],
        update: ServiceFileUpdatePlan,
    ) -> None:
        """
        分析 ORM 调用，生成替换信息或标记为人工审查。

        Args:
            lines: 源代码行列表
            plan: 重构计划
            target_models: 目标 Model 集合
            update: 更新计划（输出）
        """
        for repl_spec in plan.replacements:
            if repl_spec.model_name not in target_models:
                continue

            if repl_spec.needs_manual_review:
                update.manual_review_lines.append(
                    _ManualReviewLine(
                        line_number=repl_spec.line_number,
                        reason=repl_spec.review_reason,
                        code_snippet=repl_spec.original_code,
                    )
                )
                continue

            getter = _MODEL_GETTER_MAP.get(repl_spec.model_name)
            if getter is None:
                update.errors.append(
                    f"第 {repl_spec.line_number} 行: " f"{repl_spec.model_name} 无 ServiceLocator getter"
                )
                continue

            update.orm_replacements.append(
                _OrmReplacement(
                    line_number=repl_spec.line_number,
                    model_name=repl_spec.model_name,
                    orm_method=(
                        repl_spec.service_method.split(".")[-1]
                        if "." in repl_spec.service_method
                        else (repl_spec.service_method or "")
                    ),
                    getter_method=getter,
                    service_method=repl_spec.service_method,
                    original_pattern=f"{repl_spec.model_name}.objects.",
                    replacement_text=f"ServiceLocator.{getter}().{repl_spec.service_method}",
                )
            )

            update.changes.append(
                f"第 {repl_spec.line_number} 行: " f"{repl_spec.original_code} → {repl_spec.replacement_code}"
            )

    # ── 更新计划应用 ────────────────────────────────────────

    def _apply_update_plan(
        self,
        source: str,
        update: ServiceFileUpdatePlan,
    ) -> str:
        """
        将更新计划应用到源代码。

        执行顺序：
        1. 替换 ORM 调用（逐行正则替换）
        2. 为需要人工审查的行添加 TODO 注释
        3. 处理导入行（移除或修改）
        4. 添加 ServiceLocator 导入

        Args:
            source: 原始源代码
            update: 更新计划

        Returns:
            修改后的源代码
        """
        lines = source.splitlines(keepends=True)

        # 步骤1: 替换 ORM 调用
        lines = self._replace_orm_calls(lines, update.orm_replacements)

        # 步骤2: 为需要人工审查的行添加 TODO 注释
        lines = self._add_manual_review_comments(lines, update.manual_review_lines)

        # 步骤3: 处理导入行
        lines = self._update_import_lines(lines, update)

        # 步骤4: 添加 ServiceLocator 导入
        if update.needs_service_locator_import:
            lines = self._add_service_locator_import(lines)

        return "".join(lines)

    def _replace_orm_calls(
        self,
        lines: list[str],
        replacements: list[_OrmReplacement],
    ) -> list[str]:
        """
        逐行替换 ORM 调用。

        对于每个替换，在对应行中使用正则替换
        ``Model.objects.method(`` → ``ServiceLocator.getter().service_method(``

        Args:
            lines: 源代码行列表（带换行符）
            replacements: ORM 替换列表

        Returns:
            替换后的行列表
        """
        # 按行号分组替换
        replacements_by_line: dict[int, list[_OrmReplacement]] = {}
        for repl in replacements:
            replacements_by_line.setdefault(repl.line_number, []).append(repl)

        result = list(lines)
        for line_no, repls in replacements_by_line.items():
            idx = line_no - 1  # 转为 0-based
            if idx < 0 or idx >= len(result):
                continue

            line = result[idx]
            for repl in repls:
                # 构建精确的正则模式
                pattern = re.compile(re.escape(repl.model_name) + r"\.objects\.(\w+)\(")
                match = pattern.search(line)
                if match:
                    orm_method = match.group(1)
                    service_method = _build_service_method_name(
                        repl.model_name,
                        orm_method,
                    )
                    replacement = f"ServiceLocator.{repl.getter_method}()" f".{service_method}("
                    line = line[: match.start()] + replacement + line[match.end() :]

            result[idx] = line

        return result

    def _add_manual_review_comments(
        self,
        lines: list[str],
        review_lines: list[_ManualReviewLine],
    ) -> list[str]:
        """
        为需要人工审查的行添加 TODO 注释。

        在行末添加 ``  # TODO: 需要人工审查 - <reason>``

        Args:
            lines: 源代码行列表
            review_lines: 需要审查的行列表

        Returns:
            修改后的行列表
        """
        result = list(lines)
        review_by_line: dict[int, _ManualReviewLine] = {r.line_number: r for r in review_lines}

        for line_no, review in review_by_line.items():
            idx = line_no - 1
            if idx < 0 or idx >= len(result):
                continue

            line = result[idx]
            # 避免重复添加
            if "# TODO: 需要人工审查" in line:
                continue

            stripped = line.rstrip("\n\r")
            comment = f"  # TODO: 需要人工审查 - {review.reason}"
            result[idx] = stripped + comment + "\n"

        return result

    def _update_import_lines(
        self,
        lines: list[str],
        update: ServiceFileUpdatePlan,
    ) -> list[str]:
        """
        处理导入行：整行移除或部分修改。

        Args:
            lines: 源代码行列表
            update: 更新计划

        Returns:
            修改后的行列表
        """
        result = list(lines)

        # 收集需要处理的行号（按倒序处理，避免索引偏移）
        import_actions: list[tuple[int, str]] = []
        # (line_number, action): action = "remove" | "modify"

        for info in update.import_lines_to_remove:
            line_no = info.line_number
            if line_no in update.import_names_to_keep:
                import_actions.append((line_no, "modify"))
            else:
                import_actions.append((line_no, "remove"))

        # 按行号倒序处理
        import_actions.sort(key=lambda x: x[0], reverse=True)

        for line_no, action in import_actions:
            idx = line_no - 1
            if idx < 0 or idx >= len(result):
                continue

            if action == "remove":
                # 处理多行导入的情况
                end_idx = self._find_import_end_line(result, idx)
                for i in range(end_idx, idx - 1, -1):
                    result.pop(i)
            elif action == "modify":
                keep_names = update.import_names_to_keep[line_no]
                # 从原始行中提取 module_path
                info = next(
                    (i for i in update.import_lines_to_remove if i.line_number == line_no),
                    None,
                )
                if info is not None:
                    new_import = f"from {info.module_path} import " f"{', '.join(keep_names)}\n"
                    # 处理多行导入
                    end_idx = self._find_import_end_line(result, idx)
                    for i in range(end_idx, idx, -1):
                        result.pop(i)
                    result[idx] = new_import

        return result

    def _find_import_end_line(
        self,
        lines: list[str],
        start_idx: int,
    ) -> int:
        """
        查找导入语句的结束行索引（处理多行导入）。

        支持括号形式的多行导入::

            from apps.xxx.models import (
                ModelA,
                ModelB,
            )

        以及反斜杠续行::

            from apps.xxx.models import ModelA, \\
                ModelB

        Args:
            lines: 源代码行列表
            start_idx: 导入语句起始行索引（0-based）

        Returns:
            结束行索引（0-based）
        """
        line = lines[start_idx]

        # 检查是否有未闭合的括号
        open_parens = line.count("(") - line.count(")")
        if open_parens > 0:
            idx = start_idx + 1
            while idx < len(lines) and open_parens > 0:
                open_parens += lines[idx].count("(") - lines[idx].count(")")
                idx += 1
            return idx - 1

        # 检查反斜杠续行
        idx = start_idx
        while idx < len(lines) - 1 and lines[idx].rstrip("\n\r").endswith("\\"):
            idx += 1

        return idx

    def _add_service_locator_import(
        self,
        lines: list[str],
    ) -> list[str]:
        """
        在导入区域末尾添加 ServiceLocator 导入。

        查找最后一个 ``from`` 或 ``import`` 语句的位置，
        在其后插入 ServiceLocator 导入行。

        Args:
            lines: 源代码行列表

        Returns:
            修改后的行列表
        """
        result = list(lines)

        # 检查是否已存在
        for line in result:
            if _SERVICE_LOCATOR_IMPORT in line:
                return result

        # 查找最后一个导入语句的位置
        last_import_idx = -1
        for i, line in enumerate(result):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                last_import_idx = i
                # 处理多行导入
                if "(" in stripped and ")" not in stripped:
                    j = i + 1
                    while j < len(result) and ")" not in result[j]:
                        j += 1
                    last_import_idx = j

        insert_idx = last_import_idx + 1 if last_import_idx >= 0 else 0
        result.insert(insert_idx, f"{_SERVICE_LOCATOR_IMPORT}\n")

        return result
