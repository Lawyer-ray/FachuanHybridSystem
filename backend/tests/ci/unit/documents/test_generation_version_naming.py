"""生成文档版本号探测测试。

背景：文件名模板（FilenameTemplateService）默认产出全角括号「（）」，而补充协议服务的
旧探测正则用半角括号，max_version 恒 0 导致同日重生成永远 V1、云存储覆盖旧文件。
现已收敛为 pipeline/naming.find_max_doc_version 共享 helper（全角/半角均兼容）。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from apps.core.services.filename_template_service import GENERATED_DOC_DEFAULT, FilenameTemplateService
from apps.documents.services.generation.contract_generation_service import ContractGenerationService
from apps.documents.services.generation.pipeline.naming import (
    contract_docx_filename,
    find_max_doc_version,
    supplementary_agreement_docx_filename,
)
from apps.documents.services.generation.supplementary_agreement_generation_service import (
    SupplementaryAgreementGenerationService,
)

_TODAY = date.today().strftime("%Y%m%d")


def _render_default_template():
    """文件名模板默认值（免 DB 读取，与 FilenameTemplateService 缺省行为一致）。"""
    return patch.object(FilenameTemplateService, "get_template", return_value=GENERATED_DOC_DEFAULT)


def _make_binding_service(tmp_path, get_method: str):
    """构造本地存储的 folder_binding_service 替身，子目录固定 supplementary_agreements。"""
    binding = MagicMock()
    binding.folder_path = str(tmp_path)
    binding.storage_type = "local"
    fbs = MagicMock()
    getattr(fbs, get_method).return_value = binding
    fbs._resolve_subdir_path.return_value = "subdir"
    subdir = tmp_path / "subdir"
    subdir.mkdir(exist_ok=True)
    return fbs, subdir


class TestFindMaxDocVersion:
    """共享 helper：全角/半角括号都能解析出版本号"""

    def test_fullwidth_parens(self):
        names = [f"补充协议一（王小三案件）V1_{_TODAY}.docx"]
        assert (
            find_max_doc_version(names=names, doc_type="补充协议一", case_name="王小三案件", date_str=_TODAY) == 1
        )

    def test_halfwidth_parens(self):
        names = [f"补充协议一(王小三案件)V1_{_TODAY}.docx"]
        assert (
            find_max_doc_version(names=names, doc_type="补充协议一", case_name="王小三案件", date_str=_TODAY) == 1
        )

    def test_returns_max_version(self):
        names = [
            f"补充协议一（王小三案件）V1_{_TODAY}.docx",
            f"补充协议一（王小三案件）V3_{_TODAY}.docx",
            f"补充协议一（王小三案件）V2_{_TODAY}.docx",
        ]
        assert (
            find_max_doc_version(names=names, doc_type="补充协议一", case_name="王小三案件", date_str=_TODAY) == 3
        )

    def test_no_match_returns_zero(self):
        names = [f"其他协议（别的案件）V5_{_TODAY}.docx", "readme.txt"]
        assert (
            find_max_doc_version(names=names, doc_type="补充协议一", case_name="王小三案件", date_str=_TODAY) == 0
        )

    def test_different_date_not_counted(self):
        names = ["补充协议一（王小三案件）V9_19990101.docx"]
        assert (
            find_max_doc_version(names=names, doc_type="补充协议一", case_name="王小三案件", date_str=_TODAY) == 0
        )

    def test_mixed_parens_within_one_name(self):
        """模板渲染或手工改名可能产出半开全闭等混合形态，也应兼容。"""
        names = [f"补充协议一(王小三案件）V2_{_TODAY}.docx"]
        assert (
            find_max_doc_version(names=names, doc_type="补充协议一", case_name="王小三案件", date_str=_TODAY) == 2
        )


class TestSupplementaryAgreementNextVersion:
    """补充协议 _get_next_version：文件名模板产出的全角括号必须能被探测到"""

    def _svc(self, tmp_path):
        fbs, _subdir = _make_binding_service(tmp_path, "get_binding_for_contract")
        return SupplementaryAgreementGenerationService(folder_binding_service=fbs)

    def test_empty_folder_returns_v1(self, tmp_path):
        svc = self._svc(tmp_path)
        assert svc._get_next_version(1, "补充协议一", "王小三案件", "supplementary_agreements") == "V1"

    def test_existing_fullwidth_v1_yields_v2(self, tmp_path):
        """文件名模板默认产出全角「（）」：已有 V1 时再次生成必须得 V2（不再覆盖）。"""
        svc = self._svc(tmp_path)
        # 按真实产出链路生成文件名并落盘，保证括号形态与产线一致
        with _render_default_template():
            filename = supplementary_agreement_docx_filename(
                agreement_name="补充协议一", contract_name="王小三案件", version="V1"
            )
        assert "（" in filename  # 模板默认全角
        (tmp_path / "subdir" / filename).write_bytes(b"docx")

        assert svc._get_next_version(1, "补充协议一", "王小三案件", "supplementary_agreements") == "V2"

    def test_existing_halfwidth_v1_yields_v2(self, tmp_path):
        """历史/手工命名的半角括号文件同样要被识别。"""
        svc = self._svc(tmp_path)
        (tmp_path / "subdir" / f"补充协议一(王小三案件)V1_{_TODAY}.docx").write_bytes(b"docx")

        assert svc._get_next_version(1, "补充协议一", "王小三案件", "supplementary_agreements") == "V2"

    def test_no_binding_service_returns_v1(self):
        svc = SupplementaryAgreementGenerationService()
        assert svc._get_next_version(1, "补充协议一", "王小三案件", "supplementary_agreements") == "V1"


class TestContractGenerationNextVersion:
    """合同生成 _get_next_version 收敛到同一 helper 后仍正确（全角主路径 + 半角兜底）"""

    def _svc(self, tmp_path):
        fbs, _subdir = _make_binding_service(tmp_path, "get_binding")
        return ContractGenerationService(folder_binding_service=fbs)

    def test_existing_fullwidth_v1_yields_v2(self, tmp_path):
        svc = self._svc(tmp_path)
        with _render_default_template():
            filename = contract_docx_filename(template_name="聘请合同", contract_name="王小三案件", version="V1")
        assert "（" in filename
        (tmp_path / "subdir" / filename).write_bytes(b"docx")

        assert svc._get_next_version(1, "聘请合同", "王小三案件", "contract_documents") == "V2"

    def test_existing_halfwidth_v1_yields_v2(self, tmp_path):
        svc = self._svc(tmp_path)
        (tmp_path / "subdir" / f"聘请合同(王小三案件)V1_{_TODAY}.docx").write_bytes(b"docx")

        assert svc._get_next_version(1, "聘请合同", "王小三案件", "contract_documents") == "V2"
