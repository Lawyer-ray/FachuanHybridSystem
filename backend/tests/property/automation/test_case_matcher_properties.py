"""
Case Matcher Service 属性测试
"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.sms.case_matcher import CaseMatcher
from apps.core.enums import CaseStage, CaseStatus, CaseType


@dataclass(frozen=True)
class FakeCase:
    id: int
    name: str
    status: str
    case_type: Optional[str] = None
    current_stage: Optional[str] = None


@settings(max_examples=100, deadline=None)
@given(ids=st.lists(st.integers(min_value=1, max_value=10_000), min_size=1, max_size=20, unique=True))
def test_select_latest_case_returns_max_id(ids: List[int]):
    matcher = CaseMatcher(case_service=object(), document_parser_service=object(), party_matching_service=object())  # type: ignore[arg-type]
    cases = [FakeCase(id=i, name=str(i), status=CaseStatus.ACTIVE) for i in ids]
    selected = matcher._select_latest_case(cases)
    assert selected is not None
    assert selected.id == max(ids)


@settings(max_examples=200, deadline=None)
@given(
    statuses=st.lists(st.sampled_from([CaseStatus.ACTIVE, CaseStatus.CLOSED]), min_size=1, max_size=20),
    ids=st.lists(st.integers(min_value=1, max_value=10_000), min_size=1, max_size=20, unique=True),
)
def test_match_by_case_number_exact_status_matrix(statuses: List[str], ids: List[int]):
    size = min(len(statuses), len(ids))
    statuses = statuses[:size]
    ids = ids[:size]

    matcher = CaseMatcher(case_service=object(), document_parser_service=object(), party_matching_service=object())  # type: ignore[arg-type]
    cases = [FakeCase(id=ids[i], name=f"c{ids[i]}", status=statuses[i]) for i in range(size)]

    def _fake_get_all_cases_by_numbers(_case_numbers):
        return cases

    matcher._get_all_cases_by_numbers = _fake_get_all_cases_by_numbers # type: ignore[method-assign]

    result = matcher._match_by_case_number_exact(["(2025)粤0605民初123号"])
    active = [c for c in cases if c.status == CaseStatus.ACTIVE]
    expected = active[0] if len(active) == 1 else None

    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.id == expected.id


@settings(max_examples=80, deadline=None)
@given(
    extra_cases=st.lists(st.integers(min_value=1, max_value=10_000), min_size=0, max_size=8, unique=True),
    stage=st.sampled_from([CaseStage.FIRST_TRIAL, CaseStage.SECOND_TRIAL, CaseStage.ENFORCEMENT]),
    case_type=st.sampled_from([CaseType.CIVIL, CaseType.CRIMINAL, CaseType.ADMINISTRATIVE]),
    bankruptcy=st.booleans(),
)
def test_narrow_down_by_case_number_features_unique_returns_that_case(
    extra_cases: List[int], stage: str, case_type: str, bankruptcy: bool
):
    matcher = CaseMatcher(case_service=object(), document_parser_service=object(), party_matching_service=object())  # type: ignore[arg-type]
    special = FakeCase(
        id=99999,
        name="破产-特殊" if bankruptcy else "普通-特殊",
        status=CaseStatus.ACTIVE,
        case_type=case_type,
        current_stage=stage,
    )

    others = []
    for i, cid in enumerate(extra_cases):
        others.append(
            FakeCase(
                id=cid,
                name=f"其他-{cid}",
                status=CaseStatus.ACTIVE,
                case_type=case_type if i % 2 == 0 else CaseType.CIVIL,
                current_stage=CaseStage.FIRST_TRIAL if stage != CaseStage.FIRST_TRIAL else CaseStage.SECOND_TRIAL,
            )
        )

    cases = [special] + others

    case_numbers = ["(2025)粤0605"]
    if bankruptcy:
        case_numbers.append("破")
    if case_type == CaseType.CRIMINAL:
        case_numbers.append("刑")
    elif case_type == CaseType.ADMINISTRATIVE:
        case_numbers.append("行")
    else:
        case_numbers.append("民")

    if stage == CaseStage.ENFORCEMENT:
        case_numbers.append("执")
    elif stage == CaseStage.SECOND_TRIAL:
        case_numbers.append("终")
    else:
        case_numbers.append("初")

    if bankruptcy:
        for c in others:
            assert "破产" not in c.name

    result = matcher._narrow_down_by_case_number_features(cases, case_numbers)
    assert result is not None
    assert result.id == special.id


@settings(max_examples=120, deadline=None)
@given(
    sms_parties=st.lists(st.text(min_size=1, max_size=10), max_size=3),
    doc_parties=st.lists(st.text(min_size=1, max_size=10), max_size=3),
)
def test_extract_party_names_precedence(sms_parties: List[str], doc_parties: List[str]):
    class FakeDocumentParserService:
        def get_all_document_paths(self, _sms):
            return ["/tmp/doc"]

        def extract_parties_from_document(self, _path):
            return doc_parties

    matcher = CaseMatcher(
        case_service=object(),  # type: ignore[arg-type]
        document_parser_service=FakeDocumentParserService(),  # type: ignore[arg-type]
        party_matching_service=object(),  # type: ignore[arg-type]
    )
    sms = SimpleNamespace(party_names=sms_parties)

    result = matcher._extract_party_names(sms)

    if len(sms_parties) >= 2:
        assert result == sms_parties
    elif len(doc_parties) >= 2:
        assert result == doc_parties
    else:
        assert result == sms_parties
