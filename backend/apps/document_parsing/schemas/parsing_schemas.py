"""文档解析 API Schema"""

from typing import Any, Dict, Optional

from ninja import Schema


class ParseDocumentRequest(Schema):
    """文档解析请求"""

    backend: str = "auto"
    """后端类型：mineru、local、paddleocr、auto"""

    extract_tables: bool = True
    """是否提取表格"""

    extract_images: bool = False
    """是否提取图片"""

    return_markdown: bool = True
    """是否返回 Markdown 格式"""


class ParseDocumentResponse(Schema):
    """文档解析响应"""

    success: bool
    """是否成功"""

    text: Optional[str] = None
    """纯文本内容"""

    markdown: Optional[str] = None
    """Markdown 格式"""

    metadata: Optional[Dict[str, Any]] = None
    """元数据"""

    parse_method: Optional[str] = None
    """解析方法"""

    error: Optional[str] = None
    """错误信息（如果失败）"""


class ExtractTextRequest(Schema):
    """文本提取请求"""

    backend: str = "auto"
    """后端类型"""

    max_length: Optional[int] = None
    """最大文本长度"""


class ExtractTextResponse(Schema):
    """文本提取响应"""

    success: bool
    """是否成功"""

    text: str
    """提取的文本"""

    method: Optional[str] = None
    """使用的方法"""

    metadata: Optional[Dict[str, Any]] = None
    """元数据"""

    error: Optional[str] = None
    """错误信息（如果失败）"""
