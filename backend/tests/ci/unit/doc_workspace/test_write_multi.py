"""四条写路径：单段 / 批量 / 批注 / 只画布，以及「画布开着」的路由。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 批量全或无 | 半改过的文件既不是原稿也不是审完稿，律师无法判断哪几条生效了 |
| 同批重复锚点直接拒 | 第一条落笔后原文变成改写文本，第二条要么定位失败要么双重修改 |
| 批注读得出、作者是法穿AI | 导出 docx 给客户时意见全丢（只剩侧栏清单） |
| 批注部分成功仍落盘 | 「因为第三条锚不到就把前两条丢掉」让律师白等 |
| `apply_in_canvas` 不写盘 | 律师在画布里逐条采纳时中途落盘会打断工作流 |
| 画布开着时 `mirror_to_canvas=true` | 律师看不到修订痕迹长出来，以为 AI 没干活 |
| `w:id` 接续文档里已有的修订 | 撞号 → Word 判定文档损坏，整份合同打不开 |
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml.ns import qn

from apps.core.exceptions import ConflictError, ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService
from apps.doc_workspace.services import presence, write_service
from apps.doc_workspace.services.docx.revision import AI_AUTHOR
from apps.doc_workspace.services.docx.text import iter_paragraphs, visible_text

pytestmark = pytest.mark.django_db

KIND = "contract"
OWNER_ID = 613
SUBPATH = "1-合同/a.docx"
P1 = "甲方愿意支付人民币壹万元整。"
P2 = "乙方应当在三十日内完成交付。"
P3 = "本协议自双方签字之日起生效。"


class _Service(BoundFolderBrowseService):
    root: Path

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _require_access(self, **_kw: Any) -> None:
        return None

    def _local_root(self, _owner_id: int) -> Path:
        return self.root


def _plain_docx() -> bytes:
    doc = Document()
    for text in (P1, P2, P3):
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def folder_root(tmp_path: Path) -> Path:
    d = tmp_path / "1-合同"
    d.mkdir(parents=True)
    (d / "a.docx").write_bytes(_plain_docx())
    return tmp_path


@pytest.fixture
def wired(monkeypatch: Any, folder_root: Path) -> Path:
    from apps.contracts.services.contract.integrations import folder_browse_service as mod

    monkeypatch.setattr(mod, "ContractFolderBrowseService", lambda: _Service(folder_root))
    return folder_root


def _path(root: Path) -> Path:
    return root / "1-合同" / "a.docx"


def _text(root: Path) -> str:
    doc = Document(io.BytesIO(_path(root).read_bytes()))
    return "\n".join(visible_text(p) for p in iter_paragraphs(doc))


def _zip_names(root: Path) -> list[str]:
    with zipfile.ZipFile(_path(root)) as zf:
        return zf.namelist()


def _comments_xml(root: Path) -> str:
    with zipfile.ZipFile(_path(root)) as zf:
        return zf.read("word/comments.xml").decode("utf-8")


def _document_xml(root: Path) -> str:
    with zipfile.ZipFile(_path(root)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


class TestApplyBatchAllOrNothing:
    def test_one_bad_anchor_writes_nothing(self, wired: Path) -> None:
        before = _path(wired).read_bytes()

        result = write_service.apply_batch(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            patches=[
                {"selection": P1, "suggested": "甲方同意支付人民币壹万元整。"},
                {"selection": "这句话根本不在文档里", "suggested": "随便"},
                {"selection": P3, "suggested": "本协议自双方签字并盖章之日起生效。"},
            ],
        )

        assert result["applied"] is False
        assert result["failed_index"] == 1
        assert _path(wired).read_bytes() == before

    def test_success_lands_every_patch(self, wired: Path) -> None:
        result = write_service.apply_batch(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            patches=[
                {"selection": P1, "suggested": "甲方同意支付人民币壹万元整。"},
                {"selection": P2, "suggested": "乙方应当在十五日内完成交付。"},
            ],
        )

        assert result["applied"] is True
        assert result["count"] == 2
        assert len(result["rev_ids"]) == 4  # 每条一个 del + 一个 ins
        text = _text(wired)
        assert "甲方同意支付人民币壹万元整。" in text
        assert "乙方应当在十五日内完成交付。" in text
        assert P1 not in text
        assert P2 not in text

    def test_duplicate_anchor_in_same_batch_is_rejected(self, wired: Path) -> None:
        before = _path(wired).read_bytes()
        result = write_service.apply_batch(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            patches=[
                {"selection": P1, "suggested": "改法甲"},
                {"selection": P1, "suggested": "改法乙"},
            ],
        )
        assert result["applied"] is False
        assert "同一段原文" in result["reason"]
        assert _path(wired).read_bytes() == before

    def test_mtime_conflict_writes_nothing(self, wired: Path) -> None:
        before = _path(wired).read_bytes()
        with pytest.raises(ConflictError):
            write_service.apply_batch(
                kind=KIND,
                owner_id=OWNER_ID,
                subpath=SUBPATH,
                patches=[{"selection": P1, "suggested": "甲方同意支付。"}],
                base_mtime=1.0,
            )
        assert _path(wired).read_bytes() == before

    def test_empty_patches_rejected(self, wired: Path) -> None:
        with pytest.raises(ValidationException):
            write_service.apply_batch(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, patches=[])


class TestComments:
    def test_comment_lands_in_docx(self, wired: Path) -> None:
        result = write_service.apply_comments(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            comments=[{"selection": P1, "text": "违约金无上限，是否接受取决于谈判地位。"}],
        )

        assert result["applied"] is True
        assert len(result["comment_ids"]) == 1
        assert "word/comments.xml" in _zip_names(wired)

        comments_xml = _comments_xml(wired)
        assert "违约金无上限" in comments_xml
        # 批注里第一条就要写清针对哪句原文 —— 锚点落在整段，靠它告诉律师具体所指
        assert f"【原文】{P1}" in comments_xml
        assert AI_AUTHOR in comments_xml

        # 正文里要有锚点标记，否则 Word 不认为这条批注挂在哪
        doc_xml = _document_xml(wired)
        assert "commentRangeStart" in doc_xml
        assert "commentRangeEnd" in doc_xml
        assert "commentReference" in doc_xml

    def test_comment_does_not_change_body_text(self, wired: Path) -> None:
        write_service.apply_comments(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, comments=[{"selection": P2, "text": "建议明确起算点。"}]
        )
        text = _text(wired)
        for original in (P1, P2, P3):
            assert original in text

    def test_partial_success_still_writes(self, wired: Path) -> None:
        """批注不改正文：一条锚不到不该让另外两条白跑。"""
        result = write_service.apply_comments(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            comments=[
                {"selection": P1, "text": "第一条意见"},
                {"selection": "文档里没有这句话", "text": "锚不到"},
            ],
        )

        assert result["applied"] is True
        assert len(result["comment_ids"]) == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0]["index"] == 1
        assert "第一条意见" in _comments_xml(wired)

    def test_all_failures_writes_nothing(self, wired: Path) -> None:
        before = _path(wired).read_bytes()
        result = write_service.apply_comments(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath=SUBPATH,
            comments=[{"selection": "不存在", "text": "x"}],
        )
        assert result["applied"] is False
        assert _path(wired).read_bytes() == before

    def test_empty_text_rejected(self, wired: Path) -> None:
        with pytest.raises(ValidationException):
            write_service.apply_comments(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, comments=[])


class TestApplyInCanvas:
    def test_never_touches_disk(self, wired: Path) -> None:
        before = _path(wired).read_bytes()
        result = write_service.apply_in_canvas(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, patches=[{"selection": P1, "suggested": "改后"}]
        )

        assert result["mode"] == "canvas"
        assert result["wrote_disk"] is False
        assert result["patches"] == [{"orig": P1, "sug": "改后"}]
        assert _path(wired).read_bytes() == before


class TestPresenceRouting:
    def test_disk_by_default(self, wired: Path) -> None:
        assert write_service.write_target(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH) == "disk"

    def test_canvas_marks_mirror_but_still_writes_disk(self, wired: Path) -> None:
        """画布开着 → 写盘 **且** 要求前端重放。

        只写画布的话，重放失败（插件未握手 / 锚点漂移）会让这次 AI 改动凭空消失。
        """
        presence.mark_open(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, user_id=1)

        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=P1, suggested="甲方同意支付人民币壹万元整。"
        )

        assert result["applied"] is True
        assert result["mirror_to_canvas"] is True
        assert "甲方同意支付人民币壹万元整。" in _text(wired)

    def test_closed_presence_disables_mirror(self, wired: Path) -> None:
        presence.mark_open(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, user_id=1)
        presence.mark_closed(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH)

        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=P1, suggested="甲方同意支付人民币壹万元整。"
        )
        assert result["mirror_to_canvas"] is False


class TestRevIdContinuity:
    def test_ids_continue_existing_revision_ids(self, wired: Path) -> None:
        """文档里已有 `w:id=42` 的修订时，新修订必须从 43 起。

        撞号 → Word 判定文档损坏，整份合同打不开（真机错误是「文件已损坏，无法打开」）。
        """
        doc = Document(io.BytesIO(_path(wired).read_bytes()))
        paragraph = doc.paragraphs[0]
        existing = paragraph._element.makeelement(qn("w:ins"), {})
        existing.set(qn("w:id"), "42")
        existing.set(qn("w:author"), "张律师")
        existing.set(qn("w:date"), "2026-11-01T00:00:00Z")
        run = paragraph._element.makeelement(qn("w:r"), {})
        text = paragraph._element.makeelement(qn("w:t"), {})
        text.text = "（原有插入）"
        run.append(text)
        existing.append(run)
        paragraph._element.append(existing)
        buf = io.BytesIO()
        doc.save(buf)
        _path(wired).write_bytes(buf.getvalue())

        result = write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=P2, suggested="乙方应当在十五日内完成交付。"
        )

        assert result["applied"] is True
        new_ids = [i for i in result["rev_ids"] if i > 42]
        assert new_ids, f"新修订号必须接在 42 之后，实际 {result['rev_ids']}"

    def test_author_is_the_single_ai_constant(self, wired: Path) -> None:
        write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=P1, suggested="甲方同意支付人民币壹万元整。"
        )
        doc_xml = _document_xml(wired)
        # 文档里只该出现一个 AI 作者名（历史上曾有 法穿AI / 法穿SI 并存）
        assert doc_xml.count(AI_AUTHOR) >= 2  # del + ins 各一次
        assert "法穿SI" not in doc_xml


class TestReadRevisions:
    def test_lists_existing_revisions_with_author(self, wired: Path) -> None:
        """AI 改之前要能看见「文档里已经有的修订」，否则会把同一件事再提一遍。"""
        write_service.apply_span(
            kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH, selection=P1, suggested="甲方同意支付人民币壹万元整。"
        )

        items = write_service.read_revisions(kind=KIND, owner_id=OWNER_ID, subpath=SUBPATH)

        assert len(items) == 1
        assert items[0]["author"] == AI_AUTHOR
        assert items[0]["original"] == P1
        assert items[0]["suggested"] == "甲方同意支付人民币壹万元整。"
        assert items[0]["rev_ids"]


class TestCreateFile:
    def test_creates_docx_in_folder_without_overwriting(self, wired: Path) -> None:
        first = write_service.create_file(
            kind=KIND, owner_id=OWNER_ID, subpath_dir="1-合同", name="新文书", paragraphs=["第一段", "第二段"]
        )
        second = write_service.create_file(
            kind=KIND, owner_id=OWNER_ID, subpath_dir="1-合同", name="新文书", paragraphs=["另一份"]
        )

        assert first["created"] is True
        assert first["name"] == "新文书.docx"
        # 同名不覆盖：第二份自动加序号
        assert second["name"] != first["name"]
        assert (wired / "1-合同" / first["name"]).exists()
        assert (wired / "1-合同" / second["name"]).exists()
        # 原文件仍在
        assert (wired / "1-合同" / "a.docx").exists()

    def test_markdown_becomes_paragraphs_without_keeping_syntax(self, wired: Path) -> None:
        result = write_service.create_file(
            kind=KIND,
            owner_id=OWNER_ID,
            subpath_dir="1-合同",
            name="草稿",
            markdown="# 标题\n\n正文第一段\n\n正文第二段",
        )
        data = (wired / "1-合同" / result["name"]).read_bytes()
        doc = Document(io.BytesIO(data))
        texts = [p.text for p in doc.paragraphs if p.text]
        assert texts == ["标题", "正文第一段", "正文第二段"]
        # Markdown 标记不能落到正式文书里
        assert not any("#" in t for t in texts)

    def test_empty_content_rejected(self, wired: Path) -> None:
        with pytest.raises(ValidationException):
            write_service.create_file(kind=KIND, owner_id=OWNER_ID, subpath_dir="1-合同", name="空")

    def test_file_url_matches_editor_shape(self, wired: Path) -> None:
        result = write_service.create_file(
            kind=KIND, owner_id=OWNER_ID, subpath_dir="1-合同", name="x", paragraphs=["内容"]
        )
        assert result["file_url"].startswith(f"/api/v1/contracts/{OWNER_ID}/folder-file?subpath=")
