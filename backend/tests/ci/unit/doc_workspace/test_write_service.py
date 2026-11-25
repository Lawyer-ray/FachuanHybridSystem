"""文档工作面的写入口：修订痕迹、表格定位、原文唯一性、mtime 乐观锁。

## 这些断言各自守一个真实故障

| 断言 | 不守会怎样 |
|---|---|
| `w:ins`/`w:del` 带 `法穿AI` 作者名 | 客户在 Word「审阅」里看不出哪条是 AI 提的 |
| 表格内的条款能定位 | 付款/验收条款最常放在表格里，定位不到 = 审了等于没审 |
| 原文不唯一就失败 | 改错位置。比改不动严重得多，且不可逆 |
| `base_mtime` 不符 → 409 且文件零改动 | 两人同开后写的一方静默覆盖前一个人的修改 |
| 归一化层能命中全半角/空白差异 | 画布里看到的是全角标点，模型给的是半角，逐字匹配必失败 |
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml.ns import qn

from apps.core.exceptions import ConflictError, ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.services import write_service
from apps.doc_workspace.services.docx.revision import AI_AUTHOR
from apps.doc_workspace.services.docx.text import iter_paragraphs, visible_text

# 落笔前会先拍快照（写库），所以整个模块都需要数据库
pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 411
SUBPATH = "1-合同/a.docx"
PARA = "甲方愿意支付人民币壹万元整。"
TABLE_CELL = "验收标准：以甲方书面确认为准。"
DUPLICATED = "本协议一式两份。"


class _Service(BoundFolderBrowseService):
    """绑定临时目录、无 ACL（权限口径由 API 层用例覆盖）。"""

    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


def _build_docx() -> bytes:
    doc = Document()
    doc.add_paragraph(PARA)
    doc.add_paragraph(DUPLICATED)
    doc.add_paragraph(DUPLICATED)
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = TABLE_CELL
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def folder_root(tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    (d / "a.docx").write_bytes(_build_docx())
    return tmp_path


@pytest.fixture
def wired(monkeypatch: Any, folder_root: Path) -> Path:
    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(folder_root))
    return folder_root


def _disk_doc(folder_root: Path) -> Any:
    return Document(BytesIO((folder_root / "1-合同" / "a.docx").read_bytes()))


def _all_text(folder_root: Path) -> str:
    return "\n".join(visible_text(p) for p in iter_paragraphs(_disk_doc(folder_root)))


def _revisions(folder_root: Path) -> list[tuple[str, str, str]]:
    """[(kind, author, text)]，kind ∈ ins/del，按文档顺序。"""
    doc = _disk_doc(folder_root)
    out: list[tuple[str, str, str]] = []
    for elem in doc.element.body.iter(qn("w:ins"), qn("w:del")):
        kind = "ins" if elem.tag == qn("w:ins") else "del"
        text = "".join(t.text or "" for t in elem.iter(qn("w:t"), qn("w:delText")))
        out.append((kind, elem.get(qn("w:author")) or "", text))
    return out


class TestApplySpan:
    def test_writes_revision_with_ai_author(self, wired: Path) -> None:
        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=PARA, suggested="甲方同意支付人民币壹万元整。"
        )

        assert result["applied"] is True
        assert result["author"] == AI_AUTHOR
        revs = _revisions(wired)
        assert ("del", AI_AUTHOR, PARA) in revs
        assert ("ins", AI_AUTHOR, "甲方同意支付人民币壹万元整。") in revs

    def test_visible_text_reflects_edit_but_original_survives_as_del(self, wired: Path) -> None:
        """现行文本 = 接受修订后的样子；原文只剩在 del 痕迹里（可回退）。"""
        write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=PARA, suggested="甲方同意支付人民币壹万元整。"
        )

        text = _all_text(wired)
        assert "甲方同意支付人民币壹万元整。" in text
        assert PARA not in text

    def test_tracks_track_changes_switch(self, wired: Path) -> None:
        """不打开 `w:trackChanges`，Word 会把 ins/del 当已接受文本显示成定稿。"""
        write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=PARA, suggested="甲方同意支付人民币壹万元整。"
        )
        settings_xml = _disk_doc(wired).settings.element.xml
        assert "trackChanges" in settings_xml

    def test_locates_clause_inside_table(self, wired: Path) -> None:
        """表格里的条款必须能定位——付款/验收条款最常放在表格。"""
        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="以甲方书面确认为准",
            suggested="以甲方书面确认且验收单签章为准",
        )

        assert result["applied"] is True
        assert "以甲方书面确认且验收单签章为准" in _all_text(wired)

    def test_normalized_match_handles_fullwidth_and_spaces(self, wired: Path) -> None:
        """画布上是全角标点、模型给半角 + 多余空格时，逐字匹配必然失败。"""
        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection="验收标准: 以甲方书面确认为准。",
            suggested="验收标准：以甲方书面确认并签章为准。",
        )

        assert result["applied"] is True
        assert result["how"] == "normalized"

    def test_duplicate_original_fails_instead_of_guessing(self, wired: Path) -> None:
        """原文出现两处时**必须失败**：改错位置比改不动严重得多。"""
        before = (wired / "1-合同" / "a.docx").read_bytes()

        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=DUPLICATED, suggested="本协议一式叁份。"
        )

        assert result["applied"] is False
        assert result["candidates"] >= 2
        assert "多次" in result["reason"]
        assert (wired / "1-合同" / "a.docx").read_bytes() == before  # 一个字都没写

    def test_missing_original_fails_without_writing(self, wired: Path) -> None:
        before = (wired / "1-合同" / "a.docx").read_bytes()
        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection="这句话根本不存在", suggested="随便"
        )
        assert result["applied"] is False
        assert (wired / "1-合同" / "a.docx").read_bytes() == before


class TestMtimeOptimisticLock:
    def test_stale_mtime_raises_conflict_and_writes_nothing(self, wired: Path) -> None:
        """AI 路径也必须走这道锁：不传等于 AI 拥有比人更大的写权限。"""
        before = (wired / "1-合同" / "a.docx").read_bytes()
        stale = 1.0  # 远早于真实 mtime

        with pytest.raises(ConflictError):
            write_service.apply_span(
                kind=KIND,
                owner_id=OWNER_ID,
                subpath=SUBPATH,
                selection=PARA,
                suggested="甲方同意支付人民币壹万元整。",
                base_mtime=stale,
            )

        assert (wired / "1-合同" / "a.docx").read_bytes() == before

    def test_matching_mtime_allows_write(self, wired: Path) -> None:
        mtime = (wired / "1-合同" / "a.docx").stat().st_mtime
        result = write_service.apply_span(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            selection=PARA,
            suggested="甲方同意支付人民币壹万元整。",
            base_mtime=mtime,
        )
        assert result["applied"] is True


class TestInputGuards:
    def test_rejects_non_docx(self, wired: Path) -> None:
        with pytest.raises(ValidationException):
            write_service.apply_span(
                kind=KIND, owner_id=OWNER_ID, subpath="1-合同/a.pdf", selection="x", suggested="y"
            )

    def test_rejects_unknown_kind(self, wired: Path) -> None:
        with pytest.raises(ValidationException):
            write_service.apply_span(kind="invoice", owner_id=OWNER_ID, subpath=SUBPATH, selection="x", suggested="y")

    def test_empty_selection_rejected(self, wired: Path) -> None:
        with pytest.raises(ValidationException):
            write_service.apply_span(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection="  ", suggested="y")

    def test_editor_source_path_matches_frontend_shape(self) -> None:
        """这条串是 EditorSession 的唯一共同语言，形状必须与 folderFileUrl 一致。"""
        assert (
            write_service.editor_source_path("contract", 12, "1-合同/a b.docx")
            == "/api/v1/contracts/12/folder-file?subpath=1-%E5%90%88%E5%90%8C%2Fa%20b.docx"
        )
        assert write_service.editor_source_path("case", 12, "a.docx") == "/api/v1/cases/12/folder-file?subpath=a.docx"
