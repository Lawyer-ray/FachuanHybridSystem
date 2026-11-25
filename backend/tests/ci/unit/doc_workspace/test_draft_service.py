"""AI 起草：模板为骨、事实优先、未填槽转批注、骨架不许被改写。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 事实优先且 LLM 不得覆盖 | 金额/日期/主体名错一个字就是事故，而这几项恰恰最容易被模型「顺手规范化」 |
| 「待定 / 无 / N/A」判成没填 | 合同里出现「付款期限：待定」，客户第一眼就不信任 |
| 未填槽写成 `<待填写：x>` + 批注 | 起草稿看起来完整、实际有 12 个坑，律师无从得知 |
| 骨架段落逐字不变 | 模型一旦开始重排条款，复核成本超过它省下的时间 |
| 产物落进项目文件夹并返回 file_url | 律师要「下载 → 找文件 → 上传 → 打开」才算能改，这条链等于没做 |
| 起草后自动产生 ReviewRun | 「起草即初审」，否则律师对着空清单再点一次审查 |
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml.ns import qn

from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.models import ReviewRun
from apps.doc_workspace.services import draft_service

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 1017
SUBPATH = "1-合同/a.docx"


class _Service(BoundFolderBrowseService):
    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


@pytest.fixture
def wired(monkeypatch: Any, tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    doc = Document()
    doc.add_paragraph("占位原文件")
    buf = io.BytesIO()
    doc.save(buf)
    (d / "a.docx").write_bytes(buf.getvalue())

    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(tmp_path))
    return tmp_path


def _template() -> bytes:
    doc = Document()
    doc.add_paragraph("委托代理合同")
    doc.add_paragraph("甲方：{{party_a}}")
    doc.add_paragraph("乙方：{{party_b}}")
    doc.add_paragraph("争议解决：{{dispute_clause}}")
    doc.add_paragraph("本合同一式两份，双方各执一份。")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "服务费：{{fee}}"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _caller(payload: dict[str, Any]) -> Any:
    return lambda _messages: json.dumps(payload, ensure_ascii=False)


class TestExtractSlots:
    def test_collects_body_and_table_slots_in_order(self) -> None:
        slots = draft_service.extract_slots(_template())
        assert slots == ["party_a", "party_b", "dispute_clause", "fee"]


class TestResolveSlots:
    def test_facts_win_over_llm(self) -> None:
        """金额这类字段进了 LLM 就有格式风险，事实必须绝对优先。"""
        values, missing = draft_service.resolve_slots(
            slots=["fee", "party_a"],
            facts={"fee": "人民币壹万元整（¥10,000.00）"},
            caller=_caller({"fee": "10000元", "party_a": "某某公司"}),
        )
        assert values["fee"] == "人民币壹万元整（¥10,000.00）"
        assert values["party_a"] == "某某公司"
        assert missing == []

    @pytest.mark.parametrize("non_answer", ["", "  ", "待定", "无", "N/A", "TBD", "-"])
    def test_non_answers_count_as_missing(self, non_answer: str) -> None:
        values, missing = draft_service.resolve_slots(
            slots=["dispute_clause"], facts={}, caller=_caller({"dispute_clause": non_answer})
        )
        assert missing == ["dispute_clause"]
        assert "dispute_clause" not in values

    def test_without_caller_everything_unfilled_stays_missing(self) -> None:
        _values, missing = draft_service.resolve_slots(slots=["party_a"], facts={}, caller=None)
        assert missing == ["party_a"]

    def test_garbage_llm_output_does_not_crash(self) -> None:
        values, missing = draft_service.resolve_slots(
            slots=["party_a"], facts={}, caller=lambda _m: "对不起我无法完成"
        )
        assert values == {}
        assert missing == ["party_a"]

    def test_fenced_json_is_accepted(self) -> None:
        raw = '```json\n{"party_a": "甲公司"}\n```'
        values, missing = draft_service.resolve_slots(slots=["party_a"], facts={}, caller=lambda _m: raw)
        assert values["party_a"] == "甲公司"
        assert missing == []


class TestSkeleton:
    def test_render_keeps_non_slot_paragraphs_identical(self) -> None:
        template = _template()
        rendered = draft_service.render(
            template, {"party_a": "甲公司", "party_b": "乙公司", "dispute_clause": "", "fee": "壹万元"}, pending=[]
        )
        before = [p.text for p in Document(io.BytesIO(template)).paragraphs]
        after = [p.text for p in Document(io.BytesIO(rendered)).paragraphs]
        assert len(before) == len(after)
        for b, a in zip(before, after, strict=True):
            if "{{" in b:
                continue
            assert b == a, f"不含槽位的段落被改写了：{b!r} → {a!r}"

    def test_pending_slot_renders_visible_marker(self) -> None:
        rendered = draft_service.render(
            _template(), {"party_a": "甲", "party_b": "乙", "fee": "壹"}, pending=["dispute_clause"]
        )
        texts = "\n".join(p.text for p in Document(io.BytesIO(rendered)).paragraphs)
        assert "争议解决：<待填写：dispute_clause>" in texts
        assert "{{" not in texts

    def test_skeleton_violation_raises(self) -> None:
        """模型若被允许改结构（增删段、改编号），这里必须炸。"""
        template = _template()
        tampered = Document(io.BytesIO(template))
        tampered.paragraphs[0].text = "委托代理合同（重写版）"
        buf = io.BytesIO()
        tampered.save(buf)
        with pytest.raises(RuntimeError, match="不含槽位的段落"):
            draft_service._assert_skeleton_intact(template, buf.getvalue())


class TestDraftContract:
    def _draft(self, wired: Path, *, caller: Any = None, facts: dict[str, str] | None = None) -> Any:
        return draft_service.draft_contract(
            template_bytes=_template(),
            name="委托代理合同",
            kind=KIND,
            owner_id=OWNER_ID,
            subpath_dir="1-合同",
            facts=facts or {},
            caller=caller or _caller({"party_a": "甲公司", "party_b": "乙公司", "fee": "壹万元"}),
        )

    def test_file_lands_in_project_folder_with_openable_url(self, wired: Path) -> None:
        result = self._draft(wired)

        assert result.created is True
        assert (wired / "1-合同" / result.name).exists()
        # 前端可以直接拿它喂 OfficeView，不需要「下载→找文件→上传」
        assert result.file_url.startswith(f"/api/v1/contracts/{OWNER_ID}/folder-file?subpath=")
        assert result.subpath.endswith(".docx")

    def test_unfilled_slot_becomes_comment(self, wired: Path) -> None:
        result = self._draft(wired, facts={"party_a": "甲公司", "party_b": "乙公司", "fee": "壹万元"})

        assert result.pending == ["dispute_clause"]
        assert result.slot_fill_rate == 0.75

        import zipfile

        with zipfile.ZipFile(wired / "1-合同" / result.name) as zf:
            comments = zf.read("word/comments.xml").decode("utf-8")
        assert "待确认：dispute_clause" in comments

    def test_full_fill_has_no_pending_and_no_comment(self, wired: Path) -> None:
        result = self._draft(
            wired,
            facts={"party_a": "甲公司", "party_b": "乙公司", "fee": "壹万元", "dispute_clause": "提交甲方所在地法院"},
        )
        assert result.pending == []
        assert result.slot_fill_rate == 1.0

    def test_draft_creates_pending_review_run(self, wired: Path) -> None:
        result = self._draft(wired)
        assert result.review_run_id is not None
        run = ReviewRun.objects.get(id=result.review_run_id)
        assert run.owner_kind == KIND
        assert run.owner_id == OWNER_ID
        assert run.subpath == result.subpath
        # 「起草即初审」：轮次已建好，等后台跑模型
        assert run.status == "queued"

    def test_auto_review_can_be_disabled(self, wired: Path) -> None:
        result = draft_service.draft_contract(
            template_bytes=_template(),
            name="不审的稿子",
            kind=KIND,
            owner_id=OWNER_ID,
            subpath_dir="1-合同",
            facts={"party_a": "甲"},
            caller=_caller({}),
            auto_review=False,
        )
        assert result.review_run_id is None
        assert ReviewRun.objects.filter(subpath=result.subpath).count() == 0

    def test_existing_file_is_not_overwritten(self, wired: Path) -> None:
        first = self._draft(wired)
        second = self._draft(wired)
        assert first.name != second.name
        assert (wired / "1-合同" / "a.docx").exists()


class TestTableSlotRendering:
    def test_table_slot_is_rendered(self) -> None:
        rendered = draft_service.render(
            _template(), {"party_a": "甲", "party_b": "乙", "dispute_clause": "x", "fee": "壹万元"}, pending=[]
        )
        doc = Document(io.BytesIO(rendered))
        cell_text = doc.tables[0].cell(0, 0).text
        assert "壹万元" in cell_text
        assert "{{" not in cell_text
        # 顺带确认 qn 可用（表格段落与正文同一套 run 结构）
        assert qn("w:t") is not None
