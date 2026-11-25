"""同一份回传件从免费层升到 OCR 层：**原地升级**，不新开一行。

## 为什么这条口径值得单独一个文件

`run_key` 只认「基线 + 入站字节」，所以同一份扫描件第二次被请求核对时必然命中既有行。
如果不在这里升级，律师就永远走不通「先跑免费层看一眼、觉得可疑再花钱核」这条路——
第二次请求会拿回那条灰的「未发现差异」，而它恰恰是最容易让人放弃继续核的结论。

## 为什么已有裁决就不升级

`list_unverified` 靠「有 accept/reject 就排除」收敛清单。裁决之后再改结论，不但和那份
裁决矛盾，还会让新冒出来的红线**从待裁决清单里消失**——那比不升级危险得多。
"""

from __future__ import annotations

import hashlib

import pytest

from apps.doc_verify.domain.contracts import AssertionKind, Finding, Inbound, Report, Severity
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationRun, VerifyState
from apps.doc_verify.services.anchor.ocr_fill import OcrFillResult
from apps.doc_verify.services.verify import decision as decision_service
from apps.doc_verify.services.verify import deps
from apps.doc_verify.services.verify import run as run_service
from apps.testing.factories import CaseFactory, LawyerFactory

PDF_BYTES = b"%PDF-1.7 scanned inbound bytes"
BASELINE_SHA = hashlib.sha256(b"%PDF-1.7 outbound baseline").hexdigest()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(**overrides: object) -> OutboundArtifact:
    values: dict[str, object] = {
        "doc_type": "民事起诉状",
        "version": "V4_20261106",
        "file_name": "起诉状_V4.pdf",
        "file_sha256": BASELINE_SHA,
        "page_count": 2,
        "text_layer": "诉讼请求：返还本金 998,702.06 元",
        "capture_source": CaptureSource.SEND_TO_CLIENT,
        "verify_required": True,
    }
    values.update(overrides)
    case = values.pop("case", None) or CaseFactory()
    return OutboundArtifact.objects.create(case=case, **values)


def _scanned_inbound() -> Inbound:
    """扫描件：有页数、有指纹，**没有文本层**——这正是要升 tier 的那一档。"""
    return Inbound(sha256=_sha(PDF_BYTES), page_count=2, page_signatures=((0.1, 0.2), (0.1, 0.2)), text="")


def _report(*, compared: bool) -> Report:
    """免费层的「没比正文」与 OCR 后的「比过了」两种报告。"""
    coverage = {"text_compared": compared, "pages_no_text": 0 if compared else 2, "bytes_identical": False}
    return Report(findings=[], coverage=coverage, tier=1 if compared else 0)


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ocr_findings: list[Finding] | None = None,
) -> dict[str, int]:
    calls = {"ocr": 0, "compare": 0}

    def fake_extract(data: bytes, file_name: str = "") -> Inbound:
        return _scanned_inbound()

    def fake_fill(**_: object) -> OcrFillResult:
        calls["ocr"] += 1
        return OcrFillResult(
            text="诉讼请求：返还本金 998,670.21 元\f事实与理由",
            pages_attempted=(1, 2),
            pages_filled=(1, 2),
            pages_failed=(),
            budget_exhausted=False,
            engine="local",
        )

    def fake_compare(baseline: object, inbound: object, *, tier: int = 0) -> Report:
        calls["compare"] += 1
        compared = getattr(inbound, "text", "") != ""
        report = _report(compared=compared)
        if compared and ocr_findings:
            report.findings.extend(ocr_findings)
        return report

    monkeypatch.setattr(deps, "extract_document", fake_extract)
    monkeypatch.setattr(deps, "fill_text_with_ocr", fake_fill)
    monkeypatch.setattr(deps, "compare_documents", fake_compare)
    return calls


@pytest.mark.django_db
class TestTierUpgrade:
    def test_second_request_upgrades_the_same_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        calls = _patch(
            monkeypatch,
            ocr_findings=[
                Finding(
                    kind=AssertionKind.FIELD,
                    code="AMOUNT_MISMATCH",
                    title="金额不一致",
                    severity=Severity.RED,
                    expected="998702.06元",
                    actual="998670.21元",
                )
            ],
        )

        free = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, tier=0)
        assert free.tier == 0
        assert free.state == VerifyState.NO_DIFFERENCE_DETECTED
        assert calls["ocr"] == 0  # 免费层绝不去调 OCR

        upgraded = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)

        assert upgraded.pk == free.pk
        assert upgraded.tier == 1
        assert upgraded.state == VerifyState.CHANGED
        assert calls["ocr"] == 1
        assert upgraded.coverage["ocr"]["engine"] == "local"
        assert {item["code"] for item in upgraded.findings} == {"AMOUNT_MISMATCH"}
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1

    def test_no_upgrade_after_a_decision(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """裁决之后再改结论会让新红线从待裁决清单里消失——所以不升，只记日志。"""
        artifact = _artifact()
        calls = _patch(
            monkeypatch,
            ocr_findings=[Finding(kind=AssertionKind.FIELD, code="AMOUNT_MISMATCH", title="金额不一致", severity=Severity.RED)],
        )
        free = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, tier=0)
        decision_service.record_decision(verification=free, action="accept", reason="客户已说明", decided_by=LawyerFactory())

        again = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)

        assert again.pk == free.pk
        assert again.tier == 0
        assert again.state == VerifyState.NO_DIFFERENCE_DETECTED
        assert calls["ocr"] == 0

    def test_same_tier_request_returns_without_ocr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        calls = _patch(monkeypatch)

        first = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, tier=0)
        second = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES, tier=0)

        assert first.pk == second.pk
        assert calls["ocr"] == 0

    def test_not_required_scan_stays_on_free_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """没勾「回传后核对内容」就不自作主张花钱：tier 不会自动升。"""
        artifact = _artifact(verify_required=False)
        calls = _patch(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=PDF_BYTES)

        assert run.tier == 0
        assert run.state == VerifyState.NO_DIFFERENCE_DETECTED
        assert calls["ocr"] == 0
