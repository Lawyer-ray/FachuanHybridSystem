"""一句话起草用例：没有骨架就不生成、落位零命中只降一级、成功路径要能直开。

## 每条断言对应的真实后果

| 断言 | 不守会怎样 |
|---|---|
| 没有 `DocumentSpec` 就 `created=False` | 模型会现编一种格式，律师拿到一份根本不存在的文书样式 |
| 槽位零命中降级 `other_filing` 且带 warning | 文书悄悄落在别处，律师以为没生成；warning 是唯一的线索 |
| 兜底槽也没有时 `created=False` | 猜一条路径写进去 = 可能写进别人的案卷 |
| 成功路径返回 `file_url` 且不再回头猜路径 | 律师要「下载 → 找文件 → 上传」才算能改，这条链等于没做 |
| 未决项沿用 `<待填写：x>` + 批注 | 起草稿看起来完整、实际有坑，律师无从得知哪里空着 |

写盘与初审在用例层被替换成假实现：本文件测的是**编排决策**（生不生成、落哪、留什么痕），
不是 `write_service` / `review_pipeline` 自己的正确性——那两块各有自己的用例。
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import pytest
from docx import Document

from apps.doc_workspace.services import draft_by_type, review_pipeline, write_service
from apps.documents.services.draft import spec_service

pytestmark = pytest.mark.django_db

DOC_TYPE = "jurisdiction_objection"
DISPLAY_NAME = "管辖权异议申请书"


def _spec(*, folder_slot: str = DOC_TYPE) -> SimpleNamespace:
    """一条文书规格。真实类型是 `documents.DocumentSpec`，这里只用到属性。"""
    return SimpleNamespace(
        doc_type=DOC_TYPE,
        display_name=DISPLAY_NAME,
        skeleton_template_id=11,
        folder_slot=folder_slot,
        title_override="",
        is_active=True,
    )


def _folder_template(*kinds: str) -> SimpleNamespace:
    """一棵只有 `structure` 的文件夹树——`find_slot_paths` 也只读这一项。"""
    children = [
        {"id": f"node-{index}", "name": f"{index}-{kind}", "kind": kind, "children": []}
        for index, kind in enumerate(kinds, start=1)
    ]
    return SimpleNamespace(structure={"children": [{"id": "root", "name": "一审", "children": children}]})


def _skeleton(tmp_path: Any) -> str:
    path = tmp_path / "skeleton.docx"
    document = Document()
    document.add_paragraph(DISPLAY_NAME)
    document.add_paragraph("异议人：{{异议人}}")
    document.add_paragraph("此致")
    document.add_paragraph("{{法院名称}}")
    document.save(str(path))
    return str(path)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    *,
    kinds: tuple[str, ...],
    pending: list[str] | None = None,
    context: dict[str, str] | None = None,
    spec: SimpleNamespace | None = None,
) -> dict[str, Any]:
    """接好六个外部件（规格、事实、模板文件、文件夹树、写盘、初审），回传捕获到的调用。"""
    captured: dict[str, Any] = {"comments": [], "create_file": None, "comment_author": None}
    skeleton = _skeleton(tmp_path)

    monkeypatch.setattr(spec_service, "get_spec", lambda _doc_type: spec or _spec())
    monkeypatch.setattr(
        spec_service,
        "resolve_slot_values",
        lambda *_a, **_kw: (
            context if context is not None else {"异议人": "甲公司与乙公司", "法院名称": "海淀区人民法院"},
            pending or [],
        ),
    )
    monkeypatch.setattr(
        "apps.doc_workspace.services.queries.document_template_file", lambda _template_id: (None, skeleton)
    )
    monkeypatch.setattr(draft_by_type, "_folder_template_for", lambda _kind, _target: _folder_template(*kinds))
    monkeypatch.setattr(
        draft_by_type,
        "_load_case",
        lambda _case_id, _user, _org: SimpleNamespace(name="甲诉乙", case_type="civil", current_stage="first_trial"),
    )

    def _create_file(**kwargs: Any) -> dict[str, Any]:
        captured["create_file"] = kwargs
        base = "/api/v1/contracts" if kwargs["kind"] == "contract" else "/api/v1/cases"
        return {
            "created": True,
            "name": f"{DISPLAY_NAME}.docx",
            "subpath": f"{kwargs['subpath_dir']}/{DISPLAY_NAME}.docx",
            "file_url": f"{base}/{kwargs['owner_id']}/folder-file?subpath=draft.docx",
        }

    def _apply_comments(**kwargs: Any) -> dict[str, Any]:
        captured["comments"].extend(kwargs["comments"])
        captured["comment_author"] = kwargs.get("author")
        return {"applied": True}

    monkeypatch.setattr(write_service, "create_file", _create_file)
    monkeypatch.setattr(write_service, "apply_comments", _apply_comments)
    # 初审轮次同样替掉：真实的 `create_run` 会回头读文件（要 ACL + 磁盘），那属于
    # write_service / review_pipeline 自己的用例该管的事
    monkeypatch.setattr(review_pipeline, "create_run", lambda **_kwargs: SimpleNamespace(pk=7))
    return captured


def test_no_spec_means_no_document(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """规格表里没有这一行 → 不生成，并且**一个字都不写盘**。"""
    monkeypatch.setattr(spec_service, "get_spec", lambda _doc_type: None)

    def _never_called(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("没有骨架时不该走到写盘")

    monkeypatch.setattr(write_service, "create_file", _never_called)

    result = draft_by_type.draft_document(doc_type="判前财产保全申请书", case_id=1)

    assert result["created"] is False
    assert "还没有骨架" in result["reason"]
    assert "判前财产保全申请书" in result["reason"]
    assert result["doc_type"] == "判前财产保全申请书"
    assert result["file_url"] == ""


def test_missing_slot_degrades_to_other_filing(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """这个案件的文件夹里没有该槽位 → 只降级到 other_filing，并把降级原因说给律师听。"""
    captured = _wire(monkeypatch, tmp_path, kinds=("complaint", "other_filing"))

    result = draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017)

    assert result["created"] is True
    assert result["warnings"], "降级必须留 warning，否则律师不知道文书换了位置"
    assert draft_by_type.DEGRADED_SLOT in result["warnings"][0]
    assert captured["create_file"]["subpath_dir"] == "一审/2-other_filing"


def test_success_path_returns_openable_file_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """命中槽位 → 落进那一条路径，返回能直接交给画布的 file_url。"""
    captured = _wire(monkeypatch, tmp_path, kinds=(DOC_TYPE, "other_filing"))

    result = draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017)

    assert result["created"] is True
    assert result["subpath"].endswith(".docx")
    assert result["file_url"].startswith("/api/v1/cases/1017/folder-file")
    assert captured["create_file"]["subpath_dir"] == "一审/1-jurisdiction_objection"
    assert captured["create_file"]["kind"] == "case"
    assert result["slot_fill_rate"] == 1.0
    assert result["review_run_id"] == 7
    assert result["warnings"] == []


def test_no_placement_anywhere_refuses_to_guess(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """槽位与兜底槽都没有 → 不生成，并说清「这个案件的文件夹没有 X 的位置」。"""
    _wire(monkeypatch, tmp_path, kinds=("complaint", "defense"))

    result = draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017)

    assert result["created"] is False
    assert f"没有「{DISPLAY_NAME}」的位置" in result["reason"]
    assert draft_by_type.DEGRADED_SLOT in result["reason"]


def test_multiple_hits_take_the_first_and_warn(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """同一种槽位在同一棵树里出现多次 → 取第一处并说明，不静默挑一个。"""
    captured = _wire(monkeypatch, tmp_path, kinds=(DOC_TYPE, "complaint", DOC_TYPE))

    result = draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017)

    assert result["created"] is True
    assert any("2 处" in warning for warning in result["warnings"])
    assert captured["create_file"]["subpath_dir"] == "一审/1-jurisdiction_objection"


def test_pending_slots_are_annotated_with_the_shared_placeholder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """未决项沿用 `draft_service` 的 `<待填写：x>` 口径，批注锚点必须与正文逐字一致。"""
    captured = _wire(
        monkeypatch,
        tmp_path,
        kinds=(DOC_TYPE,),
        context={"异议人": "甲公司与乙公司"},
        pending=["法院名称"],
    )

    result = draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017, auto_review=False)

    assert result["created"] is True
    assert result["pending"] == ["法院名称"]
    assert result["slot_fill_rate"] == 0.5
    assert result["review_run_id"] is None
    assert captured["comments"] == [
        # 批注只指路、不复述：正文里已经摆着 `<待填写：法院名称>`，长文案会把批注栏
        # 撑成一篇说明文。见 `_pending_comment` 的 docstring。
        {"selection": "<待填写：法院名称>", "text": "待补：法院名称", "quote": ""}
    ]


def test_multi_line_slot_value_becomes_docx_paragraphs(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """模型爱回多段正文（`\n` 分段）；**成稿里必须是真的多段**，不能挤成一行。

    ## 这条用例曾经把 bug 当成预期行为（真机联调才发现）

    旧断言只看中间产物：`result["filled"]["法院名称"] == "第一段\a第二段"`——它验证的是
    「`_to_docx_text` 折了段落」，而 `\n → \a` 的归一化本该只在 `draft_service.render()`
    做一次。`to_body_text()` **不幂等**（它把输入自带的 `\a` 当 C0 剥掉），于是
    `_to_docx_text` 折一次、`render` 再折一次，第二次把刚插入的 `\a` 全吃掉——
    实测 5 段压成 1 行。旧断言正好在压塌之前的那一步，所以一路绿灯。

    **教训**：中间产物的形状不是用户看到的东西。这里改成解析成稿 docx 数段落。
    """
    captured = _wire(
        monkeypatch,
        tmp_path,
        kinds=(DOC_TYPE,),
        context={"异议人": "甲公司", "法院名称": "第一段\n第二段"},
    )

    draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017, auto_review=False)

    rendered = captured["create_file"]["raw_docx"]
    paragraphs = [p.text.strip() for p in Document(io.BytesIO(rendered)).paragraphs if p.text.strip()]
    assert "第一段" in paragraphs, paragraphs
    assert "第二段" in paragraphs, paragraphs
    assert "第一段第二段" not in paragraphs


def test_slot_text_is_not_refolded_before_render(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """归一化只有一处：`_to_docx_text` 不许折段落（折两次会把段落全压成一行）。

    这是上一条的根因锁：`to_body_text()` 不幂等，任何在 `render()` 之前再折一次的地方
    都会静默把多段正文压成一段。
    """
    value = "第一段\n第二段\n\n第四段"
    assert draft_by_type._to_docx_text(value) == value
    # 加粗仍要被换成哨兵（样式归本函数管）
    assert "\ue000" in draft_by_type._to_docx_text("**加粗**")


def test_comment_author_comes_from_the_request_not_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """批注署名**随本次起草请求**走：前端填什么就是什么，缺省 `Lawyer`。

    **为什么不能做成系统配置**：署名是「这一份文书上写什么名字」——同一个所里不同案子、
    不同客户的要求都可能不同。放系统配置等于让一个人替全所决定，而且改一次就悄悄改变
    所有人的历史习惯。这里守两条：传了就用传的；没传就是 `Lawyer`。
    """
    captured = _wire(monkeypatch, tmp_path, kinds=(DOC_TYPE,), pending=["法院名称"])
    draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017, comment_author="李助理", auto_review=False)
    assert captured["comment_author"] == "李助理"

    captured_default = _wire(monkeypatch, tmp_path, kinds=(DOC_TYPE,), pending=["法院名称"])
    draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1017, auto_review=False)
    assert captured_default["comment_author"] == ""


def test_contract_owner_writes_into_the_contract_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """合同侧的落位与案件侧同一套槽位，但写通道坐标必须换成 contract，否则写错文件夹。"""
    captured = _wire(monkeypatch, tmp_path, kinds=(DOC_TYPE,))
    monkeypatch.setattr(
        draft_by_type, "_load_contract", lambda _contract_id: SimpleNamespace(name="某合同", case_type="civil")
    )

    result = draft_by_type.draft_document(doc_type=DOC_TYPE, contract_id=318, auto_review=False)

    assert result["created"] is True
    assert captured["create_file"]["kind"] == "contract"
    assert captured["create_file"]["owner_id"] == 318
    assert result["file_url"].startswith("/api/v1/contracts/318/")


def test_requires_exactly_one_owner(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """两个都不给 / 都给 → 不生成：猜一个就是写进别人的案卷。"""
    monkeypatch.setattr(spec_service, "get_spec", lambda _doc_type: _spec())

    neither = draft_by_type.draft_document(doc_type=DOC_TYPE)
    both = draft_by_type.draft_document(doc_type=DOC_TYPE, case_id=1, contract_id=2)

    assert neither["created"] is False
    assert both["created"] is False
    assert "二选一" in neither["reason"]
    assert "二选一" in both["reason"]
