"""合同文件夹扫描案件信息提取与回填测试。"""

from __future__ import annotations

import pytest
from django.db import transaction

from apps.contracts.models import Contract
from apps.contracts.services.contract.integrations.case_info_extraction_service import (
    apply_case_info_to_contract,
    extract_case_info_from_candidates,
    infer_stage,
    is_judgment_candidate,
)
from apps.documents.services.extractors.judgment_pdf_extractor import JudgmentPdfExtractor


class TestInferStage:
    """案号/文书名 → 审级推断。"""

    def test_first_instance(self):
        assert infer_stage(case_number="（2025）粤0100民初111号") == "一审"  # privacy-allow 假案号

    def test_second_instance(self):
        assert infer_stage(case_number="(2025)粤06民终333号") == "二审"  # privacy-allow 假案号

    def test_enforcement(self):
        assert infer_stage(case_number="（2026）粤0100执222号") == "执行"  # privacy-allow 假案号

    def test_retrial(self):
        assert infer_stage(case_number="(2026)粤民再44号") == "再审"  # privacy-allow 假案号

    def test_document_name_fallback_enforcement(self):
        assert infer_stage(case_number="", document_name="执行裁定书") == "执行"

    def test_unknown_returns_empty(self):
        assert infer_stage(case_number="", document_name="民事判决书") == ""


class TestIsJudgmentCandidate:
    def test_judgment_pdf(self):
        assert is_judgment_candidate({"filename": "民事判决书.pdf"}) is True

    def test_mediation_pdf(self):
        assert is_judgment_candidate({"filename": "民事调解书（某甲公司诉某乙公司）.pdf"}) is True

    def test_plain_ruling_excluded(self):
        # 普通程序性裁定书（保全等）无最终结果主文，不参与提取
        assert is_judgment_candidate({"filename": "财产保全民事裁定书.pdf"}) is False

    def test_skipped_candidate_excluded(self):
        assert is_judgment_candidate({"filename": "民事判决书.pdf", "skip_reason": "跳过规则命中"}) is False

    def test_non_pdf_excluded(self):
        assert is_judgment_candidate({"filename": "民事判决书.docx"}) is False


class TestExtractCourtName:
    """JudgmentPdfExtractor 法院名称提取。"""

    _extractor = JudgmentPdfExtractor()

    def test_court_from_head(self):
        text = "广东省某市第三人民法院\n民事判决书\n（2025）粤0100民初111号\n原告：某甲公司。"  # privacy-allow 假案号
        assert self._extractor._extract_court_name(text) == "广东省某市第三人民法院"

    def test_arbitration_committee(self):
        text = "广州仲裁委员会\n仲裁裁决书\n（2025）穗仲案字第1234号"  # privacy-allow 假案号
        assert self._extractor._extract_court_name(text) == "广州仲裁委员会"

    def test_appeal_court_not_preempted(self):
        # 上诉指引中的法院名不应抢占落款法院
        text = "如不服本判决，可在判决书送达之日起十五日内向广东省东莞市中级人民法院提起上诉。"
        head_without_court = "某县人民法院\n民事判决书\n正文……" * 30
        text = head_without_court + text
        assert self._extractor._extract_court_name(text) == "某县人民法院"

    def test_no_court_returns_none(self):
        assert self._extractor._extract_court_name("没有机构的文本") is None


class TestExtractCaseInfoFromCandidates:
    """候选批量提取：单文件失败跳过、同案号去重。"""

    def test_skips_failed_extraction(self, monkeypatch, tmp_path):
        pdf = tmp_path / "民事判决书.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        from apps.contracts.services.contract.integrations import case_info_extraction_service as svc

        good = type(
            "R",
            (),
            {
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "某市人民法院",
                "content": "一、被告付款。",
            },
        )()
        dup = type(
            "R",
            (),
            {"number": "（2025）粤0100民初111号", "document_name": "民事判决书", "court_name": "", "content": "x"},  # privacy-allow 假案号
        )()
        queue: list = [Exception("boom"), good, dup]

        def _fake_extract(extractor, path, storage_provider=None):
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        monkeypatch.setattr(svc, "_extract_pdf", _fake_extract)

        candidates = [
            {"filename": "民事判决书A.pdf", "source_path": str(pdf), "skip_reason": ""},
            {"filename": "民事判决书B.pdf", "source_path": str(pdf), "skip_reason": ""},
            {"filename": "民事判决书C.pdf", "source_path": str(pdf), "skip_reason": ""},
        ]
        result = extract_case_info_from_candidates(candidates)

        assert len(result) == 1
        assert result[0]["number"] == "（2025）粤0100民初111号"  # privacy-allow 假案号
        assert result[0]["stage"] == "一审"
        assert result[0]["court_name"] == "某市人民法院"
        assert result[0]["content"] == "一、被告付款。"


