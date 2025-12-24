from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
import base64

from .services.ai.prompts import DEFAULT_FILENAME_PROMPT


class DocumentProcessIn(BaseModel):
    file_path: str = Field(...)
    kind: str = Field(...)
    limit: int | None = None  # 文字提取限制，None时使用默认值
    preview_page: int | None = None  # PDF预览页码（从1开始），None时使用默认值


class DocumentProcessOut(BaseModel):
    image_url: str | None = None
    text_excerpt: str | None = None


class OllamaChatIn(BaseModel):
    model: str = Field(...)
    prompt: str = Field(...)
    text: str = Field(...)


class OllamaChatOut(BaseModel):
    data: dict


class MoonshotChatIn(BaseModel):
    model: str = Field(...)
    prompt: str = Field(...)
    text: str = Field(...)


class MoonshotChatOut(BaseModel):
    data: dict


class AutoToolProcessIn(BaseModel):
    file_path: str = Field(...)
    prompt: str = Field(default=DEFAULT_FILENAME_PROMPT)
    model: str = Field(default="qwen3:0.6b")
    limit: int | None = None  # 文字提取限制，None时使用默认值
    preview_page: int | None = None  # PDF预览页码（从1开始），None时使用默认值


class AutoToolProcessOut(BaseModel):
    text: str | None = None
    ollama_response: dict | None = None
    error: str | None = None


# ============================================================================
# 验证码识别 Schemas
# ============================================================================

class CaptchaRecognizeIn(BaseModel):
    """验证码识别请求"""
    image_base64: str = Field(
        ...,
        description="Base64 编码的图片数据",
        min_length=1,
        json_schema_extra={"example": "iVBORw0KGgoAAAANSUhEUgAAAAUA..."}
    )
    
    @field_validator('image_base64')
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """验证 Base64 格式"""
        if not v or not v.strip():
            raise ValueError("图片数据不能为空")
        
        # 移除可能的 data URL 前缀 (e.g., "data:image/png;base64,")
        if ',' in v:
            v = v.split(',', 1)[1]
        
        v = v.strip()
        
        # 验证是否为有效的 Base64 编码
        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("无效的 Base64 编码")
        
        return v


class CaptchaRecognizeOut(BaseModel):
    """验证码识别响应"""
    success: bool = Field(..., description="是否识别成功")
    text: Optional[str] = Field(None, description="识别出的验证码文本")
    processing_time: Optional[float] = Field(None, description="处理耗时（秒）")
    error: Optional[str] = Field(None, description="错误信息")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "success": True,
                    "text": "AB12",
                    "processing_time": 0.234,
                    "error": None
                },
                {
                    "success": False,
                    "text": None,
                    "processing_time": 0.012,
                    "error": "图片格式不支持"
                }
            ]
        }


# ============================================================================
# 财产保全询价 Schemas
# ============================================================================

class PreservationQuoteCreateSchema(BaseModel):
    """创建询价任务的输入 Schema"""
    preserve_amount: Decimal = Field(
        ...,
        gt=0,
        description="保全金额，必须为正数",
        json_schema_extra={"example": 100000.00}
    )
    corp_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="企业/法院ID",
        json_schema_extra={"example": "440100"}
    )
    category_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="分类ID (cPid)",
        json_schema_extra={"example": "1"}
    )
    credential_id: int = Field(
        ...,
        gt=0,
        description="账号凭证ID",
        json_schema_extra={"example": 1}
    )

    @field_validator('preserve_amount')
    @classmethod
    def validate_preserve_amount(cls, v: Decimal) -> Decimal:
        """验证保全金额必须为正数"""
        if v <= 0:
            raise ValueError("保全金额必须为正数")
        return v

    @field_validator('corp_id', 'category_id')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """验证字段不能为空"""
        if not v or not v.strip():
            raise ValueError("字段不能为空")
        return v.strip()


