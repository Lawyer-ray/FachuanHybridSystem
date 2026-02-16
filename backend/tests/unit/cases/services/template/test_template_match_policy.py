from __future__ import annotations

from dataclasses import dataclass

from apps.cases.services.template.template_match_policy import CaseTemplateMatchInput, CaseTemplateMatchPolicy


@dataclass
class DummyTemplate:
    id: int = 1
    case_types: list[str] | None = None
    case_stages: list[str] | None = None
    legal_statuses: list[str] | None = None
    legal_status_match_mode: str | None = None


def test_match_policy_allows_empty_constraints():
    policy = CaseTemplateMatchPolicy()
    t = DummyTemplate(case_types=[], case_stages=[], legal_statuses=[])
    match_input = CaseTemplateMatchInput(case_type="civil", case_stage="filing", legal_statuses={"plaintiff"})
    assert policy.is_match(t, match_input) is True


def test_match_policy_any_legal_status():
    policy = CaseTemplateMatchPolicy()
    t = DummyTemplate(legal_statuses=["plaintiff", "defendant"], legal_status_match_mode="any")
    assert policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"defendant"})) is True
    assert policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses=set())) is True
    assert policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"third_party"})) is False


def test_match_policy_all_legal_status():
    policy = CaseTemplateMatchPolicy()
    t = DummyTemplate(legal_statuses=["plaintiff", "defendant"], legal_status_match_mode="all")
    assert policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"plaintiff"})) is False
    assert (
        policy.is_match(
            t,
            CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"plaintiff", "defendant"}),
        )
        is True
    )


def test_match_policy_exact_legal_status():
    policy = CaseTemplateMatchPolicy()
    t = DummyTemplate(legal_statuses=["plaintiff"], legal_status_match_mode="exact")
    assert policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"plaintiff"})) is True
    assert policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"defendant"})) is False
    assert (
        policy.is_match(t, CaseTemplateMatchInput(case_type=None, case_stage=None, legal_statuses={"plaintiff", "defendant"}))
        is False
    )
