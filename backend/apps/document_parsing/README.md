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

# 方式 1：自动选择后端（根据 SystemConfig）
parser = ParserFactory.create_parser(backend="auto")

# 方式 2：指定 MinerU
parser = ParserFactory.create_parser(
    backend="mineru",
    api_key="your_api_key",
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

在 SystemConfig 中添加以下配置：

```python
# 文档解析后端选择
DOCUMENT_PARSING_BACKEND = "mineru"  # mineru | local | auto

# MinerU API 配置
MINERU_API_KEY = "your_api_key_here"
MINERU_API_URL = "https://mineru.net/api/v4/extract/task"
MINERU_MODEL_VERSION = "vlm"  # vlm | MinerU-HTML
```

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

- [ ] 添加 PaddleOCR 后端
- [ ] 实现异步批量解析任务
- [ ] 添加调用次数和延迟监控
- [ ] 实现文件缓存机制
- [ ] 添加 SystemConfig 配置管理界面
