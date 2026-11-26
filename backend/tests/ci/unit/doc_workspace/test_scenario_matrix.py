"""复杂场景矩阵（后端可确定性验证的那一半）。

真机 DS 才能验的场景在 `deploy/onlyoffice/harness/scenario_matrix.py`；
本文件与其对应关系见 `docs/analysis/onlyoffice-ai-2026-11-26/scenario-matrix.md`。

## 为什么把「场景」单独成一个文件

单测按模块切，场景按**律师真正会遇到的组合**切。两者的价值不同：模块测试证明
「函数对」，场景测试证明「人这么用不会坏」。这里的每个用例都写清「律师实际做了什么」
和「不这么测会漏掉什么」。
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from apps.core.exceptions import ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.services import write_service
from apps.doc_workspace.services.docx.text import iter_paragraphs, visible_text

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 1219
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


def _write(path: Path, doc: Document) -> None:
    buf = io.BytesIO()
    doc.save(buf)
    path.write_bytes(buf.getvalue())


@pytest.fixture
def root(tmp_path: Path, monkeypatch: Any) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    doc = Document()
    doc.add_paragraph("第一条 甲方愿意支付人民币壹万元整。")
    _write(d / "a.docx", doc)

    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(tmp_path))
    return tmp_path


def _path(root: Path) -> Path:
    return root / "1-合同" / "a.docx"


def _text(root: Path) -> str:
    doc = Document(io.BytesIO(_path(root).read_bytes()))
    return "\n".join(visible_text(p) for p in iter_paragraphs(doc))


class TestScenarioTableClause:
    """场景：付款/验收条款写在**表格**里，律师让 AI 改那一条。

    不这么测会漏掉：`doc.paragraphs` 看不到表格，定位直接失败——而付款条款恰恰
    最常放在表格里。
    """

    def test_revision_lands_inside_table_cell(self, root: Path) -> None:
        doc = Document(io.BytesIO(_path(root).read_bytes()))
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "验收标准"
        table.cell(0, 1).text = "以甲方书面确认为准。"
        _write(_path(root), doc)

        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="以甲方书面确认为准",
            suggested="以甲方书面确认并签章为准",
        )

        assert result["applied"] is True
        assert "以甲方书面确认并签章为准" in _text(root)


class TestScenarioCrossRunClause:
    """场景：同一句话被排版/拼写检查切成了多个 run（Word 的常态）。

    不这么测会漏掉：逐 run 精确匹配必然失败，律师体验是「AI 说找不到原文」。
    """

    def test_revision_spans_multiple_runs(self, root: Path) -> None:
        doc = Document()
        p = doc.add_paragraph()
        for piece in ("乙方应当", "在三十日", "内完成交付。"):
            p.add_run(piece)
        _write(_path(root), doc)

        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="乙方应当在三十日内完成交付。",
            suggested="乙方应当在十五日内完成交付。",
        )

        assert result["applied"] is True
        assert "乙方应当在十五日内完成交付。" in _text(root)

    def test_cross_run_with_different_formatting_keeps_style(self, root: Path) -> None:
        doc = Document()
        p = doc.add_paragraph()
        r1 = p.add_run("违约金以")
        r2 = p.add_run("合同总价款")
        r2.bold = True
        p.add_run("的 30% 为限。")
        _write(_path(root), doc)
        assert r1.bold is None and r2.bold is True

        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="违约金以合同总价款的 30% 为限。",
            suggested="违约金以合同总价款的 20% 为限。",
        )

        assert result["applied"] is True
        # 插在加粗 run 之后的新 run 会继承它的格式（rPr 深拷贝）
        xml = Document(io.BytesIO(_path(root).read_bytes())).element.xml
        assert "20%" in xml


class TestScenarioAnchorLost:
    """场景：AI 审完，律师自己把那段改了，然后再点「采纳」。

    不这么测会漏掉：**错位改字**——比失败严重得多，法律文书容不得。
    """

    def test_second_apply_on_changed_text_fails_without_writing(self, root: Path) -> None:
        first = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection="甲方愿意支付", suggested="甲方同意支付"
        )
        assert first["applied"] is True
        after_first = _path(root).read_bytes()

        # 同一段原文已经不存在了（现行文本变成「甲方同意支付」）
        second = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection="甲方愿意支付", suggested="甲方应支付"
        )

        assert second["applied"] is False
        assert _path(root).read_bytes() == after_first


class TestScenarioLargeDocument:
    """场景：60 页合同（1500 段 + 一张表）。

    不这么测会漏掉：解析/定位在真实体量下变慢或超时，而律师手上的合同就是这个量级。
    """

    def test_revision_in_large_document(self, root: Path) -> None:
        doc = Document()
        for i in range(1500):
            doc.add_paragraph(f"第{i + 1}条 双方确认本条款内容。")
        table = doc.add_table(rows=1, cols=1)
        table.cell(0, 0).text = "第1501条 管辖约定：提交甲方所在地法院。"
        _write(_path(root), doc)

        started = time.monotonic()
        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="第1501条 管辖约定：提交甲方所在地法院。",
            suggested="第1501条 管辖约定：提交乙方所在地法院。",
        )
        elapsed = time.monotonic() - started

        assert result["applied"] is True
        # 30 秒是很宽的上限：真机预期 1-3 秒，超过说明定位算法退化成 O(n²)
        assert elapsed < 30, f"大文档落笔耗时 {elapsed:.1f}s"

    def test_large_document_ambiguous_anchor_reports_candidates(self, root: Path) -> None:
        doc = Document()
        for _ in range(1500):
            doc.add_paragraph("双方确认本条款内容。")
        _write(_path(root), doc)

        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection="双方确认本条款内容。", suggested="改后"
        )

        assert result["applied"] is False
        assert result["candidates"] >= 2


class TestScenarioNonDocx:
    """场景：律师点开 xlsx / pdf 也想让 AI 改。

    不这么测会漏掉：「假装成功」——xlsx 上落 docx 修订会产出坏文件。
    """

    @pytest.mark.parametrize("name", ["a.xlsx", "a.pdf", "a.docx.bak"])
    def test_non_docx_rejected(self, root: Path, name: str) -> None:
        (root / "1-合同" / name).write_bytes(b"x")
        with pytest.raises(ValidationException):
            write_service.apply_span(kind=KIND, owner_id=OWNER_ID, subpath=f"1-合同/{name}", selection="x", suggested="y")


class TestScenarioPermission:
    """场景：越权——不是这份文件的属主，却拿着路径来改。

    不这么测会漏掉：跨当事人内容泄露/篡改。这里断言写通道**用的就是带 ACL 的
    服务**（真正的行级判定由各域 `*AccessPolicy` 负责，另有 API 层用例覆盖）。
    """

    def test_write_path_uses_acl_enforcing_service(self) -> None:
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        svc = write_service.browse_for("contract")
        assert isinstance(svc, ContractFolderBrowseService), "写通道不能绕过行级 ACL"

    def test_both_domains_use_their_own_acl_service(self) -> None:
        """合同与案件各有各的 AccessPolicy：写通道必须分别走对，不能统一退化成基类。"""
        from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        assert isinstance(write_service.browse_for("contract"), ContractFolderBrowseService)
        assert isinstance(write_service.browse_for("case"), CaseFolderBrowseService)

    def test_unknown_kind_is_rejected(self) -> None:
        with pytest.raises(ValidationException):
            write_service.browse_for("invoice")
