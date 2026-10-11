"""oa_filing 立案合同附件：上传契约解析 / 表单注入 / 来源解析 / 暂存 单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE = "apps.oa_filing.services.filing_attachment_service"


# ── LegalUp 上传响应解析 ───────────────────────────────────────────


class TestParseLegalupResponse:
    def _parse(self, text: str, filename: str = "合同.pdf"):
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import parse_legalup_response

        return parse_legalup_response(text, filename=filename)

    def test_success(self):
        result = self._parse('{"state":"SUCCESS","url":"/legalup/projectfiles/2026/a.pdf","original":"合同.pdf"}')
        assert result == {"original": "合同.pdf", "url": "/legalup/projectfiles/2026/a.pdf"}

    def test_original_missing_falls_back_to_filename(self):
        result = self._parse('{"state":"SUCCESS","url":"/u/a.pdf"}', filename="合同V2.pdf")
        assert result["original"] == "合同V2.pdf"

    def test_state_failure_raises(self):
        with pytest.raises(RuntimeError, match="state=ERROR"):
            self._parse('{"state":"ERROR"}')

    def test_missing_url_raises(self):
        with pytest.raises(RuntimeError, match="上传失败"):
            self._parse('{"state":"SUCCESS"}')

    def test_non_json_raises(self):
        with pytest.raises(RuntimeError, match="非 JSON"):
            self._parse("<html>error</html>")


# ── 隐藏域注入 ─────────────────────────────────────────────────────


class TestApplyAttachmentPayload:
    def test_injects_paired_hidden_fields(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import apply_attachment_payload

        payload: dict[str, str] = {}
        uploads = [
            {"original": "合同.pdf", "url": "/u/1.pdf"},
            {"original": "合同.docx", "url": "/u/2.docx"},
        ]
        apply_attachment_payload(payload, uploads)
        name_fields = {k: v for k, v in payload.items() if k.startswith("filenamecontract_")}
        url_fields = {k: v for k, v in payload.items() if k.startswith("fileurlcontract_")}
        assert len(name_fields) == 2 and len(url_fields) == 2
        # 字段名前缀后的 guid 一一对应
        assert {k.removeprefix("filenamecontract_") for k in name_fields} == {
            k.removeprefix("fileurlcontract_") for k in url_fields
        }
        assert set(name_fields.values()) == {"合同.pdf", "合同.docx"}
        assert set(url_fields.values()) == {"/u/1.pdf", "/u/2.docx"}


# ── 上传 URL 构建 ──────────────────────────────────────────────────


class TestLegalupUploadUrl:
    def test_contains_required_params(self):
        from apps.oa_filing.services.oa_scripts.jtn.filing.http_filing import legalup_upload_url

        url = legalup_upload_url()
        assert "LegalUp.ashx" in url
        for param in ("action=uploadfile", "path=projectfiles", "encode=utf-8"):
            assert param in url


# ── 文件挑选：pdf 优先 / 同名多版本最新 ────────────────────────────


class TestPickLatestContractFile:
    def _make(self, path: str, mtime: float):
        return {"path": Path(path), "mtime": mtime, "stem_key": Path(path).stem.lower()}

    def test_empty_returns_none(self):
        from apps.oa_filing.services.filing_attachment_service import _pick_latest_contract_file

        assert _pick_latest_contract_file([]) is None

    def test_pdf_wins_over_newer_docx(self):
        from apps.oa_filing.services.filing_attachment_service import _pick_latest_contract_file

        candidates = [self._make("/tmp/合同.pdf", mtime=100.0), self._make("/tmp/其他合同.docx", mtime=999.0)]
        winner = _pick_latest_contract_file(candidates)
        assert winner["path"].name == "合同.pdf"

    def test_same_stem_latest_mtime_wins(self):
        from apps.oa_filing.services.filing_attachment_service import _pick_latest_contract_file

        candidates = [
            {**self._make("/tmp/合同 V1.pdf", mtime=100.0), "stem_key": "合同 v1"},
            {**self._make("/tmp/合同 V1.pdf", mtime=200.0), "stem_key": "合同 v1"},
        ]
        assert _pick_latest_contract_file(candidates)["mtime"] == 200.0

    def test_among_pdfs_latest_wins(self):
        from apps.oa_filing.services.filing_attachment_service import _pick_latest_contract_file

        candidates = [self._make("/tmp/a.pdf", mtime=100.0), self._make("/tmp/b.pdf", mtime=300.0)]
        assert _pick_latest_contract_file(candidates)["path"].name == "b.pdf"


# ── 合同正本判定（真实分类器） ─────────────────────────────────────


class TestIsContractOriginal:
    def _is(self, filename: str, source_path: str) -> bool:
        from apps.oa_filing.services.filing_attachment_service import _is_contract_original

        return _is_contract_original(filename, source_path)

    def test_contract_in_contract_folder(self):
        # 373 真实形态：文件名内嵌案由「借款合同纠纷」，但位于 1-合同 文件夹段
        assert self._is(
            "1-民商事合同（某某公司借款合同纠纷一案）V1_20261009.docx",
            "/tmp/root/1-律师资料/1-合同/1-民商事合同（某某公司借款合同纠纷一案）V1_20261009.docx",
        )

    def test_license_in_case_name_folder_excluded(self):
        # 373 实测 bug 回归：案由目录名含"合同"，整路径子串匹配曾把执业证误判进合同区
        assert not self._is(
            "黄崧_执业证.pdf",
            "/tmp/root/2026.10.09-[民商事]某某公司借款合同纠纷一案/3-执行/1-立案材料/3-委托材料/黄崧_执业证.pdf",
        )

    def test_non_contract_document_in_case_name_folder_excluded(self):
        assert not self._is(
            "6-通过媒体公布不履行义务信息的申请书（某某买卖合同纠纷一案）V1.docx",
            "/tmp/root/2026.10.09-[民商事]某某买卖合同纠纷一案/3-执行/1-立案材料/4-限制性措施/6-申请书.docx",
        )

    def test_plain_contract_filename_in_contract_folder(self):
        assert self._is("专项法律事务服务合同（张三）_20260424盖章.pdf", "/tmp/root/1-合同/xxx.pdf")

    def test_payment_note_in_contract_folder_excluded(self):
        # 342 真实形态：代付款情况说明躺在 1-合同 下，但文件名无 合同/协议
        assert not self._is("代付款情况说明(某案件)V2_20260623.pdf", "/tmp/root/1-合同/代付款情况说明.pdf")

    def test_invoice_in_contract_folder_excluded(self):
        assert not self._is("发票（张三）_20260424开具.pdf", "/tmp/root/1-合同/发票.pdf")

    def test_strong_keyword_outside_zone_accepted(self):
        assert self._is("委托合同.pdf", "/tmp/root/委托合同.pdf")

    def test_weak_keyword_outside_zone_rejected(self):
        assert not self._is("扫描合同.pdf", "/tmp/root/2026.09.01-某某合同纠纷一案/扫描合同.pdf")

    def test_case_name_filename_outside_zone_rejected(self):
        assert not self._is("民事起诉状（借款合同纠纷一案）.pdf", "/tmp/root/3-执行/民事起诉状.pdf")


# ── 本地文件夹收集（临时目录） ─────────────────────────────────────


class TestCollectLocalContractFiles:
    def test_collects_only_contract_files(self, tmp_path):
        from apps.oa_filing.services.filing_attachment_service import _collect_local_contract_files

        contract_dir = tmp_path / "1-合同"
        contract_dir.mkdir()
        (contract_dir / "委托合同.pdf").write_bytes(b"pdf")
        (contract_dir / "发票.pdf").write_bytes(b"pdf")
        other_dir = tmp_path / "3-执行"
        other_dir.mkdir()
        (other_dir / "强制执行申请书.docx").write_bytes(b"docx")

        candidates = _collect_local_contract_files(tmp_path)
        names = [item["path"].name for item in candidates]
        assert names == ["委托合同.pdf"]

    def test_missing_root_returns_empty(self, tmp_path):
        from apps.oa_filing.services.filing_attachment_service import _collect_local_contract_files

        assert _collect_local_contract_files(tmp_path / "nonexistent") == []


# ── resolver 三级来源 ──────────────────────────────────────────────


class TestResolveFilingAttachments:
    @patch(f"{_MODULE}._latest_contract_original_material_path", return_value="/media/合同.pdf")
    @patch(f"{_MODULE}._latest_contract_file_from_binding", return_value="/folder/合同.pdf")
    def test_material_takes_priority(self, mock_folder, mock_material):
        from apps.oa_filing.services.filing_attachment_service import resolve_filing_attachments

        assert resolve_filing_attachments(1) == ["/media/合同.pdf"]
        mock_folder.assert_not_called()

    @patch(f"{_MODULE}._latest_contract_original_material_path", return_value=None)
    @patch(f"{_MODULE}._latest_contract_file_from_binding", return_value="/folder/合同.pdf")
    def test_folder_fallback(self, mock_folder, mock_material):
        from apps.oa_filing.services.filing_attachment_service import resolve_filing_attachments

        assert resolve_filing_attachments(1) == ["/folder/合同.pdf"]

    @patch(f"{_MODULE}._latest_contract_original_material_path", return_value=None)
    @patch(f"{_MODULE}._latest_contract_file_from_binding", return_value=None)
    def test_no_source_returns_empty(self, mock_folder, mock_material):
        from apps.oa_filing.services.filing_attachment_service import resolve_filing_attachments

        assert resolve_filing_attachments(1) == []


# ── adapter 附件解析容错 ───────────────────────────────────────────


class TestAdapterAttachmentFallback:
    @pytest.mark.asyncio
    @patch(f"{_MODULE}.resolve_filing_attachments", side_effect=RuntimeError("boom"))
    async def test_resolver_failure_returns_empty(self, mock_resolve):
        from apps.oa_filing.services.oa_scripts.jtn.adapter import resolve_filing_attachments_safe

        result = await resolve_filing_attachments_safe(1)
        assert result == []


# ── 暂存服务（DB） ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestStageFilingAttachment:
    def _make_contract(self):
        from django.apps import apps as django_apps

        contract_model = django_apps.get_model("contracts", "Contract")
        return contract_model.objects.create(name="测试合同", case_type="civil")

    def _uploaded(self, content: bytes, name: str = "委托合同.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(name=name, content=content, content_type="application/pdf")

    def test_creates_contract_original_material(self):
        from django.apps import apps as django_apps

        from apps.oa_filing.services.filing_attachment_service import stage_filing_attachment

        contract = self._make_contract()
        result = stage_filing_attachment(contract.id, self._uploaded(b"contract-bytes"))

        material_model = django_apps.get_model("contracts", "FinalizedMaterial")
        material = material_model.objects.get(id=result["material_id"])
        assert material.category == "contract_original"
        assert material.original_filename == "委托合同.pdf"
        assert material.content_hash
        assert result["already_exists"] is False

    def test_identical_content_is_idempotent(self):
        from apps.oa_filing.services.filing_attachment_service import stage_filing_attachment

        contract = self._make_contract()
        first = stage_filing_attachment(contract.id, self._uploaded(b"same"))
        second = stage_filing_attachment(contract.id, self._uploaded(b"same"))
        assert second["already_exists"] is True
        assert second["material_id"] == first["material_id"]
