"""tier 升级规则与 OCR 接线：什么时候花钱、补出来的字有没有真的进比对、没核完怎么落状态。

三件事必须钉死：

1. 归案时勾了「回传后核对内容」+ 扫描件 = 自动升 tier 1；没勾不升；显式 tier 不降级；
   落库的 `tier` 是实际值，不是入参；
2. OCR 补出来的正文**真的**进比对（命中的红线来自补出来的字，不是来自覆盖度字段）；
3. 预算用尽 / 引擎不可用必须落灰项，状态是 `unverifiable`——绝不能是 `verified_clean`。

跨 lane 依赖照既有写法 monkeypatch `apps.doc_verify.services.verify.deps` 的同名属性。
"""

from __future__ import annotations

import hashlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from apps.doc_verify.domain.contracts import Inbound, Report
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps
from apps.doc_verify.services.verify import run as run_service
from apps.doc_verify.services.verify import tier as tier_service

BASELINE_BYTES = b"%PDF-1.7 outbound baseline"
INBOUND_BYTES = b"%PDF-1.7 inbound scan"

#: 基线（数字件文本层）与 OCR 输出。金额都是虚构样例。 privacy-allow
BASELINE_TEXT = "诉讼请求：返还本金 998,702.06 元"
#: 同一笔钱、只是数字之间被 OCR 插了空格——归一化后金额对齐，不许报红线。 privacy-allow
OCR_TEXT_SAME_AMOUNT = "诉讼请求：返还本金 998 702.06 元"
#: OCR 读错了金额——必须命中 RED（证明补出来的字真的进了比对）。 privacy-allow
OCR_TEXT_TAMPERED = "诉讼请求:返还本金 998 702.60 元"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(**overrides: Any) -> OutboundArtifact:
    values: dict[str, Any] = {
        "doc_type": "起诉状",
        "version": "V4_20261106",
        "file_name": "起诉状_V4.pdf",
        "file_sha256": _sha(BASELINE_BYTES),
        "page_count": 1,
        "page_signatures": [[0.5, 0.25]],
        "text_layer": BASELINE_TEXT,
        "capture_source": CaptureSource.SEND_TO_CLIENT,
        "verify_required": True,
    }
    values.update(overrides)
    return OutboundArtifact.objects.create(**values)


def _inbound(data: bytes, *, text: str, page_count: int = 1) -> Inbound:
    return Inbound(
        sha256=_sha(data),
        page_count=page_count,
        page_signatures=((0.5, 0.25),),
        text=text,
        file_name="回传件.pdf",
    )


def _patch_extract(monkeypatch: pytest.MonkeyPatch, *, text: str, page_count: int = 1) -> list[SimpleNamespace]:
    """替换 lane B 的入站件提取，记录入参；返回的 Inbound 与真实字节的 sha 保持一致。"""
    calls: list[SimpleNamespace] = []

    def fake_extract(data: bytes, file_name: str = "") -> Any:
        calls.append(SimpleNamespace(data=data, file_name=file_name))
        return _inbound(data, text=text, page_count=page_count)

    monkeypatch.setattr(deps, "extract_document", fake_extract)
    return calls


def _ocr_result(
    *,
    text: str,
    engine: str = "local",
    pages_attempted: int = 1,
    pages_filled: int = 1,
    pages_failed: int = 0,
    budget_exhausted: bool = False,
) -> SimpleNamespace:
    """`OcrFillResult` 的替身：字段与 `services.anchor.ocr_fill` 冻结的契约逐字一致。"""
    return SimpleNamespace(
        text=text,
        pages_attempted=pages_attempted,
        pages_filled=pages_filled,
        pages_failed=pages_failed,
        budget_exhausted=budget_exhausted,
        engine=engine,
    )


def _patch_fill(monkeypatch: pytest.MonkeyPatch, result: Any) -> list[SimpleNamespace]:
    calls: list[SimpleNamespace] = []

    def fake_fill(**kwargs: Any) -> Any:
        calls.append(SimpleNamespace(**kwargs))
        return result

    monkeypatch.setattr(deps, "fill_text_with_ocr", fake_fill)
    return calls


def _patch_compare(monkeypatch: pytest.MonkeyPatch, report: Report | None = None) -> list[SimpleNamespace]:
    calls: list[SimpleNamespace] = []

    def fake_compare(baseline: Any, inbound: Any, *, tier: int = 0) -> Any:
        calls.append(SimpleNamespace(baseline=baseline, inbound=inbound, tier=tier))
        return Report(tier=tier) if report is None else report

    monkeypatch.setattr(deps, "compare_documents", fake_compare)
    return calls


