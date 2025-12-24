# 法院文书下载 API 文档

## 📖 概述

法院文书下载 API 提供了通过 RESTful 接口下载法院文书的功能。支持 API 拦截方式和传统点击方式，自动保存文书元数据到数据库。

## 🔐 认证

所有 API 端点都需要 JWT 认证。

### 获取 Token

```bash
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

在请求头中添加 Authorization：

```bash
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

## 📋 API 端点

### 1. 创建下载任务

创建一个法院文书下载任务。

**端点**: `POST /api/v1/automation/court-documents/download`

**请求头**:
```
Content-Type: application/json
Authorization: Bearer <your_token>
```

**请求体**:
```json
{
  "url": "https://zxfw.court.gov.cn/...",
  "case_id": 123
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 文书页面 URL |
| `case_id` | integer | 否 | 关联的案件 ID |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "task_id": 456,
    "status": "pending",
    "url": "https://zxfw.court.gov.cn/...",
    "case_id": 123,
    "created_at": "2024-12-04T10:00:00Z"
  }
}
```

**错误响应**:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "URL 格式不正确",
    "details": {
      "url": ["请输入有效的 URL"]
    }
  }
}
```

### 2. 执行下载任务

执行指定的下载任务。

**端点**: `POST /api/v1/automation/court-documents/{task_id}/execute`

**请求头**:
```
Authorization: Bearer <your_token>
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | integer | 任务 ID |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "task_id": 456,
    "status": "completed",
    "success_count": 5,
    "failed_count": 0,
    "total_time": 12.5,
    "used_fallback": false,
    "documents": [
      {
        "id": 789,
        "c_wsmc": "民事判决书",
        "c_fymc": "深圳市中级人民法院",
        "c_wsbh": "WS202401001",
        "download_status": "success",
        "local_file_path": "/media/court_documents/民事判决书.pdf",
        "file_size": 1024000,
        "downloaded_at": "2024-12-04T10:05:00Z"
      }
    ]
  }
}
```

**错误响应**:

```json
{
  "success": false,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "任务不存在",
    "details": {
      "task_id": 456
    }
  }
}
```

### 3. 查询任务状态

查询下载任务的状态和结果。

**端点**: `GET /api/v1/automation/court-documents/{task_id}`

**请求头**:
```
Authorization: Bearer <your_token>
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | integer | 任务 ID |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "task_id": 456,
    "status": "completed",
    "url": "https://zxfw.court.gov.cn/...",
    "case_id": 123,
    "created_at": "2024-12-04T10:00:00Z",
    "completed_at": "2024-12-04T10:05:00Z",
    "documents_count": 5,
    "success_count": 5,
    "failed_count": 0
  }
}
```

### 4. 查询文书列表

查询下载的文书记录。

**端点**: `GET /api/v1/automation/court-documents`

**请求头**:
```
Authorization: Bearer <your_token>
```

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | integer | 否 | 按任务 ID 过滤 |
| `case_id` | integer | 否 | 按案件 ID 过滤 |
| `status` | string | 否 | 按下载状态过滤（pending/downloading/success/failed） |
| `court_name` | string | 否 | 按法院名称搜索 |
| `document_name` | string | 否 | 按文书名称搜索 |
| `page` | integer | 否 | 页码（默认 1） |
| `page_size` | integer | 否 | 每页数量（默认 20） |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "total": 50,
    "page": 1,
    "page_size": 20,
    "documents": [
      {
        "id": 789,
        "scraper_task_id": 456,
        "case_id": 123,
        "c_wsmc": "民事判决书",
        "c_fymc": "深圳市中级人民法院",
        "c_wsbh": "WS202401001",
        "c_fybh": "440300",
        "c_wjgs": "pdf",
        "download_status": "success",
        "local_file_path": "/media/court_documents/民事判决书.pdf",
        "file_size": 1024000,
        "created_at": "2024-12-04T10:00:00Z",
        "downloaded_at": "2024-12-04T10:05:00Z"
      }
    ]
  }
}
```

### 5. 获取文书详情

获取单个文书的详细信息。

**端点**: `GET /api/v1/automation/court-documents/{document_id}`

**请求头**:
```
Authorization: Bearer <your_token>
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `document_id` | integer | 文书 ID |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "id": 789,
    "scraper_task_id": 456,
    "case_id": 123,
    "c_sdbh": "SD202401001",
    "c_stbh": "ST202401001",
    "wjlj": "https://zxfw.court.gov.cn/...",
    "c_wsbh": "WS202401001",
    "c_wsmc": "民事判决书",
    "c_fybh": "440300",
    "c_fymc": "深圳市中级人民法院",
    "c_wjgs": "pdf",
    "dt_cjsj": "2024-01-01T12:00:00Z",
    "download_status": "success",
    "local_file_path": "/media/court_documents/民事判决书.pdf",
    "file_size": 1024000,
    "error_message": null,
    "created_at": "2024-12-04T10:00:00Z",
    "updated_at": "2024-12-04T10:05:00Z",
    "downloaded_at": "2024-12-04T10:05:00Z"
  }
}
```

### 6. 下载文书文件

下载已保存的文书文件。

**端点**: `GET /api/v1/automation/court-documents/{document_id}/download`

**请求头**:
```
Authorization: Bearer <your_token>
```

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `document_id` | integer | 文书 ID |

**响应**:

返回文件流，浏览器会自动下载文件。

**响应头**:
```
Content-Type: application/pdf
Content-Disposition: attachment; filename="民事判决书.pdf"
Content-Length: 1024000
```

## 📝 使用示例

### Python 示例

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# 1. 登录获取 Token
response = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "your_username",
    "password": "your_password"
})
token = response.json()["access"]

