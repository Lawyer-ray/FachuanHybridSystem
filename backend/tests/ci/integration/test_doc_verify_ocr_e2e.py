"""扫描回传件的真 OCR 端到端：**改掉金额的扫描件必须报红线**。

## 与 `test_doc_verify_e2e.py` 的分工

那个文件锁 **tier 0 免费层**的判定语义：数字件能抓改金额，扫描件只能给
「未发现差异」（没有文本层可比的已知盲区）。本文件锁 **tier ≥ 1 真 OCR 路径**：
同一份扫描件在免费层一个字都比不了，升级到 OCR 之后必须把改掉的金额抓成红色。

## 为什么这条必须用真引擎、真字节

OCR 是这条链路上唯一会「抖动」的一环：引擎装没装、模型在不在、渲染分辨率够不够，
都决定扫描页能不能取到字。用假 OCR 测这一层，等于只测了自己写的 if/else。
样本全部在用例里现场合成：三页起诉状 → 改第 1 页金额 → 整本栅格化成图片再拼回
PDF（无文本层 = 真实扫描件形态）。仓库里不放任何真实案卷。

## 引擎不可用时跳过，而不是失败

「本机没装 OCR / 模型没下载」是环境问题，不是被测逻辑的问题。判据用产品自己的
信号（`coverage["ocr"]["engine"] == "unavailable"` 或灰色 `OCR_UNAVAILABLE`），
不猜后端模块名——换引擎时本文件不用改。

## 为什么显式放宽超时、怎么看耗时

首次建 ONNX 会话约 20s，三页识别再各要一两秒：整条用例远超全局 30s 的哨兵值
（那个值是留给「线程写库未提交」这类真实竞态的，不是留给真 OCR 的）。耗时用
`pytest --durations=5` 看，逐次耗时另记一条 INFO 日志（仓库钩子禁止新增 print）。
"""

from __future__ import annotations

import importlib.util
import logging
import re
import time
import unicodedata
from collections.abc import Sequence

import pymupdf
import pytest

from apps.doc_verify.models import OutboundArtifact, VerificationRun, VerifyState
from apps.doc_verify.services.anchor.capture import capture_baseline
from apps.doc_verify.services.anchor.persist import create_artifact
from apps.doc_verify.services.verify import run as run_service
from apps.testing.factories import CaseFactory, LawyerFactory

logger = logging.getLogger(__name__)

pytest.importorskip(
    "apps.doc_verify.services.anchor.ocr_fill",
    reason="扫描页取字层（services/anchor/ocr_fill.py）未合入：tier≥1 的 OCR 路径不存在",
)

#: 本地 OCR 只走 rapidocr（`ocr_fill` 唯一的成功引擎值就是 local）。没装时引擎必然报
#: unavailable——先静态跳过，省掉一次注定失败的建会话。「装了但模型缺失 / 会话建不起来」
#: 由 :func:`_skip_if_engine_unavailable` 兜底。
_RAPIDOCR_INSTALLED = importlib.util.find_spec("rapidocr") is not None

# ── 合成样本 ────────────────────────────────────────────────────────────────

#: 出站基线里的诉请金额（客户回传时被改小 31.85 元）
_BASELINE_AMOUNT = "998,702.06"
_TAMPERED_AMOUNT = "998,670.21"

#: 字号比常规排版大一号：OCR 的渲染口径是 200dpi（`ocr_fill.OCR_RENDER_DPI`），
#: 常规 10.5~11pt 在这个分辨率下会把「2024」认成「20 2 4」——那是样本辨不清，
#: 不是链路取不到字。本文件要验的是比对结论，不是 OCR 的极限分辨率。
_FONT_SIZE = 16

#: 扫描分辨率。与 OCR 渲染口径（200dpi）对齐：扫描图再糊一层，
#: 识别精度就由这张图决定，而不再是链路本身。
_SCAN_DPI = 200

_PAGE_1 = (
    "民事起诉状\n"
    "原告：张三\n"
    "被告：李四\n"
    "诉讼请求：\n"
    f"1. 请求判令被告返还本金 {_BASELINE_AMOUNT} 元\n"
    "2. 请求判令被告支付利息 12,000 元\n"
    "3. 本案诉讼费由被告承担"
)
_PAGE_2 = "事实与理由\n双方于 2024年3月1日 签订借款合同。\n被告至今未还。\n原告多次催告无果。"
_PAGE_3 = "此致\n广州市天河区人民法院\n具状人：张三\n2026年11月25日"

_PAGE_1_TAMPERED = _PAGE_1.replace(_BASELINE_AMOUNT, _TAMPERED_AMOUNT)


