"""`decision`：裁决台账落库、回读、字段对齐与 append-only。

`Decision` 是律所留痕主体，字段少一个都可能在审计时说不清"依据是什么"。所以
回读用**整个 dataclass 相等**来断言，而不是抽查两三个字段；`dissent` 明确要求
保留（模型评估用）但不得混进 `basis`（展示层只看依据，不看被否掉的意见）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.db import connection

from apps.contract_review.services.alignment.decision import load_decision, record_decision
from apps.contract_review.services.alignment.models import ContractDecision
from apps.contract_review.services.write_contracts import Decision
from apps.core.exceptions import ConflictError, ValidationException

DECIDED_AT = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _decision(**overrides: object) -> Decision:
    values: dict[str, object] = {
        "decision_id": "decision-1",
        "session_id": "session-1",
        "owner_kind": "contract",
        "owner_id": 7,
        "subpath": "1-合同/a.docx",
        "clause_key": "第三条",
        "chosen_patch_id": "patch-1",
        "manual_text": None,
        "basis": {"citations": ["民法典第509条"], "rubric_ids": ["rubric-1"]},
        "decided_by": 42,
        "reason": "采纳 pi 的改法：违约金比例更接近同类判例",
        "dissent": ({"lane": "dsh", "replacement": "按日万分之十", "reason": "威慑不足"},),
        "decided_at": DECIDED_AT,
    }
    values.update(overrides)
    return Decision(**values)  # type: ignore[arg-type]


class TestSchema:
    def test_model_has_every_contract_field(self) -> None:
        contract_fields = {
            "decision_id",
            "session_id",
            "owner_kind",
            "owner_id",
            "subpath",
            "clause_key",
            "chosen_patch_id",
            "manual_text",
            "basis",
            "decided_by",
            "reason",
            "dissent",
            "decided_at",
        }
        model_fields = {field.name for field in ContractDecision._meta.get_fields()}

        assert contract_fields <= model_fields

    @pytest.mark.django_db
    def test_migration_0020_created_the_table(self) -> None:
        assert ContractDecision._meta.db_table in connection.introspection.table_names()


class TestRoundTrip:
    @pytest.mark.django_db
    def test_record_and_load_preserve_every_field(self) -> None:
        decision = _decision()

        recorded = record_decision(decision)
        loaded = load_decision(decision.decision_id)

        assert recorded == decision
        assert loaded == decision

    @pytest.mark.django_db
    def test_manual_rewrite_round_trip(self) -> None:
        decision = _decision(
            decision_id="decision-manual",
            chosen_patch_id=None,
            manual_text="甲方应于收到发票后二十日内支付货款。",
        )

        record_decision(decision)

        assert load_decision("decision-manual") == decision

    @pytest.mark.django_db
    def test_dissent_is_retained_but_not_part_of_basis(self) -> None:
        decision = _decision(decision_id="decision-dissent")
        record_decision(decision)

        loaded = load_decision("decision-dissent")

        assert loaded is not None
        assert loaded.dissent == decision.dissent
        assert "dissent" not in loaded.basis
        assert loaded.basis == decision.basis

    @pytest.mark.django_db
    def test_missing_decision_at_defaults_to_now(self) -> None:
        decision = _decision(decision_id="decision-now", decided_at=None)

        recorded = record_decision(decision)

        assert recorded.decided_at is not None
        assert load_decision("decision-now") == recorded

    @pytest.mark.django_db
    def test_unknown_decision_returns_none(self) -> None:
        assert load_decision("does-not-exist") is None


class TestAppendOnly:
    @pytest.mark.django_db
    def test_duplicate_decision_id_is_rejected(self) -> None:
        decision = _decision(decision_id="decision-dup")
        record_decision(decision)

        with pytest.raises(ConflictError):
            record_decision(decision)

        assert ContractDecision.objects.filter(pk="decision-dup").count() == 1


class TestValidation:
    @pytest.mark.django_db
    def test_invalid_owner_kind_is_rejected_before_insert(self) -> None:
        decision = _decision(decision_id="decision-bad-owner", owner_kind="folder")

        with pytest.raises(ValidationException):
            record_decision(decision)

        assert not ContractDecision.objects.filter(pk="decision-bad-owner").exists()

    @pytest.mark.django_db
    def test_non_dict_basis_is_rejected(self) -> None:
        decision = _decision(decision_id="decision-bad-basis", basis=["民法典第509条"])

        with pytest.raises(ValidationException):
            record_decision(decision)

    @pytest.mark.django_db
    def test_non_dict_dissent_is_rejected(self) -> None:
        decision = _decision(decision_id="decision-bad-dissent", dissent=("dsh 反对",))

        with pytest.raises(ValidationException):
            record_decision(decision)
