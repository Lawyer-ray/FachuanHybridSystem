"""文档解析 API Schema"""

from datetime import datetime
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


class ParseMemoryBlockOut(Schema):
    """块级结构（复核/质检用）

    ``confidence`` 为 None 有确切语义：**未评估**（后端无此能力或判定模型未运行），
    不能当作 0 处理——0 表示评估过且很可能是错的，两者处置完全不同。
    """

    type: str
    """块类型：text / title / table / image / formula / header / footer / unknown"""

    text: str = ""
    """该块识别文本"""

    page_no: int | None = None
    """页码（1 起）"""

    bbox: Any = None
    """原图坐标（各后端坐标系不统一，保留原值）"""

    confidence: float | None = None
    """可信度 0~1；None = 未评估"""

    needs_review: bool = False
    """是否需人工复核"""

    review_reason: str = ""
    """需复核的原因"""


class ParseCoverageOut(Schema):
    """后端块级能力位（“这个后端能提供什么”）"""

    has_blocks: bool = False
    has_bbox: bool = False
    has_confidence: bool = False
    has_page_geometry: bool = False


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

    blocks: list[ParseMemoryBlockOut] | None = None
    """块级结构；None 表示后端未提供（见 coverage.has_blocks）"""

    coverage: ParseCoverageOut | None = None
    """块级能力位"""

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

    finished_at: datetime | None = None
    """完成时间"""


class DocumentParsingRecordOut(Schema):
    """解析记录列表项（历史弹窗用，不含全文）"""

    id: int
    status: str
    """pending / processing / completed / failed"""

    file_name: str
    file_size: int
    backend_used: str | None = None
    error_message: str | None = None
    text_preview: str
    """正文前 100 字，列表速览用"""

    created_at: datetime | None = None
    completed_at: datetime | None = None


class DocumentParsingRecordDetailOut(Schema):
    """解析记录详情（点开历史项查看全文）"""

    id: int
    status: str
    file_name: str
    file_size: int
    backend_used: str | None = None
    error_message: str | None = None
    text: str
    markdown: str | None = None
    metadata: dict[str, Any] | None = None
    blocks: list[ParseMemoryBlockOut] | None = None
    """块级结构；旧记录（加块结构之前）为 None"""
    created_at: datetime | None = None
    completed_at: datetime | None = None


class DocumentParsingRecordListOut(Schema):
    """解析记录分页响应"""

    items: list[DocumentParsingRecordOut]
    count: int
    page: int
    num_pages: int
