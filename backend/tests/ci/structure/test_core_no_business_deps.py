"""Structure guard: apps/core must not gain NEW dependencies on business apps.

背景：core 已膨胀为基础设施超级包（约 334 py），且历史上已存在大量对业务 app
的反向依赖（dependencies/、dto/、service_locator_mixins/、services/search_service 等）。

本测试采用「冻结基线」模式：
- FROZEN_VIOLATIONS 记录存量违规（文件级），这些是历史遗留，将在后续批次 DI 化清理；
- **任何新增的 core → 业务 app import 都会失败**（不在基线内的文件/目标）；
- cloud_storage 的两处懒导入桥接点属于本次拆分评审过的合法边界，单独白名单。

清理一个文件后，请同步从 FROZEN_VIOLATIONS 中删除对应条目，让基线只减不增。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
CORE_DIR = BACKEND_DIR / "apps" / "core"

# ---------------------------------------------------------------------------
# 冻结基线：core 现存的对业务 app 的依赖（file 相对 backend/ → 允许的 app 集合）。
# 只减不增：修掉一处就删一行；新增依赖不允许进入本基线。
# ---------------------------------------------------------------------------
FROZEN_VIOLATIONS: dict[str, set[str]] = {
    "apps/core/api/dashboard_api.py": {"workbench"},
    "apps/core/dependencies/automation_adapters.py": {"automation", "document_recognition"},
    "apps/core/dependencies/automation_browser.py": {"automation"},
    "apps/core/dependencies/automation_sms_wiring.py": {"automation"},
    "apps/core/dependencies/automation_token.py": {"automation"},
    "apps/core/dependencies/business_case.py": {"cases"},
    "apps/core/dependencies/business_client.py": {"client"},
    "apps/core/dependencies/business_contract.py": {"contracts"},
    "apps/core/dependencies/business_import.py": {"cases", "client", "contracts", "organization"},
    "apps/core/dependencies/business_organization.py": {"organization", "reminders"},
    "apps/core/dependencies/documents_generation.py": {"documents"},
    "apps/core/dependencies/documents_query.py": {"documents", "evidence"},
    "apps/core/dependencies/oa_filing.py": {"oa_filing"},
    "apps/core/dto/cases.py": {"cases"},
    "apps/core/dto/client.py": {"client"},
    "apps/core/dto/contracts.py": {"contracts"},
    "apps/core/dto/organization.py": {"organization"},
    "apps/core/management/commands/export_seed_data.py": {"finance"},
    "apps/core/management/commands/load_seed_data.py": {"finance"},
    "apps/core/protocols/token_protocols.py": {"automation"},
    "apps/core/service_locator_mixins/automation_mixin.py": {"automation"},
    "apps/core/service_locator_mixins/contract_review_mixin.py": {"contract_review"},
    "apps/core/service_locator_mixins/documents_mixin.py": {"evidence", "documents"},
    "apps/core/service_locator_mixins/workbench_mixin.py": {"workbench"},
    "apps/core/services/bound_folder_scan_service.py": {"document_recognition"},
    "apps/core/services/court_tokens/baoquan_token_service.py": {"automation"},
    "apps/core/services/material_classification_service.py": {"contracts"},
    "apps/core/services/search_service.py": {"client", "cases", "contracts", "message_hub", "automation", "contacts"},
}

# 本次拆分评审过的懒导入桥接点（第二批 DI 化候选）
LAZY_BRIDGES: dict[str, set[str]] = {
    "apps/core/filesystem/folder_binding_base.py": {"cloud_storage"},
    "apps/core/services/bound_folder_scan_service.py": {"cloud_storage"},
}


def _iter_core_py_files() -> list[Path]:
    return sorted(CORE_DIR.rglob("*.py"))


def _rel_to_backend(path: Path) -> str:
    return path.relative_to(BACKEND_DIR).as_posix()


def _collect_imports(py_file: Path) -> list[tuple[int, str]]:
    """返回 (level, module) 列表；level=0 表示绝对导入。"""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((0, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.level, node.module))
    return out


def _app_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "apps":
        return parts[1]
    return None


def test_core_no_new_business_dependencies() -> None:
    """core 禁止新增对业务 app 的 import（基线内文件/白名单桥接除外）。"""
    offenders: list[str] = []
    for py_file in _iter_core_py_files():
        rel = _rel_to_backend(py_file)
        for level, module in _collect_imports(py_file):
            if level > 0:
                # 相对导入：apps/core/x/y.py 中 level=2 回到 apps/ 层
                if level >= 2 and module:
                    app = module.split(".")[0]
                    if app != "core" and app != "__future__":
                        offenders.append(f"{rel}: 相对导入逃逸 -> {module}")
                continue
            app = _app_of(module)
            if app is None or app == "core" or app == "cloud_storage":
                # cloud_storage 为拆分出的独立 app：仅允许已登记桥接文件引用
                if app == "cloud_storage" and rel not in LAZY_BRIDGES:
                    offenders.append(f"{rel}: 引用 apps.cloud_storage 未登记桥接点")
                continue
            allowed = FROZEN_VIOLATIONS.get(rel, set())
            if app not in allowed:
                offenders.append(f"{rel}: 新增依赖业务 app '{app}'（{module}）——请迁移出 core 或登记冻结基线并说明理由")

    assert not offenders, "core 出现新的业务依赖（禁止新增）:\n" + "\n".join(offenders)


def test_frozen_baseline_files_exist() -> None:
    """基线条目指向的文件必须真实存在，防止基线腐化。"""
    missing = [rel for rel in FROZEN_VIOLATIONS if not (BACKEND_DIR / rel).exists()]
    assert not missing, f"冻结基线中的文件已不存在（请清理基线）: {missing}"


def test_cloud_storage_app_does_not_import_business_apps() -> None:
    """新拆出的 cloud_storage app 必须保持纯净（只依赖 core 基础设施）。"""
    cs_dir = BACKEND_DIR / "apps" / "cloud_storage"
    allowed_targets = {"core", "cloud_storage"}
    offenders: list[str] = []
    for py_file in cs_dir.rglob("*.py"):
        rel = _rel_to_backend(py_file)
        for level, module in _collect_imports(py_file):
            if level > 0:
                continue
            app = _app_of(module)
            if app and app not in allowed_targets:
                offenders.append(f"{rel}: 禁止依赖业务 app '{app}'（{module}）")
    assert not offenders, "cloud_storage app 出现业务依赖:\n" + "\n".join(offenders)
