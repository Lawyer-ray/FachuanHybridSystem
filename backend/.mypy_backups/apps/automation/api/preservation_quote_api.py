"""
财产保全询价 API

提供财产保全担保费询价的 RESTful API 接口：
- POST /preservation-quotes - 创建询价任务
- GET /preservation-quotes - 列表查询
- GET /preservation-quotes/{id} - 获取详情
- POST /preservation-quotes/{id}/execute - 执行任务
"""
import logging
from typing import Optional
from ninja import Router
from ninja_jwt.authentication import JWTAuth
from django.http import HttpRequest

from apps.automation.schemas import (
    PreservationQuoteCreateSchema,
    PreservationQuoteSchema,
    QuoteListSchema,
    QuoteListItemSchema,
    QuoteExecuteResponseSchema,
)

# Exceptions are handled by global exception handlers
import math

logger = logging.getLogger("apps.automation")

# 创建路由器，使用 JWT 认证
router = Router(tags=["财产保全询价"], auth=JWTAuth())


def _get_preservation_quote_service():
    """
    工厂函数：创建财产保险询价服务实例
    
    通过ServiceLocator获取财产保全询价服务，确保依赖解耦
    
    Returns:
        IPreservationQuoteService 实例
    """
    from apps.core.interfaces import ServiceLocator
    return ServiceLocator.get_preservation_quote_service()


@router.post("/preservation-quotes", response=PreservationQuoteSchema)
def create_preservation_quote(
    request: HttpRequest,
    data: PreservationQuoteCreateSchema
):
    """
    创建询价任务
    
    创建一个新的财产保全担保费询价任务。任务创建后状态为 PENDING，
    需要调用执行接口来实际执行询价。
    
    **请求参数：**
    - preserve_amount: 保全金额（必须为正数）
    - corp_id: 企业/法院ID
    - category_id: 分类ID (cPid)
    - credential_id: 账号凭证ID
    
    **响应：**
    返回创建的询价任务详情
    
    **错误码：**
    - VALIDATION_ERROR: 数据验证失败
    """
    # 创建 Service 实例（使用工厂函数）
    service = _get_preservation_quote_service()
    
    # 调用 Service 方法
    quote = service.create_quote(
        preserve_amount=data.preserve_amount,
        corp_id=data.corp_id,
        category_id=data.category_id,
        credential_id=data.credential_id,
    )
    
    # 返回响应
    return PreservationQuoteSchema.from_model(quote)


@router.get("/preservation-quotes", response=QuoteListSchema)
def list_preservation_quotes(
    request: HttpRequest,
    page: int = 1,
    page_size: Optional[int] = None,
    status: Optional[str] = None
):
    """
    列表查询询价任务
    
    分页查询询价任务列表，支持按状态筛选。
    
    **查询参数：**
    - page: 页码（从 1 开始，默认 1）
    - page_size: 每页数量（默认 20，最大 100）
    - status: 状态筛选（可选）
      - pending: 等待中
      - running: 执行中
      - success: 成功
      - partial_success: 部分成功
      - failed: 失败
    
    **响应：**
    返回分页的任务列表，包含总数、页码等信息
    """
    # 创建 Service 实例（使用工厂函数）
    service = _get_preservation_quote_service()
    
    # 调用 Service 方法（参数验证在 Service 层）
    quotes, total = service.list_quotes(
        page=page,
        page_size=page_size,
        status=status,
    )
    
    # 计算总页数
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    
    # 转换为 Schema
    items = [QuoteListItemSchema.from_model(quote) for quote in quotes]
    
    # 返回响应
    return QuoteListSchema(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get("/preservation-quotes/{quote_id}", response=PreservationQuoteSchema)
def get_preservation_quote(
    request: HttpRequest,
    quote_id: int
):
    """
    获取询价任务详情
    
    获取指定询价任务的详细信息，包括所有保险公司的报价记录。
    
    **路径参数：**
    - quote_id: 询价任务ID
    
    **响应：**
    返回询价任务详情，包含所有保险公司报价列表
    
    **错误码：**
    - NOT_FOUND: 任务不存在
    """
    # 创建 Service 实例（使用工厂函数）
    service = _get_preservation_quote_service()
    
    # 调用 Service 方法
    quote = service.get_quote(quote_id)
    
    # 返回响应
    return PreservationQuoteSchema.from_model(quote)


@router.post("/preservation-quotes/{quote_id}/execute", response=QuoteExecuteResponseSchema)
async def execute_preservation_quote(
    request: HttpRequest,
    quote_id: int
):
    """
    执行询价任务
    
    执行指定的询价任务，系统会：
    1. 检查 Token 是否有效
    2. 获取保险公司列表
    3. 并发查询所有保险公司报价
    4. 保存报价结果
    
    **注意：**
    - 如果 Token 不存在或已过期，会返回错误提示，需要先到 /admin/automation/testcourt/ 获取 Token
    - 执行过程是异步的，可能需要几秒到几十秒
    - 单个保险公司查询失败不会影响其他查询
    
    **路径参数：**
    - quote_id: 询价任务ID
    
    **响应：**
    返回执行结果，包含成功/失败统计
    
    **错误码：**
    - NOT_FOUND: 任务不存在
    - TOKEN_ERROR: Token 相关错误
    - FETCH_COMPANIES_FAILED: 获取保险公司列表失败
    """
    # 创建 Service 实例（使用工厂函数）
    service = _get_preservation_quote_service()
    
    # 执行询价（异步）
    result = await service.execute_quote(quote_id)
    
    # 获取更新后的任务详情
    quote = service.get_quote(quote_id)
    
    # 返回响应
    return QuoteExecuteResponseSchema(
        success=True,
        message=f"询价任务执行完成，成功 {result['success_count']} 个，失败 {result['failed_count']} 个",
        data=PreservationQuoteSchema.from_model(quote),
    )


@router.post("/preservation-quotes/{quote_id}/retry", response=QuoteExecuteResponseSchema)
async def retry_preservation_quote(
    request: HttpRequest,
    quote_id: int
):
    """
    重试询价任务
    
    重新执行失败或部分成功的询价任务。系统会：
    1. 检查任务状态是否允许重试
    2. 重置任务状态
    3. 重新执行完整的询价流程
    
    **注意：**
    - 只有失败或部分成功的任务可以重试
    - 重试会使用最新的Token和账号策略
    - 之前的报价记录会被保留
    
    **路径参数：**
    - quote_id: 询价任务ID
    
    **响应：**
    返回重试执行结果
    
    **错误码：**
    - NOT_FOUND: 任务不存在
    - VALIDATION_ERROR: 任务状态不允许重试
    - TOKEN_ERROR: Token 相关错误
    """
    # 创建 Service 实例（使用工厂函数）
    service = _get_preservation_quote_service()
    
    # 重试询价（异步）
    result = await service.retry_quote(quote_id)
    
    # 获取更新后的任务详情
    quote = service.get_quote(quote_id)
    
    # 返回响应
    return QuoteExecuteResponseSchema(
        success=True,
        message=f"重试询价任务完成，成功 {result['success_count']} 个，失败 {result['failed_count']} 个",
        data=PreservationQuoteSchema.from_model(quote),
    )
