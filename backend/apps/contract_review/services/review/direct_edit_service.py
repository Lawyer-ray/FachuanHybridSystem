"""划词直改的落盘：把「选区 → 改写文本」写成 Word 修订痕迹并覆写原文件。

## 为什么由后端改 docx，而不是让前端/插件就地替换

编辑器里就地替换（`Api.GetDocument().SearchAndReplace()`）看起来更「顺滑」，
但有两个硬伤：一是痕迹质量随 DS 版本漂移，二是同一份文件被两人同时编辑时
前端各改各的会互相覆盖。后端改 docx 走的是仓库里已验证的
`DocxRevisionTool`（`<w:del>` / `<w:ins>` 逐 run 定位，跨 run 也能命中），
产物是标准 OOXML 修订，Word / WPS / DS 都能认，且只有一次原子写。

代价是 DS 画布需要重载才能看到修订——这由前端调 forcesave/reload 解决，
不影响正确性。

## 为什么以「段落」为定位单位

`apply_revision` 吃的是 `Paragraph` 对象。选区可能跨段（律师从条款中间拉到
下一段），但一期只处理**单段内**的改写：跨段改写等于重排结构（编号、缩进、
但书位置），风险和收益不对等，且模型很容易把两段合成一段。跨段选区在
`_locate` 里直接判失败，让律师缩小选区——这比悄悄改错位置安全。
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocumentType

from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

from ..formatting.docx_revision_tool import DocxRevisionTool, enable_track_changes, visible_text

logger = logging.getLogger(__name__)

# 修订作者署名：显示在 Word 修订气泡里，让客户知道是 AI 改的而非律师本人
DEFAULT_AUTHOR = "法穿AI"


def _normalize(s: str) -> str:
    """比对用归一化（与 direct_editor._normalize 同口径）。"""
    import re

    return re.sub(r"[\s\u00a0\u3000]+", "", s or "")


def locate_paragraph(doc: DocumentType, selection: str) -> Any | None:
    """在所有段落里找包含选区原文的那一段。

    匹配用**现行文本**（visible_text：直接 run + 修订插入，不含已删内容），
    与编辑器/解析端看到的「接受修订后」文本同口径——python-docx 的
    para.text 看不见 w:ins，已改过一次的段落会永远定位失败。

    先用逐字 `in`（最可靠），失败再用归一化比对（应对编辑器与 python-docx
    在空白字符上的差异）。命中多段时取第一段——选区的字面内容在合同里重复
    并不常见，真有重复也应该由律师把选区拉长到唯一。
    """
    if not selection:
        return None
    for para in doc.paragraphs:
        if selection in visible_text(para):
            return para
    norm_sel = _normalize(selection)
    if not norm_sel:
        return None
    for para in doc.paragraphs:
        if norm_sel in _normalize(visible_text(para)):
            return para
    # 表格单元格里的条款同样是正文（付款方式、违约金常见于表格）
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if selection in visible_text(para) or norm_sel in _normalize(visible_text(para)):
                        return para
    return None


# ── 模块级工具函数（原类内静态方法；Service 层禁用静态方法装饰器，纯函数一律下沉）──


def _bump_editor_doc_key(*, owner_id: int, subpath: str) -> None:
    """覆写后轮换 OnlyOffice 文档 key（打开中的编辑器画布才能拿到新内容）。

    source_path 必须与前端签配置用的 file_url 逐字一致（`folderFileUrl` 的
    口径：`/api/v1/contracts/{id}/folder-file?subpath=<encodeURIComponent>`），
    同一路径才派生出同一 task_id，才轮换到正确文档的版本。失败只记
    warning：修订已经落盘，画布刷新是增强不是前提，不该让改写报错。
    """
    from urllib.parse import quote

    from apps.onlyoffice.services.callback_service import bump_external_write

    try:
        source_path = f"/api/v1/contracts/{owner_id}/folder-file?subpath={quote(subpath, safe='')}"
        bump_external_write(source_path, task_type="contract_folder")
    except Exception:
        logger.warning("划词直改后轮换编辑器文档 key 失败（不影响已落盘的修订）", exc_info=True)


def _browse() -> Any:
    """合同绑定文件夹的服务（带合同行级 ACL 与 ContractFolderBinding 解析）。

    不用基类 `BoundFolderBrowseService`：它只做路径解析，没有合同 ACL，
    也没有 `_local_root` 的绑定解析——直接拿它会让「律师 A 能改律师 B
    的合同文件夹」变成可能。
    """
    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    return ContractFolderBrowseService()


def _read_bytes(
    browse: BoundFolderBrowseService,
    *,
    owner_id: int,
    subpath: str,
    user: Any | None,
    org_access: dict[str, Any] | None,
    perm_open_access: bool,
) -> bytes:
    """取原文件字节。走 browse 的权限校验，不自己拼路径。"""
    try:
        path = browse.resolve_file(
            owner_id=owner_id,
            subpath=subpath,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
    except NotFoundError:
        raise
    except Exception as exc:
        # 权限不足等：统一收敛成 NotFound，不泄露「存在但无权」
        logger.warning("划词直改读取源文件失败 owner=%s subpath=%s: %s", owner_id, subpath, exc)
        raise NotFoundError(message="文件不存在或无权访问", code="FOLDER_NOT_FOUND") from exc
    return Path(path).read_bytes()


class DirectEditService:
    """读取文件夹 docx → 应用一条修订 → 原子覆写。"""

    def apply(
        self,
        *,
        owner_id: int,
        subpath: str,
        selection: str,
        suggested: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        author: str = DEFAULT_AUTHOR,
        expect_mtime: float | None = None,
    ) -> dict[str, Any]:
        """把 `selection → suggested` 写成修订痕迹并覆写原文件。

        返回 `{"applied": bool, "subpath": str, "name": str, "reason": str}`。
        定位失败不抛异常而是返回 `applied=False`：这是律师常见的操作结果
        （选区已被前一次改动破坏），前端要能给出「换个选区」的提示，而不是
        500 报错页。
        """
        if not (selection or "").strip():
            raise ValidationException(message="选区为空", errors={"selection": ""})
        if not (suggested or "").strip():
            raise ValidationException(message="改写结果为空", errors={"suggested": ""})
        if not subpath.lower().endswith(".docx"):
            raise ValidationException(message="只有 .docx 支持带修订痕迹的直改", errors={"subpath": subpath})

        browse = _browse()
        source = _read_bytes(
            browse,
            owner_id=owner_id,
            subpath=subpath,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

        doc = Document(BytesIO(source))
        para = locate_paragraph(doc, selection)
        if para is None:
            logger.info("划词直改：未定位到选区，跳过落盘 subpath=%s", subpath)
            return {
                "applied": False,
                "subpath": subpath,
                "name": Path(subpath).name,
                "reason": "文档中已找不到这段原文（可能已被改动），请重新框选",
            }

        # 强制打开修订模式：否则 apply_revision 插入的 <w:del>/<w:ins>
        # 在 Word 里会被当成已接受的普通文本，律师看不出改了什么
        enable_track_changes(doc)

        tool = DocxRevisionTool()
        ok = tool.apply_revision(para, selection, suggested, author=author)
        if not ok:
            logger.warning("划词直改：apply_revision 失败 subpath=%s selection=%s", subpath, selection[:60])
            return {
                "applied": False,
                "subpath": subpath,
                "name": Path(subpath).name,
                "reason": "无法在原文里精确落笔（选区可能跨段或含特殊格式），请缩小选区后重试",
            }

        buf = BytesIO()
        doc.save(buf)
        payload = buf.getvalue()

        browse.save_file_content(
            owner_id=owner_id,
            subpath=subpath,
            data=payload,
            # 与 DS 保存回写同口径：本次改动就是当前会话产生的，
            # 严格 mtime 校验只在「编辑器开着时文件被外部改动」时误报
            expect_mtime=expect_mtime,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )
        _bump_editor_doc_key(owner_id=owner_id, subpath=subpath)
        logger.info("划词直改已落盘: owner=%s subpath=%s 长度 %d→%d", owner_id, subpath, len(selection), len(suggested))
        return {"applied": True, "subpath": subpath, "name": Path(subpath).name, "reason": ""}


def get_direct_edit_service() -> DirectEditService:
    return DirectEditService()


__all__ = ["DEFAULT_AUTHOR", "DirectEditService", "get_direct_edit_service", "locate_paragraph"]