def _make_pdf(pages: Sequence[str]) -> bytes:
    """合成数字 PDF（有文本层）。用 PyMuPDF 内置 CJK 字体，无需外部字体文件。"""
    document = pymupdf.open()
    try:
        for body in pages:
            page = document.new_page()
            y = 80
            for line in body.splitlines():
                page.insert_text((72, y), line, fontsize=_FONT_SIZE, fontname="china-s")
                y += _FONT_SIZE * 1.8
        return document.tobytes()
    finally:
        document.close()


def _scan_pdf(data: bytes) -> bytes:
    """逐页栅格化成灰度图再拼回 PDF：**没有任何文字**，即真实扫描件形态。

    灰度而不是彩色：真扫描仪的输出就是灰度/二值，彩色只是把同一页放大三倍。
    """
    source = pymupdf.open(stream=data, filetype="pdf")
    out = pymupdf.open()
    try:
        for page in source:
            pixmap = page.get_pixmap(dpi=_SCAN_DPI, colorspace=pymupdf.csGRAY)
            target = out.new_page(width=page.rect.width, height=page.rect.height)
            target.insert_image(target.rect, stream=pixmap.tobytes("png"))
        return out.tobytes()
    finally:
        out.close()
        source.close()


BASELINE_BYTES = _make_pdf([_PAGE_1, _PAGE_2, _PAGE_3])
TAMPERED_SCAN_BYTES = _scan_pdf(_make_pdf([_PAGE_1_TAMPERED, _PAGE_2, _PAGE_3]))


# ── 断言辅助 ────────────────────────────────────────────────────────────────


def _codes(run: VerificationRun) -> set[str]:
    return {str(item.get("code")) for item in run.findings}


def _compact(text: str) -> str:
    """折成全角→半角、去掉千分位与空白，只留数字与小数点。

    实测基线与回传两侧的写法会同时漂：OCR 把半角逗号认成全角（`998，670.21`）、
    把数字整段认成全角（`９９８，６７０.２１`，PP-OCRv5 server 就是这样）、也会在
    数字之间插空格（`99 8,670.21`）。三种都是识别排版差异，不是金额变了——
    NFKC 折完全角再删分隔符，断言的才是「数值有没有被改」。
    """
    return re.sub(r"[\s,，]", "", unicodedata.normalize("NFKC", str(text)))


def _freeze_artifact(data: bytes = BASELINE_BYTES) -> OutboundArtifact:
    """每个用例一份独立基线，出站时勾了「要求回传核对」。

    不能共用基线：`run_key` 只认（artifact, 入站字节），tier=0 与 tier=1 两次核对
    会撞进同一行——幂等会把后一次直接返回成前一次的结论，用例就永远绿了。
    """
    return create_artifact(
        case=CaseFactory(),
        baseline=capture_baseline(
            data=data,
            file_name="民事起诉状_V4_20261106.pdf",
            doc_type="民事起诉状",
            version="V4_20261106",
        ),
        capture_source="send_to_client",
        verify_required=True,
        captured_by=LawyerFactory(),
    )


def _skip_if_engine_unavailable(run: VerificationRun) -> None:
    """引擎不可用 → skip，并把产品自己报的信号带进跳过原因。

    判据取 `coverage["ocr"]["engine"]` 与灰色 `OCR_UNAVAILABLE`：这两个都是
    `verify_inbound` 对「引擎不可用」的正式表达，不依赖任何后端模块名。
    """
    ocr = run.coverage.get("ocr") or {}
    if ocr.get("engine") == "unavailable" or "OCR_UNAVAILABLE" in _codes(run):
        pytest.skip(
            f"真实 OCR 引擎不可用（engine={ocr.get('engine')!r}，codes={sorted(_codes(run))}）：本机未装引擎或模型缺失",
        )


