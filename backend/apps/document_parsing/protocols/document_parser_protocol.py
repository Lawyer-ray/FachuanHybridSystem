"""文档解析 Protocol 接口定义"""

from dataclasses import dataclass, field
from typing import Any, Protocol

# 块类型常量：架构层词汇（textin / mineru / local / 未来的 minicpm 都归一到这套）。
# 用字符串而非 Enum，因为 ParsedBlock.type 要能直接 JSON 化落库、透传给前端。
BLOCK_TYPE_TEXT = "text"
BLOCK_TYPE_TITLE = "title"
BLOCK_TYPE_TABLE = "table"
BLOCK_TYPE_IMAGE = "image"
BLOCK_TYPE_FORMULA = "formula"
BLOCK_TYPE_HEADER = "header"
BLOCK_TYPE_FOOTER = "footer"
BLOCK_TYPE_UNKNOWN = "unknown"

#: 后端原始元素类型 → 架构层块类型。
#: 键统一小写比较，后端（Textin 的 NarrativeText、MinerU 的 text/equation 等）差异消化在这一层，
#: 下游质检/复核界面只认右边这套词汇。
_BLOCK_TYPE_ALIASES: dict[str, str] = {
    "text": BLOCK_TYPE_TEXT,
    "narrativetext": BLOCK_TYPE_TEXT,
    "paragraph": BLOCK_TYPE_TEXT,
    "list": BLOCK_TYPE_TEXT,
    "listitem": BLOCK_TYPE_TEXT,
    "caption": BLOCK_TYPE_TEXT,
    "reference": BLOCK_TYPE_TEXT,
    "footnote": BLOCK_TYPE_TEXT,
    "title": BLOCK_TYPE_TITLE,
    "heading": BLOCK_TYPE_TITLE,
    "sectionheader": BLOCK_TYPE_TITLE,
    "doc_title": BLOCK_TYPE_TITLE,
    "table": BLOCK_TYPE_TABLE,
    "image": BLOCK_TYPE_IMAGE,
    "figure": BLOCK_TYPE_IMAGE,
    "inline_object": BLOCK_TYPE_IMAGE,
    "picture": BLOCK_TYPE_IMAGE,
    "formula": BLOCK_TYPE_FORMULA,
    "equation": BLOCK_TYPE_FORMULA,
    "interline_equation": BLOCK_TYPE_FORMULA,
    "inline_equation": BLOCK_TYPE_FORMULA,
    "header": BLOCK_TYPE_HEADER,
    "footer": BLOCK_TYPE_FOOTER,
    "page_header": BLOCK_TYPE_HEADER,
    "page_footer": BLOCK_TYPE_FOOTER,
    "page_number": BLOCK_TYPE_FOOTER,
}

#: 不进入正文的块类型（页眉页脚页码）。归一化后可用架构层词汇判断，
#: 不必各后端各维护一份排除表。
NON_BODY_BLOCK_TYPES: frozenset[str] = frozenset({BLOCK_TYPE_HEADER, BLOCK_TYPE_FOOTER})


def normalize_block_type(raw_type: str | None) -> str:
    """把后端原始元素类型归一为架构层块类型。

    未知类型（含空串）返回 ``unknown``，保留而不丢弃——质检层/复核界面
    宁可看到一个 unknown 块，也不要它凭空消失。

    Args:
        raw_type: 后端元素类型，如 ``"NarrativeText"``、``"interline_equation"``。

    Returns:
        架构层块类型常量之一。
    """
    key = str(raw_type or "").strip().lower()
    return _BLOCK_TYPE_ALIASES.get(key, BLOCK_TYPE_UNKNOWN)


@dataclass
class ParsedBlock:
    """文档块（识别的最小可信度单元）

    设计目的：诊断/复核层要判定「哪一小块可能认错了」，判定粒度必须比整页更细。
    本类只承载**定位 + 原文 + 可选可信度**三件事，不做判定、不存判定结论——
    判定由独立的质量判定后端（如 MiniCPM-OCR Jev）产出后回填到 ``confidence``。

    字段刻意保持与具体后端解耦：Textin 的 element、MinerU 的 content_list 条目、
    本地后端的文本行都能填进同一张表，下游不必知道来源。
    """

    type: str = BLOCK_TYPE_TEXT
    """架构层块类型（见 BLOCK_TYPE_* 常量）。后端差异用 normalize_block_type 消化。"""

    text: str = ""
    """该块的识别文本（表格为 Markdown/HTML，公式为 LaTeX，图片可能为空）。"""

    bbox: Any = None
    """在原图中的位置。各后端坐标系不统一（Textin element coordinates / MinerU 千分比
    bbox），因此保留原值不做换算——裁切时由调用方按来源解释，避免在这里丢失信息。"""

    page_no: int | None = None
    """所在页码，1 起。用于跨页阅读顺序与按页裁图送检。"""

    confidence: float | None = None
    """可信度，0~1，越大越可能认对。

    **None 有明确语义：未评估**（后端不支持、或判定模型未运行/运行失败）。
    绝不能把 None 当成 0——0 表示「评估过，很可能是错的」，两者在复核界面上
    是完全不同的处置。送检失败请保持 None 并在 ``review_reason`` 说明。"""

    needs_review: bool = False
    """是否需要人工复核。由阈值标定后的判定结果写入，不是后端原始输出。"""

    review_reason: str = ""
    """需要复核的原因（低于阈值 / 判定失败 / 未评估等），供复核界面显示。"""

    def is_body(self) -> bool:
        """是否属于正文（页眉页脚页码不算）。

        页眉页脚常常整段重复且无信息量，评分或送检时应跳过，否则会把
        「页码 3」这种块的分数拉进统计、污染免检率指标。
        """
        return self.type not in NON_BODY_BLOCK_TYPES


