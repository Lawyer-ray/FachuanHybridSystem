"""页图渲染的共享类型与体积口径常量。"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

#: 页图长边上限。对齐主流多模态模型的原生视觉输入尺寸（1568 是各家 tokenizer
#: 的常用切块边长）：再大的图会被服务端缩回去，白白多传几十万字节。
MAX_EDGE_PX = 1568
#: 单页字节上限。按 base64 后 4/3 膨胀估算，1.5MB 原始 ≈ 2MB 传输，
#: 10 页就在一次工具返回的可接受范围内。
MAX_PAGE_BYTES = 1536 * 1024


class RenderError(enum.StrEnum):
    """渲染失败的原因分类。

    必须区分而不是统一成「失败」：``encrypted`` 要提示用户「请上传解密版」，
    ``page_out_of_range`` 要提示用户「这份材料只有 5 页」，``too_large`` 是
    「这页太复杂，请分开查询」——三者的下一步动作完全不同。
    """

    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    PARSE_EMPTY = "parse_empty"
    ENCRYPTED = "encrypted"
    UNSUPPORTED_MIME = "unsupported_mime"
    TOO_LARGE = "too_large"
    PAGE_OUT_OF_RANGE = "page_out_of_range"


class RenderStrategy(enum.StrEnum):
    """该页最终交给模型的形态。"""

    #: 文字层足够，模型不需要图（页图里 text 字段有正文）
    TEXT = "text"
    #: 把页渲染成图片，模型走视觉通道
    PAGE_IMAGE = "page_image"
    #: 图片附件直接透传原字节（不重复编码，避免二次压缩损失）
    SOURCE_IMAGE = "source_image"


@dataclass
class RenderedPage:
    """一页的渲染结果。

    ``image_bytes`` 与 ``error`` 互斥：有图就是成功，没图必须带原因——
    这正是本模块存在的目的（禁止「空内容 + 假装成功」）。
    """

    page_no: int
    """1-based 页码（对外唯一编号口径）。"""

    strategy: RenderStrategy
    mime: str = ""
    image_bytes: bytes | None = None
    text: str = ""
    width: int = 0
    height: int = 0
    dpi: int = 0
    error: RenderError | None = None
    detail: str = ""
    cached: bool = False

    @property
    def size_bytes(self) -> int:
        return len(self.image_bytes) if self.image_bytes else 0


@dataclass
class RenderResult:
    """一次渲染的完整结果（含失败页，缺页信息不能被丢掉）。"""

    attachment_id: str
    filename: str = ""
    mime: str = ""
    #: 1-based 的原始页码清单（未截断前）
    requested_pages: list[int] = field(default_factory=list)
    #: 实际处理的页码（受 max_pages 限制）
    pages: list[RenderedPage] = field(default_factory=list)
    #: 文档总页数（非 PDF 恒为 1）
    total_pages: int = 0
    #: 超出 max_pages 而未处理的页数
    truncated_pages: int = 0
    error: RenderError | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        """至少有一页真的拿到了内容。"""
        return self.error is None and any(p.image_bytes or p.text for p in self.pages)

    @property
    def total_bytes(self) -> int:
        return sum(p.size_bytes for p in self.pages)
