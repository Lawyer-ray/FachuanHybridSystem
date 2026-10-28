"""收件箱 API Schemas。"""

from __future__ import annotations

from typing import Any, cast

from ninja import Schema

from apps.core.api.schemas import SchemaMixin
from apps.message_hub.models import InboxMessage


class AttachmentMeta(Schema):
    """附件元信息。"""

    filename: str
    original_filename: str | None = None
    custom_filename: str | None = None
    size: int
    content_type: str
    part_index: int
    """PDF 页数（上传时 / 详情读取时回填算好），前端构建初始分段用，避免整包下载。非 PDF 为 None。"""
    page_count: int | None = None
    """来源压缩包名：该文件是压缩包展开产物时有值（溯源展示用）。"""
    expanded_from: str | None = None


class MessageAckOut(Schema):
    """消息写操作确认（删除 / 草稿保存等）。"""

    ok: bool
    message_id: int


class MessageRenameOut(MessageAckOut):
    """消息重命名确认（返回更新后的标题）。"""

    subject: str


class InboxMessageOut(SchemaMixin, Schema):
    """收件箱消息列表项。"""

    id: int
    source_name: str
    source_type: str
    subject: str
    sender: str
    recipient: str
    received_at: str
    has_attachments: bool
    attachment_count: int
    uploaded_by_id: int | None
    uploaded_by_name: str
    created_at: str
    status: str = "todo"
    segs: int = 0
    named: int = 0
    pages: int = 0
    mats: int = 0
    types: list[str] = []
    compose: str = ""
    # 已读态（收件箱页用）：read_at 为 null 即未读；前端只消费布尔，保留时间戳供调试/排序
    is_read: bool = False
    read_at: str | None = None
    # 转换链路：非 manual_upload 消息「转材料包」后指向生成的材料包
    converted_message_id: int | None = None
    # 客户链接上传的包：来源链接与项目绑定徽标（归案弹窗预选用）
    upload_link_id: int | None = None
    upload_link_title: str = ""
    upload_contract_id: int | None = None
    upload_contract_name: str = ""

    @staticmethod
    def resolve_is_read(obj: InboxMessage) -> bool:
        return obj.read_at is not None

    @staticmethod
    def resolve_read_at(obj: InboxMessage) -> str | None:
        if obj.read_at is None:
            return None
        return SchemaMixin._resolve_datetime_iso(obj.read_at)

    @staticmethod
    def resolve_converted_message_id(obj: InboxMessage) -> int | None:
        return obj.converted_message_id if obj.converted_message_id else None

    @staticmethod
    def resolve_status(obj: InboxMessage) -> str:
        ds = obj.draft_state or {}
        status = str(ds.get("status") or "todo")
        return status if status in {"todo", "done", "filed"} else "todo"

    @staticmethod
    def resolve_segs(obj: InboxMessage) -> int:
        return len((obj.draft_state or {}).get("segs") or [])

    @staticmethod
    def resolve_named(obj: InboxMessage) -> int:
        """已归类份数：选了类型，或改过名（fnAuto 记录系统默认名，fn 与之不同即用户命名）。"""
        named = 0
        for s in (obj.draft_state or {}).get("segs") or []:
            has_type = bool(str(s.get("t") or "").strip())
            renamed = s.get("fnAuto") is not None and s.get("fn") != s.get("fnAuto")
            if has_type or renamed:
                named += 1
        return named

    @staticmethod
    def resolve_pages(obj: InboxMessage) -> int:
        mats = (obj.draft_state or {}).get("mats") or []
        return sum(int(m.get("pages") or 0) for m in mats)

    @staticmethod
    def resolve_mats(obj: InboxMessage) -> int:
        draft_mats = (obj.draft_state or {}).get("mats") or []
        if draft_mats:
            return len(draft_mats)
        return len(obj.attachments_meta or [])

    @staticmethod
    def resolve_types(obj: InboxMessage) -> list[str]:
        segs = (obj.draft_state or {}).get("segs") or []
        seen: list[str] = []
        for s in segs:
            t = str(s.get("t") or "").strip()
            if t and t not in seen:
                seen.append(t)
            if len(seen) >= 3:
                break
        return seen

    @staticmethod
    def _kind_label(content_type: str | None) -> str:
        ct = (content_type or "").lower()
        if ct.startswith("image/"):
            return "图片"
        if "pdf" in ct:
            return "文档"
        # Word/Excel 等统一归到"文档"
        return "文档"

    @staticmethod
    def resolve_compose(obj: InboxMessage) -> str:
        mats = (obj.draft_state or {}).get("mats") or []
        if not mats:
            group: dict[str, int] = {}
            for att in obj.attachments_meta or []:
                label = InboxMessageOut._kind_label(att.get("content_type"))
                group[label] = group.get(label, 0) + 1
            return "、".join(f"{n} 个{v}" for v, n in group.items()) if group else ""
        agg: dict[str, int] = {}
        for m in mats:
            k = str(m.get("k") or "office")
            label = "图片" if k == "photo" else "文档"
            agg[label] = agg.get(label, 0) + 1
        bits = [f"{n} 个{v}" for v, n in agg.items()]
        return " · ".join(bits) if bits else "尚未拆分"

    @staticmethod
    def resolve_source_name(obj: InboxMessage) -> str:
        return str(obj.source.display_name)

    @staticmethod
    def resolve_source_type(obj: InboxMessage) -> str:
        return str(obj.source.source_type)

    @staticmethod
    def resolve_recipient(obj: InboxMessage) -> str:
        account: str = obj.source.credential.account if obj.source.credential else ""
        return account

    @staticmethod
    def resolve_uploaded_by_id(obj: InboxMessage) -> int | None:
        return obj.uploaded_by_id if obj.uploaded_by_id else None

    @staticmethod
    def resolve_uploaded_by_name(obj: InboxMessage) -> str:
        if not obj.uploaded_by:
            return ""
        return str(obj.uploaded_by.real_name or obj.uploaded_by.username or "")

    @staticmethod
    def resolve_received_at(obj: InboxMessage) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.received_at) or ""

    @staticmethod
    def resolve_attachment_count(obj: InboxMessage) -> int:
        return len(obj.attachments_meta) if obj.attachments_meta else 0

    @staticmethod
    def resolve_created_at(obj: InboxMessage) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.created_at) or ""

    @staticmethod
    def resolve_upload_link_id(obj: InboxMessage) -> int | None:
        return obj.upload_link_id if obj.upload_link_id else None

    @staticmethod
    def resolve_upload_link_title(obj: InboxMessage) -> str:
        return str(obj.upload_link.title) if obj.upload_link else ""

    @staticmethod
    def resolve_upload_contract_id(obj: InboxMessage) -> int | None:
        return obj.upload_link.contract_id if obj.upload_link and obj.upload_link.contract_id else None

    @staticmethod
    def resolve_upload_contract_name(obj: InboxMessage) -> str:
        if not obj.upload_link or not obj.upload_link.contract:
            return ""
        return str(obj.upload_link.contract.name)


