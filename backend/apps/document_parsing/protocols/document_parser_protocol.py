"""文档解析 Protocol 接口定义"""

from typing import Protocol, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    """文档解析结果"""

    text: str
    """纯文本内容"""

    markdown: Optional[str] = None
    """Markdown 格式（MinerU 支持）"""

    tables: Optional[List[dict]] = None
    """表格数据列表"""

    metadata: Optional[dict] = None
    """元数据（页数、创建时间等）"""

    images: Optional[List[str]] = None
    """提取的图片文件路径列表"""

    parse_method: str = ""
    """使用的解析方法（mineru、pymupdf、paddleocr 等）"""

    layout: Optional[dict] = None
    """文档布局信息（标题、段落、列表等结构）"""


@dataclass
class TextExtractionResult:
    """文本提取结果"""

    text: str
    """提取的文本"""

    success: bool
    """是否成功"""

    method: str = ""
    """使用的方法"""

    page_count: Optional[int] = None
    """文档页数"""

    metadata: Optional[dict] = None
    """附加元数据"""


class IDocumentParserProtocol(Protocol):
    """文档解析 Protocol 接口

    任何文档解析后端都应实现此接口。
    """

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
        max_length: Optional[int] = None,
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

    def get_supported_formats(self) -> List[str]:
        """获取支持的文件格式列表

        Returns:
            支持的文件扩展名列表（如 ['pdf', 'doc', 'docx']）
        """
        ...