class InsuranceQuoteSchema(BaseModel):
    """保险公司报价输出 Schema"""
    id: int = Field(..., description="报价记录ID")
    preservation_quote_id: int = Field(..., description="询价任务ID")
    company_id: str = Field(..., description="保险公司ID")
    company_code: str = Field(..., description="保险公司编码")
    company_name: str = Field(..., description="保险公司名称")
    premium: Optional[Decimal] = Field(None, description="报价金额")
    status: str = Field(..., description="查询状态 (success/failed)")
    error_message: Optional[str] = Field(None, description="错误信息")
    response_data: Optional[dict] = Field(None, description="完整响应数据")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None
        }


class PreservationQuoteSchema(BaseModel):
    """询价任务输出 Schema"""
    id: int = Field(..., description="任务ID")
    preserve_amount: Decimal = Field(..., description="保全金额")
    corp_id: str = Field(..., description="企业/法院ID")
    category_id: str = Field(..., description="分类ID")
    credential_id: int = Field(..., description="凭证ID")
    status: str = Field(..., description="任务状态")
    total_companies: int = Field(..., description="保险公司总数")
    success_count: int = Field(..., description="成功查询数")
    failed_count: int = Field(..., description="失败查询数")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    finished_at: Optional[datetime] = Field(None, description="完成时间")
    quotes: List[InsuranceQuoteSchema] = Field(
        default_factory=list,
        description="保险公司报价列表"
    )

    @classmethod
    def from_model(cls, obj):
        """从 Django Model 创建 Schema，处理关联查询"""
        return cls(
            id=obj.id,
            preserve_amount=obj.preserve_amount,
            corp_id=obj.corp_id,
            category_id=obj.category_id,
            credential_id=obj.credential_id,
            status=obj.status,
            total_companies=obj.total_companies,
            success_count=obj.success_count,
            failed_count=obj.failed_count,
            error_message=obj.error_message,
            created_at=obj.created_at,
            started_at=obj.started_at,
            finished_at=obj.finished_at,
            quotes=[InsuranceQuoteSchema.model_validate(q) for q in obj.quotes.all()]
        )

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None
        }


class QuoteListItemSchema(BaseModel):
    """询价任务列表项 Schema（不包含详细报价）"""
    id: int = Field(..., description="任务ID")
    preserve_amount: Decimal = Field(..., description="保全金额")
    corp_id: str = Field(..., description="企业/法院ID")
    category_id: str = Field(..., description="分类ID")
    status: str = Field(..., description="任务状态")
    total_companies: int = Field(..., description="保险公司总数")
    success_count: int = Field(..., description="成功查询数")
    failed_count: int = Field(..., description="失败查询数")
    success_rate: float = Field(..., description="成功率（百分比）")
    created_at: datetime = Field(..., description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    finished_at: Optional[datetime] = Field(None, description="完成时间")

    @classmethod
    def from_model(cls, obj):
        """从 Django Model 创建 Schema，计算 success_rate"""
        return cls(
            id=obj.id,
            preserve_amount=obj.preserve_amount,
            corp_id=obj.corp_id,
            category_id=obj.category_id,
            status=obj.status,
            total_companies=obj.total_companies,
            success_count=obj.success_count,
            failed_count=obj.failed_count,
            success_rate=obj.get_success_rate(),
            created_at=obj.created_at,
            started_at=obj.started_at,
            finished_at=obj.finished_at
        )

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None
        }


class QuoteListSchema(BaseModel):
    """询价任务分页列表响应 Schema"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页记录数")
    total_pages: int = Field(..., description="总页数")
    items: List[QuoteListItemSchema] = Field(..., description="任务列表")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None
        }


class QuoteExecuteResponseSchema(BaseModel):
    """执行询价任务响应 Schema"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    data: Optional[PreservationQuoteSchema] = Field(None, description="询价结果")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None
        }


# ============================================================================
# 法院文书下载 Schemas
# ============================================================================

