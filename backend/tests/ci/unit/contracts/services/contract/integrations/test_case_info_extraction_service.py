"""合同文件夹扫描案件信息提取与回填测试。"""

from __future__ import annotations

import pytest
from django.db import transaction

from apps.contracts.models import Contract
from apps.contracts.services.contract.integrations.case_info_extraction_service import (
    apply_case_info_to_contract,
    extract_case_info_from_candidates,
    infer_stage,
    is_court_notice_candidate,
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

    def test_preservation_numbers(self):
        assert infer_stage(case_number="（2025）粤0100财保111号") == "保全"  # privacy-allow 假案号
        assert infer_stage(case_number="（2025）粤0100执保222号") == "保全"  # privacy-allow 假案号

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


class TestIsCourtNoticeCandidate:
    def test_notice_pdf(self):
        assert is_court_notice_candidate({"filename": "告知书（某甲公司案件）_20261010收.pdf"}) is True

    def test_court_summons_letter(self):
        assert is_court_notice_candidate({"filename": "受理案件通知书.pdf"}) is True
        assert is_court_notice_candidate({"filename": "开庭传票.pdf"}) is True

    def test_judgment_is_not_notice(self):
        assert is_court_notice_candidate({"filename": "民事判决书.pdf"}) is False

    def test_application_letter_excluded(self):
        # 律师自己出具的申请书/所函不是法院文书，不提取
        assert is_court_notice_candidate({"filename": "强制执行申请书.pdf"}) is False


class TestCaseNumberWhitespaceTolerance:
    """案号内部带空格（PDF 排版切分）时的去空白兜底。"""

    _extractor = JudgmentPdfExtractor()

    def test_spaced_enforcement_number(self):
        text = "广东省某市第三人民法院\n告知书\n（2026）粤0100 执222 号\n正文。"  # privacy-allow 假案号
        assert self._extractor._extract_case_number(text) == "（2026）粤0100执222号"  # privacy-allow 假案号

    def test_spaced_preservation_number(self):
        text = "依据（2025）粤0100 财保111 号民事裁定书，现告知如下。"  # privacy-allow 假案号
        assert self._extractor._extract_case_number(text) == "（2025）粤0100财保111号"  # privacy-allow 假案号

    def test_compact_number_still_works(self):
        text = "（2025）粤0100民初111号\n正文。"  # privacy-allow 假案号
        assert self._extractor._extract_case_number(text) == "（2025）粤0100民初111号"  # privacy-allow 假案号


class TestExtractCaseReference:
    """程序性文书轻量提取：不要求主文。"""

    def test_reference_extracts_without_main_text(self, monkeypatch, tmp_path):
        extractor = JudgmentPdfExtractor()
        text = "广东省某市第三人民法院\n告知书\n（2026）粤0100 执222 号\n正文无判决如下主文。"  # privacy-allow 假案号
        monkeypatch.setattr(extractor, "_extract_full_text", lambda path: (text, "pdf_direct"))

        result = extractor.extract_case_reference(str(tmp_path / "x.pdf"))

        assert result.number == "（2026）粤0100执222号"  # privacy-allow 假案号
        assert result.court_name == "广东省某市第三人民法院"
        assert result.content is None


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
            {
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事判决书",
                "court_name": "",
                "content": "x",
            },  # privacy-allow 假案号
        )()
        queue: list = [Exception("boom"), good, dup]

        def _fake_extract(extractor, path, mode="judgment", storage_provider=None, include_full_text=False):
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

    def test_court_notice_extracts_number_without_content(self, monkeypatch, tmp_path):
        """告知书等程序性文书走 reference 模式：提取案号/法院，主文为空。"""
        pdf = tmp_path / "告知书.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        from apps.contracts.services.contract.integrations import case_info_extraction_service as svc

        reference = type(
            "R",
            (),
            {
                "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                "document_name": None,
                "court_name": "某市第三人民法院",
                "content": None,
            },
        )()
        modes: list[str] = []

        def _fake_extract(extractor, path, mode="judgment", storage_provider=None, include_full_text=False):
            modes.append(mode)
            return reference

        monkeypatch.setattr(svc, "_extract_pdf", _fake_extract)

        candidates = [{"filename": "告知书（某甲公司案件）_20261010收.pdf", "source_path": str(pdf), "skip_reason": ""}]
        result = extract_case_info_from_candidates(candidates)

        assert modes == ["reference"]
        assert len(result) == 1
        assert result[0]["number"] == "（2026）粤0100执222号"  # privacy-allow 假案号
        assert result[0]["stage"] == "执行"
        assert result[0]["court_name"] == "某市第三人民法院"
        assert result[0]["content"] == ""
        # 文书名来自文件名关键词（仅展示用）
        assert result[0]["document_name"] == "告知书"

    def test_same_number_prefers_extraction_with_content(self, monkeypatch, tmp_path):
        """同案号多份文书（调解书+受理通知书）优先保留带主文的提取。"""
        notice_pdf = tmp_path / "受理案件通知书.pdf"
        notice_pdf.write_bytes(b"%PDF-1.4 fake")
        judgment_pdf = tmp_path / "民事调解书.pdf"
        judgment_pdf.write_bytes(b"%PDF-1.4 fake")

        from apps.contracts.services.contract.integrations import case_info_extraction_service as svc

        notice = type(
            "R",
            (),
            {
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": None,
                "court_name": "某市人民法院",
                "content": None,
            },  # privacy-allow 假案号
        )()
        judgment = type(
            "R",
            (),
            {
                "number": "（2025）粤0100民初111号",  # privacy-allow 假案号
                "document_name": "民事调解书",
                "court_name": "",
                "content": "一、调解协议。",
            },  # privacy-allow 假案号
        )()

        def _fake_extract(extractor, path, mode="judgment", storage_provider=None, include_full_text=False):
            return notice if "通知书" in path else judgment

        monkeypatch.setattr(svc, "_extract_pdf", _fake_extract)

        # 通知书排在前面也要被调解书（带主文）顶掉
        candidates = [
            {"filename": "受理案件通知书.pdf", "source_path": str(notice_pdf), "skip_reason": ""},
            {"filename": "民事调解书.pdf", "source_path": str(judgment_pdf), "skip_reason": ""},
        ]
        result = extract_case_info_from_candidates(candidates)

        assert len(result) == 1
        assert result[0]["document_name"] == "民事调解书"
        assert result[0]["content"] == "一、调解协议。"


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
        assert [n.number for n in numbers] == [
            "（2025）粤0100民初111号",  # privacy-allow 假案号
            "（2026）粤0100执222号",  # privacy-allow 假案号
        ]  # privacy-allow 假案号
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

    def test_notice_extraction_keeps_document_name_empty(self):
        """程序性文书（无主文）只建/保案号，不占文书名——留给将来的真裁判文书。"""
        from apps.cases.models import Case

        contract = self._make_contract()
        notice_extraction = [
            {
                "source_path": "/a/告知书.pdf",
                "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                "document_name": "告知书",
                "court_name": "某市第三人民法院",
                "stage": "执行",
                "content": "",
            }
        ]
        stats = apply_case_info_to_contract(contract, notice_extraction)

        case = Case.objects.get(id=stats["case_id"])
        cn = case.case_numbers.get()
        assert cn.number == "（2026）粤0100执222号"  # privacy-allow 假案号
        assert cn.document_name == ""
        assert cn.document_content == ""

        # 后续扫到执行裁定书（带主文）可正常回填
        judgment_extraction = [
            {
                "source_path": "/b/执行裁定书.pdf",
                "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                "document_name": "执行裁定书",
                "court_name": "",
                "stage": "执行",
                "content": "裁定如下：冻结被执行人账户。",
            }
        ]
        apply_case_info_to_contract(contract, judgment_extraction)
        cn.refresh_from_db()
        assert cn.document_name == "执行裁定书"
        assert cn.document_content == "裁定如下：冻结被执行人账户。"

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


