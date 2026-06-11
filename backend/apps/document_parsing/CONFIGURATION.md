# Document Parsing Service 配置指南

## 初始配置步骤

### 1. 初始化 SystemConfig

运行以下命令初始化文档解析服务的默认配置：

```bash
cd /Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend
source .venv/bin/activate
python apiSystem/manage.py init_system_config
```

这将创建以下配置项（在 http://127.0.0.1:8002/admin/core/systemconfig/ 中可见）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DOCUMENT_PARSING_BACKEND` | `mineru` | 文档解析后端选择 |
| `MINERU_API_KEY` | (空) | MinerU API Key（**必须配置**） |
| `MINERU_API_URL` | `https://mineru.net/api/v4/extract/task` | MinerU API 端点 |
| `MINERU_MODEL_VERSION` | `vlm` | MinerU 模型版本 |
| `MINERU_RATE_LIMIT_PER_MINUTE` | `60` | 每分钟调用次数限制 |
| `MINERU_RATE_LIMIT_PER_DAY` | `10000` | 每日调用次数限制 |
| `MINERU_TASK_TIMEOUT_SECONDS` | `300` | 任务超时时间（秒） |
| `MINERU_POLL_INTERVAL_SECONDS` | `2` | 结果轮询间隔（秒） |

### 2. 在 Admin 界面配置 API Key

1. 访问 http://127.0.0.1:8002/admin/core/systemconfig/
2. 找到 `MINERU_API_KEY` 配置项
3. 点击编辑，输入你的 MinerU API Key
4. 保存

### 3. 验证配置

运行以下脚本验证配置是否正确：

```python
# 在 Django shell 中测试
python apiSystem/manage.py shell

>>> from apps.core.config.system_config import SystemConfig
>>> print("API Key:", SystemConfig.get("MINERU_API_KEY"))
>>> print("Backend:", SystemConfig.get("DOCUMENT_PARSING_BACKEND"))
```

## 使用示例

### 方式 1：自动读取配置（推荐）

```python
from apps.document_parsing.services import get_document_parser

# 自动从 SystemConfig 读取配置
parser = get_document_parser(backend="auto")

# 解析文档
result = parser.parse_document(
    file_path="/path/to/document.pdf",
    extract_tables=True,
    extract_images=True,
    return_markdown=True,
)

print(f"文本长度: {len(result.text)}")
print(f"Markdown:\n{result.markdown[:500]}...")
```

### 方式 2：手动指定配置

```python
from apps.document_parsing.services import get_document_parser

# 手动指定配置（覆盖 SystemConfig）
parser = get_document_parser(
    backend="mineru",
    api_key="your_api_key",  # 可选，会覆盖 SystemConfig
    model_version="vlm",     # 可选，会覆盖 SystemConfig
)

result = parser.parse_document("/path/to/document.pdf")
```

### 方式 3：通过 REST API

```bash
# 解析文档
curl -X POST http://localhost:8002/api/v1/document-parsing/parse \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@document.pdf" \
  -d '{
    "backend": "auto",
    "extract_tables": true,
    "return_markdown": true
  }'
```

## 配置管理

### 修改配置

1. 访问 http://127.0.0.1:8002/admin/core/systemconfig/
2. 找到要修改的配置项
3. 点击编辑，修改值
4. 保存

**注意**：修改配置后，新创建的解析器会自动使用新配置。已创建的解析器实例不受影响（配置在初始化时读取）。

### 查看配置

```python
from apps.core.config.system_config import SystemConfig

# 查看单个配置
api_key = SystemConfig.get("MINERU_API_KEY")

# 查看所有文档解析配置
from apps.core.admin._system_config_data import get_document_parsing_configs
configs = get_document_parsing_configs()
for config in configs:
    print(f"{config['key']}: {SystemConfig.get(config['key'])}")
```

### 从环境变量同步配置

```bash
# 设置环境变量
export MINERU_API_KEY="your_api_key"

# 同步到 SystemConfig
python apiSystem/manage.py init_system_config --sync-env --force
```

## 故障排除

### 问题 1：未配置 API Key

**错误信息**：
```
ValueError: 未配置 MinerU API Key。请在 SystemConfig 中设置 MINERU_API_KEY
```

**解决方案**：
1. 访问 http://127.0.0.1:8002/admin/core/systemconfig/
2. 找到 `MINERU_API_KEY`，编辑并保存你的 API Key

### 问题 2：API 调用失败

**检查项**：
1. API Key 是否正确
2. 网络是否可以访问 mineru.net
3. 配置的 API URL 是否正确

**调试方法**：

```python
from apps.document_parsing.services import get_document_parser

try:
    parser = get_document_parser(backend="mineru")
    result = parser.parse_document("/path/to/test.pdf")
    print("成功:", result.text[:100])
except Exception as e:
    print("失败:", str(e))
```

## 高级配置

### 切换到本地后端

如果不想使用 MinerU API，可以切换到本地后端：

```python
# 在 SystemConfig 中修改
DOCUMENT_PARSING_BACKEND = "local"

# 或在代码中指定
parser = get_document_parser(backend="local")
```

### 混合使用

```python
# 对于重要文档使用 MinerU
mineru_parser = get_document_parser(backend="mineru")
important_result = mineru_parser.parse_document("important.pdf")

# 对于普通文档使用本地后端（免费、快速）
local_parser = get_document_parser(backend="local")
normal_result = local_parser.parse_document("normal.pdf")
```

## API Key 安全

- MinerU API Key 存储在 SystemConfig 中，标记为 `is_secret=True`
- 在 Admin 界面中显示为密码字段（隐藏）
- 不会在日志或错误信息中暴露
- 建议定期轮换 API Key

## 相关文档

- MinerU 官网：https://mineru.net
- MinerU API 文档：https://mineru.net/apiManage/docs
- SystemConfig Admin：http://127.0.0.1:8002/admin/core/systemconfig/
