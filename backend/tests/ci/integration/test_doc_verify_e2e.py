"""回传件内容核对端到端：**真字节进、真结论出**。

链路走完整条：合成 PDF → 冻结出站基线（写库）→ 客户回传件 → 提取 → 五级断言 →
状态推导 → 落库 → 律师裁决 → 待裁决清单 → API。

## 为什么这里一条 mock 都不打

这条链路的价值就在「真字节进去、真结论出来」。单测里 mock 掉比对引擎与提取层
是为了隔离职责，但如果端到端也 mock，那么「PDF 里的中文能不能取出来」「金额改了
到底报不报」这两件最要命的事一次都没被验证过。

## 为什么样本在用例里现场合成

真实案卷一旦进仓库，断言会随某份文件漂移，而且带隐私数据。这里合成一份结构完整
的起诉状（当事人 / 三项诉请含金额 / 事实与理由 / 具状日期），再派生四种回传件：
原样、改金额、删一段、扫描件（无文本层）。

## 不在本用例范围

tier>=1 的 OCR 路径：要外部模型与几十秒耗时，属真机验收；本文件锁的是
**tier 0 免费层的判定语义**——它才是决定「要不要花钱核」的那一层。
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator, Sequence

import pymupdf
import pytest
from ninja import NinjaAPI
from ninja.testing import TestClient

from apps.core.exceptions import register_exception_handlers
from apps.doc_verify.api import router
from apps.doc_verify.models import OutboundArtifact, VerificationDecision, VerificationRun, VerifyState
from apps.doc_verify.services.anchor.capture import capture_baseline
from apps.doc_verify.services.anchor.persist import create_artifact
from apps.doc_verify.services.verify import decision as decision_service
from apps.doc_verify.services.verify import policy as policy_service
from apps.doc_verify.services.verify import query as query_service
from apps.doc_verify.services.verify import run as run_service
from apps.testing.factories import CaseFactory, LawyerFactory

# ── 合成样本 ────────────────────────────────────────────────────────────────

_PAGE_1 = (
    "民事起诉状\n"
    "原告：张三\n"
    "被告：李四\n"
    "诉讼请求：\n"
    "1. 请求判令被告返还本金 998,702.06 元\n"
    "2. 请求判令被告支付利息 12,000 元\n"
    "3. 本案诉讼费由被告承担"
)
_PAGE_2 = "事实与理由\n双方于 2024年3月1日 签订借款合同。\n被告至今未还。\n原告多次催告无果。"
_PAGE_3 = "此致\n广州市天河区人民法院\n具状人：张三\n2026年11月25日"


def _make_pdf(pages: Sequence[str]) -> bytes:
    """合成数字 PDF（有文本层）。用 PyMuPDF 内置 CJK 字体，无需外部字体文件。"""
    document = pymupdf.open()
    for body in pages:
        page = document.new_page()
        y = 80
        for line in body.splitlines():
            page.insert_text((72, y), line, fontsize=11, fontname="china-s")
            y += 20
    data = document.tobytes()
    document.close()
    return data


def _make_scan(data: bytes) -> bytes:
    """把数字 PDF 逐页栅格化成图片再拼回 PDF：**没有任何文字**，即真实扫描件形态。

    用栅格化而不是「画个黑框」：这样页指纹与基线几乎一致，测出来的才是
    「没有文本层」这一条，而不是「页面被换掉了」。
    """
    source = pymupdf.open(stream=data, filetype="pdf")
    out = pymupdf.open()
    for page in source:
        pixmap = page.get_pixmap(dpi=100)
        target = out.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, stream=pixmap.tobytes("png"))
    scanned = out.tobytes()
    out.close()
    source.close()
    return scanned


BASELINE_BYTES = _make_pdf([_PAGE_1, _PAGE_2, _PAGE_3])
AMOUNT_TAMPERED_BYTES = _make_pdf([_PAGE_1.replace("998,702.06", "998,670.21"), _PAGE_2, _PAGE_3])
PARAGRAPH_REMOVED_BYTES = _make_pdf([_PAGE_1, _PAGE_2.replace("\n被告至今未还。", ""), _PAGE_3])
PAGE_REMOVED_BYTES = _make_pdf([_PAGE_1, _PAGE_2])


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _codes(run: VerificationRun) -> set[str]:
    return {str(item.get("code")) for item in run.findings}


def _severities(run: VerificationRun) -> set[str]:
    return {str(item.get("severity")) for item in run.findings}


@pytest.fixture
def artifact(db: None) -> Iterator[OutboundArtifact]:
    """冻结一份出站基线：起诉状 V4，出站时勾了「要求回传核对」。"""
    case = CaseFactory()
    lawyer = LawyerFactory()
    baseline = capture_baseline(
        data=BASELINE_BYTES,
        file_name="民事起诉状_V4_20261106.pdf",
        doc_type="民事起诉状",
        version="V4_20261106",
    )
    yield create_artifact(
        case=case,
        baseline=baseline,
        capture_source="send_to_client",
        verify_required=True,
        captured_by=lawyer,
    )


@pytest.fixture(scope="module")
def client() -> TestClient:
    api = NinjaAPI(urls_namespace="doc_verify_e2e")
    register_exception_handlers(api)
    api.add_router("/doc-verify", router)
    return TestClient(api)


# ── 四种回传件 ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestInboundScenarios:
    def test_original_bytes_are_identical(self, artifact: OutboundArtifact) -> None:
        """客户把数字件原样传回：字节相同就是硬事实，一条断言都不用跑。"""
        run = run_service.verify_inbound(artifact=artifact, data=BASELINE_BYTES, file_name="回传.pdf")

        assert run.state == VerifyState.IDENTICAL
        assert run.findings == []
        assert run.coverage["bytes_identical"] is True

    def test_amount_tampered_is_red(self, artifact: OutboundArtifact) -> None:
        """核心场景：客户悄悄把诉请金额改小 31.85 元。"""
        run = run_service.verify_inbound(artifact=artifact, data=AMOUNT_TAMPERED_BYTES, file_name="回传.pdf")

        assert run.state == VerifyState.CHANGED
        assert "AMOUNT_MISMATCH" in _codes(run)
        assert "red" in _severities(run)

        amount = next(item for item in run.findings if item["code"] == "AMOUNT_MISMATCH")
        assert amount["kind"] == "field"
        assert "998702.06" in str(amount["expected"])
        assert "998670.21" in str(amount["actual"])

    def test_paragraph_removed_is_yellow(self, artifact: OutboundArtifact) -> None:
        """客户删掉一句不利事实：字段全对，但段落少了一句。"""
        run = run_service.verify_inbound(artifact=artifact, data=PARAGRAPH_REMOVED_BYTES, file_name="回传.pdf")

        assert run.state == VerifyState.CHANGED
        assert "PARAGRAPH_MISSING" in _codes(run)
        assert "red" not in _severities(run)

    def test_page_removed_is_red_at_package_level(self, artifact: OutboundArtifact) -> None:
        """少一页：包级断言先拦，不必等全文比对。"""
        run = run_service.verify_inbound(artifact=artifact, data=PAGE_REMOVED_BYTES, file_name="回传.pdf")

        assert run.state == VerifyState.CHANGED
        assert "PAGE_COUNT_MISMATCH" in _codes(run)

    def test_scan_free_tier_is_gray_then_auto_ocr_upgrades_in_place(self, artifact: OutboundArtifact) -> None:
        """扫描件的两条事实都要锁住。

        1. **免费层不撒谎**：tier 0 一个字都没比，只能给「未发现差异」，不得是绿灯；
        2. **勾了核对就要真的升级**：同一份字节再跑一次（默认 tier），因 artifact
           勾了 verify_required 且无文本层 → 自动升到 OCR 层，**原地升级同一行**
           （不新开一行：同一份件的两条结论会让待裁决清单重复计数）。
        """
        scanned = _make_scan(BASELINE_BYTES)

        free = run_service.verify_inbound(artifact=artifact, data=scanned, file_name="扫描.pdf", tier=0)
        assert free.tier == 0
        assert free.state == VerifyState.NO_DIFFERENCE_DETECTED
        assert free.state not in {VerifyState.VERIFIED_CLEAN, VerifyState.IDENTICAL}
        assert free.coverage["text_compared"] is False
        assert free.coverage["pages_no_text"] == 3
        assert "PAGE_CHANGED" not in _codes(free)

        upgraded = run_service.verify_inbound(artifact=artifact, data=scanned, file_name="扫描.pdf")
        assert upgraded.pk == free.pk  # 原地升级，不新开行
        assert upgraded.tier == 1
        assert upgraded.coverage["ocr"]["engine"] == "local"
        assert upgraded.coverage["ocr"]["pages_filled"]
        assert upgraded.coverage["text_compared"] is True
        assert upgraded.state != VerifyState.NO_DIFFERENCE_DETECTED
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1


# ── 幂等 / 裁决 / 清单 / 策略 ────────────────────────────────────────────────


@pytest.mark.django_db
class TestRunLifecycle:
    def test_same_inbound_bytes_reuse_the_same_run(self, artifact: OutboundArtifact) -> None:
        """同一份回传件被三条链路看见（邮件/链接/手工上传）只该有一行。"""
        first = run_service.verify_inbound(artifact=artifact, data=AMOUNT_TAMPERED_BYTES, file_name="a.pdf")
        second = run_service.verify_inbound(artifact=artifact, data=AMOUNT_TAMPERED_BYTES, file_name="b.pdf")

        assert first.pk == second.pk
        assert VerificationRun.objects.filter(artifact=artifact).count() == 1

    def test_decision_is_append_only_and_clears_the_pending_list(self, artifact: OutboundArtifact) -> None:
        lawyer = LawyerFactory()
        run = run_service.verify_inbound(artifact=artifact, data=AMOUNT_TAMPERED_BYTES, file_name="回传.pdf")

        assert [item["id"] for item in query_service.list_unverified(artifact.case_id)] == [run.pk]

        decision_service.record_decision(
            verification=run, action="accept", reason="客户说明后确认可接受", decided_by=lawyer
        )
        assert query_service.list_unverified(artifact.case_id) == []

        # A deeper look after the ruling must still be auditable: 历史行不被改写
        decision_service.record_decision(verification=run, action="reject", reason="复核后改为退回重签")
        # 两条都在，顺序按 Meta.ordering（最新在前）：append-only 的第一条不会被覆盖
        rows = list(VerificationDecision.objects.filter(verification=run).values_list("action", flat=True))
        assert rows == ["reject", "accept"]

    def test_high_risk_doc_types_require_verification(self) -> None:
        """默认值比开关重要：这四类回签文书默认就要求核对。"""
        assert policy_service.should_verify("民事起诉状（一审）")
        assert policy_service.should_verify("授权委托书")
        assert policy_service.should_verify("送达地址确认书")
        assert policy_service.should_verify("退费账户确认书")
        assert not policy_service.should_verify("证据清单")
        assert not policy_service.should_verify("")


# ── API（真实 router + 真实异常处理器）──────────────────────────────────────


@pytest.mark.django_db
class TestApi:
    def test_create_run_then_read_it_back(self, artifact: OutboundArtifact, client: TestClient) -> None:
        payload = {
            "artifact_id": artifact.pk,
            "file_base64": base64.b64encode(AMOUNT_TAMPERED_BYTES).decode("ascii"),
            "file_name": "回传.pdf",
            "tier": 0,
        }
        created = client.post("/doc-verify/runs", json=payload, auth=LawyerFactory())

        assert created.status_code == 200, created.content
        body = created.json()
        assert body["state"] == VerifyState.CHANGED
        assert any(item["code"] == "AMOUNT_MISMATCH" for item in body["findings"])

        fetched = client.get(f"/doc-verify/runs/{body['id']}", auth=LawyerFactory())
        assert fetched.status_code == 200
        assert fetched.json()["inbound_sha256"] == _sha(AMOUNT_TAMPERED_BYTES)

    def test_unverified_list_returns_the_pending_run(self, artifact: OutboundArtifact, client: TestClient) -> None:
        run = run_service.verify_inbound(artifact=artifact, data=AMOUNT_TAMPERED_BYTES, file_name="回传.pdf")

        response = client.get(f"/doc-verify/unverified?case_id={artifact.case_id}", auth=LawyerFactory())

        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [run.pk]

    def test_invalid_base64_is_400_not_500(self, artifact: OutboundArtifact, client: TestClient) -> None:
        response = client.post(
            "/doc-verify/runs",
            json={"artifact_id": artifact.pk, "file_base64": "不是 base64", "file_name": "x.pdf"},
            auth=LawyerFactory(),
        )

        assert response.status_code == 400