class TestResolveTier:
    """升级规则是纯函数：显式要求不降级，只有「勾了核对 + 没文本层」才自动升。"""

    @pytest.mark.parametrize("requested", [1, 2])
    def test_explicit_request_is_never_downgraded(self, requested: int) -> None:
        assert tier_service.resolve_tier(requested=requested, verify_required=False, inbound_text="") == requested

    def test_scanned_inbound_with_verify_required_escalates_to_ocr(self) -> None:
        assert tier_service.resolve_tier(requested=0, verify_required=True, inbound_text="") == 1

    def test_whitespace_only_text_counts_as_no_text_layer(self) -> None:
        assert tier_service.resolve_tier(requested=0, verify_required=True, inbound_text=" \f \n") == 1

    def test_verify_required_with_a_text_layer_stays_free(self) -> None:
        assert tier_service.resolve_tier(requested=0, verify_required=True, inbound_text="诉讼请求:返还本金") == 0

    def test_scan_without_verify_required_stays_free(self) -> None:
        """律师没勾核对：不自作主张替他为 OCR 付钱。"""
        assert tier_service.resolve_tier(requested=0, verify_required=False, inbound_text="") == 0


@pytest.mark.django_db
class TestVerifyInboundOcrWiring:
    def test_scanned_inbound_with_verify_required_runs_ocr_at_tier_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch, text="")
        fill_calls = _patch_fill(monkeypatch, _ocr_result(text=BASELINE_TEXT))
        compare_calls = _patch_compare(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, file_name="回传件.pdf")

        assert len(fill_calls) == 1
        assert fill_calls[0].data == INBOUND_BYTES
        assert fill_calls[0].inbound.text == ""  # 补字前的提取结果
        # 比对拿到的是补字后的正文，不是原始空文本
        assert compare_calls[0].inbound.text == BASELINE_TEXT
        assert compare_calls[0].tier == 1

    def test_persisted_tier_is_the_resolved_value_not_the_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch, text="")
        _patch_fill(monkeypatch, _ocr_result(text=BASELINE_TEXT))
        _patch_compare(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, tier=0)

        run.refresh_from_db()
        assert run.tier == 1

    def test_without_verify_required_a_scan_does_not_pay_for_ocr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact(verify_required=False)
        _patch_extract(monkeypatch, text="")
        fill_calls = _patch_fill(monkeypatch, _ocr_result(text="不该被用到的正文"))
        compare_calls = _patch_compare(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        assert run.tier == 0
        assert fill_calls == []
        assert compare_calls[0].tier == 0
        assert "ocr" not in run.coverage

    def test_explicit_tier_two_is_not_downgraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact(verify_required=False)
        _patch_extract(monkeypatch, text="")
        _patch_fill(monkeypatch, _ocr_result(text=BASELINE_TEXT))
        compare_calls = _patch_compare(monkeypatch)

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, tier=2)

        run.refresh_from_db()
        assert run.tier == 2
        assert compare_calls[0].tier == 2

    def test_explicit_tier_one_fills_the_pages_that_have_no_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """数字件夹着一张扫描页：其余页有字，也不该放弃那一页。"""
        artifact = _artifact(verify_required=False)
        _patch_extract(monkeypatch, text="第一页正文\f\f第三页正文", page_count=3)
        _patch_fill(monkeypatch, _ocr_result(text="第一页正文\f第二页 OCR 正文\f第三页正文", pages_attempted=1))
        compare_calls = _patch_compare(monkeypatch)

        run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, tier=1)

        assert compare_calls[0].inbound.text == "第一页正文\f第二页 OCR 正文\f第三页正文"

    def test_run_key_does_not_include_the_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """同一份回传件换个 tier 重跑仍是同一次核对：幂等键只认基线与入站字节。"""
        artifact = _artifact(verify_required=False)
        _patch_extract(monkeypatch, text="回传正文")
        _patch_compare(monkeypatch)

        first = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, tier=0)
        second = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES, tier=2)

        assert first.id == second.id
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1


