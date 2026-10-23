"""合同绑定文件夹引用 —— 「拖拽引用」型附件的创建、读取与页图渲染。

## 与上传附件（attachments.py）的关系

- 上传附件：字节复制进 media（``default_storage``），随会话生命周期清理；
- 文件夹引用：**不复制**，``AgentAttachment.storage_path`` 留空，读取时
  按需打开绑定文件夹里的原文件——文件更新读到最新，路径即归属。
  post_delete 物理清理只认 ``storage_path``，引用型天然不会误删业务原文件。

## 权限与安全口径

ACL、绑定根解析、子路径逃逸校验复用绑定浏览基类
``BoundFolderBrowseService``（行级 ACL + 拒 ``../``/绝对路径/盘符 +
``resolve()`` 后 ``is_relative_to`` 兜底符号链接）——合同走 contracts 的
``ContractFolderBrowseService``、案件走 cases 的
``CaseFolderBrowseService``，与各自 ``folder-entries`` 目录树同口径：
树里看得见的文件才读得到。

## 缓存

页图缓存键为 ``folder:{contract_id}/{subpath}?v={size}-{mtime}``：
源文件被替换后指纹变化、旧缓存自然失效，不会脏命中。
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from apps.core.exceptions import ValidationException

from ..models import AgentAttachment, AgentSession
from .attachments import _render_bytes_pages

if TYPE_CHECKING:
    from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

logger = logging.getLogger(__name__)

#: 引用读取的体积上限（附件上传流是 20MB；绑定文件夹里的原文件不受上传
#: 限制约束，这里必须自设钳制——否则一次引用几百 MB 的扫描卷宗/视频就是
#: 内存尖峰 + base64 翻倍）。
MAX_FOLDER_FILE_BYTES = 50 * 1024 * 1024


def _reject_oversize(size: int, *, ref: str) -> None:
    """超过读取上限直接拒绝（content 抛 ValidationException → 400；
    render 路径由调用方转 RenderError.TOO_LARGE，两者文案一致）。"""
    if size > MAX_FOLDER_FILE_BYTES:
        raise ValidationException(
            message=f"文件超过 {MAX_FOLDER_FILE_BYTES // (1024 * 1024)}MB 读取上限（{size // (1024 * 1024)}MB），请拆分或压缩后再引用",
            errors={"subpath": ref},
        )


OWNER_KINDS = ("contract", "case")


def _browse_service(owner_kind: str = "contract") -> BoundFolderBrowseService:
    """延迟导入对应域的浏览服务（agent → contracts/cases 单向，无循环依赖）。"""
    if owner_kind == "case":
        from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService

        return CaseFolderBrowseService()
    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    return ContractFolderBrowseService()


def _resolve_folder_file(
    *,
    owner_kind: str,
    owner_id: int,
    subpath: str,
    user: Any,
    org_access: dict[str, Any] | None,
    perm_open_access: bool,
) -> Path:
    """ACL + 逃逸校验 + 存在性检查，返回原文件绝对路径。

    无权 / 未绑定 / 云存储绑定 / 路径不存在均抛 NotFoundError（与目录树
    同文案，不区分「无权」与「不存在」）。
    """
    return _browse_service(owner_kind).resolve_file(
        owner_id=owner_id,
        subpath=subpath,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )


def create_folder_ref(
    *,
    session: AgentSession,
    user_id: int | None,
    user: Any,
    org_access: dict[str, Any] | None,
    perm_open_access: bool,
    owner_kind: str = "contract",
    owner_id: int,
    subpath: str,
) -> AgentAttachment:
    """拖拽引用落库：校验通过即记录元数据（文件名/MIME/大小为创建时快照）。

    Raises:
        ValidationException: owner_kind 非法。
        NotFoundError: 无权访问该归属、未绑定文件夹、云存储绑定或文件不存在。
    """
    if owner_kind not in OWNER_KINDS:
        raise ValidationException(message=f"未知的引用归属类型：{owner_kind}", errors={"kind": owner_kind})
    path = _resolve_folder_file(
        owner_kind=owner_kind,
        owner_id=owner_id,
        subpath=subpath,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
    normalized = _browse_service(owner_kind).normalize_subpath(subpath)
    stat = path.stat()
    mime = mimetypes.guess_type(path.name)[0] or ""
    ref = AgentAttachment.objects.create(
        session=session,
        user_id=user_id,
        filename=path.name[:255],
        storage_path="",
        mime=mime[:100],
        size=int(stat.st_size),
        ref_owner_kind=owner_kind,
        ref_contract_id=owner_id,
        ref_subpath=normalized[:500],
    )
    logger.info(
        "folder_ref_created",
        extra={
            "action": "folder_ref_created",
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "subpath": normalized,
            "size": stat.st_size,
        },
    )
    return ref


def read_folder_file_content(
    *,
    owner_kind: str = "contract",
    owner_id: int,
    subpath: str,
    user: Any,
    org_access: dict[str, Any] | None,
    perm_open_access: bool,
) -> dict[str, Any]:
    """读原文件字节为 base64（供 mcp_server 转投 /document-parsing；不直接给模型）。

    返回结构与 ``attachments.read_attachment_content`` 同构（attachment_id
    字段放 ``folder:{kind}:{owner_id}/{subpath}`` 引用标识，contract 省略
    kind 段以兼容存量标识）。
    """
    path = _resolve_folder_file(
        owner_kind=owner_kind,
        owner_id=owner_id,
        subpath=subpath,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
    stat = path.stat()
    display = _display_ref(owner_kind, owner_id, subpath)
    _reject_oversize(stat.st_size, ref=display)
    mime = mimetypes.guess_type(path.name)[0] or ""
    with open(path, "rb") as fh:
        payload = base64.b64encode(fh.read()).decode("ascii")
    return {
        "attachment_id": display,
        "filename": path.name,
        "mime": mime,
        "size": int(stat.st_size),
        "content_base64": payload,
    }


def render_folder_file_pages(
    *,
    owner_kind: str = "contract",
    owner_id: int,
    subpath: str,
    user: Any,
    org_access: dict[str, Any] | None,
    perm_open_access: bool,
    pages: str | int | list[int] | None = None,
    dpi: int = 200,
    fmt: str = "png",
    max_pages: int = 20,
    user_id: int | None = None,
) -> Any:
    """把绑定文件夹内文件按页渲染成图（与附件版 ``render_attachment_pages`` 同规格）。"""
    path = _resolve_folder_file(
        owner_kind=owner_kind,
        owner_id=owner_id,
        subpath=subpath,
        user=user,
        org_access=org_access,
        perm_open_access=perm_open_access,
    )
    stat = path.stat()
    display = _display_ref(owner_kind, owner_id, subpath)
    mime = mimetypes.guess_type(path.name)[0] or ""
    if stat.st_size > MAX_FOLDER_FILE_BYTES:
        from . import attachment_render as render

        return render.RenderResult(
            attachment_id=display,
            filename=path.name,
            mime=mime,
            error=render.RenderError.TOO_LARGE,
            detail=f"文件超过 {MAX_FOLDER_FILE_BYTES // (1024 * 1024)}MB 读取上限，请拆分或压缩后再引用",
        )
    cache_ref = f"{display}?v={stat.st_size}-{int(stat.st_mtime)}"
    try:
        with open(path, "rb") as fh:
            file_bytes = fh.read()
    except OSError:
        logger.warning("绑定文件夹文件读取失败 ref=%s", display)
        from . import attachment_render as render

        return render.RenderResult(
            attachment_id=display,
            filename=path.name,
            mime=mime,
            error=render.RenderError.NOT_FOUND,
            detail="文件已不存在（可能已被移动或移入删除区）",
        )
    return _render_bytes_pages(
        ref_id=display,
        cache_ref=cache_ref,
        filename=path.name,
        mime=mime,
        file_bytes=file_bytes,
        pages=pages,
        dpi=dpi,
        fmt=fmt,
        max_pages=max_pages,
        user_id=user_id,
    )


def _display_ref(owner_kind: str, owner_id: int, subpath: str) -> str:
    """对外引用标识（展示/审计用；不含缓存指纹）。

    contract 保持 ``folder:{id}/{subpath}``（兼容存量缓存键与前端断言）；
    case 带类型段 ``folder:case:{id}/{subpath}`` 以示区分。
    """
    normalized = _browse_service(owner_kind).normalize_subpath(subpath)
    prefix = f"folder:{owner_id}" if owner_kind == "contract" else f"folder:case:{owner_id}"
    return f"{prefix}/{normalized}" if normalized else f"{prefix}/"


__all__: list[str] = [
    "create_folder_ref",
    "read_folder_file_content",
    "render_folder_file_pages",
]
