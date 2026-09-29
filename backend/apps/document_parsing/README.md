# 文档解析服务（document_parsing）

统一的文档解析服务：多后端（MinerU 云 API / Textin 云 SDK / 本地 PyMuPDF + OCR）把文档解析为文本 / Markdown / 元数据，云后端异步执行。

## 功能特性

- ✅ 三种后端：MinerU 云 API、Textin XParse SDK、本地 PyMuPDF + OCR（`auto` 按平台优先级自动选择，未配置回退 local）
- ✅ 后端**自描述异步能力**（`requires_async_execution` 属性）：mineru / textin 走 Django-Q2 后台 + 任务轮询，local / auto 同步返回
- ✅ 异步路径契约：先建 `DocumentParsingTask` 记录 + 约定 task_name `document_parsing_{id}`，`document_parsing_hook` 依此回写结果（勿用文件名做 task_name，曾导致 hook 全部跳过）
- ✅ 凭证池：MinerU 多 API Key、Textin 多 `app_id|secret_code`；`CredentialPool` 做按 key 并发上限 + 失败冷却 + 进程内注册表复用
- ✅ 历史解析记录：`GET /records` 分页（含 100 字预览）与全文详情，供前端历史弹窗
- ✅ 共享页工件清理：页眉、独立数字行页码、HTML 注释、markdown 强调标记
- ✅ Markdown 输出、表格与图片提取、多后端切换

## 使用方法

### 方法 1：统一入口（推荐）

```python
from apps.document_parsing.services import get_document_parser

parser = get_document_parser(backend="mineru")
result = parser.parse_document(file_path="/path/to/document.pdf")
print(result.text, result.markdown)
```

### 方法 2：工厂模式

```python
from apps.document_parsing.services.parser_factory import ParserFactory

# auto：按「文档解析平台」优先级；mineru/textin 显式指定；local 本地
parser = ParserFactory.create_parser(backend="auto")
```

### 方法 3：REST API

前缀 `/api/v1/document-parsing`（JWTOrSessionAuth；multipart form 字段优先于 JSON body）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/parse` | 解析文档（同步返回或建异步任务） |
| POST | `/extract-text` | 纯文本提取（可 max_length） |
| GET | `/task/{task_id}` | 异步任务状态 / 结果轮询 |
| GET | `/records` | 历史解析记录分页（status 过滤） |
| GET | `/records/{record_id}` | 记录全文详情 |

## 配置

解析平台统一在后台「文档解析平台」管理页（`/admin/core/documentparseprovider/`）配置，**不再使用 SystemConfig**：

- 每行一个凭证，多凭证自动轮询并发，失败凭证自动 30 秒冷却并切换
- Textin 凭证格式：每行 `app_id|secret_code`（管道符分隔）；MinerU 凭证：每行一个 API Key
- 每凭证并发上限：`0` 表示不限制

## 数据模型

- `DocumentParsingTask` — 解析任务与结果（file_name、status pending/processing/completed/failed、backend_used、text、markdown、metadata、error_message；自带 mark_* 状态方法）
- `DocumentParsingTool` — managed=False 虚拟模型（Admin 工作台入口）

## Admin

- `DocumentParsingToolAdmin`：渲染工作台 + `upload/` POST 视图（后台直接上传解析）
- `DocumentParsingTaskAdmin`：状态 / 文本预览 + `download_markdown` 自定义 URL

## 异步任务

`tasks.execute_parse_document` / `execute_extract_text`（Q2 worker，timeout 600）+ `document_parsing_hook` 完成回写。async 视图中触发 ORM 的调用必须 `sync_to_async` 包裹（防 SynchronousOnlyOperation）。

## 在其他 App 中集成

```python
from apps.document_parsing.services import get_document_parser

parser = get_document_parser(backend="mineru")
result = parser.extract_text(file_path=path, max_length=50000)
```

消费方：labor_arbitration（仲裁文书解析）、pdf_splitting（云端整本解析优先）、document_recognition（文本提取）等。

## 支持的文件格式

| 格式 | MinerU / Textin | 本地后端 |
|------|--------|----------|
| PDF  | ✅     | ✅       |
| DOC / DOCX / PPT / PPTX / XLS / XLSX | ✅ | ❌ |
| JPG / PNG | ✅ | ✅ |