@pytest.mark.django_db
class TestOcrTextReachesTheComparison:
    """不 patch 比对引擎：真实 `domain.compare` 跑在 OCR 补出来的正文上。"""

    def test_tampered_ocr_amount_is_a_red_finding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch, text="")
        _patch_fill(monkeypatch, _ocr_result(text=OCR_TEXT_TAMPERED))

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        run.refresh_from_db()
        assert run.tier == 1
        assert run.state == VerifyState.CHANGED
        amounts = [finding for finding in run.findings if finding["code"] == "AMOUNT_MISMATCH"]
        assert len(amounts) == 1
        assert amounts[0]["severity"] == "red"
        assert amounts[0]["expected"] == "998702.06元"
        assert amounts[0]["actual"] == "998702.60元"

    def test_ocr_digit_gaps_do_not_fake_an_amount_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OCR 只是把 `998,702.06` 读成 `998 702.06`：归一化后金额对齐，不该报红线。"""
        artifact = _artifact()
        _patch_extract(monkeypatch, text="")
        _patch_fill(monkeypatch, _ocr_result(text=OCR_TEXT_SAME_AMOUNT))

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        run.refresh_from_db()
        assert run.findings == []
        assert run.state == VerifyState.VERIFIED_CLEAN
        assert run.coverage["ocr"]["pages_filled"] == 1


@pytest.mark.django_db
class TestOcrShortfallIsNeverGreen:
    def test_budget_exhausted_adds_gray_and_state_is_unverifiable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch, text="")
        _patch_fill(
            monkeypatch,
            _ocr_result(text="", pages_attempted=10, pages_filled=0, pages_failed=4, budget_exhausted=True),
        )
        # 就算比对引擎回报「全比过了」，预算用尽本身仍是一条没核完的证据——不许变绿
        _patch_compare(monkeypatch, Report(findings=[], coverage={"text_compared": True, "pages_no_text": 0}))

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        run.refresh_from_db()
        gray = [finding for finding in run.findings if finding["code"] == "OCR_BUDGET_EXHAUSTED"]
        assert len(gray) == 1
        assert gray[0]["severity"] == "gray"
        assert gray[0]["title"] == "OCR 预算用尽，仍有页未核对"
        assert run.state == VerifyState.UNVERIFIABLE
        assert run.coverage["ocr"] == {
            "pages_attempted": 10,
            "pages_filled": 0,
            "pages_failed": 4,
            "budget_exhausted": True,
            "engine": "local",
        }

    def test_unavailable_engine_adds_gray_and_is_never_verified_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        artifact = _artifact()
        _patch_extract(monkeypatch, text="")
        _patch_fill(
            monkeypatch,
            _ocr_result(text="", engine="unavailable", pages_attempted=0, pages_filled=0, pages_failed=1),
        )
        _patch_compare(monkeypatch, Report(findings=[], coverage={"text_compared": True, "pages_no_text": 0}))

        run = run_service.verify_inbound(artifact=artifact, data=INBOUND_BYTES)

        run.refresh_from_db()
        gray = [finding for finding in run.findings if finding["code"] == "OCR_UNAVAILABLE"]
        assert len(gray) == 1
        assert gray[0]["severity"] == "gray"
        assert gray[0]["title"] == "OCR 引擎不可用，无法核对正文"
        assert run.state == VerifyState.UNVERIFIABLE
        assert run.state != VerifyState.VERIFIED_CLEAN
        assert run.coverage["ocr"]["engine"] == "unavailable"


class TestDepsFillForwarding:
    """`deps.fill_text_with_ocr` 的唯一职责：把入站件拆成对方契约要的参数。

    用 sys.modules 注入替身模块：`ocr_fill` 此刻可能还不在树上，但转发形状今天就要锁住。
    """

    def test_forwards_page_count_existing_text_and_default_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = ModuleType("apps.doc_verify.services.anchor.ocr_fill")
        module.OCR_PAGE_BUDGET = 10  # type: ignore[attr-defined]
        calls: list[SimpleNamespace] = []

        def fake_fill(
            data: bytes,
            *,
            page_count: int,
            existing_text: str,
            page_budget: int,
            hint_pages: Any,
        ) -> Any:
            calls.append(
                SimpleNamespace(
                    data=data,
                    page_count=page_count,
                    existing_text=existing_text,
                    page_budget=page_budget,
                    hint_pages=hint_pages,
                )
            )
            return _ocr_result(text=existing_text)

        module.fill_text_with_ocr = fake_fill  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "apps.doc_verify.services.anchor.ocr_fill", module)

        inbound = Inbound(sha256=_sha(INBOUND_BYTES), page_count=7, text="已提取正文", file_name="回传件.pdf")
        deps.fill_text_with_ocr(data=INBOUND_BYTES, inbound=inbound)

        assert calls[0].data == INBOUND_BYTES
        assert calls[0].page_count == 7
        assert calls[0].existing_text == "已提取正文"
        assert calls[0].page_budget == 10  # 预算常量只有对方一份，默认值来自 ocr_fill
        assert calls[0].hint_pages == ()

    def test_explicit_budget_and_hint_pages_are_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        module = ModuleType("apps.doc_verify.services.anchor.ocr_fill")
        module.OCR_PAGE_BUDGET = 10  # type: ignore[attr-defined]
        calls: list[SimpleNamespace] = []

        def fake_fill(data: bytes, **kwargs: Any) -> Any:
            calls.append(SimpleNamespace(data=data, kwargs=kwargs))
            return _ocr_result(text="")

        module.fill_text_with_ocr = fake_fill  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "apps.doc_verify.services.anchor.ocr_fill", module)

        inbound = Inbound(sha256=_sha(INBOUND_BYTES), page_count=3, text="", file_name="回传件.pdf")
        deps.fill_text_with_ocr(data=INBOUND_BYTES, inbound=inbound, page_budget=2, hint_pages=(3,))

        assert calls[0].kwargs["page_budget"] == 2
        assert calls[0].kwargs["hint_pages"] == (3,)
