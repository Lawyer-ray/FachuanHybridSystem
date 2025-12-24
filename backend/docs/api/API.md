# API 文档

## 概述

法传混合系统提供 RESTful API，基于 django-ninja 框架构建。所有 API 端点都需要 JWT 认证（除了登录和健康检查）。

**Base URL**: `http://localhost:8000/api/v1`

**API 文档**: http://localhost:8000/api/docs

## 认证

### 获取 Token

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "your_username",
  "password": "your_password"
}
```

**响应**:

```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### 使用 Token

在所有需要认证的请求中添加 Authorization 头：

```http
GET /api/v1/cases
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

### 刷新 Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

## 案件管理 API

### 列表查询

```http
GET /api/v1/cases?page=1&page_size=20&status=active&search=关键词
Authorization: Bearer <token>
```

**查询参数**:
- `page` (int, optional): 页码，默认 1
- `page_size` (int, optional): 每页数量，默认 20，最大 100
- `status` (string, optional): 案件状态
- `search` (string, optional): 搜索关键词
- `contract_id` (int, optional): 合同 ID
- `case_type` (string, optional): 案件类型

**响应**:

```json
{
  "items": [
    {
      "id": 1,
      "name": "张三诉李四合同纠纷案",
      "case_type": "civil",
      "current_stage": "first_trial",
      "status": "active",
      "contract": {
        "id": 1,
        "name": "委托代理合同001"
      },
      "created_by": {
        "id": 1,
        "username": "lawyer1"
      },
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-20T15:45:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

### 创建案件

```http
POST /api/v1/cases
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "张三诉李四合同纠纷案",
  "case_type": "civil",
  "contract_id": 1,
  "current_stage": "first_trial",
  "description": "案件描述...",
  "parties": [
    {
      "name": "张三",
      "party_type": "plaintiff",
      "legal_status": "natural_person"
    },
    {
      "name": "李四",
      "party_type": "defendant",
      "legal_status": "natural_person"
    }
  ]
}
```

**响应**: 201 Created

```json
{
  "id": 1,
  "name": "张三诉李四合同纠纷案",
  "case_type": "civil",
  "current_stage": "first_trial",
  "status": "active",
  "contract_id": 1,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 获取案件详情

```http
GET /api/v1/cases/{id}
Authorization: Bearer <token>
```

**响应**:

```json
{
  "id": 1,
  "name": "张三诉李四合同纠纷案",
  "case_type": "civil",
  "current_stage": "first_trial",
  "status": "active",
  "description": "案件描述...",
  "contract": {
    "id": 1,
    "name": "委托代理合同001",
    "status": "active"
  },
  "parties": [
    {
      "id": 1,
      "name": "张三",
      "party_type": "plaintiff",
      "legal_status": "natural_person"
    }
  ],
  "assignments": [
    {
      "id": 1,
      "lawyer": {
        "id": 1,
        "name": "王律师"
      },
      "assigned_at": "2024-01-15T10:30:00Z"
    }
  ],
  "logs": [
    {
      "id": 1,
      "content": "案件已创建",
      "created_by": "lawyer1",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "created_by": {
    "id": 1,
    "username": "lawyer1"
  },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-20T15:45:00Z"
}
```

### 更新案件

```http
PUT /api/v1/cases/{id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "张三诉李四合同纠纷案（更新）",
  "current_stage": "second_trial",
  "description": "更新后的描述..."
}
```

**响应**: 200 OK

### 删除案件

```http
DELETE /api/v1/cases/{id}
Authorization: Bearer <token>
```

**响应**: 204 No Content

## 合同管理 API

### 列表查询

```http
GET /api/v1/contracts?page=1&page_size=20&status=active
Authorization: Bearer <token>
```

**响应**:

```json
{
  "items": [
    {
      "id": 1,
      "name": "委托代理合同001",
      "case_type": "civil",
      "status": "active",
      "fee_mode": "fixed",
      "fixed_amount": 50000.00,
      "assigned_lawyer": {
        "id": 1,
        "name": "王律师"
      },
      "law_firm": {
        "id": 1,
        "name": "XX律师事务所"
      },
      "created_at": "2024-01-10T09:00:00Z"
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 20
}
```

### 创建合同

```http
POST /api/v1/contracts
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "委托代理合同001",
  "case_type": "civil",
  "fee_mode": "fixed",
  "fixed_amount": 50000.00,
  "representation_stages": ["first_trial", "second_trial"],
  "assigned_lawyer_id": 1,
  "law_firm_id": 1,
  "start_date": "2024-01-10",
  "end_date": "2024-12-31"
}
```

**响应**: 201 Created

### 获取合同详情

```http
GET /api/v1/contracts/{id}
Authorization: Bearer <token>
```

### 更新合同

```http
PUT /api/v1/contracts/{id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "status": "completed",
  "end_date": "2024-06-30"
}
```

### 添加支付记录

```http
POST /api/v1/contracts/{id}/payments
Authorization: Bearer <token>
Content-Type: application/json

{
  "amount": 10000.00,
  "payment_date": "2024-01-15",
  "payment_method": "bank_transfer",
  "notes": "首期款"
}
```

## 客户管理 API

### 列表查询

```http
GET /api/v1/clients?page=1&page_size=20&client_type=natural_person&search=张三
Authorization: Bearer <token>
```

**响应**:

```json
{
  "items": [
    {
      "id": 1,
      "name": "张三",
      "client_type": "natural_person",
      "id_number": "110101199001011234",
      "phone": "13800138000",
      "is_our_client": true,
      "created_at": "2024-01-05T14:20:00Z"
    }
  ],
  "total": 30,
  "page": 1,
  "page_size": 20
}
```

### 创建客户

```http
POST /api/v1/clients
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "张三",
  "client_type": "natural_person",
  "id_number": "110101199001011234",
  "phone": "13800138000",
  "address": "北京市朝阳区...",
  "is_our_client": true
}
```

### 获取客户详情

```http
GET /api/v1/clients/{id}
Authorization: Bearer <token>
```

### 更新客户

```http
PUT /api/v1/clients/{id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "phone": "13900139000",
  "address": "新地址..."
}
```

## 自动化服务 API

### 创建保全询价任务

```http
POST /api/v1/automation/preservation-quotes
Authorization: Bearer <token>
Content-Type: application/json

{
  "case_id": 1,
  "preservation_amount": 1000000.00,
  "preservation_type": "property",
  "applicant_name": "张三",
  "applicant_id_number": "110101199001011234"
}
```

**响应**: 201 Created

```json
{
  "id": 1,
  "case_id": 1,
  "preservation_amount": 1000000.00,
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 查询询价任务

```http
GET /api/v1/automation/preservation-quotes?status=pending&case_id=1
Authorization: Bearer <token>
```

**响应**:

```json
{
  "items": [
    {
      "id": 1,
      "case_id": 1,
      "preservation_amount": 1000000.00,
      "status": "pending",
      "quotes": [],
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

### 执行询价任务

```http
POST /api/v1/automation/preservation-quotes/{id}/execute
Authorization: Bearer <token>
```

**响应**: 200 OK

```json
{
  "id": 1,
  "status": "processing",
  "message": "询价任务已提交"
}
```

### 获取询价结果

```http
GET /api/v1/automation/preservation-quotes/{id}
Authorization: Bearer <token>
```

**响应**:

```json
{
  "id": 1,
  "case_id": 1,
  "preservation_amount": 1000000.00,
  "status": "completed",
  "quotes": [
    {
      "id": 1,
      "company_name": "XX保险公司",
      "premium": 5000.00,
      "rate": "0.5%",
      "created_at": "2024-01-15T11:00:00Z"
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T11:00:00Z"
}
```

## 错误响应

所有错误响应都遵循统一格式：

```json
{
  "error": "错误消息",
  "code": "ERROR_CODE",
  "errors": {
    "field1": "字段错误详情",
    "field2": "字段错误详情"
  }
}
```

### 常见错误码

| HTTP 状态码 | 错误码 | 说明 |
|-----------|--------|------|
| 400 | VALIDATION_ERROR | 数据验证失败 |
| 400 | DUPLICATE_NAME | 名称重复 |
| 401 | AUTHENTICATION_ERROR | 认证失败 |
| 403 | PERMISSION_DENIED | 权限不足 |
| 404 | NOT_FOUND | 资源不存在 |
| 409 | CONFLICT | 资源冲突 |
| 429 | RATE_LIMIT_ERROR | 请求过于频繁 |
| 500 | INTERNAL_ERROR | 系统错误 |
| 502 | EXTERNAL_SERVICE_ERROR | 外部服务错误 |

### 错误示例

**验证错误**:

```json
{
  "error": "数据验证失败",
  "code": "VALIDATION_ERROR",
  "errors": {
    "name": "名称不能为空",
    "phone": "手机号格式不正确"
  }
}
```

**权限错误**:

```json
{
  "error": "无权限访问该资源",
  "code": "PERMISSION_DENIED"
}
```

**资源不存在**:

```json
{
  "error": "案件不存在",
  "code": "NOT_FOUND"
}
```

## 分页

所有列表 API 都支持分页：

**请求参数**:
- `page` (int): 页码，从 1 开始
- `page_size` (int): 每页数量，默认 20，最大 100

**响应格式**:

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

## 过滤和搜索

大多数列表 API 支持过滤和搜索：

**过滤参数**:
- `status`: 状态过滤
- `case_type`: 类型过滤
- `created_after`: 创建时间过滤（起始）
- `created_before`: 创建时间过滤（结束）

**搜索参数**:
- `search`: 关键词搜索（搜索名称、描述等字段）

**示例**:

```http
GET /api/v1/cases?status=active&case_type=civil&search=张三&created_after=2024-01-01
```

## 排序

部分列表 API 支持排序：

**排序参数**:
- `order_by`: 排序字段
- `order`: 排序方向（`asc` 或 `desc`）

**示例**:

```http
GET /api/v1/cases?order_by=created_at&order=desc
```

## 速率限制

API 有速率限制以防止滥用：

- **认证用户**: 1000 请求/小时
- **未认证用户**: 100 请求/小时

超过限制会返回 429 错误：

```json
{
  "error": "请求过于频繁，请稍后重试",
  "code": "RATE_LIMIT_ERROR"
}
```

## 版本控制

当前 API 版本：`v1`

所有 API 端点都以 `/api/v1` 开头。未来版本会使用 `/api/v2` 等。

## 健康检查

### 简单健康检查

```http
GET /api/v1/health
```

**响应**:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 详细健康检查

```http
GET /api/v1/health/detail
```

**响应**:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "services": {
    "database": "healthy",
    "redis": "healthy",
    "task_queue": "healthy"
  },
  "version": "2.0.0"
}
```

## 更多信息

- **交互式 API 文档**: http://localhost:8000/api/docs
- **OpenAPI Schema**: http://localhost:8000/api/openapi.json
- **项目文档**: 查看 `README.md`
- **架构文档**: 查看 `docs/adr/`

## 联系方式

如有问题或建议，请联系：
- Issue Tracker: [链接]
- Email: [邮箱]
