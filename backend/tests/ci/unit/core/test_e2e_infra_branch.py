"""端到端验证：middleware / 请求上下文 / config 体系 / 删除项与保留项。

覆盖分支 refactor/core-cleanup 在基础设施/配置层的改动：
  1. RequestIdMiddleware 真实 HTTP 请求链路（含改用 get_trace_ids 后的行为不变）
  2. 配置体系完整性（CONFIG_REGISTRY 无 steering 副作用、config.yaml 合法）
  3. 删除项验证（import 应失败）
  4. 保留项仍可用（防止误删）
  5. qcluster_spawn 的 setattr 修复
  6. validators / init_system_config 仍正常
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
import yaml

# =====================================================================
# 场景 1: RequestIdMiddleware 真实请求链路（热路径）
# =====================================================================


@pytest.mark.django_db
class TestRequestIdMiddlewareRealRequestChain:
    """用 Django test Client 发真实 HTTP 请求，验证中间件全链路行为。"""

    def test_request_sets_request_id_and_response_header(self, client) -> None:
        """请求经过中间件后 request.request_id 被设置，响应带回 X-Request-ID。"""
        from apps.core.infrastructure import request_context as rc

        captured: dict[str, str | None] = {}

        # 用一个中间件之后的钩子捕获 request.request_id（用 middleware 后置信号不可行，
        # 这里通过 patch _cleanup 之前的 set_response_id 间接观测）。
        original_cleanup = rc.clear_request_context

        def _spy_cleanup() -> None:
            # clear 之前读取 context，验证期间确实被设置过
            captured["request_id"] = rc.request_id_var.get()
            captured["trace_id"] = rc.trace_id_var.get()
            captured["span_id"] = rc.span_id_var.get()
            original_cleanup()

        with patch("apps.core.middleware.request_id.clear_request_context", side_effect=_spy_cleanup):
            response = client.get("/health/", HTTP_X_REQUEST_ID="trace-chain-abc")

        assert response.status_code in (200, 503)
        assert response.headers["X-Request-ID"] == "trace-chain-abc"
        # 请求期间 set_request_context 被调用，request_id 为 header 值
        assert captured["request_id"] == "trace-chain-abc"

    def test_valid_x_request_id_header_is_adopted(self, client) -> None:
        """合法 X-Request-ID 被采用，响应头回显同一值。"""
        response = client.get("/health/", HTTP_X_REQUEST_ID="my-req-42")
        assert response.headers["X-Request-ID"] == "my-req-42"

    def test_invalid_x_request_id_with_space_is_rejected(self, client) -> None:
        """含空格的非法 X-Request-ID 被拒绝，生成新的 8 位 hex ID。"""
        response = client.get("/health/", HTTP_X_REQUEST_ID="bad id with spaces")
        rid = response.headers["X-Request-ID"]
        assert rid != "bad id with spaces"
        assert len(rid) == 8
        assert all(c in "0123456789abcdef" for c in rid)

    def test_no_header_generates_new_id(self, client) -> None:
        """不带 header 时自动生成 8 位 hex ID。"""
        response = client.get("/health/")
        rid = response.headers["X-Request-ID"]
        assert len(rid) == 8
        assert all(c in "0123456789abcdef" for c in rid)

    def test_set_and_clear_request_context_called(self, client) -> None:
        """set_request_context 与 clear_request_context 都被调用。"""
        from apps.core.middleware import request_id as mw

        with (
            patch.object(mw, "set_request_context", wraps=mw.set_request_context) as mock_set,
            patch.object(mw, "clear_request_context", wraps=mw.clear_request_context) as mock_clear,
        ):
            client.get("/health/", HTTP_X_REQUEST_ID="ctx-check-1")

        mock_set.assert_called_once()
        mock_clear.assert_called_once()
        kwargs = mock_set.call_args.kwargs
        assert kwargs["request_id"] == "ctx-check-1"

    def test_trace_id_falls_back_to_request_id_when_empty(self, client) -> None:
        """重点：改用 get_trace_ids() 后，trace_id 为空时回退用 request_id。"""
        from apps.core.middleware import request_id as mw

        seen: dict[str, str | None] = {}

        def _capture_set(*, request_id, trace_id, span_id):
            seen["request_id"] = request_id
            seen["trace_id"] = trace_id
            seen["span_id"] = span_id

        # get_trace_ids 返回空 trace_id（模拟无上游 trace 的场景）
        with (
            patch.object(mw, "get_trace_ids", return_value=(None, None)),
            patch.object(mw, "set_request_context", side_effect=_capture_set),
        ):
            client.get("/health/", HTTP_X_REQUEST_ID="fallback-rid")

        assert seen["request_id"] == "fallback-rid"
        # trace_id 为空 → 回退为 request_id
        assert seen["trace_id"] == "fallback-rid"

    def test_trace_id_used_when_present(self, client) -> None:
        """get_trace_ids 返回非空 trace_id 时，trace_id 被透传（不回退）。"""
        from apps.core.middleware import request_id as mw

        seen: dict[str, str | None] = {}

        def _capture_set(*, request_id, trace_id, span_id):
            seen["request_id"] = request_id
            seen["trace_id"] = trace_id
            seen["span_id"] = span_id

        with (
            patch.object(mw, "get_trace_ids", return_value=("upstream-trace-xyz", "span-777")),
            patch.object(mw, "set_request_context", side_effect=_capture_set),
        ):
            client.get("/health/", HTTP_X_REQUEST_ID="rid-2")

        assert seen["request_id"] == "rid-2"
        assert seen["trace_id"] == "upstream-trace-xyz"
        assert seen["span_id"] == "span-777"

    def test_empty_string_trace_id_falls_back(self, client) -> None:
        """get_trace_ids 返回空字符串 trace_id 时同样回退（falsy 值）。"""
        from apps.core.middleware import request_id as mw

        seen: dict[str, str | None] = {}

        def _capture_set(*, request_id, trace_id, span_id):
            seen["trace_id"] = trace_id

        with (
            patch.object(mw, "get_trace_ids", return_value=("", "")),
            patch.object(mw, "set_request_context", side_effect=_capture_set),
        ):
            client.get("/health/", HTTP_X_REQUEST_ID="empty-fallback")

        assert seen["trace_id"] == "empty-fallback"


# =====================================================================
# 场景 2: 配置体系完整性
# =====================================================================


class TestConfigSystemIntegrity:
    """配置导入、单例、registry 无 steering 副作用、YAML 合法。"""

    def test_config_public_api_importable(self) -> None:
        """apps.core.config 公共 API 全部可用。"""
        from apps.core.config import ConfigException, ConfigManager, get_config, get_config_manager

    def test_get_config_manager_is_singleton(self) -> None:
        """get_config_manager() 返回单例。"""
        from apps.core.config import get_config_manager

        a = get_config_manager()
        b = get_config_manager()
        assert a is b

    def test_reads_config_yaml_value(self) -> None:
        """能读到 config.yaml 的值。"""
        from apps.core.config import get_config

        assert get_config("features.document_processing.default_text_limit") == 5000

    def test_registry_has_no_steering_keys(self) -> None:
        """CONFIG_REGISTRY 不含任何 steering.* key，但仍含其他 key。"""
        from apps.core.config.schema.registry import CONFIG_REGISTRY

        keys = list(CONFIG_REGISTRY.keys())
        assert keys, "CONFIG_REGISTRY 不应为空"
        assert len(keys) > 50, f"registry 数量不合理: {len(keys)}"
        steering_keys = [k for k in keys if "steering" in k.lower()]
        assert steering_keys == [], f"registry 仍含 steering key: {steering_keys}"

    def test_config_package_has_no_steering_attr(self) -> None:
        """apps.core.config 包没有 steering 属性。"""
        import apps.core.config as cfg_pkg

        assert not hasattr(cfg_pkg, "steering")

    @pytest.mark.parametrize("filename", ["config.yaml", "config.example.yaml"])
    def test_config_yaml_files_are_valid_and_steering_free(self, filename: str) -> None:
        """config.yaml / config.example.yaml 是合法 YAML 且无 steering 顶层键。"""
        path = Path(__file__).resolve()
        # tests/ci/unit/core/test_*.py → backend/apps/core/config/
        backend_root = next(p for p in path.parents if p.name == "backend")
        cfg_file = backend_root / "apps" / "core" / "config" / filename
        assert cfg_file.exists(), f"配置文件不存在: {cfg_file}"

        with cfg_file.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        assert isinstance(data, dict), f"{filename} 解析结果应为 dict"
        assert "steering" not in data, f"{filename} 仍含 steering 顶层键"


# =====================================================================
# 场景 3: 删除项验证（import 应失败）
# =====================================================================


class TestDeletedModulesRaiseOnImport:
    """已删除模块 import 应抛 ModuleNotFoundError。"""

    @pytest.mark.parametrize(
        "module_name",
        [
            "apps.core.config.steering",
            "apps.core.config.steering.cache_strategies",
            "apps.core.config.steering.dependency_manager",
            "apps.core.config.steering._perf_monitor",
            "apps.core.infrastructure.tracing",
            "apps.core.cloud_storage",
            "apps.core.utils.chinese_format",
            "apps.core.dependencies.oa_filing",
        ],
    )
    def test_module_import_fails(self, module_name: str) -> None:
        """删除的模块 import 应抛 ModuleNotFoundError。"""
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)

    def test_infrastructure_no_tracing_attr(self) -> None:
        """apps.core.infrastructure 没有 tracing 属性。"""
        import apps.core.infrastructure as infra

        assert not hasattr(infra, "tracing")


# =====================================================================
# 场景 4: 保留项仍可用（防止误删）
# =====================================================================


class TestRetainedModulesStillWork:
    """保留的公共 API 仍可导入且行为正确。"""

    def test_utils_id_card_exports(self) -> None:
        """from apps.core.utils import IdCardUtils, IdCardInfo 成功。"""
        from apps.core.utils import IdCardInfo, IdCardUtils

    def test_utils_all_only_two_names(self) -> None:
        """apps.core.utils.__all__ 只保留 IdCardInfo/IdCardUtils。"""
        from apps.core import utils

        assert set(utils.__all__) == {"IdCardInfo", "IdCardUtils"}

    def test_utils_submodules_importable(self) -> None:
        """utils 子模块全部可用。"""
        from apps.core.utils import id_card_utils, path, startup_db, validators

    def test_id_card_utils_functional(self) -> None:
        """IdCardUtils 可实际调用。"""
        from apps.core.utils import IdCardInfo, IdCardUtils

        result = IdCardUtils.validate_id_card("11010519491231002X")
        assert isinstance(result, dict)
        assert result["valid"] is True

        info = IdCardUtils.parse_id_card_info("11010519491231002X")
        assert isinstance(info, IdCardInfo)
        assert info.birth_date == "1949年12月31日"
        # 第17位为 2（偶数）→ 女
        assert info.gender == "女"

    def test_constants_large_file_max_size(self) -> None:
        """LARGE_FILE_MAX_SIZE 存在且值 = 50MB。"""
        from apps.core.constants import LARGE_FILE_MAX_SIZE

        assert LARGE_FILE_MAX_SIZE == 50 * 1024 * 1024

    def test_services_lazy_getattr_still_works(self) -> None:
        """services/__init__ 的 __getattr__ 懒加载没被破坏。"""
        import apps.core.services as svc
        from apps.core.services import ConversationService, SystemUpdateService

        assert isinstance(svc, ModuleType)
        # 不存在的属性应抛 AttributeError
        with pytest.raises(AttributeError):
            svc.NoSuchServiceXYZ

    def test_help_command_lists_remaining_commands(self) -> None:
        """4 个管理命令删除后 get_commands() 仍能正常列出剩余命令。"""
        from django.core.management import get_commands

        commands = get_commands()
        # Django 6.1 已无独立 help 命令入口，用 check 命令验证管理框架正常
        assert "check" in commands
        # 已删除的命令不应出现
        for deleted in (
            "collect_court_templates",
            "test_court_template_collection",
            "ensure_cloakbrowser",
            "start_resource_monitor",
        ):
            assert deleted not in commands, f"命令 {deleted} 应已删除"
        # 剩余核心命令仍在
        assert "init_system_config" in commands
        assert len(commands) > 10

    def test_call_check_command_works(self) -> None:
        """call_command('check') 不抛异常（管理命令框架正常）。"""
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("check", stdout=out)


# =====================================================================
# 场景 5: qcluster_spawn 修复验证
# =====================================================================


class TestQclusterSpawnPatch:
    """setattr 挂属性修复：可导入、可调用、幂等、带 _fachuan_spawn_patched。"""

    def test_import_patch_function(self) -> None:
        """patch 函数可导入。"""
        from apps.core.tasking.qcluster_spawn import patch_django_q_mp_context_for_macos

    def test_patch_is_idempotent_and_sets_attr(self) -> None:
        """调用后 get_mp_context 被替换且带 _fachuan_spawn_patched；重复调用幂等。"""
        from django_q import cluster as django_q_cluster

        from apps.core.tasking.qcluster_spawn import patch_django_q_mp_context_for_macos

        # 保存原始状态以便恢复
        original = django_q_cluster.get_mp_context
        try:
            patch_django_q_mp_context_for_macos()

            if __import__("sys").platform != "darwin":
                # 非 macOS 直接 return，不 patch
                assert getattr(django_q_cluster.get_mp_context, "_fachuan_spawn_patched", False) is False
                return

            patched = django_q_cluster.get_mp_context
            assert getattr(patched, "_fachuan_spawn_patched", False) is True

            # 第二次调用直接 return（幂等）：函数对象不变
            patch_django_q_mp_context_for_macos()
            assert django_q_cluster.get_mp_context is patched
        finally:
            django_q_cluster.get_mp_context = original


# =====================================================================
# 场景 6: validators / init_system_config 仍正常
# =====================================================================


class TestValidatorsAndInitSystemConfig:
    """删 type: ignore 后验证器与管理命令仍正常。"""

    def test_validators_main_methods_callable(self) -> None:
        """主要验证函数可调用且行为正确。"""
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("13800138000") == "13800138000"
        assert Validators.validate_phone(None) is None
        with pytest.raises(Exception):
            Validators.validate_phone("123")

        assert Validators.validate_email("a@b.com") == "a@b.com"
        with pytest.raises(Exception):
            Validators.validate_email("not-an-email")

        assert Validators.validate_id_card("11010519491231002X") == "11010519491231002X"
        assert Validators.validate_required("v", "f") == "v"

    def test_init_system_config_command_importable(self) -> None:
        """init_system_config 的 Command 可导入。"""
        from apps.core.management.commands.init_system_config import Command

        assert hasattr(Command, "handle")
