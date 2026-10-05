"""guarantee upload_mixin 单元测试 — 身份材料匹配与上传载荷构造。

覆盖模块：
- ``_pick_identity_files_from_map``：按 label 文本在 party_material_map 中精确匹配材料
- ``GuaranteeUploadMixin._build_file_payload / _build_file_payloads``：Playwright
  set_input_files 载荷（带原始文件名）构造

全部为纯逻辑测试，不起浏览器、不做真实网络请求。
"""

from __future__ import annotations

from typing import Any

from apps.automation.services.scraper.sites.guarantee.upload_mixin import (
    GuaranteeUploadMixin,
    _pick_identity_files_from_map,
)


def _party(name: str, client_type: str = "natural", materials: dict[str, list[str]] | None = None) -> dict[str, Any]:
    return {"name": name, "client_type": client_type, "materials": materials or {}}


def _map(
    applicants: list[dict[str, Any]] | None = None,
    respondents: list[dict[str, Any]] | None = None,
    lawyers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "applicants": applicants or [],
        "respondents": respondents or [],
        "lawyers": lawyers or [],
    }


class TestPickApplicant:
    def test_legal_person_gets_legal_rep_and_license(self) -> None:
        party_map = _map(
            applicants=[
                _party(
                    "广州市某某科技有限公司",
                    "legal",
                    {"法定代表人身份证明书": ["/m/a1.pdf"], "营业执照": ["/m/a2.pdf"], "身份证": ["/m/a3.pdf"]},
                )
            ]
        )
        result = _pick_identity_files_from_map(
            label_text="申请人-广州市某某科技有限公司-法人", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/a1.pdf", "/m/a2.pdf"]

    def test_natural_person_gets_id_card_only(self) -> None:
        party_map = _map(applicants=[_party("张三", "natural", {"身份证": ["/m/id1.pdf"], "营业执照": ["/m/biz.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="申请人-张三-自然人", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/id1.pdf"]

    def test_unknown_applicant_returns_empty(self) -> None:
        party_map = _map(applicants=[_party("李四", "natural", {"身份证": ["/m/id.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="申请人-王五-自然人", party_material_map=party_map, items=[], used=set()
        )
        assert result == []

    def test_name_substring_match(self) -> None:
        """标签里的名字包含 party 名（或反向）时仍能匹配。"""
        party_map = _map(applicants=[_party("张三", "natural", {"身份证": ["/m/id.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="申请人-张三丰-自然人", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/id.pdf"]


class TestPickRespondent:
    def test_legal_person_gets_license(self) -> None:
        party_map = _map(respondents=[_party("某某局", "legal", {"营业执照": ["/m/r1.pdf"], "身份证": ["/m/r2.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="被申请人-某某局-法人", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/r1.pdf"]

    def test_natural_person_gets_id_card(self) -> None:
        party_map = _map(respondents=[_party("赵六", "natural", {"身份证": ["/m/r3.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="被申请人-赵六-自然人", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/r3.pdf"]

    def test_missing_respondent_returns_empty(self) -> None:
        result = _pick_identity_files_from_map(
            label_text="被申请人-不存在-自然人", party_material_map=_map(), items=[], used=set()
        )
        assert result == []


class TestPickLawyer:
    def test_lawyer_by_extracted_name(self) -> None:
        party_map = _map(lawyers=[_party("房长波", materials={"律师证": ["/m/l1.pdf"], "所函": ["/m/l2.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="原告代理人-房长波-执业律师", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/l1.pdf", "/m/l2.pdf"]

    def test_defendant_agent_name_extracted(self) -> None:
        party_map = _map(lawyers=[_party("钱律师", materials={"律师证": ["/m/d1.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="被告代理人-钱律师-执业律师", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/d1.pdf"]

    def test_falls_back_to_first_lawyer_when_name_unmatched(self) -> None:
        party_map = _map(
            lawyers=[
                _party("律师甲", materials={"律师证": ["/m/x1.pdf"]}),
                _party("律师乙", materials={"律师证": ["/m/x2.pdf"]}),
            ]
        )
        result = _pick_identity_files_from_map(
            label_text="代理人-某人-执业律师", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/x1.pdf"]

    def test_no_lawyers_returns_empty(self) -> None:
        result = _pick_identity_files_from_map(
            label_text="代理人-某人-执业律师", party_material_map=_map(), items=[], used=set()
        )
        assert result == []


class TestPickGenericAndEdge:
    def test_empty_party_map_returns_empty(self) -> None:
        result = _pick_identity_files_from_map(
            label_text="申请人-张三-自然人", party_material_map=None, items=[], used=set()
        )
        assert result == []

    def test_generic_label_picks_first_party_with_materials(self) -> None:
        party_map = _map(applicants=[_party("王二", "natural", {"身份证": ["/m/g1.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="身份证明材料（申请人-王二）", party_material_map=party_map, items=[], used=set()
        )
        assert result == ["/m/g1.pdf"]

    def test_used_paths_are_excluded(self) -> None:
        party_map = _map(applicants=[_party("张三", "natural", {"身份证": ["/m/used.pdf", "/m/free.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="申请人-张三-自然人", party_material_map=party_map, items=[], used={"/m/used.pdf"}
        )
        assert result == ["/m/free.pdf"]

    def test_unrelated_label_returns_empty(self) -> None:
        party_map = _map(applicants=[_party("张三", "natural", {"身份证": ["/m/i.pdf"]})])
        result = _pick_identity_files_from_map(
            label_text="上传证据材料", party_material_map=party_map, items=[], used=set()
        )
        assert result == []


class _UploadStub(GuaranteeUploadMixin):
    def __init__(self, material_items: list[dict[str, str]]) -> None:
        self._material_items = material_items
        self.page = None  # 载荷构造不触碰页面


class TestBuildFilePayload:
    def test_payload_with_original_name_and_real_file(self, tmp_path) -> None:
        pdf = tmp_path / "stored-uuid.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        stub = _UploadStub([{"path": str(pdf), "type_name": "起诉状", "original_name": "起诉状-张三.pdf"}])

        payload = stub._build_file_payload(str(pdf))

        assert isinstance(payload, dict)
        assert payload["name"] == "起诉状-张三.pdf"
        assert payload["mimeType"] == "application/pdf"
        assert payload["buffer"] == b"%PDF-1.4 test"

    def test_returns_path_when_no_original_name(self, tmp_path) -> None:
        pdf = tmp_path / "plain.pdf"
        pdf.write_bytes(b"data")
        stub = _UploadStub([{"path": str(pdf), "type_name": "", "original_name": ""}])

        assert stub._build_file_payload(str(pdf)) == str(pdf)

    def test_returns_path_when_entry_missing(self, tmp_path) -> None:
        pdf = tmp_path / "not-in-items.pdf"
        pdf.write_bytes(b"data")
        stub = _UploadStub([{"path": "/other/file.pdf", "type_name": "", "original_name": ""}])

        assert stub._build_file_payload(str(pdf)) == str(pdf)

    def test_unreadable_file_falls_back_to_path(self, tmp_path) -> None:
        missing = tmp_path / "gone.pdf"
        stub = _UploadStub([{"path": str(missing), "type_name": "x", "original_name": "gone.pdf"}])

        assert stub._build_file_payload(str(missing)) == str(missing)

    def test_unknown_mime_defaults_octet_stream(self, tmp_path) -> None:
        doc = tmp_path / "blob.unknownext"
        doc.write_bytes(b"123")
        stub = _UploadStub([{"path": str(doc), "type_name": "x", "original_name": "blob.unknownext"}])

        payload = stub._build_file_payload(str(doc))

        assert isinstance(payload, dict)
        assert payload["mimeType"] == "application/octet-stream"


class TestBuildFilePayloads:
    def test_single_file_returns_single_payload(self, tmp_path) -> None:
        f1 = tmp_path / "a.pdf"
        f1.write_bytes(b"a")
        stub = _UploadStub([{"path": str(f1), "type_name": "", "original_name": "a.pdf"}])

        payload = stub._build_file_payloads([str(f1)])

        assert isinstance(payload, dict)
        assert payload["name"] == "a.pdf"

    def test_multiple_files_return_list(self, tmp_path) -> None:
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.write_bytes(b"a")
        f2.write_bytes(b"bb")
        stub = _UploadStub(
            [
                {"path": str(f1), "type_name": "", "original_name": "a.pdf"},
                {"path": str(f2), "type_name": "", "original_name": "b.pdf"},
            ]
        )

        payloads = stub._build_file_payloads([str(f1), str(f2)])

        assert isinstance(payloads, list)
        assert len(payloads) == 2
        assert [p["name"] for p in payloads] == ["a.pdf", "b.pdf"]

    def test_plain_paths_returned_as_strings(self, tmp_path) -> None:
        stub = _UploadStub([])
        payloads = stub._build_file_payloads([str(tmp_path / "x.pdf"), str(tmp_path / "y.pdf")])
        assert payloads == [str(tmp_path / "x.pdf"), str(tmp_path / "y.pdf")]
