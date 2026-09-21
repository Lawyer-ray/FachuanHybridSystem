"""
apps/core 大清理（refactor/core-cleanup）后的删除完整性 + 架构守卫 E2E 测试。

背景：本分支删除了 config/steering/、infrastructure/event_bus.py + events.py + tracing.py、
interfaces/ 的 6 个死 shim、llm/costs.py、dependencies/oa_filing.py、utils/chinese_format.py、
cloud_storage/ 空壳、protocols/common_protocols.py、documents/models/evidence.py 等死代码，
并改造了 protocols/__init__.py（`from .common import` 替代 `common_protocols`）与
interfaces/__init__.py（去掉 EventBus/Events 导出）。

本文件从「外部可观察行为」角度守卫这些删除：
  1. ServiceLocator 双入口身份一致（重导出层未断链）
  2. EventBus/Events 彻底消失
  3. interfaces/ 的 6 个死 shim 全部不可导入
  4. protocols 链路完整（from .common import 改造未断链）
  5. 全仓 import 冒烟（排除 migrations）
  6. API 路由聚合完好（core 的 5 个 system-config 路由）

注意：本测试只做「读」操作，不触碰数据库、不发起网络请求。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[4]
APPS_DIR = BACKEND_DIR / "apps"


# ─── 1. ServiceLocator 双入口身份一致 ────────────────────────────────────────


def test_service_locator_dual_entry_same_class_object() -> None:
    """`apps.core.interfaces.ServiceLocator` 与 `apps.core.infrastructure.service_locator.ServiceLocator`
    必须是同一个 class 对象（重导出层未用 import-and-subclass 破坏身份）。"""
    from apps.core.infrastructure.service_locator import ServiceLocator as InfraSL
    from apps.core.interfaces import ServiceLocator as InterfacesSL

    assert InterfacesSL is InfraSL, "ServiceLocator 双入口身份不一致：interfaces 层可能重新定义/包装了 class"


@pytest.mark.django_db
def test_service_locator_getters_return_instances() -> None:
    """ServiceLocator.get_system_config_service() / get_llm_service() 能正常返回实例。"""
    from apps.core.interfaces import ServiceLocator

    system_config_service = ServiceLocator.get_system_config_service()
    llm_service = ServiceLocator.get_llm_service()

    assert system_config_service is not None
    assert llm_service is not None

    # get_or_create 语义：二次调用应返回同一实例（缓存生效，证明 DI 容器完好）
    assert ServiceLocator.get_system_config_service() is system_config_service
    assert ServiceLocator.get_llm_service() is llm_service


@pytest.mark.django_db
def test_service_locator_get_business_config_service() -> None:
    """Core mixin 的另一个常用 getter 也可用（证明 mixin 组装未断）。"""
    from apps.core.interfaces import ServiceLocator

    service = ServiceLocator.get_business_config_service()
    assert service is not None


# ─── 2. EventBus / Events 彻底消失 ──────────────────────────────────────────


def test_interfaces_module_has_no_eventbus_or_events_attr() -> None:
    """`apps.core.interfaces` 模块没有 EventBus / Events 属性。"""
    import apps.core.interfaces as interfaces_mod

    assert not hasattr(interfaces_mod, "EventBus"), "interfaces 仍暴露 EventBus 属性"
    assert not hasattr(interfaces_mod, "Events"), "interfaces 仍暴露 Events 属性"
    # __all__ 中也不应出现
    assert "EventBus" not in interfaces_mod.__all__
    assert "Events" not in interfaces_mod.__all__


def test_import_eventbus_from_interfaces_raises_importerror() -> None:
    """`from apps.core.interfaces import EventBus` 必须抛 ImportError。"""
    with pytest.raises(ImportError):
        from apps.core.interfaces import EventBus  # type: ignore[attr-defined]


def test_deleted_event_bus_modules_are_gone() -> None:
    """删除的 event_bus / events / tracing 模块文件确实不存在。"""
    infra = BACKEND_DIR / "apps" / "core" / "infrastructure"
    for name in ("event_bus.py", "events.py", "tracing.py"):
        assert not (infra / name).exists(), f"{name} 应已被删除但仍存在"


# ─── 3. interfaces/ 的 6 个死 shim 全不可导入 ────────────────────────────────

DEAD_SHIM_MODULES = [
    "apps.core.interfaces.dtos",
    "apps.core.interfaces.automation_protocols",
    "apps.core.interfaces.case_protocols",
    "apps.core.interfaces.contract_protocols",
    "apps.core.interfaces.document_protocols",
    "apps.core.interfaces.organization_protocols",
]


@pytest.mark.parametrize("module_name", DEAD_SHIM_MODULES)
def test_dead_shim_module_not_importable(module_name: str) -> None:
    """6 个死 shim 子模块必须 ModuleNotFoundError。"""
    # 先确保不在 sys.modules 缓存中
    sys.modules.pop(module_name, None)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_interfaces_dir_contains_only_expected_files() -> None:
    """interfaces/ 目录只剩 __init__.py + service_locator.py（+ __pycache__）。"""
    interfaces_dir = BACKEND_DIR / "apps" / "core" / "interfaces"
    py_files = {p.name for p in interfaces_dir.glob("*.py")}
    assert py_files == {"__init__.py", "service_locator.py"}, (
        f"interfaces/ 目录存在意料之外的 .py 文件: {sorted(py_files)}"
    )


# ─── 4. protocols 链路完整 ──────────────────────────────────────────────────


def test_protocols_common_imports_available() -> None:
    """`from apps.core.protocols import ...` 的常用接口全部可用
    （证明 `from .common import` 替代 `common_protocols` 的改造没断链）。"""
    from apps.core.protocols import IAccountSelectionStrategy, ICaseService, ILLMService, ISystemConfigService

    assert ICaseService is not None
    assert ILLMService is not None
    assert ISystemConfigService is not None
    assert IAccountSelectionStrategy is not None


def test_protocols_common_module_importable() -> None:
    """`apps.core.protocols.common` 子包可导入（替代方案落地）。"""
    import apps.core.protocols.common as common_mod

    assert hasattr(common_mod, "ILLMService")
    assert hasattr(common_mod, "ISystemConfigService")
    assert hasattr(common_mod, "IAccountSelectionStrategy")


def test_common_protocols_module_gone() -> None:
    """旧的 `apps.core.protocols.common_protocols` 必须 ModuleNotFoundError。"""
    sys.modules.pop("apps.core.protocols.common_protocols", None)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("apps.core.protocols.common_protocols")


def test_icase_service_identity_across_entry_points() -> None:
    """`from apps.core.interfaces import ICaseService` 与
    `from apps.core.protocols import ICaseService` 是同一对象（无重复定义）。"""
    from apps.core.interfaces import ICaseService as ViaInterfaces
    from apps.core.protocols import ICaseService as ViaProtocols

    assert ViaInterfaces is ViaProtocols


def test_illm_service_identity_across_entry_points() -> None:
    """ILLMService 同样保证双入口同一对象。"""
    from apps.core.interfaces import ILLMService as ViaInterfaces
    from apps.core.protocols import ILLMService as ViaProtocols

    assert ViaInterfaces is ViaProtocols


def test_all_protocols_in_all_are_resolvable() -> None:
    """protocols.__all__ 中的每个名字都能从模块解析到（__all__ 未列无效导出）。"""
    import apps.core.protocols as protocols_mod

    missing = [name for name in protocols_mod.__all__ if not hasattr(protocols_mod, name)]
    assert not missing, f"protocols.__all__ 中存在无法解析的导出: {missing}"


# ─── 5. 全仓 import 冒烟 ────────────────────────────────────────────────────


def _iter_app_packages() -> list[str]:
    """列出 apps 下所有一级 app 包名。"""
    return sorted(
        p.name
        for p in APPS_DIR.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith("__")
    )


def _is_skippable_module(mod_name: str) -> bool:
    """跳过 migrations（由 Django 迁移机制加载，冒烟无意义且依赖 DB 状态）。"""
    return ".migrations" in mod_name


def _collect_app_modules() -> list[str]:
    """遍历 apps 下所有模块（排除 migrations），返回完整模块名列表。"""
    modules: list[str] = []
    for app_pkg in _iter_app_packages():
        root = f"apps.{app_pkg}"
        try:
            pkg = importlib.import_module(root)
        except Exception as exc:  # pragma: no cover - 失败由调用方断言
            raise AssertionError(f"导入 app 根包失败: {root}: {exc!r}") from exc
        for mod_info in pkgutil.walk_packages(pkg.__path__, prefix=f"{root}."):
            if _is_skippable_module(mod_info.name):
                continue
            modules.append(mod_info.name)
    return sorted(modules)


def test_all_app_modules_import_successfully() -> None:
    """全仓 import 冒烟：遍历 apps 下所有模块（排除 migrations），全部 import 成功。

    基线：约 1915 个模块 ALL OK。任何 ImportError / ModuleNotFoundError 都是回归。
    """
    modules = _collect_app_modules()
    assert len(modules) > 1500, f"模块数量异常偏低（{len(modules)}），遍历逻辑可能有 bug"

    failures: list[str] = []
    for mod_name in modules:
        try:
            importlib.import_module(mod_name)
        except Exception as exc:
            failures.append(f"{mod_name}: {type(exc).__name__}: {exc}")

    assert not failures, f"{len(failures)} 个模块导入失败:\n" + "\n".join(failures[:40])


# ─── 6. API 路由聚合完好 ────────────────────────────────────────────────────


def test_api_v1_imports_successfully() -> None:
    """`from apiSystem.api import api_v1` 成功（API 聚合层未断）。"""
    from apiSystem.api import api_v1

    assert api_v1 is not None


def test_core_system_config_routes_registered() -> None:
    """core 的 5 个 system-config 路由都在（list/update/create/patch/delete）。"""
    from apps.core.api import router as core_router

    # path_operations: dict[str, PathView]，PathView.operations 持 Operation 列表
    paths = list(core_router.path_operations.keys())
    assert "/system-configs" in paths, f"缺少 system-config 列表路由；现有: {paths}"
    assert "/system-configs/{key}" in paths, f"缺少 system-config 单项路由；现有: {paths}"

    methods = {
        (path, method)
        for path, path_view in core_router.path_operations.items()
        for op in path_view.operations
        for method in op.methods
        if path.startswith("/system-configs")
    }
    expected_methods = {
        ("/system-configs", "GET"),
        ("/system-configs", "PUT"),
        ("/system-configs", "POST"),
        ("/system-configs/{key}", "PATCH"),
        ("/system-configs/{key}", "DELETE"),
    }
    missing = expected_methods - methods
    assert not missing, f"缺少 system-config 操作: {sorted(missing)}"


def test_core_config_router_mounted_on_api_v1() -> None:
    """core 的 config router 被挂载到 api_v1 的 /config 前缀下。"""
    from apiSystem.api import api_v1

    # _routers: list[tuple[str, Router]]（prefix, router）
    prefixes = [prefix for prefix, _router in api_v1._routers]
    assert any(prefix.rstrip("/").endswith("/config") for prefix in prefixes), (
        f"api_v1 未挂载 /config router；现有前缀: {prefixes}"
    )


def test_api_v1_total_router_count_reasonable() -> None:
    """api_v1 聚合的路由数量在合理范围（防路由大面积丢失）。"""
    from apiSystem.api import api_v1

    count = len(api_v1._routers)
    assert count >= 40, f"api_v1 路由数量异常偏低: {count}"


# ─── 7. 其他删除项验证（补充守卫） ───────────────────────────────────────────


@pytest.mark.parametrize(
    "rel_path",
    [
        "apps/core/llm/costs.py",
        "apps/core/utils/chinese_format.py",
        "apps/core/dependencies/oa_filing.py",
        "apps/documents/models/evidence.py",
    ],
)
def test_other_deleted_files_are_gone(rel_path: str) -> None:
    """其他删除项的文件确实不存在。"""
    assert not (BACKEND_DIR / rel_path).exists(), f"{rel_path} 应已被删除但仍存在"


def test_steering_dir_gone() -> None:
    """config/steering/ 目录整体删除。"""
    assert not (BACKEND_DIR / "apps" / "core" / "config" / "steering").exists()


def test_no_residual_references_to_deleted_steering() -> None:
    """仓库内无对 `apps.core.config.steering` 的残留 import（仅扫 .py，排除缓存目录）。"""
    py_files = [
        p for base in (APPS_DIR, BACKEND_DIR / "apiSystem") for p in base.rglob("*.py") if "__pycache__" not in p.parts
    ]
    assert py_files, "未找到任何 .py 文件，遍历逻辑可能有 bug"

    hits = [str(p) for p in py_files if "apps.core.config.steering" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, "发现 steering 残留引用:\n" + "\n".join(hits)
