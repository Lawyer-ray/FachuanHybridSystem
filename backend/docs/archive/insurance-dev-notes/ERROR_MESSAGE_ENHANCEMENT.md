# 错误信息增强 - 记录完整请求和响应

## 实现日期
2025-11-29

## 需求
在 Django Admin 的保险公司报价记录中，无论成功或失败，都要在 `error_message` 字段中记录完整的请求和响应信息，方便调试。

## 实现方案

### 1. 数据结构修改

**文件**: `backend/apps/automation/services/insurance/court_insurance_client.py`

在 `PremiumResult` 数据类中添加 `request_info` 字段：

```python
@dataclass
class PremiumResult:
    """报价结果"""
    company: InsuranceCompany
    premium: Optional[Decimal]
    status: str  # "success" or "failed"
    error_message: Optional[str]
    response_data: Optional[Dict]
    request_info: Optional[Dict] = None  # 请求信息（用于调试）
```

### 2. 请求信息构建

在 `fetch_premium` 方法中，构建包含所有请求参数的字典：

```python
# 构建请求信息（用于记录）
request_info = {
    "url": self.PREMIUM_QUERY_URL,
    "method": "POST",
    "timestamp": current_time_ms,
    "params": params.copy(),
    "body": request_body.copy(),
    "headers": {k: v[:50] + "..." if k == "Bearer" and len(v) > 50 else v for k, v in headers.items()},
    "timeout": timeout if timeout else self.DEFAULT_TIMEOUT,
}
```

### 3. 错误信息格式

所有返回的 `error_message` 都使用 JSON 格式，包含以下结构：

#### 3.1 成功时的信息

```json
{
  "status": "success",
  "request": {
    "url": "https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium",
    "method": "POST",
    "timestamp": "1764374731053",
    "params": {
      "time": "1764374731053",
      "preserveAmount": "3",
      "institution": "002",
      "corpId": "2550"
    },
    "body": {
      "preserveAmount": "3",
      "institution": "002",
      "corpId": "2550"
    },
    "headers": {
      "Accept": "*/*",
      "Bearer": "eyJhbGciOiJIUzUxMiJ9...",
      ...
    },
    "timeout": 60.0
  },
  "response": {
    "status_code": 200,
    "body": {
      "code": 200,
      "message": null,
      "timestamp": 1764374731053,
      "data": {
        "minPremium": "500",
        "minAmount": "500",
        "minRate": "0.002",
        "maxRate": "0.005",
        "maxAmount": "500",
        "maxApplyAmount": "1000000000"
      }
    },
    "elapsed_seconds": 1.234
  }
}
```

#### 3.2 HTTP 错误时的信息

```json
{
  "error": "HTTP 500",
  "request": { ... },
  "response": {
    "status_code": 500,
    "headers": { ... },
    "body": "{\"code\":500,\"message\":\"系统异常\",\"timestamp\":1764374731053,\"data\":null}",
    "elapsed_seconds": 0.567
  }
}
```

#### 3.3 超时错误时的信息

```json
{
  "error": "查询超时",
  "exception": "ReadTimeout('...')",
  "exception_type": "ReadTimeout",
  "request": { ... }
}
```

#### 3.4 未找到费率数据时的信息

```json
{
  "error": "响应中未找到费率数据",
  "request": { ... },
  "response": {
    "status_code": 200,
    "body": { ... },
    "elapsed_seconds": 0.789
  }
}
```

#### 3.5 未知错误时的信息

```json
{
  "error": "未知错误",
  "exception": "ValueError('...')",
  "exception_type": "ValueError",
  "traceback": "Traceback (most recent call last):\n  ...",
  "request": { ... }
}
```

### 4. 代码修改位置

所有返回 `PremiumResult` 的地方都进行了修改：

1. **HTTP 状态码错误** (status_code != 200)
2. **成功响应** (premium is not None)
3. **未找到费率数据** (premium is None but status_code == 200)
4. **超时异常** (httpx.TimeoutException)
5. **HTTP 异常** (httpx.HTTPError)
6. **未知异常** (Exception)

### 5. Admin 界面显示