class APIInterceptResponseSchema(BaseModel):
    """API拦截响应Schema"""
    code: int = Field(..., description="响应代码")
    msg: str = Field(..., description="响应消息")
    data: List[dict] = Field(..., description="文书数据列表")
    success: bool = Field(..., description="是否成功")
    totalRows: int = Field(..., description="总行数")
    
    @field_validator('data')
    @classmethod
    def validate_data_structure(cls, v: List[dict]) -> List[dict]:
        """验证data数组中每个元素的必需字段"""
        required_fields = [
            'c_sdbh', 'c_stbh', 'wjlj', 'c_wsbh', 
            'c_wsmc', 'c_fybh', 'c_fymc', 'c_wjgs', 'dt_cjsj'
        ]
        for idx, item in enumerate(v):
            missing_fields = [field for field in required_fields if field not in item]
            if missing_fields:
                raise ValueError(
                    f"数据项 {idx} 缺少必需字段: {', '.join(missing_fields)}"
                )
        return v


class CourtDocumentSchema(BaseModel):
    """文书记录输出Schema"""
    id: int = Field(..., description="记录ID")
    scraper_task_id: int = Field(..., description="爬虫任务ID")
    case_id: Optional[int] = Field(None, description="关联案件ID")
    
    # 文书信息
    c_sdbh: str = Field(..., description="送达编号")
    c_stbh: str = Field(..., description="上传编号")
    wjlj: str = Field(..., description="文件链接")
    c_wsbh: str = Field(..., description="文书编号")
    c_wsmc: str = Field(..., description="文书名称")
    c_fybh: str = Field(..., description="法院编号")
    c_fymc: str = Field(..., description="法院名称")
    c_wjgs: str = Field(..., description="文件格式")
    dt_cjsj: datetime = Field(..., description="创建时间（原始）")
    
    # 下载状态
    download_status: str = Field(..., description="下载状态")
    local_file_path: Optional[str] = Field(None, description="本地文件路径")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    error_message: Optional[str] = Field(None, description="错误信息")
    
    # 时间戳
    created_at: datetime = Field(..., description="记录创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    downloaded_at: Optional[datetime] = Field(None, description="下载完成时间")
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v is not None else None
        }


# ============================================================================
# 性能监控 Schemas
# ============================================================================

class PerformanceMetricsOut(BaseModel):
    """性能指标输出Schema"""
    total_acquisitions: int = Field(..., description="总获取次数")
    successful_acquisitions: int = Field(..., description="成功获取次数")
    failed_acquisitions: int = Field(..., description="失败获取次数")
    success_rate: float = Field(..., description="成功率（百分比）")
    avg_duration: float = Field(..., description="平均耗时（秒）")
    avg_login_duration: float = Field(..., description="平均登录耗时（秒）")
    timeout_count: int = Field(..., description="超时次数")
    network_error_count: int = Field(..., description="网络错误次数")
    captcha_error_count: int = Field(..., description="验证码错误次数")
    credential_error_count: int = Field(..., description="凭证错误次数")
    concurrent_acquisitions: int = Field(..., description="当前并发获取数")
    cache_hit_rate: float = Field(..., description="缓存命中率（百分比）")


class StatisticsReportOut(BaseModel):
    """统计报告输出Schema"""
    period: dict = Field(..., description="统计周期信息")
    summary: dict = Field(..., description="汇总统计")
    status_breakdown: List[dict] = Field(..., description="按状态分组统计")
    site_breakdown: List[dict] = Field(..., description="按网站分组统计")
    account_breakdown: List[dict] = Field(..., description="按账号分组统计")
    daily_trend: List[dict] = Field(..., description="每日趋势")
    real_time_metrics: dict = Field(..., description="实时指标")


class AlertSchema(BaseModel):
    """告警信息Schema"""
    type: str = Field(..., description="告警类型")
    message: str = Field(..., description="告警消息")
    severity: str = Field(..., description="严重程度")


class HealthCheckOut(BaseModel):
    """健康检查输出Schema"""
    status: str = Field(..., description="健康状态")
    timestamp: str = Field(..., description="检查时间")
    metrics: dict = Field(..., description="性能指标")
    alerts: List[AlertSchema] = Field(..., description="告警列表")
    thresholds: dict = Field(..., description="告警阈值")