class InboxMessageDetailOut(InboxMessageOut):
    """收件箱消息详情（含正文和附件详情）。"""

    body_text: str
    body_html: str
    attachments: list[AttachmentMeta]
    draft_state: dict = {}

    @staticmethod
    def resolve_attachments(obj: InboxMessage) -> list[dict[str, Any]]:
        return obj.get_public_attachments_meta()

    @staticmethod
    def resolve_draft_state(obj: InboxMessage) -> dict[str, Any]:
        return obj.draft_state or {}


# ---------------------------------------------------------------------------
# 客户上传链接
# ---------------------------------------------------------------------------


class UploadLinkCreateIn(Schema):
    """创建链接入参。"""

    title: str
    note: str = ""
    client_name: str = ""
    contract_id: int | None = None
    expires_days: int = 30


class UploadLinkOut(SchemaMixin, Schema):
    """客户上传链接（律师端列表行；token 明文绝不在此出现）。"""

    id: int
    title: str
    note: str
    client_name: str
    contract_id: int | None = None
    contract_name: str = ""
    status: str
    state: str
    expires_at: str
    created_at: str
    pack_count: int
    used_bytes: int
    quota_total_bytes: int
    quota_max_packs: int
    last_uploaded_at: str | None = None

    @staticmethod
    def resolve_state(obj: Any) -> str:
        from apps.message_hub.services.client_upload_service import link_state

        return link_state(obj)

    @staticmethod
    def resolve_contract_id(obj: Any) -> int | None:
        return obj.contract_id if obj.contract_id else None

    @staticmethod
    def resolve_contract_name(obj: Any) -> str:
        return str(obj.contract.name) if obj.contract else ""

    @staticmethod
    def resolve_expires_at(obj: Any) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.expires_at) or ""

    @staticmethod
    def resolve_created_at(obj: Any) -> str:
        return SchemaMixin._resolve_datetime_iso(obj.created_at) or ""

    @staticmethod
    def resolve_last_uploaded_at(obj: Any) -> str | None:
        if not obj.last_uploaded_at:
            return None
        return SchemaMixin._resolve_datetime_iso(obj.last_uploaded_at)


class UploadLinkCreatedOut(UploadLinkOut):
    """创建 / 轮换响应：附带 token 明文（仅此一次，前端即时组装分享 URL）。"""

    token: str


class PublicLinkInfoOut(Schema):
    """公开链接信息（token 持有者可见；不含律师端统计细节）。"""

    title: str
    note: str
    client_name: str
    lawyer_name: str
    contract_name: str = ""
    state: str
    expires_at: str
    remaining_bytes: int


class PublicUploadFileOut(Schema):
    """公开侧文件条目（仅文件名与大小）。"""

    filename: str
    size: int


class PublicUploadOut(Schema):
    """公开上传响应：本批已收文件与剩余额度。"""

    files: list[PublicUploadFileOut]
    remaining_bytes: int
