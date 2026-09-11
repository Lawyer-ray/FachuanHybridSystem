# Document Parsing Service

统一的文档解析服务，支持多后端（MinerU API、本地 PyMuPDF + OCR）。

## 功能特性

- ✅ MinerU API 集成（云端解析）
- ✅ 本地 PyMuPDF + OCR 后端
- ✅ 支持 PDF、DOC、PPT、Excel、图片等格式
- ✅ Markdown 格式输出
- ✅ 表格和图片提取
- ✅ 文档布局分析
- ✅ 多后端切换
- ✅ 异常处理和日志

## 使用方法

### 方法 1：直接使用 DocumentParserService

```python
from apps.document_parsing.services import get_document_parser

# 创建解析器（默认使用 MinerU）
parser = get_document_parser(backend="mineru")

# 解析文档
result = parser.parse_document(
    file_path="/path/to/document.pdf",
    extract_tables=True,
    extract_images=True,
    return_markdown=True,
)

# 使用结果
print(f"文本长度: {len(result.text)}")
print(f"Markdown:\n{result.markdown}")
```

### 方法 2：使用工厂模式

```python
from apps.document_parsing.services import ParserFactory

# 方式 1：自动选择后端（按「文档解析平台」优先级，未配置时回退 local）
parser = ParserFactory.create_parser(backend="auto")

# 方式 2：指定 MinerU（凭证从「文档解析平台」自动读取，亦可在 provider 中显式传入）
parser = ParserFactory.create_parser(
    backend="mineru",
    provider=my_provider,  # DocumentParseProvider 实例；省略时按解析服务自动查找启用平台
    model_version="vlm",
)

# 方式 3：指定本地后端
parser = ParserFactory.create_parser(backend="local")

# 解析文档
result = parser.parse_document("/path/to/document.pdf")
```

### 方法 3：通过 REST API

```bash
# 解析文档
curl -X POST http://localhost:8002/api/v1/document-parsing/parse \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -d '{
    "backend": "mineru",
    "extract_tables": true,
    "return_markdown": true
  }'

# 提取文本
curl -X POST http://localhost:8002/api/v1/document-parsing/extract-text \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -d '{
    "backend": "mineru",
    "max_length": 10000
  }'
```

## 配置

解析平台统一在后台「文档解析平台」管理页（`/admin/core/documentparseprovider/`）配置，**不再使用 SystemConfig**：

- 每行一个凭证，**多凭证自动轮询并发**，失败凭证自动 30 秒冷却并切换
- TextinParse 凭证格式：每行 `app_id|secret_code`（管道符分隔）
- MinerU 凭证格式：每行一个 API Key
- 每凭证并发上限：控制单个凭证同时进行的解析数（`0` 表示不限制）
- `backend="auto"` 按平台优先级自动选择启用解析服务；未配置任何平台时回退本地 `local`

## 在其他 App 中集成

### 示例：在 document_recognition 中使用

```python
# apps/document_recognition/services/text_extraction_service.py

from apps.document_parsing.services import get_document_parser

class TextExtractionService:
    def extract_text(self, file_path: str) -> TextExtractionResult:
        # 使用统一的文档解析服务
        parser = get_document_parser(backend="mineru")
        
        result = parser.extract_text(
            file_path=file_path,
            max_length=50000,
        )
        
        return TextExtractionResult(
            text=result.text,
            method=result.method,
            success=result.success,
        )
```

## 支持的文件格式

| 格式 | MinerU | 本地后端 |
|------|--------|----------|
| PDF  | ✅     | ✅       |
| DOC  | ✅     | ❌       |
| DOCX | ✅     | ❌       |
| PPT  | ✅     | ❌       |
| PPTX | ✅     | ❌       |
| XLS  | ✅     | ❌       |
| XLSX | ✅     | ❌       |
| JPG  | ✅     | ✅       |
| PNG  | ✅     | ✅       |

## 架构优势

1. **职责清晰**：专注于文档解析，与业务逻辑解耦
2. **统一接口**：所有 app 通过相同的方式调用文档解析
3. **可替换性**：底层可以是 MinerU、PyMuPDF、PaddleOCR，调用方无需关心
4. **配置集中**：API Key、调用参数、限流、监控统一管理
5. **按需扩展**：未来可以添加更多解析后端，不影响现有代码

## TODO

- [x] 添加 PaddleOCR 本地后端（local 内集成 PyMuPDF + RapidOCR）
- [x] 实现异步批量解析任务
- [ ] 添加调用次数和延迟监控
- [ ] 实现文件缓存机制
- [x] 文档解析平台管理界面（多凭证并发）
