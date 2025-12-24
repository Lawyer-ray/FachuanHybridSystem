# 法院文书下载快速参考

## 🚀 5 分钟快速开始

### 1. 环境准备

```bash
# 激活虚拟环境
source backend/venv311/bin/activate

# 安装 Playwright 浏览器
playwright install chromium

# 运行数据库迁移
cd backend/apiSystem
python manage.py migrate automation
```

### 2. 配置（可选）

在 `settings.py` 中添加：

```python
# 文书下载配置
COURT_DOCUMENT_DOWNLOAD_DIR = os.path.join(MEDIA_ROOT, "court_documents")
COURT_DOCUMENT_API_TIMEOUT = 30000  # 30 秒
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = 60000  # 60 秒
COURT_DOCUMENT_DOWNLOAD_DELAY = (1, 2)  # 1-2 秒
```

### 3. 使用方式

#### 方式一：Django Admin（推荐）

```
1. 访问: http://localhost:8000/admin/automation/scrapetask/
2. 创建任务，选择「法院文书下载」类型
3. 输入 URL，保存
4. 查看结果: http://localhost:8000/admin/automation/courtdocument/
```

#### 方式二：Python 代码

```python
from apps.automation.services.scraper.scrapers.court_document import CourtDocumentScraper
from apps.automation.models import ScraperTask

# 创建任务
task = ScraperTask.objects.create(
    task_type="court_document",
    url="https://zxfw.court.gov.cn/...",
    status="pending"
)

# 执行下载
scraper = CourtDocumentScraper(task)
result = scraper.download()

print(f"成功: {result['success_count']}, 失败: {result['failed_count']}")
```

#### 方式三：API 调用

```bash
# 获取 Token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass"}' \
  | jq -r '.access')

# 创建并执行任务
curl -X POST http://localhost:8000/api/v1/automation/court-documents/download \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://zxfw.court.gov.cn/...","case_id":123}'
```

## 📋 常用命令

```bash
# 查看文书记录
python manage.py shell
>>> from apps.automation.models import CourtDocument
>>> CourtDocument.objects.filter(download_status="success").count()

# 查看错误日志
tail -f backend/logs/error.log

# 运行测试
pytest tests/integration/automation/test_court_document_integration.py -v

# 清理失败记录
python manage.py shell
>>> from apps.automation.models import CourtDocument
>>> CourtDocument.objects.filter(download_status="failed").delete()
```

## 🔧 配置项速查

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| `COURT_DOCUMENT_DOWNLOAD_DIR` | `MEDIA_ROOT/court_documents` | 文件保存目录 |
| `COURT_DOCUMENT_API_TIMEOUT` | 30000 | API 拦截超时（毫秒） |
| `COURT_DOCUMENT_DOWNLOAD_TIMEOUT` | 60000 | 文件下载超时（毫秒） |
| `COURT_DOCUMENT_DOWNLOAD_DELAY` | (1, 2) | 下载延迟（秒） |

## 📊 数据模型速查

### CourtDocument 主要字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `c_wsmc` | string | 文书名称 |
| `c_fymc` | string | 法院名称 |
| `c_wsbh` | string | 文书编号 |
| `download_status` | string | 下载状态（pending/downloading/success/failed） |
| `local_file_path` | string | 本地文件路径 |
| `file_size` | integer | 文件大小（字节） |
| `error_message` | string | 错误信息 |

### 查询示例

```python
# 查询成功下载的文书
CourtDocument.objects.filter(download_status="success")

# 查询特定任务的文书
CourtDocument.objects.filter(scraper_task_id=123)

# 查询特定法院的文书
CourtDocument.objects.filter(c_fymc__contains="深圳")

# 查询失败的文书
CourtDocument.objects.filter(download_status="failed")
```

## 🔍 常见问题速查

### API 拦截超时

**问题**: `API拦截超时（30000ms）`

**解决**:
```python
# 增加超时时间
COURT_DOCUMENT_API_TIMEOUT = 60000
```

### 文件下载失败

**问题**: `下载失败: timeout`

**解决**:
```python
# 增加下载超时
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = 120000
```

### 目录权限错误

**问题**: `PermissionError: [Errno 13] Permission denied`

**解决**:
```bash
chmod 755 backend/apiSystem/media/court_documents
```

### Playwright 浏览器未安装

**问题**: `Executable doesn't exist`

**解决**:
```bash
playwright install chromium
```

## 📈 性能指标

- **API 拦截方式**: 2-5 秒/文书
- **传统点击方式**: 5-10 秒/文书
- **效率提升**: 3-5 倍
- **推荐延迟**: 1-2 秒

## 🔗 完整文档

- **使用指南**: `docs/guides/COURT_DOCUMENT_DOWNLOAD_GUIDE.md`
- **配置说明**: `docs/operations/COURT_DOCUMENT_CONFIG.md`
- **API 文档**: `docs/api/COURT_DOCUMENT_API.md`
- **设计文档**: `.kiro/specs/court-document-api-optimization/design.md`

## 📞 获取帮助

1. 查看错误日志: `tail -f backend/logs/error.log`
2. 查阅完整文档
3. 联系技术支持

---

**最后更新**: 2024-12
