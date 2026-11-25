"""OCR 降级的两条灰度契约：**只准报「无法核对」，绝不准报「核对通过」**。

预算耗尽（还有扫描页没轮到）与引擎不可用（没装 / 模型缺失）都会让正文只剩一部分
可比。这两种情形下报告给绿灯，就是替客户说了一句系统并没有证据支持的话。

本文件**不跑真引擎**：`deps.fill_text_with_ocr` 换成给定结果，验的是核对编排拿到
这些结果后怎么落 finding 与 state。真 OCR 的端到端在
`tests/ci/integration/test_doc_verify_ocr_e2e.py`（首次建 ONNX 会话约 20s，
模型文件也不进 CI）。
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from apps.doc_verify.domain.contracts import Inbound
from apps.doc_verify.models import CaptureSource, OutboundArtifact, VerificationRun, VerifyState
from apps.doc_verify.services.verify import deps
from apps.doc_verify.services.verify import run as run_service

pytest.importorskip(
    "apps.doc_verify.services.anchor.ocr_fill",
    reason="扫描页取字层（services/anchor/ocr_fill.py）未合入：拿不到 OcrFillResult 的真实形状",
)
from apps.doc_verify.services.anchor.ocr_fill import ENGINE_LOCAL, ENGINE_UNAVAILABLE, OcrFillResult

if not hasattr(deps, "fill_text_with_ocr"):
    pytest.skip(
        "核对编排（services/verify）尚未接入 OCR：deps.fill_text_with_ocr 不存在",
        allow_module_level=True,
    )

# ── 合成样本（基线走 ORM 直建，本文件不需要真 PDF）─────────────────────────

_SCAN_BYTES = b"%PDF-1.7 scan-without-text-layer"
_BASELINE_BYTES = b"%PDF-1.7 outbound baseline"

_PAGE_1 = (
    "民事起诉状\n"
    "诉讼请求：\n"
    "1. 请求判令被告返还本金 998,702.06 元\n"
    "2. 请求判令被告支付利息 12,000 元\n"
    "3. 本案诉讼费由被告承担"
)
_PAGE_2 = "事实与理由\n双方于 2024年3月1日 签订借款合同。"
_PAGE_3 = "此致\n广州市天河区人民法院\n2026年11月25日"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact() -> OutboundArtifact:
    """一条三页起诉状的出站基线（正文是原稿文本层，扫描件侧一个字都没有）。"""
    return OutboundArtifact.objects.create(
        doc_type="民事起诉状",
        version="V4_20261106",
        file_sha256=_sha(_BASELINE_BYTES),
        page_count=3,
        page_signatures=[[0.5, 0.25]] * 3,
        text_layer="\f".join([_PAGE_1, _PAGE_2, _PAGE_3]),
        capture_source=CaptureSource.SEND_TO_CLIENT,
        verify_required=True,
    )


def _patch_scan_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    """回传件是扫描件：页数对、**一个字都没有**。

    只换入站提取，不碰比对引擎：灰项由引擎按覆盖度生成，换掉引擎这条用例就只是
    在测自己写的替身。页级指纹留空——页级断言不归本文件，真扫描件由端到端那条覆盖。
    """

    def fake_extract(data: bytes, file_name: str = "") -> Inbound:
        return Inbound(sha256=_sha(data), page_count=3, file_name=file_name)

    monkeypatch.setattr(deps, "extract_document", fake_extract)


def _patch_ocr(monkeypatch: pytest.MonkeyPatch, result: OcrFillResult) -> None:
    """把取字层换成一个固定结果（预算 / 引擎状态由用例指定）。"""

    def fake_fill(data: bytes, **kwargs: Any) -> OcrFillResult:
        return result

    monkeypatch.setattr(deps, "fill_text_with_ocr", fake_fill)


def _codes(run: VerificationRun) -> set[str]:
    return {str(item.get("code")) for item in run.findings}


def _finding(run: VerificationRun, code: str) -> dict[str, Any]:
    assert code in _codes(run), f"没有 {code}：codes={sorted(_codes(run))}"
    return next(item for item in run.findings if item["code"] == code)


# ── 两条降级路径 ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOcrGracefulDegradation:
    def test_budget_exhausted_is_gray_unverifiable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """预算耗尽：只补到第 1 页，2/3 页没轮到——报告不许说「核对通过」。"""
        artifact = _artifact()
        _patch_scan_extract(monkeypatch)
        _patch_ocr(
            monkeypatch,
            OcrFillResult(
                text=f"{_PAGE_1}\f\f",
                pages_attempted=(1,),
                pages_filled=(1,),
                pages_failed=(),
                budget_exhausted=True,
                engine=ENGINE_LOCAL,
            ),
        )

        run = run_service.verify_inbound(artifact=artifact, data=_SCAN_BYTES, file_name="扫描件.pdf", tier=1)

        assert run.tier == 1
        assert run.state == VerifyState.UNVERIFIABLE
        assert run.state != VerifyState.VERIFIED_CLEAN
        assert _finding(run, "OCR_BUDGET_EXHAUSTED")["severity"] == "gray"

    def test_engine_unavailable_is_gray_unverifiable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """引擎不可用：一页都没认账——同样只能落在「无法核对」。"""
        artifact = _artifact()
        _patch_scan_extract(monkeypatch)
        _patch_ocr(
            monkeypatch,
            OcrFillResult(
                text="",
                pages_attempted=(),
                pages_filled=(),
                pages_failed=(),
                budget_exhausted=False,
                engine=ENGINE_UNAVAILABLE,
            ),
        )

        run = run_service.verify_inbound(artifact=artifact, data=_SCAN_BYTES, file_name="扫描件.pdf", tier=1)

        assert run.tier == 1
        assert run.state == VerifyState.UNVERIFIABLE
        assert run.state != VerifyState.VERIFIED_CLEAN
        assert _finding(run, "OCR_UNAVAILABLE")["severity"] == "gray"
        assert "AMOUNT_MISMATCH" not in _codes(run)
