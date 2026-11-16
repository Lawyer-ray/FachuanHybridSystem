"""附件上传 / 文件夹引用 / 分页渲染的请求响应契约。"""

from __future__ import annotations

from typing import Literal

from ninja import Schema


class AttachmentOut(Schema):
    """附件上传回执：消息里以 [已上传附件：name (attachment_id=…)] 引用。

    引用型（拖拽绑定文件夹文件）带 ``ref_owner_kind`` / ``ref_contract_id``（归属 id，合同或案件）/ ``ref_subpath``，
    上传型两者为空——前端据此渲染不同 chip。
    """

    attachment_id: str
    filename: str
    size: int
    mime: str = ""
    ref_owner_kind: str = "contract"
    ref_contract_id: int | None = None
    ref_subpath: str = ""


class FolderRefIn(Schema):
    """拖拽引用入参：指向合同/案件绑定文件夹内的一个文件（不复制字节）。"""

    kind: Literal["contract", "case"] = "contract"
    owner_id: int
    subpath: str


class AttachmentPageOut(Schema):
    """附件的一页渲染图（base64）。

    ``has_text_layer`` 是「这页可选出文字」的事实陈述：扫描件为 false，
    调用方据此决定是否走 OCR，而不是把空白渲染当成功文本。

    文字层页（``has_text_layer=true``）**不渲染图**：``b64`` 为空、``bytes=0``，
    调用方应改走文本通道（省视觉 token）。``error`` 是该页粒度的错误码
    （如 encrypted / too_large），成功为空；``detail`` 是可读原因。
    """

    page: int
    mime: str
    b64: str
    bytes: int
    width: int
    height: int
    has_text_layer: bool
    text: str = ""
    error: str = ""
    detail: str = ""


class AttachmentPagesOut(Schema):
    """附件分页渲染结果（MCP 取页面图给模型看）。字段名与 T1 的 RenderResult 一一对应。

    失败时 ``pages_returned`` 为空、``error`` 给出错误码——**不用空图冒充
    成功**：一页空 base64 会让模型以为「这页是空白」而不是「渲染失败」。
    """

    attachment_id: str
    filename: str = ""
    mime: str = ""
    total_pages: int = 0
    pages_returned: list[AttachmentPageOut] = []
    #: text / image / mixed
    strategy: str = ""
    #: not_found / forbidden / parse_empty / encrypted / unsupported_mime /
    #: too_large / page_out_of_range 之一；空串表示成功
    error: str = ""
    #: 与 error 配套的可读原因（MCP 侧直接转给模型看）
    detail: str = ""
    notices: list[str] = []
    #: 请求的页数超过 max_pages 被截断时为 true（与 notices 同时给出）
    truncated_pages: bool = False
