"""文档解析 API Schema"""

from typing import Any

from ninja import Schema


class ParseDocumentRequest(Schema):
    """文档解析请求"""

    backend: str = "auto"
    """后端类型：mineru、textin、local、paddleocr、auto"""

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

    task_id: str | None = None
    """异步任务 ID（异步模式下返回）"""

    status: str = "completed"
    """任务状态：pending / completed / failed"""

    text: str | None = None
    """纯文本内容"""

    markdown: str | None = None
    """Markdown 格式"""

    metadata: dict[str, Any] | None = None
    """元数据"""

    parse_method: str | None = None
    """解析方法"""

    error: str | None = None
    """错误信息（如果失败）"""


class ExtractTextRequest(Schema):
    """文本提取请求"""

    backend: str = "auto"
    """后端类型"""

    max_length: int | None = None
    """最大文本长度"""


class ExtractTextResponse(Schema):
    """文本提取响应"""

    success: bool
    """是否成功"""

    task_id: str | None = None
    """异步任务 ID（异步模式下返回）"""

    status: str = "completed"
    """任务状态：pending / completed / failed"""

    text: str
    """提取的文本"""

    method: str | None = None
    """使用的方法"""

    metadata: dict[str, Any] | None = None
    """元数据"""

    error: str | None = None
    """错误信息（如果失败）"""


class TaskStatusResponse(Schema):
    """异步任务状态查询响应"""

    task_id: str
    """任务 ID"""

    status: str
    """任务状态：pending / running / success / failure / not_found"""

    result: dict[str, Any] | None = None
    """任务结果（成功时包含解析结果）"""

    started_at: str | None = None
    """开始时间"""

    finished_at: str | None = None
    """完成时间"""
