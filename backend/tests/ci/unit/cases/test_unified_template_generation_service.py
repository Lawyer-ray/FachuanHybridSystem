"""UnifiedTemplateGenerationService 单元测试。

覆盖参数校验、协作者编排（resolver/party_selection/context/renderer/filename）、
模板信息查询与案件缺失报错。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.template.unified.party_selection import SelectedParties
from apps.cases.services.template.unified_template_generation_service import UnifiedTemplateGenerationService
from apps.core.exceptions import NotFoundError, ValidationException


def _make_service(
    *, resolved_code: str | None = "plain", selected: SelectedParties | None = None
) -> tuple[UnifiedTemplateGenerationService, dict[str, MagicMock]]:
    resolver = MagicMock()
    resolver.resolve.return_value = SimpleNamespace(
        template=SimpleNamespace(id=11, name="委托书模板"),
        template_path="/templates/poa.docx",
        effective_function_code=resolved_code,
    )
    party_repo = MagicMock()
    party_repo.count_our_parties.return_value = 1
    party_selection = MagicMock()
    party_selection.select.return_value = selected or SelectedParties(client=None, clients=None)
    context_builder = MagicMock()
    context_builder.build.return_value = {"k": "v"}
    renderer = MagicMock()
    renderer.render.return_value = b"docx-bytes"
    filename_policy = MagicMock()
    filename_policy.build.return_value = "委托书模板（案件）V1_20261005.docx"

    service = UnifiedTemplateGenerationService(
        template_lookup_service=resolver,
        resolver=resolver,
        party_selection_policy=party_selection,
        context_builder=context_builder,
        renderer=renderer,
        filename_policy=filename_policy,
        party_repo=party_repo,
    )
    collaborators = {
        "resolver": resolver,
        "party_repo": party_repo,
        "party_selection": party_selection,
        "context_builder": context_builder,
        "renderer": renderer,
        "filename_policy": filename_policy,
    }
    return service, collaborators


class TestInitDefaults:
    def test_default_collaborators_created(self) -> None:
        service = UnifiedTemplateGenerationService()
        assert service._party_repo is not None
        assert service._resolver is not None
        assert service._party_selection_policy is not None
        assert service._context_builder is not None
        assert service._renderer is not None
        assert service._filename_policy is not None


class TestGenerateDocument:
    def test_missing_both_params_raises(self) -> None:
        service, _ = _make_service()
        with pytest.raises(ValidationException) as exc_info:
            service.generate_document(case_id=1)
        assert exc_info.value.code == "INVALID_PARAMS"

    def test_happy_path_orchestration(self) -> None:
        service, parts = _make_service()
        case = SimpleNamespace(id=1, name="测试案件")

        with patch(
            "apps.cases.services.template.unified_template_generation_service.get_case_service"
        ) as mock_get_case_service:
            mock_get_case_service.return_value.get_case_model_internal.return_value = case
            content, filename = service.generate_document(case_id=1, template_id=11, client_id=101, mode="individual")

        assert content == b"docx-bytes"
        assert filename == "委托书模板（案件）V1_20261005.docx"

        parts["resolver"].resolve.assert_called_once_with(template_id=11, function_code=None)
        select_kwargs = parts["party_selection"].select.call_args.kwargs
        assert select_kwargs["case"] is case
        assert select_kwargs["function_code"] == "plain"
        assert select_kwargs["client_id"] == 101
        assert select_kwargs["mode"] == "individual"
        assert select_kwargs["legal_rep_cert_code"] == UnifiedTemplateGenerationService.LEGAL_REP_CERT_CODE
        assert select_kwargs["power_of_attorney_code"] == UnifiedTemplateGenerationService.POWER_OF_ATTORNEY_CODE
        parts["context_builder"].build.assert_called_once_with(case=case, client=None, clients=None)
        parts["renderer"].render.assert_called_once_with(template_path="/templates/poa.docx", context={"k": "v"})
        build_kwargs = parts["filename_policy"].build.call_args.kwargs
        assert build_kwargs["inputs"].template_name == "委托书模板"
        assert build_kwargs["inputs"].case_name == "测试案件"
        assert build_kwargs["inputs"].our_party_count == 1

    def test_case_missing_raises_not_found(self) -> None:
        service, _ = _make_service()
        with patch(
            "apps.cases.services.template.unified_template_generation_service.get_case_service"
        ) as mock_get_case_service:
            mock_get_case_service.return_value.get_case_model_internal.return_value = None
            with pytest.raises(NotFoundError) as exc_info:
                service.generate_document(case_id=99, function_code="power_of_attorney")
        assert exc_info.value.code == "CASE_NOT_FOUND"

    def test_client_name_used_in_filename_inputs(self) -> None:
        client = SimpleNamespace(id=101, name="甲公司")
        service, parts = _make_service(selected=SelectedParties(client=client, clients=None))
        case = SimpleNamespace(id=1, name="测试案件")

        with patch(
            "apps.cases.services.template.unified_template_generation_service.get_case_service"
        ) as mock_get_case_service:
            mock_get_case_service.return_value.get_case_model_internal.return_value = case
            service.generate_document(case_id=1, function_code="power_of_attorney", client_id=101)

        build_kwargs = parts["filename_policy"].build.call_args.kwargs
        assert build_kwargs["inputs"].client_name == "甲公司"

    def test_function_code_passthrough(self) -> None:
        service, parts = _make_service()
        case = SimpleNamespace(id=1, name="测试案件")

        with patch(
            "apps.cases.services.template.unified_template_generation_service.get_case_service"
        ) as mock_get_case_service:
            mock_get_case_service.return_value.get_case_model_internal.return_value = case
            service.generate_document(case_id=1, function_code="legal_rep_certificate")

        parts["resolver"].resolve.assert_called_once_with(template_id=None, function_code="legal_rep_certificate")


class TestGetTemplateInfo:
    def test_missing_params_raises(self) -> None:
        service, _ = _make_service()
        with pytest.raises(ValidationException) as exc_info:
            service.get_template_info()
        assert exc_info.value.code == "INVALID_PARAMS"

    def test_delegates_to_resolver(self) -> None:
        service, parts = _make_service()
        parts["resolver"].get_template_info.return_value = {"id": 11, "name": "模板"}

        result = service.get_template_info(template_id=11)
        assert result == {"id": 11, "name": "模板"}
        parts["resolver"].get_template_info.assert_called_once_with(template_id=11, function_code=None)

    def test_delegates_by_function_code(self) -> None:
        service, parts = _make_service()
        parts["resolver"].get_template_info.return_value = {"id": 12}

        result = service.get_template_info(function_code="power_of_attorney")
        assert result == {"id": 12}
        parts["resolver"].get_template_info.assert_called_once_with(template_id=None, function_code="power_of_attorney")
