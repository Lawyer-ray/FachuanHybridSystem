# Document Parsing Service 配置指南

## 支持的解析后端

| 后端 | 标识 | 类型 | 支持格式 | 说明 |
|------|------|------|----------|------|
| MinerU | `mineru` | 云端 | PDF/DOC/PPT/Excel/图片 | 通过 MinerU 云 API 解析，默认后端 |
| TextinParse | `textin` | 云端 | PDF/DOC/图片/OFD/RTF/HTML/CSV/TXT | 通过 TextinParse 云 API（xparse-client SDK）解析，格式覆盖更广 |
| 本地 | `local` | 本地 | PDF | 使用 PyMuPDF + RapidOCR，无网络依赖 |

云端后端（`mineru` / `textin`）含 HTTP 上传 + 轮询，阻塞时间长，API 层会自动走异步路径（通过后端 `requires_async_execution` 属性判断）。

## 初始配置步骤

### 1. 初始化 SystemConfig

```bash
cd /Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend
source .venv/bin/activate
python apiSystem/manage.py init_system_config
```

将创建以下配置项（在 http://127.0.0.1:8002/admin/core/systemconfig/ 中可见）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DOCUMENT_PARSING_BACKEND` | `mineru` | 默认解析后端（mineru / textin / local） |
| `MINERU_API_KEY` | (空) | MinerU API Key（**使用 mineru 时必须配置**） |
| `TEXTIN_APP_ID` | (空) | TextinParse App ID（**使用 textin 时必须配置**） |
| `TEXTIN_SECRET_CODE` | (空) | TextinParse Secret Code（**使用 textin 时必须配置**） |

> 注：MinerU 的 API URL、模型版本、轮询间隔、超时时间等均为后端内部固定常量，无需在 SystemConfig 中配置。

### 2. 在 Admin 界面配置凭证

1. 访问 http://127.0.0.1:8002/admin/core/systemconfig/
2. 根据选择的后端，编辑对应的凭证配置项：
   - MinerU：`MINERU_API_KEY`
   - TextinParse：`TEXTIN_APP_ID` 和 `TEXTIN_SECRET_CODE`
3. 保存

### 3. 验证配置

```python
# 在 Django shell 中测试
python apiSystem/manage.py shell

>>> from apps.document_parsing.services import get_document_parser
>>> parser = get_document_parser(backend="mineru")  # 或 "textin"
>>> result = parser.parse_document("/path/to/test.pdf")
>>> print("文本长度:", len(result.text))
```

## 使用示例

### 方式 1：自动读取配置（推荐）

```python
from apps.document_parsing.services import get_document_parser

# 自动从 SystemConfig 读取 DOCUMENT_PARSING_BACKEND
parser = get_document_parser(backend="auto")

result = parser.parse_document(
    file_path="/path/to/document.pdf",
    extract_tables=True,
    extract_images=False,
    return_markdown=True,
)

print(f"文本长度: {len(result.text)}")
print(f"Markdown:\n{result.markdown[:500]}...")
```

### 方式 2：手动指定后端

```python
from apps.document_parsing.services import get_document_parser

# 指定 textin 后端（凭证从 SystemConfig 自动读取）
parser = get_document_parser(backend="textin")
result = parser.parse_document("/path/to/document.pdf")

# 指定 mineru 后端
parser = get_document_parser(backend="mineru")
result = parser.parse_document("/path/to/document.pdf")
```

### 方式 3：通过 REST API

```bash
# 解析文档（multipart 上传）
curl -X POST http://localhost:8002/api/v1/document-parsing/parse \
  -H "Authorization: Bearer <your-token>" \
  -F "file=@document.pdf" \
  -F "backend=textin" \
  -F "return_markdown=true"

# 显式指定 mineru/textin 时走异步路径，返回 task_id
# 用 GET /task/{task_id} 轮询结果
curl http://localhost:8002/api/v1/document-parsing/task/{task_id} \
  -H "Authorization: Bearer <your-token>"
```

## 配置管理

### 修改配置

1. 访问 http://127.0.0.1:8002/admin/core/systemconfig/
2. 找到要修改的配置项
3. 点击编辑，修改值
4. 保存

**注意**：修改配置后，新创建的解析器会自动使用新配置。已创建的解析器实例不受影响（配置在初始化时读取）。

### 切换默认后端

将 `DOCUMENT_PARSING_BACKEND` 改为 `textin` / `mineru` / `local`，之后所有 `backend="auto"` 的调用都会使用新后端。

## 故障排除

### 未配置凭证

```
ValueError: 未配置 MinerU API Key。请在 SystemConfig 中设置 MINERU_API_KEY
ValueError: 未配置 TextinParse 凭证。请在 SystemConfig 中设置 TEXTIN_APP_ID 和 TEXTIN_SECRET_CODE
```

按错误提示在 SystemConfig 中配置对应凭证。

### API 调用失败

**检查项**：
1. 凭证是否正确
2. 网络是否可访问对应服务（mineru.net / textin 云端）
3. 文件格式是否在 `get_supported_formats()` 返回的列表中

## 凭证安全

- API Key / App ID / Secret Code 均存储在 SystemConfig 中，标记为 `is_secret=True`
- 在 Admin 界面中显示为密码字段（隐藏）
- 不会在日志或错误信息中暴露
- 建议定期轮换凭证

## 相关文档

- MinerU 官网：https://mineru.net
- MinerU API 文档：https://mineru.net/apiManage/docs
- SystemConfig Admin：http://127.0.0.1:8002/admin/core/systemconfig/