class ResourceUsageOut(BaseModel):
    """资源使用情况输出Schema"""
    total_acquisitions: int = Field(..., description="总并发获取数")
    site_acquisitions: dict = Field(..., description="按网站分组的并发数")
    account_acquisitions: dict = Field(..., description="按账号分组的并发数")
    active_locks: int = Field(..., description="活跃锁数量")
    queue_size: int = Field(..., description="队列大小")
    config: dict = Field(..., description="并发配置")


# ============================================================================
# 法院短信处理 Schemas
# ============================================================================

@dataclass
class SMSParseResult:
    """短信解析结果"""
    sms_type: str
    download_links: List[str]
    case_numbers: List[str]
    party_names: List[str]
    has_valid_download_link: bool


class CourtSMSSubmitIn(BaseModel):
    """提交法院短信请求"""
    content: str = Field(
        ...,
        min_length=1,
        description="短信内容",
        json_schema_extra={"example": "【佛山市禅城区人民法院】法穿你好，请查收..."}
    )
    received_at: Optional[datetime] = Field(
        None,
        description="收到时间，默认为当前时间",
        json_schema_extra={"example": "2025-12-14T10:30:00Z"}
    )
    sender: Optional[str] = Field(
        None,
        description="发送方号码",
        json_schema_extra={"example": "10690..."}
    )

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """验证短信内容不能为空"""
        if not v or not v.strip():
            raise ValueError("短信内容不能为空")
        return v.strip()


class CourtSMSSubmitOut(BaseModel):
    """提交法院短信响应"""
    success: bool = Field(..., description="是否成功")
    data: dict = Field(..., description="短信记录信息")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {
                    "id": 123,
                    "status": "pending",
                    "created_at": "2025-12-14T10:30:05Z"
                }
            }
        }


class CourtSMSDetailOut(BaseModel):
    """短信处理详情响应"""
    id: int = Field(..., description="短信记录ID")
    content: str = Field(..., description="短信内容")
    received_at: datetime = Field(..., description="收到时间")
    sender: Optional[str] = Field(None, description="发送方号码")
    
    # 解析结果
    sms_type: Optional[str] = Field(None, description="短信类型")
    download_links: List[str] = Field(default_factory=list, description="下载链接列表")
    case_numbers: List[str] = Field(default_factory=list, description="案号列表")
    party_names: List[str] = Field(default_factory=list, description="当事人名称列表")
    
    # 处理状态
    status: str = Field(..., description="处理状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    retry_count: int = Field(..., description="重试次数")
    
    # 关联信息
    case: Optional[dict] = Field(None, description="关联案件信息")
    documents: List[dict] = Field(default_factory=list, description="关联文书列表")
    
    # 飞书通知
    feishu_sent_at: Optional[datetime] = Field(None, description="飞书发送时间")
    feishu_error: Optional[str] = Field(None, description="飞书发送错误")
    
    # 时间戳
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @classmethod
    def from_model(cls, obj):
        """从 Django Model 创建 Schema"""
        return cls(
            id=obj.id,
            content=obj.content,
            received_at=obj.received_at,
            sender=obj.sender,
            sms_type=obj.sms_type,
            download_links=obj.download_links,
            case_numbers=obj.case_numbers,
            party_names=obj.party_names,
            status=obj.status,
            error_message=obj.error_message,
            retry_count=obj.retry_count,
            case={
                "id": obj.case.id,
                "name": obj.case.name
            } if obj.case else None,
            documents=[
                {
                    "id": doc.id,
                    "name": doc.c_wsmc,
                    "download_url": f"/media/{doc.local_file_path}" if doc.local_file_path else None
                }
                for doc in obj.scraper_task.court_documents.all() if obj.scraper_task
            ],
            feishu_sent_at=obj.feishu_sent_at,
            feishu_error=obj.feishu_error,
            created_at=obj.created_at,
            updated_at=obj.updated_at
        )

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v is not None else None
        }