@pytest.mark.django_db
class TestApplyCaseInfoToContract:
    """回填：多阶段共存、空字段才回填、法院去重。"""

    def _make_contract(self):
        return Contract.objects.create(
            name="某甲公司诉某乙公司买卖合同纠纷",
            case_type="civil",
        )

    def test_multi_stage_numbers_coexist(self):
        contract = self._make_contract()
        extractions = [
            {
                "source_path": "/a/民事判决书.pdf",
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "某市第三人民法院",
                "stage": "一审",
                "content": "一审判决主文。",
            },
            {
                "source_path": "/b/执行裁定书.pdf",
                "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                "document_name": "执行裁定书",
                "court_name": "某市第三人民法院",
                "stage": "执行",
                "content": "执行裁定主文。",
            },
        ]

        stats = apply_case_info_to_contract(contract, extractions)

        from apps.cases.models import Case, CaseNumber

        case = Case.objects.get(id=stats["case_id"])
        numbers = list(case.case_numbers.order_by("id"))
        assert [n.number for n in numbers] == ["（2025）粤0100民初111号", "（2026）粤0100执222号"]  # privacy-allow 假案号
        assert numbers[0].document_content == "一审判决主文。"
        assert numbers[1].document_content == "执行裁定主文。"
        # 同一法院只建一条审理机构
        assert case.supervising_authorities.filter(authority_type="trial", name="某市第三人民法院").count() == 1

    def test_full_name_vs_short_name_court_dedup(self):
        """全称（广东省××法院）与既有简称（××法院）视为同一家，不重复建。"""
        from apps.cases.models import Case, SupervisingAuthority

        contract = self._make_contract()
        case = Case.objects.create(contract=contract, name="既有案件")
        SupervisingAuthority.objects.create(case=case, authority_type="trial", name="某市第三人民法院")

        extractions = [
            {
                "source_path": "/a/民事判决书.pdf",
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "广东省某市第三人民法院",
                "stage": "一审",
                "content": "主文。",
            }
        ]
        stats = apply_case_info_to_contract(contract, extractions)

        assert stats["courts_created"] == 0
        assert case.supervising_authorities.filter(authority_type="trial").count() == 1

    def test_existing_content_not_overwritten(self):
        from apps.cases.models import Case, CaseNumber

        contract = self._make_contract()
        case = Case.objects.create(contract=contract, name="既有案件")
        CaseNumber.objects.create(
            case=case,
            number="（2025）粤0100民初111号",  # privacy-allow 假案号
            document_name="人工维护的文书名",
            document_content="人工维护的主文",
        )

        extractions = [
            {
                "source_path": "/a/民事判决书.pdf",
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "某市人民法院",
                "stage": "一审",
                "content": "新提取主文。",
            }
        ]
        stats = apply_case_info_to_contract(contract, extractions)

        assert stats["case_numbers_created"] == 0
        cn = case.case_numbers.get()
        assert cn.document_name == "人工维护的文书名"
        assert cn.document_content == "人工维护的主文"
        # 法院是新增信息，允许补建
        assert case.supervising_authorities.filter(name="某市人民法院").exists()

    def test_deselected_items_not_applied(self):
        from apps.cases.models import Case

        contract = self._make_contract()
        extractions = [
            {
                "source_path": "/a/民事判决书.pdf",
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "",
                "stage": "一审",
                "content": "主文。",
            }
        ]
        stats = apply_case_info_to_contract(contract, extractions, selected_paths=set())

        assert stats["case_id"] is None
        assert not Case.objects.filter(contract=contract).exists()

    def test_creates_case_when_missing(self):
        from apps.cases.models import Case

        contract = self._make_contract()
        extractions = [
            {
                "source_path": "/a/民事判决书.pdf",
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "某市人民法院",
                "stage": "一审",
                "content": "主文。",
            }
        ]
        stats = apply_case_info_to_contract(contract, extractions)

        assert stats["case_created"] is True
        case = Case.objects.get(id=stats["case_id"])
        assert case.contract_id == contract.id
        assert case.case_type == "civil"

    def test_reimport_is_idempotent(self):
        contract = self._make_contract()
        extractions = [
            {
                "source_path": "/a/民事判决书.pdf",
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "某市人民法院",
                "stage": "一审",
                "content": "主文。",
            }
        ]
        apply_case_info_to_contract(contract, extractions)
        stats = apply_case_info_to_contract(contract, extractions)

        from apps.cases.models import CaseNumber, SupervisingAuthority

        assert stats["case_numbers_created"] == 0
        assert stats["case_numbers_filled"] == 0
        assert stats["courts_created"] == 0
        case_id = stats["case_id"]
        assert CaseNumber.objects.filter(case_id=case_id).count() == 1
        assert SupervisingAuthority.objects.filter(case_id=case_id).count() == 1


@pytest.mark.django_db
class TestApplyCaseInfoRollbackSafety:
    """回填与导入事务兼容性冒烟（不炸唯一约束）。"""

    def test_apply_inside_transaction(self):
        with transaction.atomic():
            contract = Contract.objects.create(name="事务内合同", case_type="civil")
            stats = apply_case_info_to_contract(
                contract,
                [
                    {
                        "source_path": "/x.pdf",
                        "number": "(2026)粤01执55号",  # privacy-allow 假案号
                        "document_name": "执行裁定书",
                        "court_name": "某市中级人民法院",
                        "stage": "执行",
                        "content": "主文",
                    }
                ],
            )
            assert stats["case_numbers_created"] == 1