class TestPreservationNumberExcluded:
    """保全类案号（财保/执保）是程序性编号，不纳入提取。"""

    def test_is_preservation_number(self):
        from apps.contracts.services.contract.integrations.case_info_extraction_service import is_preservation_number

        assert is_preservation_number("（2025）粤0100财保111号") is True  # privacy-allow 假案号
        assert is_preservation_number("（2025）粤0100执保222号") is True  # privacy-allow 假案号
        assert is_preservation_number("（2025）粤0100民保333号") is True  # privacy-allow 假案号
        assert is_preservation_number("（2025）粤0100民初111号") is False  # privacy-allow 假案号
        assert is_preservation_number("（2026）粤0100执222号") is False  # privacy-allow 假案号

    def test_extraction_skips_preservation_numbers(self, monkeypatch, tmp_path):
        """告知书里的首个案号是执保号时跳过；主案号正常保留。"""
        from apps.contracts.services.contract.integrations import case_info_extraction_service as svc

        def _fake_extract(extractor, path, mode="judgment", storage_provider=None, include_full_text=False):
            if "执行告知书" in path:
                return type(
                    "R",
                    (),
                    {
                        "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                        "document_name": None,
                        "court_name": "某市人民法院",
                        "content": None,
                    },
                )()
            return type(
                "R",
                (),
                {
                    "number": "（2025）粤0100执保999号",  # privacy-allow 假案号
                    "document_name": None,
                    "court_name": "某市人民法院",
                    "content": None,
                },
            )()

        monkeypatch.setattr(svc, "_extract_pdf", _fake_extract)

        candidates = [
            {"filename": "结案告知书.pdf", "source_path": "/a/结案告知书.pdf", "skip_reason": ""},
            {"filename": "执行告知书.pdf", "source_path": "/b/执行告知书.pdf", "skip_reason": ""},
        ]
        result = extract_case_info_from_candidates(candidates)

        assert [item["number"] for item in result] == ["（2026）粤0100执222号"]  # privacy-allow 假案号


