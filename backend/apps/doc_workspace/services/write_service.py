"""对「项目文件夹里的那一份文件」落笔的唯一入口。

## 为什么必须收成一个入口

在它之前，同一份 docx 有三条互不相通的写路径：

| 路径 | 谁在用 | 问题 |
|---|---|---|
| `/contract-review/direct-edit/apply` | MCP `rewrite_folder_file` | 端点在待删除的 app 里；**不传 `expect_mtime`**，等于主动放弃乐观锁 |
| `/contract-review/direct-edit/patch/*` | 只有 AI 可达 | 挂在同一个待删 app 下，且没有 UI 入口 |
| 插件桥 `apply-revision` | 画布内 | 只改画布不写盘 |

三条路径各自实现「怎么定位原文、怎么造 `w:ins`、作者叫什么」，于是漂移成了
两套作者名、两套定位口径（其中一套还不看表格）。

**路由规则（唯一一条，改之前先想清楚）**：

    画布开着 → 只写画布；画布没开 → 只写磁盘。二者永不同时发生。

同一次改写既写盘又在画布上重放，会出现「修订痕迹落两遍」；而且写盘会让画布
代次落后于磁盘，律师接下来的保存就被判成「旧画布」而丢弃（真的踩过）。
现阶段 `apply_span` 只实现「写磁盘」这一半，画布侧的编排在 `canvas` 模块里加。
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

from docx import Document

from apps.core.exceptions import ConflictError, ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

from .docx.comments import add_comment
from .docx.locate import LocateFailure, locate
from .docx.revision import apply_revision, enable_track_changes, resolve_ai_author

logger = logging.getLogger(__name__)

KIND_CONTRACT = "contract"
KIND_CASE = "case"
_ALLOWED_KINDS = (KIND_CONTRACT, KIND_CASE)


def browse_for(kind: str) -> BoundFolderBrowseService:
    """合同/案件绑定文件夹服务（各自带行级 ACL）。

    **不能用基类 `BoundFolderBrowseService`**：它只做路径解析，没有 ACL——
    直接拿它会让「律师 A 能改律师 B 的文件」成真。
    """
    if kind == KIND_CONTRACT:
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        return ContractFolderBrowseService()
    if kind == KIND_CASE:
        from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService

        return CaseFolderBrowseService()
    raise ValidationException(message=f"不支持的文件夹类型：{kind}", errors={"kind": kind})


def editor_source_path(kind: str, owner_id: int, subpath: str) -> str:
    """站内路径，口径与前端 `folderFileUrl` **逐字一致**。

    这条串是 `EditorSession.source_path` 的唯一共同语言：签发配置、保存回调、
    key 轮换三处都靠它相认。只要有一处 quote 口径不同，就会派生出不同的
    `task_id`，表现为「明明开着却找不到会话」。
    """
    base = "/api/v1/cases" if kind == KIND_CASE else "/api/v1/contracts"
    return f"{base}/{owner_id}/folder-file?subpath={quote(subpath, safe='')}"


def task_type_of(kind: str) -> str:
    return "case_folder" if kind == KIND_CASE else "contract_folder"


def _bump_editor(kind: str, owner_id: int, subpath: str) -> None:
    """磁盘被外部改写后轮换 DS 的 document key（否则画布永远回旧缓存）。"""
    from apps.onlyoffice.services.callback_service import bump_external_write

    try:
        bump_external_write(editor_source_path(kind, owner_id, subpath), task_type=task_type_of(kind))
    except (OSError, ValueError, RuntimeError, KeyError):
        # 修订已经落盘，画布刷新是增强不是前提，不该让改写整体报错
        logger.warning("落笔后轮换编辑器 key 失败（不影响已落盘的修订）", exc_info=True)


def _require(kind: str, owner_id: int, subpath: str) -> None:
    if kind not in _ALLOWED_KINDS:
        raise ValidationException(message=f"kind 必须是 {'/'.join(_ALLOWED_KINDS)}", errors={"kind": kind})
    if not isinstance(owner_id, int) or isinstance(owner_id, bool) or owner_id <= 0:
        raise ValidationException(message="owner_id 必须是正整数", errors={"owner_id": owner_id})
    if not (subpath or "").strip():
        raise ValidationException(message="subpath 不能为空", errors={"subpath": subpath})
    if not subpath.lower().endswith(".docx"):
        raise ValidationException(message="暂时只支持 docx 的修订落笔", errors={"subpath": subpath})


def write_bytes(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    data: bytes,
    expect_mtime: float | None = None,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """整份字节原地覆写（回滚历史版本、批量渲染产物落回原文件走它）。

    **不在这里做快照**：调用方必须自己先 `snapshot_service.capture()`。
    唯一允许直接调它的场景是「回滚」，因为回滚在调用之前已经快照过当前内容
    （见 `snapshot_service.restore`）。
    """
    _require(kind, owner_id, subpath)
    result = browse_for(kind).save_file_content(
        owner_id=owner_id,
        subpath=subpath,
        data=data,
        expect_mtime=expect_mtime,
        user=user,
        org_access=org_access,
        perm_open_access=False,
    )
    _bump_editor(kind, owner_id, subpath)
    return dict(result)


#: 与 `apps/core/filesystem/bound_folder_browse.py` 里 `save_file_content` 的容差一致：
#: 不同文件系统的 mtime 精度不同（ext4 纳秒 / HFS+ 秒），严格相等会误报冲突。
_MTIME_TOLERANCE = 1.0


TARGET_DISK = "disk"
TARGET_CANVAS = "canvas"


def write_target(*, kind: str, owner_id: int, subpath: str, user: Any = None) -> str:
    """这次写要不要**同时**下发画布重放。

    **注意：这个值不决定「写不写盘」。** 两种情况都写盘：

    | 画布 | 行为 | 理由 |
    |---|---|---|
    | 开着 | 写盘 + `mirror_to_canvas=True` | 律师立刻看到痕迹；重放失败也不会丢内容 |
    | 没开 | 只写盘 | 没人需要重放 |

    计划阶段曾写成「画布开着就只写画布」，那样重放失败（插件未握手 / 锚点漂移）
    就等于这次 AI 改动凭空消失，而律师看不到任何报错。落盘兜底的成本是一次
    原子写，换来的是「绝不因重放失败而丢内容」。
    """
    from . import presence

    if presence.is_open(kind=kind, owner_id=owner_id, subpath=subpath):
        return TARGET_CANVAS
    return TARGET_DISK


def _require_dir(kind: str, owner_id: int, subpath_dir: str) -> None:
    """目录版校验：`subpath` 是**目录**，不该过 `.docx` 那道门。"""
    if kind not in _ALLOWED_KINDS:
        raise ValidationException(message=f"kind 必须是 {'/'.join(_ALLOWED_KINDS)}", errors={"kind": kind})
    if not isinstance(owner_id, int) or isinstance(owner_id, bool) or owner_id <= 0:
        raise ValidationException(message="owner_id 必须是正整数", errors={"owner_id": owner_id})
    if ".." in (subpath_dir or "").split("/"):
        raise ValidationException(message="目标目录不能跳出绑定根", errors={"subpath_dir": subpath_dir})


def read_bytes(*, kind: str, owner_id: int, subpath: str, user: Any = None, org_access: Any = None) -> bytes:
    return read_bytes_with_mtime(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)[0]


def read_bytes_with_mtime(
    *, kind: str, owner_id: int, subpath: str, user: Any = None, org_access: Any = None
) -> tuple[bytes, float]:
    """读文件字节 + 当下 mtime（mtime 用于乐观锁）。"""
    svc = browse_for(kind)
    path = Path(
        svc.resolve_file(
            owner_id=owner_id,
            subpath=subpath,
            user=user,
            org_access=org_access,
            perm_open_access=False,
        )
    )
    return path.read_bytes(), path.stat().st_mtime


def assert_mtime_current(*, actual: float, expected: float | None) -> None:
    """提前撞一下乐观锁，**在写任何东西之前**。

    为什么要有这一步：快照必须在覆盖**之前**拍，但如果等到
    `save_file_content` 才报 409，那时已经多留了一版「和当前内容一模一样」的
    快照，时间线上会凭空多出一条不存在的版本。先撞锁再快照，顺序才对。
    """
    if expected is None:
        return
    if abs(actual - expected) > _MTIME_TOLERANCE:
        raise ConflictError(
            message="文件已被他人修改，请重新读取后再修改",
            code="FILE_MODIFIED",
            errors={"mtime": actual, "expect": expected},
        )


def apply_span(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    selection: str,
    suggested: str,
    base_mtime: float | None = None,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """把 `selection` 换成 `suggested`，以 Word 修订痕迹写回**原文件**。

    `base_mtime` 是打开时文件的 mtime。传了就做乐观锁校验：两人同开同一份时，
    后写的一方 mtime 已经变了，直接覆写会静默丢掉前一个人的修改。
    **AI 路径也必须传**——历史上这一条被漏掉过，等于 AI 拥有比人更大的写权限。
    """
    _require(kind, owner_id, subpath)
    if not (selection or "").strip():
        raise ValidationException(message="selection 不能为空：它是定位锚点", errors={"selection": selection})
    if not (suggested or "").strip():
        raise ValidationException(message="suggested 不能为空", errors={"suggested": suggested})

    raw, mtime = read_bytes_with_mtime(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)
    assert_mtime_current(actual=mtime, expected=base_mtime)
    doc = Document(BytesIO(raw))

    hit = locate(doc, selection)
    if isinstance(hit, LocateFailure):
        return {"applied": False, "reason": hit.reason, "candidates": hit.candidates}

    enable_track_changes(doc)
    result = apply_revision(hit.paragraph, selection, suggested, author=resolve_ai_author())
    if not result.ok:
        return {"applied": False, "reason": result.reason}

    buffer = BytesIO()
    doc.save(buffer)

    # **先留底再覆盖**：这是「改坏了能救回来」的唯一保障。顺序不能反——
    # 反过来一旦写盘中途失败，旧内容就永远没了。
    from . import snapshot_service

    snapshot_service.capture(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        data=raw,
        reason=snapshot_service.SnapshotReason.AI_REWRITE,
        source_mtime=mtime,
        actor_kind=snapshot_service.ActorKind.AI,
        actor_id=getattr(user, "pk", None),
    )

    # 乐观锁与原子替换都在 `save_file_content` 里（不传 expect_mtime 就等于放弃
    # 那道锁，所以 AI 路径也必须带上它）
    browse_for(kind).save_file_content(
        owner_id=owner_id,
        subpath=subpath,
        data=buffer.getvalue(),
        expect_mtime=base_mtime,
        user=user,
        org_access=org_access,
        perm_open_access=False,
    )

    _bump_editor(kind, owner_id, subpath)
    logger.info(
        "AI 修订已落盘: kind=%s owner=%s subpath=%s how=%s rev_ids=%s",
        kind,
        owner_id,
        subpath,
        result.how,
        result.rev_ids,
    )
    return {
        "applied": True,
        "kind": kind,
        "owner_id": owner_id,
        "subpath": subpath,
        "how": result.how,
        "mode": "disk",
        "author": resolve_ai_author(),
        "rev_ids": list(result.rev_ids),
        "file_url": editor_source_path(kind, owner_id, subpath),
        # 画布开着时前端要把这条修订重放进当前画布（免整页重载）。
        # 重放成功必须调 `/onlyoffice/canvas-ack`，否则后续保存会被当成旧画布丢掉。
        "mirror_to_canvas": write_target(kind=kind, owner_id=owner_id, subpath=subpath, user=user) == TARGET_CANVAS,
    }


def apply_batch(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    patches: list[dict[str, str]],
    base_mtime: float | None = None,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """一次落多条修订，**全或无**。

    ## 为什么必须全或无

    十条修订里第七条定位不到时，只写入前六条的结果是「半改过的文件」：律师看到
    的是一份既不是原稿也不是审完稿的文本，且无法判断哪几条生效了。宁可整批
    不写，让他重新框选。

    实现上的保证很简单：**所有修改都在内存里做，只有全部成功才落盘**。
    任何一条失败就直接返回，磁盘一个字节都不变。

    ## 同批重复锚点直接判失败

    两条 patch 用同一段原文时，第一条落笔后原文就变成了改写后的文本，第二条要
    么定位失败、要么在改写文本里又一次命中（双重修改）。两种都是错，所以**先查重**。
    """
    _require(kind, owner_id, subpath)
    if not patches:
        raise ValidationException(message="patches 不能为空", errors={"patches": []})

    seen: dict[str, int] = {}
    for index, patch in enumerate(patches):
        selection = str(patch.get("selection") or "")
        suggested = str(patch.get("suggested") or "")
        if not selection.strip():
            return {"applied": False, "reason": f"第 {index + 1} 条的 selection 为空", "failed_index": index}
        if not suggested.strip():
            return {"applied": False, "reason": f"第 {index + 1} 条的 suggested 为空", "failed_index": index}
        from .docx.text import normalize

        key = normalize(selection)
        if key in seen:
            return {
                "applied": False,
                "reason": (
                    f"第 {index + 1} 条与第 {seen[key] + 1} 条用了同一段原文，无法判断改哪一处；"
                    "请把各自的原文片段加长到彼此不同"
                ),
                "failed_index": index,
            }
        seen[key] = index

    raw, mtime = read_bytes_with_mtime(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)
    assert_mtime_current(actual=mtime, expected=base_mtime)

    doc = Document(BytesIO(raw))
    enable_track_changes(doc)
    rev_ids: list[int] = []

    for index, patch in enumerate(patches):
        selection = str(patch.get("selection") or "").strip()
        suggested = str(patch.get("suggested") or "").strip()
        hit = locate(doc, selection)
        if isinstance(hit, LocateFailure):
            return {
                "applied": False,
                "reason": f"第 {index + 1} 条：{hit.reason}",
                "failed_index": index,
            }
        result = apply_revision(hit.paragraph, selection, suggested, author=resolve_ai_author())
        if not result.ok:
            return {
                "applied": False,
                "reason": f"第 {index + 1} 条：{result.reason}",
                "failed_index": index,
            }
        rev_ids.extend(result.rev_ids)

    buffer = BytesIO()
    doc.save(buffer)

    from . import snapshot_service

    snapshot_service.capture(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        data=raw,
        reason=snapshot_service.SnapshotReason.AI_REVIEW_APPLY,
        source_mtime=mtime,
        actor_kind=snapshot_service.ActorKind.AI,
        actor_id=getattr(user, "pk", None),
    )
    browse_for(kind).save_file_content(
        owner_id=owner_id,
        subpath=subpath,
        data=buffer.getvalue(),
        expect_mtime=base_mtime,
        user=user,
        org_access=org_access,
        perm_open_access=False,
    )
    _bump_editor(kind, owner_id, subpath)
    logger.info("批量修订已落盘: %s/%s/%s 共 %d 条", kind, owner_id, subpath, len(patches))
    return {
        "applied": True,
        "mode": "disk",
        "count": len(patches),
        "author": resolve_ai_author(),
        "rev_ids": rev_ids,
        "file_url": editor_source_path(kind, owner_id, subpath),
        "mirror_to_canvas": write_target(kind=kind, owner_id=owner_id, subpath=subpath, user=user) == TARGET_CANVAS,
    }


def apply_comments(
    *,
    kind: str,
    owner_id: int,
    subpath: str,
    comments: list[dict[str, str]],
    base_mtime: float | None = None,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """给若干段挂批注（不改正文）。

    与 `apply_batch` 不同：批注**不做全或无**。批注不改变正文，部分成功仍然是
    一份完整可用的文档；反而是「因为第三条锚不到就把前两条也丢掉」会让律师白等。
    """
    _require(kind, owner_id, subpath)
    if not comments:
        raise ValidationException(message="comments 不能为空", errors={"comments": []})

    raw, mtime = read_bytes_with_mtime(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)
    assert_mtime_current(actual=mtime, expected=base_mtime)
    doc = Document(BytesIO(raw))

    landed: list[int] = []
    failures: list[dict[str, Any]] = []
    for index, item in enumerate(comments):
        selection = str(item.get("selection") or "").strip()
        text = str(item.get("text") or "").strip()
        if not text:
            failures.append({"index": index, "reason": "批注内容为空"})
            continue
        if not selection:
            failures.append({"index": index, "reason": "缺少定位原文"})
            continue
        hit = locate(doc, selection)
        if isinstance(hit, LocateFailure):
            failures.append({"index": index, "reason": hit.reason})
            continue
        # `quote` 可由调用方覆盖：占位符批注的锚点本身就是占位文字，再回显一遍是噪声。
        quote = str(item.get("quote", selection))
        outcome = add_comment(hit.paragraph, text=text, quote=quote, author=resolve_ai_author())
        if outcome.ok:
            landed.append(outcome.comment_id)
        else:
            failures.append({"index": index, "reason": outcome.reason})

    if not landed:
        return {"applied": False, "reason": "所有批注都没能定位到原文", "failures": failures}

    buffer = BytesIO()
    doc.save(buffer)
    from . import snapshot_service

    snapshot_service.capture(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        data=raw,
        reason=snapshot_service.SnapshotReason.AI_REVIEW_APPLY,
        source_mtime=mtime,
        actor_kind=snapshot_service.ActorKind.AI,
        actor_id=getattr(user, "pk", None),
    )
    browse_for(kind).save_file_content(
        owner_id=owner_id,
        subpath=subpath,
        data=buffer.getvalue(),
        expect_mtime=base_mtime,
        user=user,
        org_access=org_access,
        perm_open_access=False,
    )
    _bump_editor(kind, owner_id, subpath)
    return {
        "applied": True,
        "mode": "disk",
        "comment_ids": landed,
        "failures": failures,
        "file_url": editor_source_path(kind, owner_id, subpath),
        "mirror_to_canvas": write_target(kind=kind, owner_id=owner_id, subpath=subpath, user=user) == TARGET_CANVAS,
    }


def apply_in_canvas(*, kind: str, owner_id: int, subpath: str, patches: list[dict[str, str]]) -> dict[str, Any]:
    """**只下发画布，不碰磁盘**。

    仅用于前端自己编排的流程（例如律师在审查清单里逐条采纳：他要的是「先在画布
    里看到痕迹，最后一起保存」，中途落盘反而会打断这条工作流）。

    注意：这条路**没有落盘兜底**。重放失败就等于没改，所以它只应该用在
    「律师正看着画布、失败会立刻被看到」的场景；AI 工具调用一律走 `apply_span`。
    """
    _require(kind, owner_id, subpath)
    if not patches:
        raise ValidationException(message="patches 不能为空", errors={"patches": []})
    return {
        "applied": False,
        "mode": "canvas",
        "wrote_disk": False,
        "patches": [{"orig": str(p.get("selection") or ""), "sug": str(p.get("suggested") or "")} for p in patches],
        "file_url": editor_source_path(kind, owner_id, subpath),
    }


def read_revisions(
    *, kind: str, owner_id: int, subpath: str, user: Any = None, org_access: Any = None
) -> list[dict[str, Any]]:
    """列出文件里已有的修订（AI 据此避免重复提同一件事）。"""
    _require(kind, owner_id, subpath)
    from .docx.reader import read_revisions as _read

    doc = Document(BytesIO(read_bytes(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)))
    return [
        {
            "paragraph_index": r.paragraph_index,
            "author": r.author,
            "original": r.original,
            "suggested": r.suggested,
            "rev_ids": list(r.rev_ids),
        }
        for r in _read(doc)
    ]


def create_file(
    *,
    kind: str,
    owner_id: int,
    subpath_dir: str,
    name: str,
    paragraphs: list[str] | None = None,
    markdown: str = "",
    raw_docx: bytes | None = None,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """在文件夹里新建一份 docx（同名自动加序号，**绝不覆盖**）。

    `paragraphs` 给结构化段落；只给 `markdown` 时按空行切段，`#` 开头的行当标题。
    **不解释 Markdown 语法**：这里产出的是给律师改的正式文书，不是渲染预览——
    把 `**加粗**` 之类标记留在正文里是错的，所以只用标题层级和段落切分。
    """
    _require_dir(kind, owner_id, subpath_dir)
    if not (name or "").strip():
        raise ValidationException(message="name 不能为空", errors={"name": name})
    if not name.lower().endswith(".docx"):
        name = f"{name}.docx"

    if raw_docx is not None:
        # 起草链路：成稿已经是渲染好的 docx（模板骨架 + 填好的槽），不能再拆成段落
        paragraphs = []
        heading_flags = []
    elif not paragraphs:
        blocks: list[tuple[str, str]] = []
        for chunk in (markdown or "").split("\n\n"):
            text = chunk.strip()
            if not text:
                continue
            if text.startswith("#"):
                level = len(text) - len(text.lstrip("#"))
                blocks.append(("heading", text.lstrip("# ").strip() or "（无标题）"))
                del level
            else:
                blocks.append(("body", text))
        paragraphs = [t for _kind, t in blocks]
        heading_flags = [k == "heading" for k, _t in blocks]
    else:
        heading_flags = [False] * len(paragraphs)

    if raw_docx is not None:
        buffer = BytesIO(raw_docx)
    else:
        if not paragraphs:
            raise ValidationException(message="正文为空：至少给一段内容", errors={"markdown": markdown})
        doc = Document()
        for text, is_heading in zip(paragraphs, heading_flags, strict=False):
            doc.add_paragraph(text, style="Heading 1" if is_heading else None)
        buffer = BytesIO()
        doc.save(buffer)

    svc = browse_for(kind)
    result = svc.save_new_file(
        owner_id=owner_id,
        subpath=f"{subpath_dir.rstrip('/')}/__new__" if subpath_dir.strip() else "__new__",
        name=name,
        data=buffer.getvalue(),
        user=user,
        org_access=org_access,
        perm_open_access=False,
    )
    new_subpath = str((result or {}).get("subpath") or "")
    logger.info("已在文件夹新建文档: %s/%s %s -> %s", kind, owner_id, name, new_subpath)
    return {
        "created": True,
        "name": str((result or {}).get("name") or name),
        "subpath": new_subpath,
        "file_url": editor_source_path(kind, owner_id, new_subpath) if new_subpath else "",
    }
