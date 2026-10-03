"""文档生成结果和占位符注册表测试。"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from apps.documents.services.generation.result import GenerationResult
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.context_builder import EnhancedContextBuilder
from apps.documents.services.placeholders.contract.criminal_cause_service import CriminalCauseService
from apps.documents.services.placeholders.litigation.basic_placeholder_services import (
    LitigationCauseOfActionPlaceholderService,
)
from apps.documents.services.placeholders.litigation.enforcement_basic_service import EnforcementCauseOfActionService
from apps.documents.services.placeholders.registry import PlaceholderRegistry


class TestGenerationResult:
    """GenerationResult 数据类测试。"""

    def test_success_result(self) -> None:
        result = GenerationResult(
            success=True,
            file_path="/path/to/file.docx",
            file_name="file.docx",
            duration_ms=1500,
        )
        assert result.success is True
        assert result.file_path == "/path/to/file.docx"
        assert result.file_name == "file.docx"
        assert result.duration_ms == 1500
        assert result.error_message is None

    def test_failure_result(self) -> None:
        result = GenerationResult(
            success=False,
            error_message="生成失败",
            duration_ms=500,
        )
        assert result.success is False
        assert result.error_message == "生成失败"

    def test_success_without_path_raises(self) -> None:
        """成功但无路径应抛出异常。"""
        with pytest.raises(ValueError, match="文件路径"):
            GenerationResult(success=True)

    def test_failure_without_error_raises(self) -> None:
        """失败但无错误信息应抛出异常。"""
        with pytest.raises(ValueError, match="错误信息"):
            GenerationResult(success=False)

    def test_negative_duration_raises(self) -> None:
        """负耗时应抛出异常。"""
        with pytest.raises(ValueError, match="负数"):
            GenerationResult(success=True, file_path="/path", duration_ms=-1)


class TestPlaceholderRegistry:
    """PlaceholderRegistry 测试。"""

    def setup_method(self) -> None:
        # 重置单例
        PlaceholderRegistry._instance = None
        PlaceholderRegistry._initialized = False
        PlaceholderRegistry._services = {}
        PlaceholderRegistry._key_owner_names = {}

    def test_singleton(self) -> None:
        """单例模式。"""
        r1 = PlaceholderRegistry()
        r2 = PlaceholderRegistry()
        assert r1 is r2

    def test_register_service(self) -> None:
        """注册占位符服务。"""
        class TestService(BasePlaceholderService):
            name = "test_reg"
            display_name = "测试注册"
            placeholder_keys = ["key1"]

            def generate(self, context_data):
                return {"key1": "value1"}

        PlaceholderRegistry.register(TestService)
        registry = PlaceholderRegistry()
        assert "test_reg" in registry._services

    def test_register_invalid_service(self) -> None:
        """注册无效服务应抛出异常。"""
        with pytest.raises(ValueError, match="继承自 BasePlaceholderService"):
            PlaceholderRegistry.register(type("Bad", (), {}))

    def test_register_service_without_name(self) -> None:
        """无名称的服务应抛出异常。"""
        class NoNameService(BasePlaceholderService):
            name = ""
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        with pytest.raises(ValueError, match="name"):
            PlaceholderRegistry.register(NoNameService)

    def test_register_duplicate_raises(self) -> None:
        """重复注册应抛出异常。"""
        class DupService(BasePlaceholderService):
            name = "dup_test"
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        PlaceholderRegistry.register(DupService)
        with pytest.raises(Exception):
            PlaceholderRegistry.register(DupService)


class _RegistryStateGuard:
    """保存并恢复 PlaceholderRegistry 全局单例状态,避免测试间互相污染。"""

    _saved: tuple[Any, ...] | None = None

    def save(self) -> None:
        self._saved = (
            PlaceholderRegistry._instance,
            PlaceholderRegistry._initialized,
            dict(PlaceholderRegistry._services),
            dict(PlaceholderRegistry._key_owner_names),
        )
        PlaceholderRegistry._instance = None
        PlaceholderRegistry._initialized = False
        PlaceholderRegistry._services = {}
        PlaceholderRegistry._key_owner_names = {}

    def restore(self) -> None:
        if self._saved is None:
            return
        instance, initialized, services, key_owner_names = self._saved
        PlaceholderRegistry._instance = instance
        PlaceholderRegistry._initialized = initialized
        PlaceholderRegistry._services = services
        PlaceholderRegistry._key_owner_names = key_owner_names


class TestPlaceholderRegistryKeyConflict(_RegistryStateGuard):
    """占位符键注册冲突检测测试。"""

    REGISTRY_LOGGER = "apps.documents.services.placeholders.registry"

    def setup_method(self) -> None:
        self.save()

    def teardown_method(self) -> None:
        self.restore()

    @staticmethod
    def _make_conflict_service(*, name: str, module: str, value: str) -> type[BasePlaceholderService]:
        class _Service(BasePlaceholderService):
            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {"共享键": value}

        _Service.name = name
        _Service.placeholder_keys = ["共享键"]
        _Service.__module__ = module
        return _Service

    def test_conflicting_key_logs_error_with_both_services_and_key(self, caplog) -> None:
        """第二个服务注册同键时触发 error 日志,包含两个服务名与键名。"""
        svc_first = self._make_conflict_service(name="svc_first", module="tests.zzz_first", value="first")
        svc_second = self._make_conflict_service(name="svc_second", module="tests.aaa_second", value="second")

        with caplog.at_level(logging.ERROR, logger=self.REGISTRY_LOGGER):
            PlaceholderRegistry.register(svc_first)
            PlaceholderRegistry.register(svc_second)

        messages = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
        assert any("共享键" in msg and "svc_first" in msg and "svc_second" in msg for msg in messages)

    def test_conflict_winner_deterministic_regardless_of_order(self, caplog) -> None:
        """无论注册顺序如何,键归属均由模块路径排序确定(取先者)。"""
        svc_aaa = self._make_conflict_service(name="svc_aaa", module="tests.aaa", value="aaa")
        svc_zzz = self._make_conflict_service(name="svc_zzz", module="tests.zzz", value="zzz")

        with caplog.at_level(logging.ERROR, logger=self.REGISTRY_LOGGER):
            PlaceholderRegistry.register(svc_zzz)
            PlaceholderRegistry.register(svc_aaa)
            registry = PlaceholderRegistry()
            owner = registry.get_service_for_placeholder("共享键")
            assert owner is not None and owner.name == "svc_aaa"
            assert registry.get_placeholder_key_owner("共享键") == "svc_aaa"

        # 反向注册顺序,归属不变
        PlaceholderRegistry().clear()
        PlaceholderRegistry.register(svc_aaa)
        PlaceholderRegistry.register(svc_zzz)
        registry = PlaceholderRegistry()
        owner = registry.get_service_for_placeholder("共享键")
        assert owner is not None and owner.name == "svc_aaa"
        assert registry.get_placeholder_key_owner("共享键") == "svc_aaa"

    def test_unique_key_no_error_logged(self, caplog) -> None:
        """唯一键注册不触发冲突日志。"""
        svc = self._make_conflict_service(name="svc_unique", module="tests.unique", value="v")

        with caplog.at_level(logging.ERROR, logger=self.REGISTRY_LOGGER):
            PlaceholderRegistry.register(svc)

        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_owner_returns_none_for_unknown_key(self) -> None:
        """未注册的键无归属。"""
        assert PlaceholderRegistry().get_placeholder_key_owner("不存在键") is None

    def test_relevant_services_deduplicated_by_type(self) -> None:
        """required_placeholders 命中同一服务多个键时,按服务类型去重(注册表每次返回新实例)。"""
        class TwoKeyService(BasePlaceholderService):
            name = "two_key_service"
            placeholder_keys = ["k1", "k2"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {"k1": "v1", "k2": "v2"}

        PlaceholderRegistry.register(TwoKeyService)
        services = EnhancedContextBuilder()._get_relevant_services(required_placeholders=["k1", "k2"])
        assert len(services) == 1
        assert isinstance(services[0], TwoKeyService)


class TestCauseOfActionKeyCollision(_RegistryStateGuard):
    """「案由」三服务撞键修复:合同流取真实案由,诉讼流保持案件案由。"""

    def setup_method(self) -> None:
        self.save()

    def teardown_method(self) -> None:
        self.restore()

    @staticmethod
    def _register_cause_services(*, criminal_last: bool) -> None:
        """按指定顺序注册三个声明「案由」的真实服务。"""
        services: list[type[Any]] = (
            [EnforcementCauseOfActionService, LitigationCauseOfActionPlaceholderService, CriminalCauseService]
            if criminal_last
            else [CriminalCauseService, EnforcementCauseOfActionService, LitigationCauseOfActionPlaceholderService]
        )
        for service_class in services:
            PlaceholderRegistry.register(service_class)

    def test_owner_is_criminal_cause_service_in_both_orders(self) -> None:
        """两种注册顺序下,「案由」归属均为 CriminalCauseService。"""
        for criminal_last in (True, False):
            PlaceholderRegistry().clear()
            self._register_cause_services(criminal_last=criminal_last)
            registry = PlaceholderRegistry()
            owner = registry.get_service_for_placeholder("案由")
            assert owner is not None and owner.name == "criminal_cause_service"
            assert registry.get_placeholder_key_owner("案由") == "criminal_cause_service"

    def test_contract_flow_gets_real_cause_of_action(self) -> None:
        """合同流(只有 contract、无 case)的「案由」来自 CriminalCauseService,不再是 "/"。"""
        self._register_cause_services(criminal_last=True)
        case = SimpleNamespace(id=None, cause_of_action="危险作业罪")
        contract = SimpleNamespace(cases=SimpleNamespace(all=lambda: [case]))

        context = EnhancedContextBuilder().build_context({"contract": contract})

        assert context["案由"] == "危险作业罪"

    def test_contract_flow_with_required_placeholder_only_runs_owner(self) -> None:
        """指定 required_placeholders 时,「案由」只由归属服务产出。"""
        self._register_cause_services(criminal_last=True)
        case = SimpleNamespace(id=None, cause_of_action="危险作业罪")
        contract = SimpleNamespace(cases=SimpleNamespace(all=lambda: [case]))

        context = EnhancedContextBuilder().build_context({"contract": contract}, required_placeholders=["案由"])

        assert context["案由"] == "危险作业罪"

    def test_litigation_flow_cause_of_action_comes_from_case(self) -> None:
        """诉讼流(有 case)的「案由」仍等于案件案由(回归保护)。"""
        self._register_cause_services(criminal_last=True)
        case = SimpleNamespace(id=None, cause_of_action="买卖合同纠纷")

        context = EnhancedContextBuilder().build_context({"case": case})

        assert context["案由"] == "买卖合同纠纷"

    def test_litigation_dto_flow_cause_of_action_comes_from_dto(self) -> None:
        """起诉状/答辩状流(case_dto)的「案由」仍等于 DTO 案由(回归保护)。"""
        self._register_cause_services(criminal_last=True)
        case_dto = SimpleNamespace(id=None, cause_of_action=" 机动车交通事故责任纠纷 ")

        context = EnhancedContextBuilder().build_context({"case_dto": case_dto})

        assert context["案由"] == "机动车交通事故责任纠纷"

    def test_non_owner_service_output_dropped(self) -> None:
        """非归属服务(无案件上下文的诉讼服务)产出的兜底值不会覆盖归属服务。"""
        self._register_cause_services(criminal_last=True)
        case = SimpleNamespace(id=None, cause_of_action="走私普通货物罪")
        contract = SimpleNamespace(cases=SimpleNamespace(all=lambda: [case]))

        litigation_service = LitigationCauseOfActionPlaceholderService()
        assert litigation_service.generate({"contract": contract}) == {"案由": ""}

        context = EnhancedContextBuilder().build_context({"contract": contract})
        assert context["案由"] == "走私普通货物罪"
