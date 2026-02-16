# 文书投递服务模块

本目录包含按投递类型拆分的文书投递服务。

## 模块结构

### 1. ApiDeliveryService (api_delivery_service.py)
**职责**: API 方式文书投递

**核心方法**:
- `query_documents()` - 通过 API 查询文书列表
- `fetch_page()` - 获取指定页的文书
- `should_process_document()` - 判断是否需要处理文书
- `download_document()` - 通过 API 下载文书
- `create_delivery_record()` - 创建投递记录

**特点**:
- 直接调用法院 API
- 支持分页查询
- 自动检查文书处理状态

### 2. PlaywrightDeliveryService (playwright_delivery_service.py)
**职责**: Playwright 浏览器自动化方式投递

**核心方法**:
- `navigate_to_delivery_page()` - 导航到文书送达页面
- `extract_document_entries()` - 从页面提取文书条目
- `should_process_entry()` - 判断是否需要处理文书
- `download_document()` - 通过页面点击下载文书
- `has_next_page()` / `go_to_next_page()` - 翻页操作

**特点**:
- 使用精确 XPath 定位元素
- 支持待查阅/已查阅标签页切换
- 自动翻页处理

### 3. DocumentProcessor (document_processor.py)
**职责**: 文书下载后的处理

**核心方法**:
- `extract_zip_if_needed()` - 解压 ZIP 文件
- `process_document()` - 处理下载的文书
- `record_query_history()` - 记录查询历史
- `_process_sms_in_thread()` - 在独立线程中处理 SMS

**处理流程**:
1. 解压文件（如果是 ZIP）
2. 创建 CourtSMS 记录
3. 案件匹配（案号 → 当事人）
4. 重命名文书
5. 添加到案件日志
6. 发送通知

**特点**:
- 在独立线程中执行 ORM 操作（避免异步上下文问题）
- 支持多种案件匹配策略
- 自动同步案号到案件

## 使用示例

### 直接使用拆分后的服务

```python
from apps.automation.services.document_delivery.delivery import (
    ApiDeliveryService,
    PlaywrightDeliveryService,
    DocumentProcessor
)

# API 方式
api_client = CourtDocumentApiClient()
api_delivery = ApiDeliveryService(api_client=api_client)
result = api_delivery.query_documents(token, cutoff_time, credential_id)

# Playwright 方式
playwright_delivery = PlaywrightDeliveryService()
playwright_delivery.navigate_to_delivery_page(page, "pending")
entries = playwright_delivery.extract_document_entries(page)

# 文档处理
processor = DocumentProcessor()
process_result = processor.process_document(record, file_path, extracted_files, credential_id)
```

### 通过主服务使用（推荐）

```python
from apps.automation.services.document_delivery import DocumentDeliveryService

# 主服务会自动协调三种投递方式
service = DocumentDeliveryService()
result = service.query_and_download(
    credential_id=1,
    cutoff_time=datetime.now() - timedelta(days=7),
    tab="pending",
    debug_mode=False
)
```

## 降级策略

主服务 `DocumentDeliveryService` 实现了三级降级策略：

1. **优先**: API 方式（最快、最稳定）
2. **次选**: Playwright + API（登录后尝试 API）
3. **回退**: Playwright 页面方式（最可靠）

## 线程安全

所有涉及 ORM 操作的方法都在独立线程中执行，避免在 Playwright 异步上下文中直接操作数据库导致的问题。

## 文件大小

- `api_delivery_service.py`: 359 行
- `playwright_delivery_service.py`: 360 行
- `document_processor.py`: 542 行
- 总计: 1275 行（原文件 1844 行）

## 向后兼容

原有的 `DocumentDeliveryService` 接口保持不变，所有现有代码无需修改。
