# Insurance 模块

财产保全担保费询价服务模块，提供与法院保险系统的 API 交互功能。

## 主要服务类

### PreservationQuoteService

财产保全询价服务，管理询价任务的完整生命周期。

**职责：**
- 创建询价任务
- 执行询价流程（获取 Token → 获取保险公司列表 → 并发查询报价）
- 获取询价结果
- 列表查询和分页

**依赖注入：**
```python
from apps.automation.services.insurance import PreservationQuoteService

# 使用默认依赖
service = PreservationQuoteService()

# 注入自定义依赖（推荐用于测试）
service = PreservationQuoteService(
    token_service=mock_token_service,
    auto_token_service=mock_auto_token_service,
    insurance_client=mock_client
)
```

### CourtInsuranceClient

法院保险询价 API 客户端，处理与法院保险系统的 HTTP 通信。

**功能：**
- 获取保险公司列表
- 查询单个保险公司报价
- 并发查询所有保险公司报价

**性能优化：**
- 使用 httpx.AsyncClient 连接池复用
- 支持 HTTP/2 多路复用
- 自动重试网络错误

## 使用示例

### 创建询价任务

```python
from decimal import Decimal
from apps.automation.services.insurance import PreservationQuoteService

service = PreservationQuoteService()

# 创建询价任务
quote = service.create_quote(
    preserve_amount=Decimal("100000.00"),
    corp_id="法院ID",
    category_id="分类ID",
    credential_id=1  # 可选
)
print(f"任务创建成功: {quote.id}")
```

### 执行询价

```python
import asyncio

async def execute():
    service = PreservationQuoteService()
    result = await service.execute_quote(quote_id=1)
    print(f"询价完成: {result['success_count']}/{result['total_companies']} 成功")

asyncio.run(execute())
```

### 获取询价结果

```python
service = PreservationQuoteService()
quote = service.get_quote(quote_id=1)

for insurance_quote in quote.quotes.all():
    print(f"{insurance_quote.company_name}: ¥{insurance_quote.premium}")
```

## 异常处理

模块定义了以下业务异常（位于 `exceptions.py`）：

| 异常类型 | 说明 |
|---------|------|
| TokenError | Token 获取或验证失败 |
| APIError | API 调用失败 |
| NetworkError | 网络连接错误 |
| ValidationError | 数据验证失败 |
| CompanyListEmptyError | 保险公司列表为空 |
| QuoteExecutionError | 询价执行失败 |

## 相关文档

- [自动 Token 获取集成指南](../../../../docs/guides/AUTO_TOKEN_ACQUISITION_INTEGRATION.md)
- [Token 性能优化指南](../../../../docs/guides/TOKEN_PERFORMANCE_OPTIMIZATION.md)
