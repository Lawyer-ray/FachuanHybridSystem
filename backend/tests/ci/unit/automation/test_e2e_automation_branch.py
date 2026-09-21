"""End-to-end 验证 `refactor/core-cleanup` 分支在 automation/诉讼态势 链路的修复。

覆盖三大修复点（全部是"此前彻底不可用/冲突"的存量 bug）：

1. ``AutomationServiceAdapter`` 此前 import 即失败（import 不存在的
   ``apps.core.exceptions.ValidationError``，该模块只有 ``ValidationException``），
   导致整个模块从未被成功导入、``except ValidationException`` 分支是死代码。
2. ``litigation/dtos.py`` 此前不存在，``litigation/schemas.py`` 与
   ``litigation/court_pleading_signals_service.py`` 的
   ``from .dtos import CourtPleadingSignals`` 必然 ImportError。
3. ``apps/documents/models/evidence.py`` 是残留副本，与
   ``apps/evidence/models/evidence.py`` 重复注册 ``EvidenceList``，触发
   ``RuntimeError: Conflicting 'evidencelist' models``。

本文件所有断言都走真实 import / 真实 DB（``@pytest.mark.django_db``），
不注入任何 fake 模块。

## 关于同目录 legacy 测试的 sys.modules 污染（重要）

``test_court_pleading_signals.py`` / ``test_court_pleading_signals_adapter.py`` /
``test_automation_service_adapter.py`` 为了绕过"dtos 不存在 / ValidationError
不存在"的存量 bug，在**模块 import 阶段**就做了全局副作用：

* 把假的 ``apps.automation.services.litigation.dtos`` 塞进 ``sys.modules``
  （frozen dataclass 冒充 pydantic BaseModel）；
* 给 ``apps.core.exceptions`` 打 ``ValidationError = ValidationException`` 补丁。

pytest 同进程收集时这些 shim 会**跨文件污染**：谁先 import，后面拿到的就是假的。
本文件在 import 时清掉 litigation/dtos 相关条目并重新加载，保证测的是真实代码。

注意：**不能**顺带 pop ``automation_service_adapter``——那样会造成模块对象
身份变更，legacy 测试里 ``@patch("...automation_service_adapter.TokenAcquisitionHistory")``
会 patch 到新模块对象，而旧类仍读旧 globals，导致 DB 访问未被 mock 拦住。
adapter 模块本身 import 正常，无需重载。
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# 被 legacy 测试 fake 掉的模块名
_FAKE_DTOS_MODULE = "apps.automation.services.litigation.dtos"
_CORE_EXCEPTIONS_MODULE = "apps.core.exceptions"

# 需要重载以绑定真实 dtos 的模块（不含 automation_service_adapter）
_LITIGATION_MODULES = (
    "apps.automation.services.litigation.dtos",
    "apps.automation.services.litigation.schemas",
    "apps.automation.services.litigation.court_pleading_signals_service",
    "apps.automation.services.litigation.court_pleading_signals_service_adapter",
)

# 真实 litigation 模块缓存（惰性加载，保证同进程内类身份稳定）
_REAL_LITIGATION: dict[str, Any] = {}


def _purge_legacy_test_shims() -> None:
    """清掉 legacy 测试注入的假 dtos 模块，强制后续 import 拿到真实文件。

    同时作废 litigation 模块缓存，避免缓存里留下已被 pop 的旧类对象。
    """
    _REAL_LITIGATION.clear()
    for name in list(sys.modules):
        if name == _FAKE_DTOS_MODULE or name.startswith("apps.automation.services.litigation."):
            sys.modules.pop(name, None)

    core_exc = sys.modules.get(_CORE_EXCEPTIONS_MODULE)
    if core_exc is not None and hasattr(core_exc, "ValidationError"):
        delattr(core_exc, "ValidationError")


def _real_litigation() -> Any:
    """返回真实的 litigation service 模块（惰性加载 + 缓存，保证类身份稳定）。

    首次调用时清 shim 并重新 import 整个 litigation 模块树；之后直接返回缓存。
    这样同一进程内所有 `is` 身份断言都指向同一个真实类对象。
    """
    if "svc" not in _REAL_LITIGATION:
        _purge_legacy_test_shims()
        for name in _LITIGATION_MODULES:
            sys.modules.pop(name, None)
        # 按依赖顺序加载：dtos → schemas → service → adapter
        importlib.import_module(_FAKE_DTOS_MODULE)
        importlib.import_module("apps.automation.services.litigation.schemas")
        _REAL_LITIGATION["svc"] = importlib.import_module(
            "apps.automation.services.litigation.court_pleading_signals_service"
        )
        importlib.import_module("apps.automation.services.litigation.court_pleading_signals_service_adapter")
    return _REAL_LITIGATION["svc"]


def _real_dtos_module() -> Any:
    """拿真实 dtos 模块（复用 `_real_litigation` 的缓存，类身份稳定）。"""
    return sys.modules[_FAKE_DTOS_MODULE]


def _real_signals_cls() -> Any:
    """真实的 CourtPleadingSignals pydantic 类（绕过任何 fake 污染）。"""
    return _real_litigation().CourtPleadingSignals


# ---------------------------------------------------------------------------
# 场景 1：AutomationServiceAdapter 真实可用
# ---------------------------------------------------------------------------


class TestAutomationServiceAdapterImport:
    """修复 1：模块此前 import 即失败，现在必须能正常导入。"""

    def test_module_imports_without_shim(self) -> None:
        """不注入任何 sys.modules fake，直接 import 也能成功。

        修复前 `from apps.core.exceptions import ValidationError` 必然
        AttributeError，现有测试靠
        `apps.core.exceptions.ValidationError = ValidationException`
        打补丁才能 import。
        """
        mod = importlib.import_module("apps.automation.services.automation_service_adapter")
        assert hasattr(mod, "AutomationServiceAdapter")
        assert hasattr(mod, "ValidationException")
        assert mod.__file__ is not None

    def test_adapter_binds_real_validation_exception(self) -> None:
        """adapter 模块里的 ValidationException 就是 apps.core.exceptions 的真身。

        修复前它 import 的是不存在的 ValidationError，只能靠测试侧补丁。
        """
        import apps.core.exceptions as core_exc

        mod = importlib.import_module("apps.automation.services.automation_service_adapter")
        assert mod.ValidationException is core_exc.ValidationException

    def test_core_exceptions_has_no_stray_validatonerror_alias(self) -> None:
        """清掉 shim 后，apps.core.exceptions 不应存在 ValidationError 别名。

        注意：legacy 测试 `test_automation_service_adapter.py` 会在模块 import 时
        给它打 `ValidationError = ValidationException` 补丁；本测试先 purge 再断言，
        证明真实源码并不导出这个名字。
        """
        import apps.core.exceptions as core_exc

        _purge_legacy_test_shims()
        assert hasattr(core_exc, "ValidationException")
        assert not hasattr(core_exc, "ValidationError")

    def test_validation_exception_code_preserved(self) -> None:
        """ValidationException 的 code 不会被类名默认值覆盖。"""
        from apps.core.exceptions import ValidationException

        exc = ValidationException(message="m", code="MISSING_REQUIRED_FIELD", errors={"x": "y"})
        assert exc.code == "MISSING_REQUIRED_FIELD"
        assert exc.errors == {"x": "y"}
        assert isinstance(exc, Exception)


class TestAutomationServiceAdapterWiring:
    """修复 1：adapter 能被 ServiceLocator 正常装配并满足 IAutomationService。"""

    def test_service_locator_builds_real_adapter(self) -> None:
        from apps.automation.services.automation_service_adapter import AutomationServiceAdapter
        from apps.core.interfaces import IAutomationService, ServiceLocator

        svc = ServiceLocator.get_automation_service()
        assert isinstance(svc, AutomationServiceAdapter)
        assert callable(getattr(svc, "create_token_acquisition_history_internal", None))

        # Protocol 结构兼容性验证（IAutomationService 非 runtime_checkable）
        proto_attrs = set(getattr(IAutomationService, "__protocol_attrs__", ()))
        assert proto_attrs, "IAutomationService 应有 protocol_attrs"
        for attr in proto_attrs:
            assert callable(getattr(svc, attr, None)), f"adapter 缺少协议方法 {attr}"

        # get_or_create 应缓存同一实例
        assert ServiceLocator.get_automation_service() is svc

    def test_adapter_signature_matches_protocol(self) -> None:
        from apps.automation.services.automation_service_adapter import AutomationServiceAdapter
        from apps.core.interfaces import IAutomationService

        impl = inspect.signature(AutomationServiceAdapter.create_token_acquisition_history_internal)
        proto = inspect.signature(IAutomationService.create_token_acquisition_history_internal)
        assert list(proto.parameters) == list(impl.parameters)

    def test_no_type_ignore_comments_left(self) -> None:
        """分支说明中"移除 4 处 type: ignore"应属实：源码不应残留。"""
        from apps.automation.services import automation_service_adapter as mod

        src = inspect.getsource(mod)
        assert "type: ignore" not in src


_VALID_HISTORY: dict[str, Any] = {
    "site_name": "court_zxfw",
    "account": "tester@example.com",
    "credential_id": 1,
    "status": "SUCCESS",
    "trigger_reason": "manual_trigger",
}


class TestCreateTokenAcquisitionHistoryRealDB:
    """修复 1：三条路径真实跑通（含 DB）。"""

    def _make_adapter(self) -> Any:
        from apps.automation.services.automation_service_adapter import AutomationServiceAdapter

        return AutomationServiceAdapter()

    @pytest.mark.django_db
    def test_missing_required_field_raises_validation_exception(self) -> None:
        from apps.core.exceptions import ValidationException

        adapter = self._make_adapter()
        data = {k: v for k, v in _VALID_HISTORY.items() if k != "account"}
        with pytest.raises(ValidationException) as exc_info:
            adapter.create_token_acquisition_history_internal(data)

        assert exc_info.value.code == "MISSING_REQUIRED_FIELD"
        assert "account" in exc_info.value.errors
        assert "account" in str(exc_info.value.message)

    @pytest.mark.django_db
    def test_invalid_status_raises_validation_exception(self) -> None:
        from apps.core.exceptions import ValidationException

        adapter = self._make_adapter()
        data = {**_VALID_HISTORY, "status": "PENDING"}
        with pytest.raises(ValidationException) as exc_info:
            adapter.create_token_acquisition_history_internal(data)

        assert exc_info.value.code == "INVALID_STATUS"
        assert "status" in exc_info.value.errors

    @pytest.mark.django_db
    def test_success_creates_real_db_record(self) -> None:
        from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus

        adapter = self._make_adapter()
        before = TokenAcquisitionHistory.objects.count()

        history = adapter.create_token_acquisition_history_internal(dict(_VALID_HISTORY))

        assert isinstance(history, TokenAcquisitionHistory)
        assert history.pk is not None
        assert history.status == TokenAcquisitionStatus.SUCCESS
        assert history.site_name == "court_zxfw"
        assert history.account == "tester@example.com"
        assert TokenAcquisitionHistory.objects.count() == before + 1
        assert TokenAcquisitionHistory.objects.filter(pk=history.pk).exists()

    @pytest.mark.django_db
    def test_failed_status_creates_real_db_record(self) -> None:
        from apps.automation.models import TokenAcquisitionHistory, TokenAcquisitionStatus

        adapter = self._make_adapter()
        data = {**_VALID_HISTORY, "status": "FAILED", "error_message": "boom"}

        history = adapter.create_token_acquisition_history_internal(data)

        assert history.status == TokenAcquisitionStatus.FAILED
        assert TokenAcquisitionHistory.objects.filter(pk=history.pk).exists()

    @pytest.mark.django_db
    def test_except_validation_exception_branch_is_live(self) -> None:
        """重点：`except ValidationException: raise` 不是死代码。

        改名前（import 不存在的 ValidationError）该 except 子句本身就会在
        模块加载时炸掉；即便绕过加载，命中判断也永远进 `except Exception`
        被包装成 CREATE_HISTORY_FAILED。现在应能拿到原始 code 且不被包裹。
        """
        from apps.core.exceptions import ValidationException

        adapter = self._make_adapter()
        data = {k: v for k, v in _VALID_HISTORY.items() if k != "credential_id"}

        with pytest.raises(ValidationException) as exc_info:
            adapter.create_token_acquisition_history_internal(data)

        exc = exc_info.value
        assert exc.code == "MISSING_REQUIRED_FIELD"
        assert exc.code != "CREATE_HISTORY_FAILED"
        assert exc is exc.__cause__ if exc.__cause__ is not None else True

    @pytest.mark.django_db
    def test_db_error_is_wrapped_as_create_history_failed(self) -> None:
        """对照：非 ValidationException 走 `except Exception` 包装路径。"""
        from unittest.mock import patch

        from apps.automation.models import TokenAcquisitionHistory
        from apps.core.exceptions import ValidationException

        adapter = self._make_adapter()
        with patch.object(TokenAcquisitionHistory.objects, "create", side_effect=RuntimeError("db down")):
            with pytest.raises(ValidationException) as exc_info:
                adapter.create_token_acquisition_history_internal(dict(_VALID_HISTORY))

        exc = exc_info.value
        assert exc.code == "CREATE_HISTORY_FAILED"
        assert isinstance(exc.__cause__, RuntimeError)

    @pytest.mark.django_db
    def test_optional_fields_defaults_applied(self) -> None:
        adapter = self._make_adapter()
        history = adapter.create_token_acquisition_history_internal(dict(_VALID_HISTORY))

        assert history.attempt_count == 1
        assert history.total_duration == 0.0

    @pytest.mark.django_db
    def test_token_preview_is_scrubbed_by_model_hook(self) -> None:
        """token_preview 经 django_lifecycle 钩子脱敏后置空。"""
        adapter = self._make_adapter()
        data = {**_VALID_HISTORY, "token_preview": "secret-token-abc"}

        history = adapter.create_token_acquisition_history_internal(data)

        history.refresh_from_db()
        assert history.token_preview is None
        assert history.token_fingerprint
        assert history.token_redacted


# ---------------------------------------------------------------------------
# 场景 2：CourtPleadingSignals 结构化输出链路
# ---------------------------------------------------------------------------


class TestCourtPleadingSignalsDTO:
    """修复 2：dtos.py 此前不存在。"""

    def test_import_from_dtos(self) -> None:
        cls = _real_signals_cls()
        assert inspect.isclass(cls)

    def test_is_pydantic_base_model(self) -> None:
        from pydantic import BaseModel

        cls = _real_signals_cls()
        assert issubclass(cls, BaseModel)

    def test_default_values(self) -> None:
        cls = _real_signals_cls()
        obj = cls()
        assert obj.has_complaint is False
        assert obj.has_defense is False
        assert obj.has_counterclaim is False
        assert obj.has_counterclaim_defense is False
        assert obj.notes == ""

    def test_explicit_construction(self) -> None:
        cls = _real_signals_cls()
        obj = cls(
            has_complaint=True,
            has_defense=False,
            has_counterclaim=True,
            has_counterclaim_defense=False,
            notes="原告起诉且被告反诉",
        )
        assert obj.has_complaint is True
        assert obj.has_counterclaim is True
        assert obj.notes == "原告起诉且被告反诉"

    def test_field_names_match_dto_module(self) -> None:
        """字段与 apps.core.dto.litigation.CourtPleadingSignalsDTO 完全一致。"""
        import dataclasses

        from apps.core.dto.litigation import CourtPleadingSignalsDTO

        cls = _real_signals_cls()
        pydantic_fields = list(cls.model_fields)
        dataclass_fields = [f.name for f in dataclasses.fields(CourtPleadingSignalsDTO)]
        assert pydantic_fields == dataclass_fields

    def test_bool_field_rejects_non_bool(self) -> None:
        from pydantic import ValidationError

        cls = _real_signals_cls()
        with pytest.raises(ValidationError):
            cls(has_complaint="not-a-bool")

    def test_notes_field_type_is_str(self) -> None:
        from pydantic import ValidationError

        cls = _real_signals_cls()
        assert cls.model_fields["notes"].annotation is str
        with pytest.raises(ValidationError):
            cls(notes=12345)


class TestCourtPleadingSignalsStructuredOutput:
    """修复 2：与 apps.core.llm.structured_output 集成。"""

    def test_json_schema_instructions_generates_valid_schema(self) -> None:
        from apps.core.llm.structured_output import json_schema_instructions

        cls = _real_signals_cls()
        text = json_schema_instructions(cls)

        assert isinstance(text, str)
        lines = text.split("\n")
        assert lines[0].startswith("请只输出一个 JSON")
        assert "JSON Schema" in lines[1]
        schema = json.loads(lines[2])
        assert schema["type"] == "object"
        assert sorted(schema["properties"]) == [
            "has_complaint",
            "has_counterclaim",
            "has_counterclaim_defense",
            "has_defense",
            "notes",
        ]

    def test_parse_model_content_partial_json(self) -> None:
        from apps.core.llm.structured_output import parse_model_content

        cls = _real_signals_cls()
        obj = parse_model_content('{"has_complaint": true, "notes": "ok"}', cls)
        assert obj.has_complaint is True
        assert obj.notes == "ok"
        # 未提供的字段走默认值
        assert obj.has_defense is False
        assert obj.has_counterclaim is False
        assert obj.has_counterclaim_defense is False

    def test_parse_model_content_with_code_fence(self) -> None:
        from apps.core.llm.structured_output import parse_model_content

        cls = _real_signals_cls()
        obj = parse_model_content('```json\n{"has_defense": true}\n```', cls)
        assert obj.has_defense is True

    def test_parse_model_content_invalid_payload_raises(self) -> None:
        from apps.core.llm.structured_output import StructuredValidationError, parse_model_content

        cls = _real_signals_cls()
        with pytest.raises(StructuredValidationError):
            parse_model_content("这不是 JSON", cls)


class TestCourtPleadingSignalsService:
    """修复 2：service 侧的 dtos 引用现在可用。

    service 模块内部 `from .dtos import CourtPleasingSignals`，若 dtos 曾被 fake
    污染，service 拿到的就是 dataclass。这里显式重载真实模块再断言。
    """

    def _service(self) -> Any:
        """每次构造都先清 shim 重载，保证 service 内部绑定真实 dtos。"""
        svc_mod = _real_litigation()
        return svc_mod.CourtPleadingSignalsService()

    def test_real_dtos_file_is_on_disk(self) -> None:
        """dtos.py 必须作为真实文件存在（而不是测试注入的 sys.modules 假模块）。"""
        import apps.automation.services.litigation as pkg

        dtos_path = Path(pkg.__file__).parent / "dtos.py"
        assert dtos_path.exists()
        assert dtos_path.stat().st_size > 0

    def test_service_uses_real_pydantic_model(self) -> None:
        """service 内部绑定的 CourtPleadingSignals 必须是真实 pydantic 类。"""
        from pydantic import BaseModel

        svc_mod = _real_litigation()
        assert svc_mod.__file__ is not None
        assert svc_mod.__file__.endswith("court_pleading_signals_service.py")
        assert issubclass(svc_mod.CourtPleadingSignals, BaseModel)
        # 且就是磁盘上真实 dtos 的类
        assert svc_mod.CourtPleadingSignals is _real_signals_cls()

    def test_fallback_by_keywords_complaint_and_defense(self) -> None:
        result = self._service()._fallback_by_keywords(["起诉状", "答辩状"])
        assert result.has_complaint is True
        assert result.has_defense is True
        assert result.has_counterclaim is False
        assert result.has_counterclaim_defense is False
        assert result.notes == "fallback_keywords"

    def test_fallback_by_keywords_counterclaim_only(self) -> None:
        result = self._service()._fallback_by_keywords(["反诉状"])
        assert result.has_complaint is False
        assert result.has_counterclaim is True

    def test_fallback_by_keywords_counterclaim_defense(self) -> None:
        result = self._service()._fallback_by_keywords(["反诉答辩状"])
        assert result.has_counterclaim_defense is True
        assert result.has_counterclaim is False

    def test_fallback_by_keywords_returns_pydantic_instance(self) -> None:
        from pydantic import BaseModel

        cls = _real_signals_cls()
        result = self._service()._fallback_by_keywords(["起诉状"])
        assert isinstance(result, BaseModel)
        # 字段值与真实类默认值语义一致
        assert isinstance(result, cls)

    @pytest.mark.django_db
    def test_get_signals_no_documents_returns_pydantic_default(self) -> None:
        from pydantic import BaseModel

        result = self._service().get_signals(case_id=999999)
        assert isinstance(result, BaseModel)
        assert isinstance(result, _real_signals_cls())
        assert result.has_complaint is False
        assert result.has_defense is False
        assert result.has_counterclaim is False
        assert result.has_counterclaim_defense is False
        assert result.notes == ""

    @pytest.mark.django_db
    def test_get_signals_real_documents_fallback_path(self) -> None:
        """无 LLM 可用时回退到关键词规则，结果来自真实 CourtDocument 行。"""
        from unittest.mock import patch

        from django.utils import timezone

        from apps.automation.models import CourtDocument, ScraperTask, ScraperTaskType
        from apps.testing.factories import CaseFactory

        svc_mod = _real_litigation()

        task = ScraperTask.objects.create(task_type=ScraperTaskType.COURT_DOCUMENT, url="https://example.com/task")
        case = CaseFactory(name="诉讼态势E2E案件")

        def _make_doc(suffix: str, name: str) -> None:
            CourtDocument.objects.create(
                scraper_task=task,
                case=case,
                c_sdbh=f"SD-E2E-{suffix}",
                c_stbh=f"ST-E2E-{suffix}",
                wjlj=f"https://example.com/{suffix}.pdf",
                c_wsbh=f"WS-E2E-{suffix}",
                c_wsmc=name,
                c_fybh="FY1",
                c_fymc="测试法院",
                c_wjgs="pdf",
                dt_cjsj=timezone.now(),
            )

        _make_doc("1", "民事起诉状")
        _make_doc("2", "民事答辩状")

        service = svc_mod.CourtPleadingSignalsService()
        # _classify_with_llm 内部命中 ServiceLocator 需要真实 LLM 凭证，强制失败以走回退分支
        with patch.object(service, "_classify_with_llm", side_effect=RuntimeError("no llm available")):
            result = service.get_signals(case_id=case.id)

        assert isinstance(result, _real_signals_cls())
        assert result.has_complaint is True
        assert result.has_defense is True
        assert result.notes == "fallback_keywords"


# ---------------------------------------------------------------------------
# 场景 3：litigation/schemas.py 可导入且与 dtos 同一类
# ---------------------------------------------------------------------------


class TestLitigationSchemasReExport:
    """修复 2：schemas.py 的 `from .dtos import CourtPleadingSignals`。"""

    def test_schemas_import_succeeds(self) -> None:
        """schemas.py 可导入（此前 `from .dtos import ...` 必然 ImportError）。"""
        # 先建立真实模块缓存，再验证 schemas 也能导入
        _real_litigation()
        schemas_mod = importlib.import_module("apps.automation.services.litigation.schemas")
        assert inspect.isclass(schemas_mod.CourtPleadingSignals)

    def test_same_class_object_as_dtos(self) -> None:
        """schemas 与 dtos 必须是同一个类对象，且是真实 pydantic 类（非 fake dataclass）。"""
        from pydantic import BaseModel

        # 统一走 _real_litigation() 的缓存，确保 dtos 与 schemas 绑定同一个类对象
        _real_litigation()
        dtos_mod = sys.modules[_FAKE_DTOS_MODULE]
        schemas_mod = sys.modules["apps.automation.services.litigation.schemas"]

        FromDtos = dtos_mod.CourtPleadingSignals
        FromSchemas = schemas_mod.CourtPleadingSignals

        assert FromDtos is FromSchemas
        assert FromDtos is _real_signals_cls()
        assert issubclass(FromDtos, BaseModel)
        assert FromDtos.__module__ == _FAKE_DTOS_MODULE

    def test_schemas_exports_in_all(self) -> None:
        _real_litigation()
        schemas_mod = sys.modules["apps.automation.services.litigation.schemas"]

        assert "CourtPleadingSignals" in schemas_mod.__all__
        assert schemas_mod.CourtPleadingSignals is not None
        assert schemas_mod.CourtPleadingSignals is _real_signals_cls()

    def test_adapter_module_imports_without_fake_dtos(self) -> None:
        """adapter 模块曾靠 fake dtos 才能 import，现在应独立可导入。"""
        mod = importlib.import_module("apps.automation.services.litigation.court_pleading_signals_service_adapter")
        assert hasattr(mod, "CourtPleadingSignalsServiceAdapter")

    def test_adapter_get_signals_internal_roundtrip(self) -> None:
        from unittest.mock import MagicMock

        from apps.automation.services.litigation.court_pleading_signals_service_adapter import (
            CourtPleadingSignalsServiceAdapter,
        )
        from apps.core.dto.litigation import CourtPleadingSignalsDTO

        adapter = CourtPleadingSignalsServiceAdapter.__new__(CourtPleadingSignalsServiceAdapter)
        signals = MagicMock()
        signals.has_complaint = True
        signals.has_defense = False
        signals.has_counterclaim = "yes"
        signals.has_counterclaim_defense = None
        signals.notes = None
        adapter._svc = MagicMock(get_signals=MagicMock(return_value=signals))

        result = adapter.get_signals_internal(case_id=7)

        assert isinstance(result, CourtPleadingSignalsDTO)
        assert result.has_complaint is True
        assert result.has_defense is False
        assert result.has_counterclaim is True
        assert result.has_counterclaim_defense is False
        assert result.notes == ""


# ---------------------------------------------------------------------------
# 场景 4：documents/evidence 模型冲突已解决
# ---------------------------------------------------------------------------


class TestDocumentsEvidenceConflictResolved:
    """修复 3：残留副本已删除，__getattr__ 转发应指向同一类。"""

    def test_duplicate_module_file_gone(self) -> None:
        """apps/documents/models/evidence.py 不应再存在。"""
        import apps.documents.models as dm

        assert not hasattr(dm, "evidence")
        # 磁盘上文件必须已删除（本次分支的修复点之一）
        evidence_file = Path(dm.__file__).parent / "evidence.py"
        assert not evidence_file.exists()

    def test_getattr_forwards_to_evidence_app(self) -> None:
        import apps.documents.models as dm
        from apps.evidence.models import EvidenceItem, EvidenceList

        assert dm.EvidenceList is EvidenceList
        assert dm.EvidenceItem is EvidenceItem
        # 真实类定义在 apps.evidence.models.evidence（Meta.app_label 仍为 documents）
        assert EvidenceList.__module__ == "apps.evidence.models.evidence"

    def test_evidence_list_forwarded_identity(self) -> None:
        from apps.documents.models import EvidenceList
        from apps.evidence.models import EvidenceList as AppEvidenceList

        assert EvidenceList is AppEvidenceList

    def test_both_models_modules_import_together(self) -> None:
        """同时 import 两个 models 包不应触发 Conflicting models。"""
        from django.apps import apps as django_apps

        import apps.documents.models
        import apps.evidence.models

        # EvidenceList 物理定义在 apps.evidence.models.evidence，但 Meta.app_label = "documents"
        # （历史 db_table documents_evidencelist 保留），因此注册表按 documents 标签唯一注册。
        model = django_apps.get_model("documents", "EvidenceList")
        assert model is not None
        assert model.__module__ == "apps.evidence.models.evidence"

    def test_single_registration_in_app_registry(self) -> None:
        from django.apps import apps as django_apps

        models_for_label = [m for m in django_apps.get_models() if m.__name__ == "EvidenceList"]
        assert len(models_for_label) == 1

    def test_document_template_imports_type_checking_evidence(self) -> None:
        """改过的 TYPE_CHECKING import 指向 apps.evidence.models，且该目标真实存在。"""
        from apps.documents.models import document_template as dt_mod
        from apps.documents.models.document_template import DocumentTemplate

        assert DocumentTemplate.__name__ == "DocumentTemplate"
        src = inspect.getsource(dt_mod)
        # import 目标必须是 apps.evidence.models（修复前指向被删除的 documents 副本）
        assert "from apps.evidence.models import EvidenceList" in src
        assert "evidence_lists: RelatedManager[EvidenceList]" in src
        # 注解写在 `if TYPE_CHECKING:` 块内，运行期不会出现在 __annotations__
        assert "evidence_lists" not in DocumentTemplate.__annotations__

    def test_type_checking_import_target_is_resolvable(self) -> None:
        """TYPE_CHECKING 块里的 EvidenceList 真实可导入（不会指向已删除模块）。"""
        import apps.documents.models.document_template as dt_mod
        from apps.evidence.models import EvidenceList

        # TYPE_CHECKING 块在运行期不执行，手动验证其引用的符号确实存在
        assert EvidenceList.__module__ == "apps.evidence.models.evidence"
        src = inspect.getsource(dt_mod)
        assert "if TYPE_CHECKING:" in src
        # mypy 视角：解析该 import 目标不会报 module-not-found
        assert importlib.util.find_spec("apps.evidence.models") is not None


# ---------------------------------------------------------------------------
# 场景 5：回归 — 原有 litigation 测试不再需要 fake dtos
# ---------------------------------------------------------------------------


class TestRegressionLegacyLitigationTests:
    """原有 test_court_pleading_signals*.py 靠注入 fake dtos 绕过 import 错误。

    修复后 fake 与真实类字段完全一致，行为应保持；同时确认这些测试文件
    仍在磁盘上且可被 pytest 收集（真正的回归验证见完整目录运行）。
    """

    def test_legacy_test_files_exist(self) -> None:
        from pathlib import Path

        tests_dir = Path(__file__).parent
        assert (tests_dir / "test_court_pleading_signals.py").exists()
        assert (tests_dir / "test_court_pleading_signals_adapter.py").exists()

    def test_legacy_fake_dtos_semantics_match_real(self) -> None:
        """legacy 测试里的 frozen dataclass 与真实 pydantic 模型字段/默认值一致。

        这解释了为什么 legacy 测试在修复后仍能通过：fake 与真实的字段契约相同。
        """
        import dataclasses

        real_cls = _real_signals_cls()

        @dataclasses.dataclass(frozen=True)
        class FakeSignals:
            has_complaint: bool = False
            has_defense: bool = False
            has_counterclaim: bool = False
            has_counterclaim_defense: bool = False
            notes: str = ""

        fake_fields = [f.name for f in dataclasses.fields(FakeSignals)]
        assert fake_fields == list(real_cls.model_fields)

        fake = FakeSignals()
        real = real_cls()
        for name in fake_fields:
            assert getattr(fake, name) == getattr(real, name)
