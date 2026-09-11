# Document Parsing Service 配置指南

## 支持的解析后端

| 后端 | 标识 | 类型 | 支持格式 | 说明 |
|------|------|------|----------|------|
| MinerU | `mineru` | 云端 | PDF/DOC/PPT/Excel/图片 | 通过 MinerU 云 API 解析 |
| TextinParse | `textin` | 云端 | PDF/DOC/图片/OFD/RTF/HTML/CSV/TXT | 通过 TextinParse 云 API（xparse-client SDK）解析，格式覆盖更广 |
| 本地 | `local` | 本地 | PDF | 使用 PyMuPDF + RapidOCR，无网络依赖 |

云端后端（`mineru` / `textin`）含 HTTP 上传 + 轮询，阻塞时间长，API 层会自动走异步路径（通过后端 `requires_async_execution` 属性判断）。

## 配置入口

文档解析平台统一由后台「文档解析平台」管理页（`http://127.0.0.1:8002/admin/core/documentparseprovider/`）管理，**不再使用「系统配置」下的解析服务项**。

每个平台是一份供应商配置，支持多凭证并发：

| 字段 | 说明 |
|------|------|
| 平台名称 | 任意可辨识名称，唯一 |
| 解析服务 | `textin`（TextinParse）或 `mineru`（MinerU） |
| 凭证 | 每行一个凭证；TextinParse 每行 `app_id\|secret_code`（管道符分隔），MinerU 每行一个 API Key |
| 每凭证并发上限 | 单个凭证同时进行的解析数上限；`0` 表示不限制 |
| 优先级 | 数字越小越优先；`backend="auto"` 时选择最高优先级的启用平台 |
| 启用 | 停用即不再参与解析 |

## 首次配置步骤

### 1. 迁移旧配置（升级场景）

从旧版本升级时运行 `manage.py migrate` 会自动完成：将系统配置里的 `MINERU_API_KEY`、`TEXTIN_APP_ID`、`TEXTIN_SECRET_CODE`、`DOCUMENT_PARSING_BACKEND` 播种为「文档解析平台」记录，并删除旧键。

### 2. 在 Admin 界面配置凭证

1. 访问 http://127.0.0.1:8002/admin/core/documentparseprovider/
2. 新增或编辑平台记录：
   - MinerU：在「凭证」中每行填一个 API Key
   - TextinParse：在「凭证」中每行填一组 `app_id|secret_code`
3. 保存

> 多凭证自动轮询分配：失败凭证进入 30 秒冷却并自动切换下一个；配合「每凭证并发上限」精细控制并发。

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

### 方式 1：自动选择（推荐）

```python
from apps.document_parsing.services import get_document_parser

# auto：按优先级选择最高优先级的启用解析平台；未配置任何平台时回退本地 local
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

# 指定 textin 后端（凭证从「文档解析平台」自动读取）
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

### 修改配置 / 切换默认解析服务

- 修改凭证或并发上限：在「文档解析平台」编辑对应记录后保存，进程内缓存 300 秒自动失效即生效
- **切换默认后端**：调整各平台记录的「优先级」——`backend="auto"` 始终选择**优先级最小**的启用平台；若某服务需停用，取消勾选「启用」即可
- 若删除所有平台，`auto` 会自动回退到本地解析（`local`）

### 多凭证并发

- MinerU：每行一个 API Key，多 Key 自动轮询，总并发 ≈ Key 数 × 每凭证并发上限
- TextinParse：每行一组 `app_id|secret_code`，多组凭证共同提升并发，总并发 ≈ 凭证组数 × 每凭证并发上限

## 故障排除

### 未配置凭证

```
ValueError: 未配置 MinerU 解析平台。
ValueError: TextinParse 解析平台未填写有效凭证。
```

在「文档解析平台」管理页填写对应平台的凭证（确保格式正确：MinerU 每行一个 Key，TextinParse 每行 `app_id|secret_code`）。

### 所有凭证失败冷却中

```
TextinAPIError / MinerU 错误：所有凭证仍在失败冷却中。
```

代表平台下所有凭证近期均调用失败，自动进入 30 秒冷却。检查凭证是否过期、网络是否可达对应服务。

### API 调用失败

**检查项**：
1. 凭证是否正确、是否仍在有效期内
2. 网络是否可访问对应服务（mineru.net / textin 云端）
3. 文件格式是否在 `get_supported_formats()` 返回的列表中

## 凭证安全

- 平台 `credentials` 字段以 `is_secret=True` / SecretCodec 加密存储，Admin 中显示为密码字段（隐藏）
- 不会在日志或错误信息中暴露明文凭证
- 建议定期轮换凭证（修改后保存即生效）

## 相关文档

- MinerU 官网：https://mineru.net
- MinerU API 文档：https://mineru.net/apiManage/docs
- 「文档解析平台」Admin：http://127.0.0.1:8002/admin/core/documentparseprovider/