在 Django Admin 的 `InsuranceQuoteInline` 中，`error_message` 字段会显示完整的 JSON 信息。

由于内容较长，建议：
- 使用 `readonly_fields` 显示
- 使用 `format_html` 格式化显示（可选）
- 或者使用自定义模板显示（可选）

## 使用示例

### 查看错误信息

1. 进入 Django Admin
2. 打开询价任务详情页
3. 查看保险公司报价内联表格
4. 点击查看 `error_message` 字段

### 解析错误信息

```python
import json

# 从数据库读取
insurance_quote = InsuranceQuote.objects.get(id=1)

# 解析 JSON
error_info = json.loads(insurance_quote.error_message)

# 查看请求信息
print("请求 URL:", error_info["request"]["url"])
print("请求参数:", error_info["request"]["params"])
print("请求体:", error_info["request"]["body"])

# 查看响应信息（如果有）
if "response" in error_info:
    print("响应状态码:", error_info["response"]["status_code"])
    print("响应内容:", error_info["response"]["body"])
```

## 优点

### 1. 完整的调试信息
- 包含请求的所有参数（URL、headers、body、params）
- 包含响应的所有信息（status_code、headers、body）
- 包含异常的完整堆栈信息

### 2. 结构化数据
- 使用 JSON 格式，易于解析
- 可以使用工具（如 jq）进行查询和过滤
- 可以导出到日志分析系统

### 3. 成功和失败都记录
- 成功的请求也记录完整信息，方便对比
- 失败的请求包含详细的错误原因

### 4. 便于问题排查
- 可以直接复制请求信息，使用 curl 或 Postman 重现问题
- 可以对比成功和失败的请求，找出差异
- 可以分析响应内容，定位 API 问题

## 注意事项

### 1. 数据库字段大小

`error_message` 字段是 `TextField`，可以存储大量文本。但如果响应内容非常大，可能需要：
- 截断响应内容（保留前 N 个字符）
- 或者将完整响应存储到文件系统

### 2. 敏感信息

`error_message` 中包含 Bearer Token（已截断），但仍需注意：
- 不要将 `error_message` 暴露给前端用户
- 定期清理旧的错误记录
- 在日志中脱敏处理

### 3. JSON 格式化

在 Admin 界面显示时，可以使用 `<pre>` 标签格式化 JSON：

```python
def error_message_display(self, obj):
    """格式化显示错误信息"""
    if obj.error_message:
        try:
            import json
            error_info = json.loads(obj.error_message)
            formatted = json.dumps(error_info, ensure_ascii=False, indent=2)
            return format_html('<pre style="max-height: 400px; overflow: auto;">{}</pre>', formatted)
        except:
            return obj.error_message
    return "-"
```

## 测试清单

- [x] 修改 PremiumResult 数据类
- [x] 构建 request_info 字典
- [x] 修改所有返回 PremiumResult 的地方
- [x] 成功时记录完整信息
- [x] HTTP 错误时记录完整信息
- [x] 超时时记录完整信息
- [x] 未找到费率数据时记录完整信息
- [x] 未知异常时记录完整信息
- [ ] 测试询价流程，验证错误信息正确记录
- [ ] 在 Admin 界面查看错误信息
- [ ] 验证 JSON 格式正确
- [ ] 验证敏感信息已脱敏

## 相关文件

- `backend/apps/automation/services/insurance/court_insurance_client.py` - 客户端代码
- `backend/apps/automation/models.py` - 数据模型
- `backend/apps/automation/admin/preservation_quote_admin.py` - Admin 配置

## 后续优化建议

### 1. 错误信息可视化

在 Admin 界面添加一个自定义视图，以更友好的方式展示错误信息：
- 请求信息折叠面板
- 响应信息语法高亮
- 错误信息突出显示

### 2. 错误统计

统计不同类型的错误：
- HTTP 500 错误的保险公司
- 超时的保险公司
- 未找到费率数据的保险公司

### 3. 错误导出

支持将错误信息导出为：
- JSON 文件
- CSV 文件（展开字段）
- 日志文件

### 4. 错误重现

提供一个工具，可以根据 `error_message` 中的请求信息，自动重现请求：
```bash
python manage.py replay_request --quote-id 123
```