# 设置请求头
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# 2. 创建下载任务
response = requests.post(
    f"{BASE_URL}/automation/court-documents/download",
    json={
        "url": "https://zxfw.court.gov.cn/...",
        "case_id": 123
    },
    headers=headers
)
task_id = response.json()["data"]["task_id"]
print(f"任务创建成功，ID: {task_id}")

# 3. 执行下载任务
response = requests.post(
    f"{BASE_URL}/automation/court-documents/{task_id}/execute",
    headers=headers
)
result = response.json()["data"]
print(f"下载完成: 成功 {result['success_count']}, 失败 {result['failed_count']}")

# 4. 查询文书列表
response = requests.get(
    f"{BASE_URL}/automation/court-documents",
    params={"task_id": task_id},
    headers=headers
)
documents = response.json()["data"]["documents"]
for doc in documents:
    print(f"文书: {doc['c_wsmc']}, 状态: {doc['download_status']}")

# 5. 下载文书文件
document_id = documents[0]["id"]
response = requests.get(
    f"{BASE_URL}/automation/court-documents/{document_id}/download",
    headers=headers
)
with open("downloaded_document.pdf", "wb") as f:
    f.write(response.content)
print("文件下载成功")
```

### JavaScript 示例

```javascript
const BASE_URL = "http://localhost:8000/api/v1";

// 1. 登录获取 Token
async function login() {
  const response = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username: "your_username",
      password: "your_password",
    }),
  });
  const data = await response.json();
  return data.access;
}

// 2. 创建下载任务
async function createDownloadTask(token, url, caseId) {
  const response = await fetch(`${BASE_URL}/automation/court-documents/download`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({
      url: url,
      case_id: caseId,
    }),
  });
  const data = await response.json();
  return data.data.task_id;
}

// 3. 执行下载任务
async function executeTask(token, taskId) {
  const response = await fetch(
    `${BASE_URL}/automation/court-documents/${taskId}/execute`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    }
  );
  const data = await response.json();
  return data.data;
}

// 4. 查询文书列表
async function getDocuments(token, taskId) {
  const response = await fetch(
    `${BASE_URL}/automation/court-documents?task_id=${taskId}`,
    {
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    }
  );
  const data = await response.json();
  return data.data.documents;
}

// 5. 下载文书文件
async function downloadDocument(token, documentId) {
  const response = await fetch(
    `${BASE_URL}/automation/court-documents/${documentId}/download`,
    {
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    }
  );
  const blob = await response.blob();
  
  // 创建下载链接
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "document.pdf";
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

// 使用示例
async function main() {
  try {
    // 登录
    const token = await login();
    console.log("登录成功");
    
    // 创建任务
    const taskId = await createDownloadTask(
      token,
      "https://zxfw.court.gov.cn/...",
      123
    );
    console.log(`任务创建成功，ID: ${taskId}`);
    
    // 执行任务
    const result = await executeTask(token, taskId);
    console.log(`下载完成: 成功 ${result.success_count}, 失败 ${result.failed_count}`);
    
    // 查询文书
    const documents = await getDocuments(token, taskId);
    console.log(`共 ${documents.length} 个文书`);
    
    // 下载第一个文书
    if (documents.length > 0) {
      await downloadDocument(token, documents[0].id);
      console.log("文件下载成功");
    }
  } catch (error) {
    console.error("错误:", error);
  }
}

main();
```

### cURL 示例

```bash
# 1. 登录获取 Token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_username","password":"your_password"}' \
  | jq -r '.access')

# 2. 创建下载任务
TASK_ID=$(curl -X POST http://localhost:8000/api/v1/automation/court-documents/download \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url":"https://zxfw.court.gov.cn/...","case_id":123}' \
  | jq -r '.data.task_id')

echo "任务创建成功，ID: $TASK_ID"

# 3. 执行下载任务
curl -X POST http://localhost:8000/api/v1/automation/court-documents/$TASK_ID/execute \
  -H "Authorization: Bearer $TOKEN"

# 4. 查询文书列表
curl -X GET "http://localhost:8000/api/v1/automation/court-documents?task_id=$TASK_ID" \
  -H "Authorization: Bearer $TOKEN"

# 5. 下载文书文件（假设文书 ID 为 789）
curl -X GET http://localhost:8000/api/v1/automation/court-documents/789/download \
  -H "Authorization: Bearer $TOKEN" \
  -o document.pdf
```

## 🔍 错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| `VALIDATION_ERROR` | 400 | 请求参数验证失败 |
| `AUTHENTICATION_ERROR` | 401 | 认证失败或 Token 无效 |
| `PERMISSION_DENIED` | 403 | 权限不足 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `DOCUMENT_NOT_FOUND` | 404 | 文书不存在 |
| `FILE_NOT_FOUND` | 404 | 文件不存在 |
| `API_INTERCEPT_TIMEOUT` | 500 | API 拦截超时 |
| `DOWNLOAD_FAILED` | 500 | 文件下载失败 |
| `SERVICE_ERROR` | 500 | 服务内部错误 |

## 📊 响应格式

### 成功响应

```json
{
  "success": true,
  "data": {
    // 响应数据
  }
}
```

### 错误响应

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "错误描述",
    "details": {
      // 详细错误信息
    }
  }
}
```

## 🔗 相关文档

- **使用指南**: `docs/guides/COURT_DOCUMENT_DOWNLOAD_GUIDE.md`
- **配置说明**: `docs/operations/COURT_DOCUMENT_CONFIG.md`
- **设计文档**: `.kiro/specs/court-document-api-optimization/design.md`

---

**最后更新**: 2024-12
**维护者**: 开发团队