class TestSummarizeEnforcementNotice:
    """执行告知书正文 → 执行结果摘要。"""

    _SAMPLE = (
        "广东省某市第三人民法院 告知书 （2026）粤0100执222号"  # privacy-allow 假案号
        "本案在财产保全阶段依据（2025）粤0100财保11号民事裁定书继续冻结被执行人账户"  # privacy-allow
        "（扣划该账户60001元），上述继续冻结期限为一年。"
        "本案扣划被执行人账户存款61001元，扣除执行费1500元，余款60022元"
        "（优先支付受理费、保全费）已支付给申请执行人。本案案款尚未全部执行到位。"
        "由于被执行人未能按照生效法律文书履行付款义务，本院拟将被执行人限制其高消费。"
        "依照《中华人民共和国民事诉讼法》之规定，本院将依法终结执行，"
        "若你方发现被执行人有可供执行财产或者财产线索时，可以向人民法院申请恢复执行。"
    )

    def test_picks_money_and_status_in_document_order(self):
        from apps.contracts.services.contract.integrations.case_info_extraction_service import (
            _summarize_enforcement_notice,
        )

        summary = _summarize_enforcement_notice(self._SAMPLE)
        # 款项句（发放语义）入选，保全段落的"扣划该账户60001元"无发放语义不入选
        assert "已支付给申请执行人" in summary
        assert "60001" not in summary
        # 状态句：尚未到位 + 终结执行，按文书原句顺序
        assert summary.index("尚未全部执行到位") < summary.index("终结执行")
        # 限制高消费属进度噪音，三句封顶时不选
        assert "限制其高消费" not in summary

    def test_preservation_only_text_returns_empty(self):
        from apps.contracts.services.contract.integrations.case_info_extraction_service import (
            _summarize_enforcement_notice,
        )

        text = "本案在财产保全阶段继续冻结被执行人账户（扣划该账户60001元），冻结期限为一年。"
        assert _summarize_enforcement_notice(text) == ""

    def test_empty_text_returns_empty(self):
        from apps.contracts.services.contract.integrations.case_info_extraction_service import (
            _summarize_enforcement_notice,
        )

        assert _summarize_enforcement_notice("") == ""
        assert _summarize_enforcement_notice("   ") == ""

    def test_long_sentence_trimmed_at_comma(self):
        from apps.contracts.services.contract.integrations.case_info_extraction_service import _trim_notice_sentence

        sentence = (
            "依照《中华人民共和国民事诉讼法》第一百五十七条第一款第十一项、第二百六十八条之规定，"
            "本院将依法终结执行，若你方发现被执行人有可供执行财产或者财产线索时，"
            "可以自终结执行之日起定期向人民法院申请恢复执行并附相关证据材料"
        )
        trimmed = _trim_notice_sentence(sentence, limit=90)
        assert len(trimmed) <= 91
        assert trimmed.endswith("…")
        assert "终结执行" in trimmed


