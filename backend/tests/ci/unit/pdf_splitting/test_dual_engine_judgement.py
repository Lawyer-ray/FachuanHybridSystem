"""双引擎分歧 → 裁块 → 判定 的接线测试。

## 这一层必须锁住什么

接线本身不难，难的是**「什么时候不该判」**：判错一条的代价是律师相信了一个错值，
而判都不判只是多进一次人工。所以这里的用例大多数在测「不许判」的分支：

- 开关关着 → 连一页都不渲染（渲染是唯一有 I/O 代价的准备动作）
- 证件/账号类 → 不渲染、不发请求
- 框不可信（近似推出来的 / 越界 / 两侧框不是同一行 / 两侧角度不一致）→ 不判
- 裁块失败 → 这一条留人工，**其余条目照常继续**（一条坏页不该带走整批）

真实 PDF 用 pymupdf 现画一页，块的矩形由 ``page.search_for`` 实测得到——
硬编码坐标会在换字体/换 dpi 时悄悄指到空白处，那种测试通过了也说明不了什么。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf as fitz
import pytest

from apps.pdf_splitting.services.split import disagreement_judge
from apps.pdf_splitting.services.split import dual_engine_judgement as judgement
from apps.pdf_splitting.services.split import dual_engine_runner
from apps.pdf_splitting.services.split.disagreement_judge import CandidateScore, Judgement
from apps.pdf_splitting.services.split.dual_engine import EngineDisagreement, EngineVariant
from apps.pdf_splitting.services.split.dual_engine_runner import disagreements_to_dicts
from apps.pdf_splitting.services.split.field_verification import FieldVerification

TARGET_TEXT = "6529346.56"
OTHER_TEXT = "6592946.56"


# ── 夹具：一页真实 PDF + 由 search_for 实测出来的归一化矩形 ──────────────


@pytest.fixture()
def pdf_with_amount(tmp_path: Path) -> Iterator[tuple[Path, list[float]]]:
    """画一页含金额的 PDF，返回 ``(路径, 该行文字的归一化四点)``。"""
    path = tmp_path / "page.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 120), TARGET_TEXT, fontsize=14)
    hits = page.search_for(TARGET_TEXT)
    assert hits, "画上去的字必须能被 search_for 找到，否则这个夹具本身失效"
    rect = hits[0]
    width, height = page.rect.width, page.rect.height
    normalized = [
        rect.x0 / width,
        rect.y0 / height,
        rect.x1 / width,
        rect.y1 / height,
    ]
    doc.save(path.as_posix())
    doc.close()
    yield path, normalized


def _block(rect: list[float], *, engine: str = "mineru", approx: bool = False) -> dict[str, Any]:
    """``engine_block_to_dict`` 的形状（归一化 0–1 + approx 标记）。"""
    return {
        "engine": engine,
        "page_no": 1,
        "text": "…",
        "rect": {"x": rect[0], "y": rect[1], "w": rect[2] - rect[0], "h": rect[3] - rect[1]},
        "block_type": "text",
        "approx": approx,
    }


def _disagreement(*, page_no: int = 1, left: str = TARGET_TEXT, right: str = OTHER_TEXT) -> EngineDisagreement:
    return EngineDisagreement(
        page_no=page_no,
        kind="numeric_drift",
        severity="high",
        variants=[
            EngineVariant(engine="mineru", text=left[:8], full_text=left),
            EngineVariant(engine="paddleocr_vl", text=right[:8], full_text=right),
        ],
        context=f"{left} | {right}"[:40],
    )


def _accepting_judge() -> Judgement:
    return Judgement(
        decision="accept",
        winner=TARGET_TEXT,
        scores=(
            CandidateScore(text=TARGET_TEXT, prob_yes=0.9961, verdict="scored"),
            CandidateScore(text=OTHER_TEXT, prob_yes=0.00001, verdict="scored"),
        ),
        reason="ratio_ok",
        ratio=99610.0,
    )


@pytest.fixture()
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judgement, "is_enabled", lambda: True)


@pytest.fixture()
def disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judgement, "is_enabled", lambda: False)


# ── 域推断 ──────────────────────────────────────────────────────────────


class TestInferDomain:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("公民身份号码 440524199003078230", "id_card"),
            ("440524199003078230", "id_card"),
            ("统一社会信用代码 91440300MA5DB1XY3K", "uscc"),
            ("账号 6222021234567890123", "account_no"),  # pragma: allowlist secret —— 虚构账号
            ("卡号 6222021234567890", "account_no"),  # pragma: allowlist secret —— 虚构卡号
            ("6222021234567890", "bank_card"),  # pragma: allowlist secret —— 虚构卡号
            ("（20XX）粤01民初某某号", "text"),
            ("乙方不承担连带保证责任", "text"),
            ("应补缴6529346.56元", "text"),
            ("", "text"),
        ],
    )
    def test_识别域(self, text: str, expected: str) -> None:
        assert judgement.infer_domain(text) == expected

    def test_案号不许被误判成证件或账号(self) -> None:
        """案号里也有长数字串和「号」字，但它必须走正文判定（实测它能被判定器判对）。"""
        assert judgement.infer_domain("（20XX）粤01民初某某号民事判决书") == "text"


# ── 框的可用性 ──────────────────────────────────────────────────────────


class TestBuildCrop:
    def test_两框重叠时取并集(self) -> None:
        left = _block([0.1, 0.1, 0.4, 0.12], engine="mineru")
        right = _block([0.12, 0.101, 0.42, 0.121], engine="paddleocr_vl")
        crop = judgement._build_crop([left, right], {}, 1)
        assert crop is not None
        assert crop.bbox_milli == pytest.approx([100.0, 100.0, 420.0, 121.0])
        assert crop.angle == 0
        assert crop.source == "mineru+paddleocr_vl"

    def test_近似框不许用(self) -> None:
        """``approx=True`` 表示坐标是推出来的；拿它裁图会裁到错的位置。"""
        assert judgement._build_crop([_block([0.1, 0.1, 0.4, 0.12], approx=True)], {}, 1) is None

    def test_反向或零面积框不许用(self) -> None:
        assert judgement._build_crop([_block([0.4, 0.1, 0.4, 0.12])], {}, 1) is None
        assert judgement._build_crop([_block([0.4, 0.12, 0.1, 0.1])], {}, 1) is None

    def test_越界框不许用(self) -> None:
        assert judgement._build_crop([_block([0.1, 0.1, 1.5, 0.12])], {}, 1) is None

    def test_两侧框不是同一行时放弃(self) -> None:
        """一个在上行、一个在下行：并集会横跨两行，候选文本必然与裁块不同域。"""
        top = _block([0.1, 0.10, 0.4, 0.12], engine="mineru")
        bottom = _block([0.1, 0.30, 0.4, 0.32], engine="paddleocr_vl")
        assert judgement._build_crop([top, bottom], {}, 1) is None

    def test_两侧角度不一致时放弃(self) -> None:
        """角度不同说明两者坐标不在同一个朝向里，硬裁必错位。"""
        left = _block([0.1, 0.1, 0.4, 0.12], engine="mineru")
        right = _block([0.12, 0.1, 0.42, 0.12], engine="paddleocr_vl")
        angles = {"mineru": {1: 0}, "paddleocr_vl": {1: 90}}
        assert judgement._build_crop([left, right], angles, 1) is None

    def test_角度一致时带上该角度(self) -> None:
        left = _block([0.1, 0.1, 0.4, 0.12], engine="paddleocr_vl")
        crop = judgement._build_crop([left], {"paddleocr_vl": {1: 90}}, 1)
        assert crop is not None
        assert crop.angle == 90


# ── 判定主流程 ──────────────────────────────────────────────────────────


class TestJudgeDisagreements:
    def test_关着时连一页都不渲染(
        self,
        disabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount

        def _boom(*_args: Any, **_kwargs: Any) -> bytes:
            raise AssertionError("开关关着时不该渲染任何页面")

        monkeypatch.setattr(judgement, "_render_page", _boom)
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[_disagreement()],
            blocks_by_disagreement={},
        )
        assert out == {}

    def test_证件类不渲染不发请求(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        monkeypatch.setattr(
            judgement, "_render_page", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("不该渲染"))
        )
        item = _disagreement(left="440524199003078230", right="440524199003078220")
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[item],
            blocks_by_disagreement={judgement.disagreement_key(item): [_block(rect)]},
        )
        annotation = out[judgement.disagreement_key(item)]
        assert annotation["decision"] == "human"
        assert annotation["reason"] == "domain_blocked"
        assert annotation["domain"] == "id_card"

    def test_没有可用框时不判(self, enabled: None, pdf_with_amount: tuple[Path, list[float]]) -> None:
        path, _rect = pdf_with_amount
        item = _disagreement()
        out = judgement.judge_disagreements(pdf_path=path, disagreements=[item], blocks_by_disagreement={})
        assert out[judgement.disagreement_key(item)]["reason"] == "no_usable_box"

    def test_正常路径透传判定并落附注(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        item = _disagreement()
        seen: dict[str, Any] = {}

        def _verify(*, page_image: bytes, bbox_milli: list[float], candidates: list[str], domain: str):
            seen["bbox"] = bbox_milli
            seen["candidates"] = candidates
            seen["domain"] = domain
            seen["image_ok"] = page_image.startswith(b"\x89PNG")
            return FieldVerification(
                decision="accept",
                winner=TARGET_TEXT,
                reason="ratio_ok",
                crop_bytes=b"png",
                crop_bbox_px=(1, 2, 3, 4),
                judgement=_accepting_judge(),
            )

        monkeypatch.setattr(judgement, "verify_field", _verify)
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[item],
            blocks_by_disagreement={judgement.disagreement_key(item): [_block(rect)]},
        )
        annotation = out[judgement.disagreement_key(item)]

        assert seen["image_ok"] is True, "渲染出来的必须是 PNG 字节"
        assert seen["candidates"] == [TARGET_TEXT, OTHER_TEXT], "候选取变体全文，且保持两侧顺序"
        assert seen["domain"] == "text"
        assert seen["bbox"][0] == pytest.approx(rect[0] * 1000, abs=1)
        assert annotation["decision"] == "accept"
        assert annotation["winner"] == TARGET_TEXT
        assert annotation["ratio"] == pytest.approx(99610.0)
        assert [row["prob_yes"] for row in annotation["scores"]] == [0.9961, 0.00001]
        assert all("text" not in row for row in annotation["scores"]), "附注不留候选全文（summary 已有）"

    def test_同一页只渲染一次(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        calls: list[int] = []
        original = judgement._render_page

        def _counting(pdf: Path, page_no: int, dpi: int, angle: int) -> bytes:
            calls.append(page_no)
            return original(pdf, page_no, dpi, angle)

        monkeypatch.setattr(judgement, "_render_page", _counting)
        monkeypatch.setattr(
            judgement,
            "verify_field",
            lambda **_k: FieldVerification(
                decision="human",
                winner=None,
                reason="ratio_low",
                crop_bytes=b"png",
                crop_bbox_px=(0, 0, 1, 1),
                judgement=None,
            ),
        )
        items = [_disagreement(left=TARGET_TEXT, right=OTHER_TEXT), _disagreement(left="1.00", right="1.0O")]
        blocks = {judgement.disagreement_key(item): [_block(rect)] for item in items}
        judgement.judge_disagreements(pdf_path=path, disagreements=items, blocks_by_disagreement=blocks)

        assert calls == [1], "同页多条分歧只渲染一次"

    def test_裁块失败只影响这一条(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        first, second = _disagreement(), _disagreement(left="3282858.48", right="3282858.4B")
        state = {"n": 0}
        original = judgement._render_page

        def _fail_once(pdf: Path, page_no: int, dpi: int, angle: int) -> bytes:
            state["n"] += 1
            if state["n"] == 1:
                raise OSError("源文件读不了")
            return original(pdf, page_no, dpi, angle)

        monkeypatch.setattr(judgement, "_render_page", _fail_once)
        monkeypatch.setattr(
            judgement,
            "verify_field",
            lambda **_k: FieldVerification(
                decision="accept",
                winner="x",
                reason="ratio_ok",
                crop_bytes=b"png",
                crop_bbox_px=(0, 0, 1, 1),
                judgement=_accepting_judge(),
            ),
        )
        blocks = {judgement.disagreement_key(item): [_block(rect)] for item in (first, second)}
        out = judgement.judge_disagreements(pdf_path=path, disagreements=[first, second], blocks_by_disagreement=blocks)

        assert out[judgement.disagreement_key(first)]["reason"] == "crop_failed"
        assert out[judgement.disagreement_key(second)]["decision"] == "accept"

    def test_超出预算的条目原样留人工(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        items = [_disagreement(left=f"值{i}A", right=f"值{i}B") for i in range(3)]
        monkeypatch.setattr(
            judgement,
            "verify_field",
            lambda **_k: FieldVerification(
                decision="human",
                winner=None,
                reason="ratio_low",
                crop_bytes=b"png",
                crop_bbox_px=(0, 0, 1, 1),
                judgement=None,
            ),
        )
        blocks = {judgement.disagreement_key(item): [_block(rect)] for item in items}
        out = judgement.judge_disagreements(
            pdf_path=path, disagreements=items, blocks_by_disagreement=blocks, max_judged=1
        )

        assert len(out) == 1, "预算用尽即停，剩下的条目连附注都不写（前端按「没判」处理）"

    def test_候选相同的分歧不判(self, enabled: None, pdf_with_amount: tuple[Path, list[float]]) -> None:
        """两侧读法去重后只剩一条：没有分歧可判，省掉两次请求。"""
        path, rect = pdf_with_amount
        item = _disagreement(left=TARGET_TEXT, right=TARGET_TEXT)
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[item],
            blocks_by_disagreement={judgement.disagreement_key(item): [_block(rect)]},
        )
        assert out == {}


# ── 汇总与落盘形状 ──────────────────────────────────────────────────────


class TestSummaryAndSerialization:
    def test_summarize_计数与原因分布(self) -> None:
        annotations = {
            (1, "k", "c"): {"decision": "accept", "reason": "ratio_ok"},
            (2, "k", "c"): {"decision": "human", "reason": "ratio_low"},
            (3, "k", "c"): {"decision": "human", "reason": "ratio_low"},
        }
        summary = judgement.summarize(annotations)
        assert summary == {
            "annotated": 3,
            "accepted": 1,
            "human": 2,
            "reasons": {"ratio_ok": 1, "ratio_low": 2},
        }

    def test_附注挂到分歧的judge键上(self) -> None:
        item = _disagreement()
        key = judgement.disagreement_key(item)
        rows = disagreements_to_dicts([item], judgements={key: {"decision": "accept", "winner": "x"}})
        assert rows[0]["judge"] == {"decision": "accept", "winner": "x"}

    def test_没判过的分歧不写judge键(self) -> None:
        """缺键 = 根本没过这一层（关着 / 没预算）；空 dict 会被前端当成“判过但没结论”。"""
        rows = disagreements_to_dicts([_disagreement()])
        assert "judge" not in rows[0]

    def test_判定不会删除任何分歧(self) -> None:
        """自动裁定只加标记，绝不把一条分歧从律师眼前拿掉。"""
        items = [_disagreement(), _disagreement(left="1.0", right="1.O")]
        keys = {judgement.disagreement_key(item): {"decision": "accept", "winner": "x"} for item in items}
        rows = disagreements_to_dicts(items, judgements=keys)
        assert len(rows) == 2
        assert [row["page_no"] for row in rows] == [1, 1]


# ── 接线：run_dual_engine 的 summary 形状 ────────────────────────────────


class TestRunnerWiring:
    """锁住 ``run_dual_engine`` 里那段接线：引擎并行、比对外，还必须有判定与汇总。

    这里把「两个引擎并行跑」换成假结果，只保留被验证的那一段——
    真引擎要打两次云端，且结果不可控（PaddleOCR 侧实测会 10010 队列满 / 503 / 500），
    那样的测试在 CI 里只会红，不会告诉你接线对不对。
    """

    def test_判定结果进summary并被汇总(
        self,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
        tmp_path: Path,
    ) -> None:
        path, _rect = pdf_with_amount
        item = _disagreement()

        monkeypatch.setattr(
            dual_engine_runner,
            "_run_engines_parallel",
            lambda *a, **k: {
                "mineru": ({1: TARGET_TEXT}, [], {}, ""),
                "paddleocr_vl": ({1: OTHER_TEXT}, [], {}, ""),
            },
        )
        monkeypatch.setattr(dual_engine_runner, "compare_pages", lambda *a, **k: [item])
        monkeypatch.setattr(
            dual_engine_runner,
            "judge_disagreements",
            lambda **k: {judgement.disagreement_key(item): {"decision": "accept", "winner": TARGET_TEXT}},
        )
        monkeypatch.setattr(dual_engine_runner, "gate_state", lambda: (True, disagreement_judge.GATE_ENABLED))

        outcome = dual_engine_runner.run_dual_engine(
            path,
            engine_factories={"mineru": lambda: None, "paddleocr_vl": lambda: None},
        )

        rows = outcome.summary[dual_engine_runner.SUMMARY_ENGINE_DISAGREEMENTS]
        judge_summary = outcome.summary[dual_engine_runner.SUMMARY_ENGINE_DISAGREE_JUDGE]
        assert rows[0]["judge"]["decision"] == "accept"
        assert judge_summary["enabled"] is True
        assert judge_summary["annotated"] == 1
        assert judge_summary["accepted"] == 1

    def test_判定整体炸了也不影响双引擎产出(
        self,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        """裁定只是「多一票参考」：它炸了，分歧与页面数据必须原样还在。"""
        path, _rect = pdf_with_amount
        item = _disagreement()
        monkeypatch.setattr(
            dual_engine_runner,
            "_run_engines_parallel",
            lambda *a, **k: {"mineru": ({1: TARGET_TEXT}, [], {}, ""), "paddleocr_vl": ({1: OTHER_TEXT}, [], {}, "")},
        )
        monkeypatch.setattr(dual_engine_runner, "compare_pages", lambda *a, **k: [item])

        def _boom(**_k: Any) -> dict[Any, Any]:
            raise RuntimeError("判定服务不可用")

        monkeypatch.setattr(dual_engine_runner, "judge_disagreements", _boom)
        monkeypatch.setattr(dual_engine_runner, "gate_state", lambda: (True, disagreement_judge.GATE_ENABLED))

        outcome = dual_engine_runner.run_dual_engine(path, engine_factories={"mineru": lambda: None})

        rows = outcome.summary[dual_engine_runner.SUMMARY_ENGINE_DISAGREEMENTS]
        assert len(rows) == 1, "判定炸了，分歧必须还在"
        assert "judge" not in rows[0]
        assert outcome.summary[dual_engine_runner.SUMMARY_ENGINE_DISAGREE_JUDGE]["annotated"] == 0


class TestSkipGuards:
    """两道止损闸门：多行块与长度悬殊的「分歧」判不出有意义的结论。

    实测依据：判定器在单行裁块上给 0.946–0.996（案号 / 金额），但在真实卷宗的
    多行块上 3/3 落到 prob_low（抵押登记表）。既然结论注定是「不适用」，
    就不该白花两次调用，更不该把它写成「判过但没结论」让排障的人多绕一圈。
    """

    def test_多行块不判(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        long_text = "甲" * (judgement.MAX_JUDGEABLE_CHARS + 1)
        item = _disagreement(left=long_text, right=long_text + "乙")
        monkeypatch.setattr(judgement, "verify_field", lambda **_k: (_ for _ in ()).throw(AssertionError("不该判")))
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[item],
            blocks_by_disagreement={judgement.disagreement_key(item): [_block(rect)]},
        )
        assert out[judgement.disagreement_key(item)]["reason"] == "multiline_block"

    def test_两侧长度悬殊不判(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        path, rect = pdf_with_amount
        item = _disagreement(left="EMS", right="EMS 全球特快专递 单位名称")
        monkeypatch.setattr(judgement, "verify_field", lambda **_k: (_ for _ in ()).throw(AssertionError("不该判")))
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[item],
            blocks_by_disagreement={judgement.disagreement_key(item): [_block(rect)]},
        )
        assert out[judgement.disagreement_key(item)]["reason"] == "length_mismatch"

    def test_单行候选照常判(
        self,
        enabled: None,
        monkeypatch: pytest.MonkeyPatch,
        pdf_with_amount: tuple[Path, list[float]],
    ) -> None:
        """闸门不能误伤真正该判的那一类（单行数字，实测 0.946–0.996）。"""
        path, rect = pdf_with_amount
        item = _disagreement()
        monkeypatch.setattr(
            judgement,
            "verify_field",
            lambda **_k: FieldVerification(
                decision="accept",
                winner=TARGET_TEXT,
                reason="ratio_ok",
                crop_bytes=b"png",
                crop_bbox_px=(0, 0, 1, 1),
                judgement=_accepting_judge(),
            ),
        )
        out = judgement.judge_disagreements(
            pdf_path=path,
            disagreements=[item],
            blocks_by_disagreement={judgement.disagreement_key(item): [_block(rect)]},
        )
        assert out[judgement.disagreement_key(item)]["decision"] == "accept"

    def test_两侧框高度悬殊时放弃(self) -> None:
        """一行 vs 两行（实测抵押登记表就这么配错）：并集裁块与两侧候选都不同域。"""
        one_line = _block([0.1, 0.100, 0.4, 0.108], engine="local_ppocr")
        two_lines = _block([0.1, 0.100, 0.4, 0.140], engine="mineru")
        assert judgement._build_crop([one_line, two_lines], {}, 1) is None


def test_dual_engine_summary_展开判定总账() -> None:
    """分段阶段展开 summary 时，判定总账必须跟着出来且形状固定。

    这条链路过两个**白名单**（tasks 落盘 + `_dual_engine_summary` 展开），
    漏一个就会出现「后端算了、前端什么都看不到」——正是前端最常报的那类
    「明明跑了却没有」。所以这里直接锁展开结果。
    """
    from apps.pdf_splitting.services.split.service import _dual_engine_summary

    empty = _dual_engine_summary({})["engine_disagreements_judge"]
    # ``requested``（任务级开关要求值）必须与 ``enabled``（有效值）成对出现：
    # 缺键时前端只能当 false，就会把「你开了但没生效」融成「你没开」。
    # ``reason`` 同理：没有它，前端只能说「未生效」，说不出**该去改哪个配置项**
    # （总闸没开 / 缺 key 是两个不同的运维动作）。
    assert empty == {
        "enabled": False,
        "requested": False,
        "reason": "not_requested",
        "annotated": 0,
        "accepted": 0,
        "human": 0,
        "reasons": {},
    }

    payload = {
        "engine_disagreements_judge": {
            "enabled": True,
            "requested": True,
            "reason": "enabled",
            "annotated": 3,
            "accepted": 1,
            "human": 2,
            "reasons": {},
        }
    }
    out = _dual_engine_summary(payload)["engine_disagreements_judge"]
    assert out["accepted"] == 1
    # 已知键必须原样透传：`reason` 落在白名单外时会被这里悄悄吃掉。
    assert out["reason"] == "enabled"