@dataclass
class ParseCoverage:
    """后端能力位（「这个后端能提供什么」的声明）

    存在的理由：选型与门禁判断必须看**能力**而不是看失败。例如 Textin 不返回任何
    原位可信度，这属于能力缺失而非解析失败；把两者混为一谈会导致「无置信度就
    当成低置信度」的误处置。能力位让缺能力变成一次可查询的显式事实。
    """

    has_blocks: bool = False
    """是否返回块级结构（layout.pages[].blocks）。没有块就无法按块送检。"""
    has_bbox: bool = False
    """块是否带坐标（bbox）。没有坐标就无法从原图裁出对应区域送判定模型。"""
    has_confidence: bool = False
    """是否自带原位可信度分数（目前三家后端都没有，靠独立判定层外挂）。"""
    has_page_geometry: bool = False
    """是否带页面宽高。坐标若无页面尺寸参照，裁切比例无法换算。"""

    def can_attach_confidence(self) -> bool:
        """是否具备「外挂块级可信度」的前置条件。

        判定模型（Jev 类）需要「块裁切原图 + 候选文本」两个输入，
        因此至少要同时具备块结构与坐标。
        """
        return self.has_blocks and self.has_bbox

    def as_dict(self) -> dict[str, bool]:
        """序列化用（落 metadata / 透传 API）。"""
        return {
            "has_blocks": self.has_blocks,
            "has_bbox": self.has_bbox,
            "has_confidence": self.has_confidence,
            "has_page_geometry": self.has_page_geometry,
        }


@dataclass
class ParsedDocument:
    """文档解析结果"""

    text: str
    """纯文本内容"""

    markdown: str | None = None
    """Markdown 格式（MinerU 支持）"""

    tables: list[dict] | None = None
    """表格数据列表"""

    metadata: dict | None = None
    """元数据（页数、创建时间等）"""

    images: list[str] | None = None
    """提取的图片文件路径列表"""

    parse_method: str = ""
    """使用的解析方法（mineru、textin、pymupdf 等）"""

    layout: dict | None = None
    """文档布局信息（标题、段落、列表等结构）"""

    blocks: list[ParsedBlock] | None = None
    """扁平化的块级结构（跨页顺序），供块级质检/复核使用。

    为 None 表示后端未提供块级结构（见 ``coverage.has_blocks``），
    和「提供了但为空列表」不同：后者是解析了但没识别出任何块。"""

    coverage: ParseCoverage = field(default_factory=ParseCoverage)
    """后端能力位。默认全 False——不声明即视为无能力，避免静默假设。"""


@dataclass
class TextExtractionResult:
    """文本提取结果"""

    text: str
    """提取的文本"""

    success: bool
    """是否成功"""

    method: str = ""
    """使用的方法"""

    page_count: int | None = None
    """文档页数"""

    metadata: dict | None = None
    """附加元数据"""


class IDocumentParserProtocol(Protocol):
    """文档解析 Protocol 接口

    任何文档解析后端都应实现此接口。
    """

    # 后端能力声明：是否需要异步执行（含 HTTP 上传 + 轮询，阻塞时间长）
    # 云端后端（MinerU、TextinParse）应为 True，本地后端（PyMuPDF）为 False
    requires_async_execution: bool

    def parse_document(
        self,
        file_path: str,
        file_type: str = "pdf",
        extract_tables: bool = True,
        extract_images: bool = False,
        return_markdown: bool = False,
        **kwargs: Any,
    ) -> ParsedDocument:
        """解析文档，返回结构化的解析结果

        Args:
            file_path: 文件路径
            file_type: 文件类型（pdf、doc、ppt、xlsx、jpg 等）
            extract_tables: 是否提取表格
            extract_images: 是否提取图片
            return_markdown: 是否返回 Markdown 格式
            **kwargs: 其他参数

        Returns:
            ParsedDocument 解析结果

        Raises:
            DocumentParsingError: 解析失败
            FileFormatNotSupportedError: 不支持的文件格式
            ParsingTimeoutError: 解析超时
        """
        ...

    def extract_text(
        self,
        file_path: str,
        max_length: int | None = None,
        **kwargs: Any,
    ) -> TextExtractionResult:
        """提取文档纯文本

        Args:
            file_path: 文件路径
            max_length: 最大文本长度（None 表示不限制）
            **kwargs: 其他参数

        Returns:
            TextExtractionResult 提取结果

        Raises:
            DocumentParsingError: 提取失败
        """
        ...

    def get_supported_formats(self) -> list[str]:
        """获取支持的文件格式列表

        Returns:
            支持的文件扩展名列表（如 ['pdf', 'doc', 'docx']）
        """
        ...