# ── 真 OCR 端到端 ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRealScanOcr:
    @pytest.mark.timeout(240)
    @pytest.mark.skipif(not _RAPIDOCR_INSTALLED, reason="本地 OCR 引擎 rapidocr 未安装：tier≥1 必然报 unavailable")
    def test_tampered_amount_on_a_scanned_copy_is_red(self) -> None:
        """核心场景：客户把扫描件第 1 页的诉请金额改小 31.85 元再传回。"""
        artifact = _freeze_artifact()

        started = time.perf_counter()
        run = run_service.verify_inbound(
            artifact=artifact,
            data=TAMPERED_SCAN_BYTES,
            file_name="回传扫描件.pdf",
            tier=1,
        )
        elapsed = time.perf_counter() - started
        logger.info("真 OCR 端到端：tier=1 用时 %.1fs，%d 页，state=%s", elapsed, run.page_count, run.state)

        _skip_if_engine_unavailable(run)

        assert run.tier == 1
        assert run.state == VerifyState.CHANGED
        assert "AMOUNT_MISMATCH" in _codes(run), f"扫描页的金额没有被取出来比对：codes={sorted(_codes(run))}"

        amount = next(item for item in run.findings if item["code"] == "AMOUNT_MISMATCH")
        assert amount["severity"] == "red"
        # 两侧都要对上：expected 来自基线文本层（原稿），actual 只能是 OCR 取出来的字。
        # 只断言「有红线」的话，任何 OCR 噪声都能让这条用例通过——那就没验到「改金额被抓到」。
        assert _BASELINE_AMOUNT.replace(",", "") in _compact(amount["expected"])
        assert _TAMPERED_AMOUNT.replace(",", "") in _compact(amount["actual"])

        ocr = run.coverage.get("ocr") or {}
        assert ocr.get("pages_filled"), f"OCR 覆盖度没有记录补了哪几页：coverage={run.coverage}"

    def test_the_same_scan_is_invisible_at_tier_zero(self) -> None:
        """对照组：同一份扫描件在免费层只能给「未发现差异」，**绝不许**给「核对通过」。

        扫描件在 tier 0 一个字都比不了，所以既不能报「核过了」，也报不出「有改动」。
        有了这条对照，tier=1 那条红线才只能来自 OCR 取出来的字。
        """
        artifact = _freeze_artifact()

        run = run_service.verify_inbound(
            artifact=artifact,
            data=TAMPERED_SCAN_BYTES,
            file_name="回传扫描件.pdf",
            tier=0,
        )

        assert run.tier == 0
        assert run.state == VerifyState.NO_DIFFERENCE_DETECTED
        assert run.state not in {VerifyState.VERIFIED_CLEAN, VerifyState.IDENTICAL}
        assert run.coverage["text_compared"] is False
        assert "AMOUNT_MISMATCH" not in _codes(run)


# ── 全量覆盖：不许「只核前 N 页」 ───────────────────────────────────────────

_FILLER_PAGE = "随附材料说明\n本页与本案诉讼请求无关，仅用于把被改金额的那一页推到第 12 页。"
_TAIL_PAGE = "附：诉讼请求金额核定\n本案诉请本金 998,702.06 元，利息 12,000 元。\n具状人：张三"


def _filler_pages(count: int) -> list[str]:
    return [f"{_FILLER_PAGE}\n材料顺序：第 {index} 份" for index in range(1, count + 1)]


# transaction=True：12 页真 OCR 会跑一两分钟，事务型用例（事务一直开着）会撞上
# Postgres 的 idle-in-transaction 超时——那是测试写法的问题，不是被测代码开事务。
@pytest.mark.django_db(transaction=True)
class TestFullDocumentCoverage:
    @pytest.mark.timeout(900)
    @pytest.mark.skipif(not _RAPIDOCR_INSTALLED, reason="本地 OCR 引擎 rapidocr 未安装：tier≥1 必然报 unavailable")
    def test_tamper_on_the_twelfth_page_is_still_detected(self) -> None:
        """12 页 > 旧默认上限 10 页：只核前 10 页的做法会漏掉最后一页的改动。

        律师的原话是「不可能只核对前 10 页」——没核的页恰恰是客户最可能动手脚的地方。
        这条用例把改动放在**最后一页**，只要实现仍偷偷截断，它就必然报不出红线。
        """
        pages = [_PAGE_1, _PAGE_2, *_filler_pages(9), _TAIL_PAGE]
        assert len(pages) == 12

        tampered_tail = _TAIL_PAGE.replace(_BASELINE_AMOUNT, _TAMPERED_AMOUNT)
        inbound_scan = _scan_pdf(_make_pdf([_PAGE_1, _PAGE_2, *_filler_pages(9), tampered_tail]))
        artifact = _freeze_artifact(_make_pdf(pages))

        started = time.perf_counter()
        run = run_service.verify_inbound(
            artifact=artifact,
            data=inbound_scan,
            file_name="回传扫描件_12页.pdf",
            tier=1,
        )
        elapsed = time.perf_counter() - started
        logger.info(
            "全量覆盖：12 页扫描件 tier=1 用时 %.1fs，pages_filled=%s",
            elapsed,
            (run.coverage.get("ocr") or {}).get("pages_filled"),
        )

        _skip_if_engine_unavailable(run)

        ocr = run.coverage.get("ocr") or {}
        assert run.page_count == 12
        # 每一页都要核：12 页全部取到字，预算没有被截断
        assert len(ocr.get("pages_filled") or ()) == 12, f"只核了一部分页：{ocr}"
        assert ocr.get("budget_exhausted") is False
        # 改动在第 12 页，仍必须被抓到
        assert run.state == VerifyState.CHANGED
        assert "AMOUNT_MISMATCH" in _codes(run), f"最后一页的改金额没有被抓到：codes={sorted(_codes(run))}"
        amount = next(item for item in run.findings if item["code"] == "AMOUNT_MISMATCH")
        assert _TAMPERED_AMOUNT.replace(",", "") in _compact(amount["actual"])