class CourtSMSListOut(BaseModel):
    """短信列表项响应"""
    id: int = Field(..., description="短信记录ID")
    content: str = Field(..., description="短信内容（截取前100字符）")
    received_at: datetime = Field(..., description="收到时间")
    sms_type: Optional[str] = Field(None, description="短信类型")
    status: str = Field(..., description="处理状态")
    case_name: Optional[str] = Field(None, description="关联案件名称")
    has_documents: bool = Field(..., description="是否有关联文书")
    feishu_sent: bool = Field(..., description="是否已发送飞书通知")
    created_at: datetime = Field(..., description="创建时间")

    @classmethod
    def from_model(cls, obj):
        """从 Django Model 创建 Schema"""
        return cls(
            id=obj.id,
            content=obj.content[:100] + "..." if len(obj.content) > 100 else obj.content,
            received_at=obj.received_at,
            sms_type=obj.sms_type,
            status=obj.status,
            case_name=obj.case.name if obj.case else None,
            has_documents=bool(obj.scraper_task and obj.scraper_task.court_documents.exists()),
            feishu_sent=bool(obj.feishu_sent_at),
            created_at=obj.created_at
        )

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v is not None else None
        }


class CourtSMSAssignCaseIn(BaseModel):
    """手动指定案件请求"""
    case_id: int = Field(
        ...,
        gt=0,
        description="案件ID",
        json_schema_extra={"example": 456}
    )


class CourtSMSAssignCaseOut(BaseModel):
    """手动指定案件响应"""
    success: bool = Field(..., description="是否成功")
    data: dict = Field(..., description="更新后的短信信息")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {
                    "id": 123,
                    "status": "matching",
                    "case": {
                        "id": 456,
                        "name": "广州市鸡鸡百货有限公司诉..."
                    }
                }
            }
        }


# ============================================================================
# 文书送达自动下载 Schemas
# ============================================================================

@dataclass
class DocumentDeliveryRecord:
    """文书送达记录"""
    case_number: str           # 案号
    send_time: datetime        # 发送时间
    element_index: int         # 页面元素索引（用于定位下载按钮）
    document_name: str = ""    # 文书名称（可选）
    court_name: str = ""       # 法院名称（可选）
    
    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "case_number": self.case_number,
            "send_time": self.send_time.isoformat() if self.send_time else None,
            "element_index": self.element_index,
            "document_name": self.document_name,
            "court_name": self.court_name
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentDeliveryRecord":
        """从字典反序列化"""
        send_time = None
        if data.get("send_time"):
            if isinstance(data["send_time"], str):
                send_time = datetime.fromisoformat(data["send_time"].replace('Z', '+00:00'))
            elif isinstance(data["send_time"], datetime):
                send_time = data["send_time"]
        
        # 确保字符串字段的类型安全
        document_name = data.get("document_name", "")
        if not isinstance(document_name, str):
            document_name = str(document_name) if document_name is not None else ""
        
        court_name = data.get("court_name", "")
        if not isinstance(court_name, str):
            court_name = str(court_name) if court_name is not None else ""
        
        case_number = data["case_number"]
        if not isinstance(case_number, str):
            case_number = str(case_number) if case_number is not None else ""
        
        element_index = data["element_index"]
        if not isinstance(element_index, int):
            element_index = int(element_index) if element_index is not None else 0
        
        return cls(
            case_number=case_number,
            send_time=send_time,
            element_index=element_index,
            document_name=document_name,
            court_name=court_name
        )


@dataclass
class DocumentQueryResult:
    """文书查询结果"""
    total_found: int           # 发现的文书总数
    processed_count: int       # 处理的文书数
    skipped_count: int         # 跳过的文书数（时间过滤或已处理）
    failed_count: int          # 处理失败数
    case_log_ids: List[int]    # 创建的案件日志 ID 列表
    errors: List[str]          # 错误信息列表


@dataclass
class DocumentProcessResult:
    """单个文书处理结果"""
    success: bool              # 是否成功
    case_id: Optional[int]     # 匹配的案件ID
    case_log_id: Optional[int] # 创建的案件日志ID
    renamed_path: Optional[str] # 重命名后的文件路径
    notification_sent: bool    # 是否发送了通知
    error_message: Optional[str] # 错误信息
