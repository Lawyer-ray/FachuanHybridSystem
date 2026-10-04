"""supplementary_agreement_generation_service.py 补覆盖测试。

用替身合同服务覆盖生成主流程的各失败/成功分支、文件名生成、
上下文构建与绑定文件夹保存。渲染器与模板匹配器全部 mock，不读真实 docx。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.documents.services.generation.supplementary_agreement_generation_service import (
    SupplementaryAgreementGenerationService,
)

PIPELINE = "apps.documents.services.generation.pipeline"
WIRING = "apps.documents.services.infrastructure.wiring"
_UNSET = object()


_DEFAULT_DETAILS: dict = {"id": 1, "name": "王小三案件", "case_type": "civil"}


def _contract_service(
    *,
    details: object = _UNSET,
    contract: object = _UNSET,
    agreement: object = _UNSET,
) -> MagicMock:
    svc = MagicMock()
    svc.get_contract_with_details_internal.return_value = _DEFAULT_DETAILS if details is _UNSET else details
    # MagicMock 支持迭代（默认空），build_context 内的 parties/contract_parties 过滤可用
    svc.get_contract_model_internal.return_value = MagicMock() if contract is _UNSET else contract
    svc.get_supplementary_agreement_model_internal.return_value = MagicMock() if agreement is _UNSET else agreement
    return svc


def _template(location: str = "/tmp/tpl.docx") -> MagicMock:
    tpl = MagicMock()
    tpl.get_file_location.return_value = location
    return tpl


def _agreement(name: str = "补充协议一") -> SimpleNamespace:
    return SimpleNamespace(name=name, id=11)


def _contract(name: str = "王小三案件") -> SimpleNamespace:
    return SimpleNamespace(name=name, id=1)


class TestLazyProperties:
    def test_contract_service_lazy_load(self):
        sentinel = MagicMock()
        with patch(f"{WIRING}.get_contract_service", return_value=sentinel):
            svc = SupplementaryAgreementGenerationService()
            assert svc.contract_service is sentinel
            assert svc.contract_service is sentinel  # 二次访问不重复加载

    def test_folder_binding_service_passthrough(self):
        fbs = MagicMock()
        svc = SupplementaryAgreementGenerationService(folder_binding_service=fbs)
        assert svc.folder_binding_service is fbs


class TestGenerateSupplementaryAgreement:
    def test_contract_details_missing(self):
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service(details=None))
        content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error == "合同不存在"

    def test_contract_model_missing(self):
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service(contract=None))
        content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error == "合同不存在"

    def test_agreement_missing(self):
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service(agreement=None))
        content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error == "补充协议不存在"

    def test_template_missing(self):
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service())
        with patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher:
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = None
            content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error == "请先添加补充协议模板"

    def test_template_file_missing(self, tmp_path):
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service())
        with patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher:
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = _template(
                str(tmp_path / "not_exist.docx")
            )
            content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error == "模板文件不存在"

    def test_template_no_location(self):
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service())
        with patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher:
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = _template("")
            content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error == "模板文件不存在"

    def test_render_failure_returns_error(self, tmp_path):
        tpl_file = tmp_path / "tpl.docx"
        tpl_file.write_bytes(b"docx")
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service())
        with (
            patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher,
            patch(f"{PIPELINE}.DocxRenderer") as mock_renderer,
        ):
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = _template(str(tpl_file))
            mock_renderer.return_value.render.side_effect = ValueError("render boom")
            content, filename, error = svc.generate_supplementary_agreement(1, 11)
        assert (content, filename) == (None, None)
        assert error is not None and error.startswith("生成补充协议失败")

    def test_success_returns_content_and_filename(self, tmp_path):
        tpl_file = tmp_path / "tpl.docx"
        tpl_file.write_bytes(b"docx")
        fbs = MagicMock()
        fbs.save_file_for_contract.return_value = "saved/path.docx"
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service(), folder_binding_service=fbs)
        with (
            patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher,
            patch(f"{PIPELINE}.DocxRenderer") as mock_renderer,
            patch.object(svc, "generate_filename", return_value="补充协议一（王小三案件）V1_20260102.docx") as mock_fn,
        ):
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = _template(str(tpl_file))
            mock_renderer.return_value.render.return_value = b"rendered"
            content, filename, error = svc.generate_supplementary_agreement(1, 11)

        assert error is None
        assert content == b"rendered"
        assert filename == "补充协议一（王小三案件）V1_20260102.docx"
        mock_fn.assert_called_once()
        assert svc._last_saved_path == "saved/path.docx"

    def test_result_variant_wraps_output(self, tmp_path):
        tpl_file = tmp_path / "tpl.docx"
        tpl_file.write_bytes(b"docx")
        svc = SupplementaryAgreementGenerationService(contract_service=_contract_service())
        with (
            patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher,
            patch(f"{PIPELINE}.DocxRenderer") as mock_renderer,
            patch.object(svc, "generate_filename", return_value="f.docx"),
        ):
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = _template(str(tpl_file))
            mock_renderer.return_value.render.return_value = b"rendered"
            content, filename, saved_path, error = svc.generate_supplementary_agreement_result(1, 11)

        assert content == b"rendered"
        assert filename == "f.docx"
        assert error is None
        assert saved_path is None  # 未注入 folder_binding_service


class TestFindSupplementaryAgreementTemplate:
    def test_matcher_invoked_then_cast_raises(self):
        """疑似缺陷：cast("DocumentTemplate" | None, ...) 在运行期求值 str | None 抛 TypeError。

        首参表达式在 TemplateMatcher() 之前求值，导致方法必然抛错且匹配器不会执行。
        此处只锁定现状，不改产品代码；修复后应改为断言返回模板本身。
        """
        import pytest

        svc = SupplementaryAgreementGenerationService(contract_service=MagicMock())
        tpl = _template()
        with patch(f"{PIPELINE}.TemplateMatcher") as mock_matcher:
            mock_matcher.return_value.match_supplementary_agreement_template.return_value = tpl
            with pytest.raises(TypeError):
                svc.find_supplementary_agreement_template("civil")
            mock_matcher.return_value.match_supplementary_agreement_template.assert_not_called()


class TestBuildContext:
    def test_delegates_to_pipeline_builder(self):
        svc = SupplementaryAgreementGenerationService(contract_service=MagicMock())
        contract, agreement = MagicMock(), MagicMock()
        expected = {"补充协议名称": "补充协议一"}
        with patch(f"{PIPELINE}.PipelineContextBuilder") as mock_builder:
            mock_builder.return_value.build_supplementary_agreement_context.return_value = expected
            result = svc.build_context(contract, agreement)

        assert result is expected
        kwargs = mock_builder.return_value.build_supplementary_agreement_context.call_args.kwargs
        assert kwargs["contract"] is contract
        assert kwargs["supplementary_agreement"] is agreement
        assert kwargs["agreement_principals"] == []
        assert kwargs["contract_principals"] == []
        assert kwargs["agreement_opposing"] == []


class TestGenerateFilename:
    def test_uses_defaults_for_missing_names(self, tmp_path):
        from apps.core.services.filename_template_service import GENERATED_DOC_DEFAULT, FilenameTemplateService

        svc = SupplementaryAgreementGenerationService()
        agreement = SimpleNamespace(name=None, id=1)
        contract = SimpleNamespace(name=None, id=1)
        with patch.object(FilenameTemplateService, "get_template", return_value=GENERATED_DOC_DEFAULT):
            filename = svc.generate_filename(contract, agreement, contract_id=1)
        assert "补充协议" in filename
        assert "未命名合同" in filename
        assert filename.endswith(".docx")

    def test_contains_names_and_version(self, tmp_path):
        from apps.core.services.filename_template_service import GENERATED_DOC_DEFAULT, FilenameTemplateService

        fbs, _subdir = _make_binding_service(tmp_path)
        svc = SupplementaryAgreementGenerationService(folder_binding_service=fbs)
        with patch.object(FilenameTemplateService, "get_template", return_value=GENERATED_DOC_DEFAULT):
            filename = svc.generate_filename(_contract(), _agreement(), contract_id=1)
        assert "补充协议一" in filename
        assert "王小三案件" in filename
        assert "V1_" in filename
        assert filename.endswith(".docx")


def _make_binding_service(tmp_path) -> tuple[MagicMock, object]:
    """构造本地存储的 folder_binding_service 替身（子目录固定 subdir）。"""
    binding = MagicMock()
    binding.folder_path = str(tmp_path)
    binding.storage_type = "local"
    fbs = MagicMock()
    fbs.get_binding_for_contract.return_value = binding
    fbs._resolve_subdir_path.return_value = "subdir"
    subdir = tmp_path / "subdir"
    subdir.mkdir(exist_ok=True)
    return fbs, subdir


class TestPrincipalCollectors:
    def test_agreement_principals(self):
        svc = SupplementaryAgreementGenerationService(contract_service=MagicMock())
        client_a, client_b = object(), object()
        p1 = SimpleNamespace(client=client_a)
        p2 = SimpleNamespace(client=client_b)
        agreement = MagicMock()
        agreement.parties.filter.return_value = [p1, p2]
        assert svc._get_agreement_principals(agreement) == [client_a, client_b]
        agreement.parties.filter.assert_called_once_with(role="PRINCIPAL")

    def test_contract_principals(self):
        svc = SupplementaryAgreementGenerationService(contract_service=MagicMock())
        client = object()
        party = SimpleNamespace(client=client)
        contract = MagicMock()
        contract.contract_parties.filter.return_value = [party]
        assert svc._get_contract_principals(contract) == [client]
        contract.contract_parties.filter.assert_called_once_with(role="PRINCIPAL")

    def test_agreement_opposing(self):
        svc = SupplementaryAgreementGenerationService(contract_service=MagicMock())
        client = object()
        party = SimpleNamespace(client=client)
        agreement = MagicMock()
        agreement.parties.filter.return_value = [party]
        assert svc._get_agreement_opposing(agreement) == [client]
        agreement.parties.filter.assert_called_once_with(role="OPPOSING")


class TestSaveToBoundFolder:
    def test_no_service_returns_none(self):
        svc = SupplementaryAgreementGenerationService()
        assert svc._save_to_bound_folder_if_exists(1, b"data", "f.docx", "sub") is None

    def test_success_returns_path(self):
        fbs = MagicMock()
        fbs.save_file_for_contract.return_value = "bound/f.docx"
        svc = SupplementaryAgreementGenerationService(folder_binding_service=fbs)
        result = svc._save_to_bound_folder_if_exists(1, b"data", "f.docx", "sub")
        assert result == "bound/f.docx"
        fbs.save_file_for_contract.assert_called_once_with(
            contract_id=1, file_content=b"data", file_name="f.docx", subdir_key="sub"
        )

    def test_save_returns_none_path(self):
        fbs = MagicMock()
        fbs.save_file_for_contract.return_value = None
        svc = SupplementaryAgreementGenerationService(folder_binding_service=fbs)
        assert svc._save_to_bound_folder_if_exists(1, b"data", "f.docx", "sub") is None

    def test_save_error_returns_none(self):
        fbs = MagicMock()
        fbs.save_file_for_contract.side_effect = OSError("disk full")
        svc = SupplementaryAgreementGenerationService(folder_binding_service=fbs)
        assert svc._save_to_bound_folder_if_exists(1, b"data", "f.docx", "sub") is None
