"""
跨模块依赖分析器

扫描 Service 层的跨模块 Model 导入，分析每个违规：
- 源模块 → 目标模块的依赖关系
- 导入的 Model 类名
- 对应的 ServiceLocator getter 方法
- 是否需要新增 Protocol / getter

输出 JSON 分析报告到 tools/architecture_compliance/output/cross_module_analysis.json
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .logging_config import get_logger, setup_logging

logger = get_logger("cross_module_deps")

# 匹配 from apps.<module>.models import ... 的正则
_CROSS_MODULE_RE: re.Pattern[str] = re.compile(
    r"^apps\.([a-zA-Z_][a-zA-Z0-9_]*)\.models"
)


# ── 数据模型 ────────────────────────────────────────────────

@dataclass
class CrossModuleViolation:
    """单条跨模块导入违规"""

    file_path: str
    line_number: int
    source_module: str
    target_module: str
    imported_models: list[str]
    import_statement: str
    existing_getter: Optional[str] = None
    needs_new_getter: bool = False
    needs_new_protocol: bool = False
    resolution_notes: str = ""


@dataclass
class ModuleDependency:
    """模块间依赖汇总"""

    source_module: str
    target_module: str
    violation_count: int = 0
    imported_models: list[str] = field(default_factory=list)
    getter_method: Optional[str] = None


@dataclass
class AnalysisReport:
    """完整分析报告"""

    total_violations: int = 0
    violations_with_existing_getter: int = 0
    violations_needing_new_getter: int = 0
    module_dependencies: list[ModuleDependency] = field(default_factory=list)
    violations: list[CrossModuleViolation] = field(default_factory=list)
    model_to_getter_mapping: dict[str, str] = field(default_factory=dict)
    summary: str = ""


# ── Model → ServiceLocator getter 映射 ─────────────────────

# 已有的 ServiceLocator getter 方法及其覆盖的 Model 类
_MODEL_GETTER_MAP: dict[str, str] = {
    # core.models
    "SystemConfig": "get_system_config_service",
    "CauseOfAction": "get_cause_court_query_service",
    # cases.models
    "Case": "get_case_service",
    "CaseLog": "get_case_service",
    "CaseNumber": "get_case_service",
    "CaseParty": "get_case_service",
    "CaseAssignment": "get_case_service",
    "SimpleCaseType": "get_case_service",
    # contracts.models
    "PartyRole": "get_contract_service",
    # client.models
    "Client": "get_client_service",
    # organization.models
    "Lawyer": "get_lawyer_service",
}


# ── 扫描逻辑 ───────────────────────────────────────────────

def _extract_module_name(file_path: Path) -> Optional[str]:
    """从文件路径提取所属 apps 子模块名"""
    parts = file_path.parts
    for i, part in enumerate(parts):
        if part == "apps" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _get_source_line(source: str, lineno: int) -> str:
    """获取源代码指定行"""
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def scan_file(file_path: Path) -> list[CrossModuleViolation]:
    """
    扫描单个文件的跨模块 Model 导入。

    Args:
        file_path: Python 文件路径

    Returns:
        该文件中的跨模块违规列表
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        logger.warning("无法解析文件 %s: %s", file_path, exc)
        return []

    current_module = _extract_module_name(file_path)
    violations: list[CrossModuleViolation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module is None:
            continue

        match = _CROSS_MODULE_RE.match(node.module)
        if match is None:
            continue

        target_module: str = match.group(1)

        # 同模块导入不算违规
        if current_module is not None and target_module == current_module:
            continue

        imported_names = [alias.name for alias in (node.names or [])]
        import_stmt = _get_source_line(source, node.lineno)

        # 查找每个导入 Model 对应的 getter
        existing_getter: Optional[str] = None
        needs_new = False
        for name in imported_names:
            getter = _MODEL_GETTER_MAP.get(name)
            if getter is not None:
                existing_getter = getter
            else:
                needs_new = True

        violation = CrossModuleViolation(
            file_path=str(file_path),
            line_number=node.lineno,
            source_module=current_module or "unknown",
            target_module=target_module,
            imported_models=imported_names,
            import_statement=import_stmt,
            existing_getter=existing_getter,
            needs_new_getter=needs_new,
            needs_new_protocol=needs_new,
            resolution_notes=_build_resolution_notes(
                imported_names, existing_getter, needs_new,
            ),
        )
        violations.append(violation)

    return violations


def _build_resolution_notes(
    imported_names: list[str],
    existing_getter: Optional[str],
    needs_new: bool,
) -> str:
    """生成修复建议说明"""
    parts: list[str] = []
    for name in imported_names:
        getter = _MODEL_GETTER_MAP.get(name)
        if getter is not None:
            parts.append(f"{name} → ServiceLocator.{getter}()")
        else:
            parts.append(f"{name} → 需要新增 ServiceLocator getter")
    return "; ".join(parts)


def scan_directory(root: Path) -> list[CrossModuleViolation]:
    """
    递归扫描目录下 services/ 中的跨模块 Model 导入。

    Args:
        root: 扫描根目录

    Returns:
        所有跨模块违规列表
    """
    violations: list[CrossModuleViolation] = []
    for py_file in sorted(root.rglob("*.py")):
        if "services" not in py_file.parts:
            continue
        file_violations = scan_file(py_file)
        violations.extend(file_violations)
    return violations


# ── 分析汇总 ───────────────────────────────────────────────

def build_report(violations: list[CrossModuleViolation]) -> AnalysisReport:
    """
    根据违规列表生成分析报告。

    Args:
        violations: 跨模块违规列表

    Returns:
        完整分析报告
    """
    report = AnalysisReport(
        total_violations=len(violations),
        violations=violations,
        model_to_getter_mapping=dict(_MODEL_GETTER_MAP),
    )

    # 统计
    with_getter = sum(1 for v in violations if not v.needs_new_getter)
    report.violations_with_existing_getter = with_getter
    report.violations_needing_new_getter = len(violations) - with_getter

    # 按 source→target 聚合模块依赖
    dep_map: dict[tuple[str, str], ModuleDependency] = {}
    for v in violations:
        key = (v.source_module, v.target_module)
        if key not in dep_map:
            dep_map[key] = ModuleDependency(
                source_module=v.source_module,
                target_module=v.target_module,
                getter_method=v.existing_getter,
            )
        dep = dep_map[key]
        dep.violation_count += 1
        for model in v.imported_models:
            if model not in dep.imported_models:
                dep.imported_models.append(model)

    report.module_dependencies = list(dep_map.values())

    report.summary = (
        f"共 {report.total_violations} 个跨模块导入违规, "
        f"{report.violations_with_existing_getter} 个可用现有 getter 解决, "
        f"{report.violations_needing_new_getter} 个需要新增 getter"
    )

    return report


def save_report(report: AnalysisReport, output_path: Path) -> None:
    """
    将分析报告保存为 JSON。

    Args:
        report: 分析报告
        output_path: 输出文件路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("分析报告已保存: %s", output_path)


# ── 入口 ───────────────────────────────────────────────────

def main() -> None:
    """主入口：扫描 backend/apps 并生成分析报告"""
    setup_logging()

    project_root = Path(__file__).resolve().parent.parent.parent
    backend_apps = project_root / "backend" / "apps"
    output_file = (
        Path(__file__).resolve().parent / "output" / "cross_module_analysis.json"
    )

    logger.info("开始扫描跨模块依赖: %s", backend_apps)
    violations = scan_directory(backend_apps)
    report = build_report(violations)

    logger.info(report.summary)
    for dep in report.module_dependencies:
        logger.info(
            "  %s → %s: %d 个违规, Models: %s, Getter: %s",
            dep.source_module,
            dep.target_module,
            dep.violation_count,
            ", ".join(dep.imported_models),
            dep.getter_method or "需要新增",
        )

    save_report(report, output_file)
    logger.info("分析完成")


if __name__ == "__main__":
    main()