class TestEnforcementNoticeContentExtraction:
    """执行阶段程序性文书提炼执行结果摘要作为内容。"""

    def test_enforcement_notice_gets_summary_content(self, monkeypatch, tmp_path):
        pdf = tmp_path / "告知书.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        from apps.contracts.services.contract.integrations import case_info_extraction_service as svc

        reference = type(
            "R",
            (),
            {
                "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                "document_name": None,
                "court_name": "某市第三人民法院",
                "content": None,
                "full_text": "本案扣划被执行人账户存款61001元已支付给申请执行人。本案案款尚未全部执行到位。",
            },
        )()

        def _fake_extract(extractor, path, mode="judgment", storage_provider=None, include_full_text=False):
            assert mode == "reference" and include_full_text is True
            return reference

        monkeypatch.setattr(svc, "_extract_pdf", _fake_extract)

        candidates = [{"filename": "告知书（某甲公司案件）_20261010收.pdf", "source_path": str(pdf), "skip_reason": ""}]
        result = extract_case_info_from_candidates(candidates)

        assert len(result) == 1
        assert result[0]["stage"] == "执行"
        assert "已支付给申请执行人" in result[0]["content"]
        assert "尚未全部执行到位" in result[0]["content"]
        assert result[0]["document_name"] == "告知书"

    def test_first_instance_notice_keeps_content_empty(self, monkeypatch, tmp_path):
        pdf = tmp_path / "传票.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        from apps.contracts.services.contract.integrations import case_info_extraction_service as svc

        reference = type(
            "R",
            (),
            {
                "number": "（2026）粤0100民初333号",  # privacy-allow 假案号
                "document_name": None,
                "court_name": "某市人民法院",
                "content": None,
                "full_text": "定于2026年11月1日开庭审理，特此通知。",
            },
        )()

        def _fake_extract(extractor, path, mode="judgment", storage_provider=None, include_full_text=False):
            return reference

        monkeypatch.setattr(svc, "_extract_pdf", _fake_extract)

        candidates = [{"filename": "传票.pdf", "source_path": str(pdf), "skip_reason": ""}]
        result = extract_case_info_from_candidates(candidates)

        assert len(result) == 1
        assert result[0]["stage"] == "一审"
        assert result[0]["content"] == ""


@pytest.mark.django_db
class TestApplyEnforcementNoticeContent:
    """执行告知书摘要回填：content 视同主文，文书名一并落库。"""

    def _make_contract(self):
        contract = Contract.objects.create(
            name="某甲公司诉某乙公司买卖合同纠纷",
            case_type="civil",
        )
        return contract

    def test_notice_content_fills_document_fields(self):
        from apps.cases.models import Case

        contract = self._make_contract()
        extraction = [
            {
                "source_path": "/a/告知书.pdf",
                "number": "（2026）粤0100执222号",  # privacy-allow 假案号
                "document_name": "告知书",
                "court_name": "某市第三人民法院",
                "stage": "执行",
                "content": "本案扣划被执行人账户存款61001元已支付给申请执行人。本案案款尚未全部执行到位。",
            }
        ]
        stats = apply_case_info_to_contract(contract, extraction)

        case = Case.objects.get(id=stats["case_id"])
        cn = case.case_numbers.get()
        assert cn.document_name == "告知书"
        assert "已支付给申请执行人" in cn.document_content
