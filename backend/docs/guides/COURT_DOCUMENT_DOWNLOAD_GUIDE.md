# 法院文书下载优化功能使用指南

## 📖 概述

法院文书下载优化功能通过拦截 zxfw.court.gov.cn 的文书列表 API 接口，直接获取文书下载链接和元数据，避免传统的页面点击操作，大幅提高下载效率。同时将文书元数据持久化到数据库，便于后续管理和查询。

### 核心优势

- **效率提升**: API 拦截方式比传统点击下载快 3-5 倍
- **数据完整**: 自动保存文书元数据（编号、名称、法院信息等）
- **稳定可靠**: 内置回退机制，API 失败时自动切换到传统方式
- **易于管理**: Django Admin 后台完整的文书记录管理
- **批量下载**: 支持一次性下载多个文书

## 🚀 快速开始

### 1. 环境配置

确保已安装必要的依赖：

```bash
# 激活虚拟环境
source backend/venv311/bin/activate

# 安装依赖（如果还没安装）
pip install playwright
playwright install chromium
```

### 2. 配置项说明

在 `backend/apiSystem/apiSystem/settings.py` 中添加以下配置：

```python
# 法院文书下载配置
COURT_DOCUMENT_DOWNLOAD_DIR = os.path.join(MEDIA_ROOT, "court_documents")
COURT_DOCUMENT_API_TIMEOUT = 30000  # API 拦截超时（毫秒）
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = 60000  # 文件下载超时（毫秒）
COURT_DOCUMENT_DOWNLOAD_DELAY = (1, 2)  # 下载延迟范围（秒）
```

**配置项详解**：

| 配置项 | 类型 | 默认值 | 说明 |
|-------|------|--------|------|
| `COURT_DOCUMENT_DOWNLOAD_DIR` | str | `MEDIA_ROOT/court_documents` | 文书文件保存目录 |
| `COURT_DOCUMENT_API_TIMEOUT` | int | 30000 | API 拦截最大等待时间（毫秒） |
| `COURT_DOCUMENT_DOWNLOAD_TIMEOUT` | int | 60000 | 单个文件下载超时时间（毫秒） |
| `COURT_DOCUMENT_DOWNLOAD_DELAY` | tuple | (1, 2) | 下载间隔随机延迟范围（秒） |

### 3. 数据库迁移

运行迁移以创建 `CourtDocument` 模型：

```bash
cd backend/apiSystem
python manage.py migrate automation
```

## 📋 使用方式

### 方式一：Django Admin 后台

这是最简单的使用方式，适合日常操作。

#### 步骤：

1. **访问 Admin 后台**
   ```
   http://localhost:8000/admin/automation/scrapetask/
   ```

2. **创建下载任务**
   - 点击「添加爬虫任务」
   - 任务类型：选择「法院文书下载」
   - URL：输入文书页面 URL（如 `https://zxfw.court.gov.cn/...`）
   - 关联案件：可选，关联到具体案件
   - 点击「保存」

3. **查看下载结果**
   - 任务完成后，访问 `http://localhost:8000/admin/automation/courtdocument/`
   - 可以看到所有下载的文书记录
   - 点击文书记录查看详情
   - 已下载的文书可以直接下载文件

#### Admin 功能特性：

- **搜索功能**: 支持按文书名称、法院名称、文书编号搜索
- **过滤器**: 按下载状态、法院名称、创建时间过滤
- **批量操作**: 支持批量删除、批量导出
- **文件下载**: 已下载文书提供文件下载链接

### 方式二：Python 代码调用

适合需要编程控制的场景。

#### 示例代码：

```python
from apps.automation.services.scraper.scrapers.court_document import CourtDocumentScraper
from apps.automation.models import ScraperTask

# 1. 创建爬虫任务
task = ScraperTask.objects.create(
    task_type="court_document",
    url="https://zxfw.court.gov.cn/...",
    case_id=123,  # 可选
    status="pending"
)

# 2. 执行下载
scraper = CourtDocumentScraper(task)
result = scraper.download()

# 3. 查看结果
print(f"下载成功: {result['success_count']}")
print(f"下载失败: {result['failed_count']}")
print(f"总耗时: {result['total_time']}秒")

# 4. 获取文书记录
documents = task.documents.all()
for doc in documents:
    print(f"文书: {doc.c_wsmc}, 状态: {doc.download_status}")
```

### 方式三：API 调用

适合前端或第三方系统集成。

#### API 端点：

```
POST /api/v1/automation/court-documents/download
```

#### 请求示例：

```bash
curl -X POST http://localhost:8000/api/v1/automation/court-documents/download \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -d '{
    "url": "https://zxfw.court.gov.cn/...",
    "case_id": 123
  }'
```

#### 响应示例：

```json
{
  "success": true,
  "data": {
    "task_id": 456,
    "success_count": 5,
    "failed_count": 0,
    "total_time": 12.5,
    "documents": [
      {
        "id": 789,
        "c_wsmc": "民事判决书",
        "c_fymc": "深圳市中级人民法院",
        "download_status": "success",
        "local_file_path": "/media/court_documents/民事判决书.pdf"
      }
    ]
  }
}
```

## 🔧 工作原理

### 下载流程

```
1. 打开文书页面
   ↓
2. 拦截 API 响应（最多等待 30 秒）
   ├─ 成功 → 3a. 解析文书列表
   └─ 失败 → 3b. 触发回退机制（传统点击下载）
   ↓
4. 遍历文书列表
   ├─ 创建数据库记录
   ├─ 直接下载文件
   └─ 更新下载状态
   ↓
5. 返回下载结果
```

### API 拦截机制

系统会监听以下 API 接口：

```
https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew
```

**API 响应格式**：

```json
{
  "code": 200,
  "msg": "成功",
  "success": true,
  "totalRows": 5,
  "data": [
    {
      "c_sdbh": "送达编号",
      "c_stbh": "上传编号",
      "wjlj": "https://...",
      "c_wsbh": "文书编号",
      "c_wsmc": "文书名称",
      "c_fybh": "法院编号",
      "c_fymc": "法院名称",
      "c_wjgs": "pdf",
      "dt_cjsj": "2024-01-01 12:00:00"
    }
  ]
}
```

### 回退机制

当 API 拦截失败时（超时或响应异常），系统会自动切换到传统的页面点击下载方式：

1. 定位文书列表元素
2. 逐个点击下载按钮
3. 等待文件下载完成
4. 保存文件并更新状态

**回退触发条件**：
- API 拦截超时（30 秒）
- API 响应格式异常
- API 返回空数据

## 📊 数据模型

### CourtDocument 模型

```python
class CourtDocument(models.Model):
    # 关联字段
    scraper_task = ForeignKey(ScraperTask)  # 关联的爬虫任务
    case = ForeignKey(Case, null=True)      # 关联的案件（可选）
    
    # API 返回的原始字段
    c_sdbh = CharField(max_length=128)      # 送达编号
    c_stbh = CharField(max_length=512)      # 上传编号
    wjlj = URLField(max_length=1024)        # 文件链接
    c_wsbh = CharField(max_length=128)      # 文书编号
    c_wsmc = CharField(max_length=512)      # 文书名称
    c_fybh = CharField(max_length=64)       # 法院编号
    c_fymc = CharField(max_length=256)      # 法院名称
    c_wjgs = CharField(max_length=32)       # 文件格式
    dt_cjsj = DateTimeField()               # 创建时间（原始）
    
    # 下载状态字段
    download_status = CharField(            # 下载状态
        choices=[
            ("pending", "待下载"),
            ("downloading", "下载中"),
            ("success", "成功"),
            ("failed", "失败"),
        ]
    )
    local_file_path = CharField(null=True)  # 本地文件路径
    file_size = BigIntegerField(null=True)  # 文件大小（字节）
    error_message = TextField(null=True)    # 错误信息
    
    # 时间戳
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
    downloaded_at = DateTimeField(null=True)
```

### 数据库索引

为提高查询性能，已添加以下索引：

- `(scraper_task, download_status)` - 按任务查询文书
- `case` - 按案件查询文书
- `c_wsbh` - 按文书编号查询
- `c_fymc` - 按法院名称查询
- `download_status` - 按下载状态查询
- `created_at` - 按创建时间排序

### 唯一约束

- `(c_wsbh, c_sdbh)` - 文书编号 + 送达编号唯一，避免重复下载

## 🔍 查询和管理

### 查询文书记录

```python
from apps.automation.models import CourtDocument

# 查询所有成功下载的文书
documents = CourtDocument.objects.filter(download_status="success")

# 查询特定任务的文书
task_documents = CourtDocument.objects.filter(scraper_task_id=123)

# 查询特定案件的文书
case_documents = CourtDocument.objects.filter(case_id=456)

# 查询特定法院的文书
court_documents = CourtDocument.objects.filter(c_fymc__contains="深圳")

# 按文书名称搜索
search_documents = CourtDocument.objects.filter(c_wsmc__icontains="判决书")

# 查询下载失败的文书
failed_documents = CourtDocument.objects.filter(download_status="failed")
```

### 使用 Service 层

```python
from apps.automation.services.scraper.court_document_service import CourtDocumentService

service = CourtDocumentService()

# 获取任务的所有文书
documents = service.get_documents_by_task(task_id=123)

# 获取单个文书
document = service.get_document_by_id(document_id=789)

# 更新下载状态
service.update_download_status(
    document_id=789,
    status="success",
    local_file_path="/media/court_documents/判决书.pdf",
    file_size=1024000
)
```

## ⚠️ 错误处理

### 常见错误及解决方案

#### 1. API 拦截超时

**错误信息**: `API拦截超时（30000ms）`

**原因**: 
- 网络延迟
- 页面加载慢
- API 接口未触发

**解决方案**:
- 增加 `COURT_DOCUMENT_API_TIMEOUT` 配置
- 检查网络连接
- 系统会自动触发回退机制

#### 2. 文件下载失败

**错误信息**: `下载失败: timeout`

**原因**:
- 文件过大
- 网络不稳定
- 下载链接失效

**解决方案**:
- 增加 `COURT_DOCUMENT_DOWNLOAD_TIMEOUT` 配置
- 检查下载链接是否有效
- 重试下载

#### 3. 数据库保存失败

**错误信息**: `保存文书记录失败: ...`

**原因**:
- 数据库连接问题
- 字段值超长
- 唯一约束冲突

**解决方案**:
- 检查数据库连接
- 检查字段长度限制
- 文件下载不受影响，可手动补录数据

#### 4. 回退机制失败

**错误信息**: `回退机制也失败: ...`

**原因**:
- 页面结构变化
- 元素定位失败
- 网络问题

**解决方案**:
- 检查页面结构是否变化
- 更新元素选择器
- 联系技术支持

### 错误日志

所有错误都会记录到日志文件：

```bash
# 查看错误日志
tail -f backend/logs/error.log

# 查看 API 日志
tail -f backend/logs/api.log
```

## 📈 性能优化

### 下载性能

- **API 拦截方式**: 平均 2-5 秒/文书
- **传统点击方式**: 平均 5-10 秒/文书
- **批量下载**: 支持并发下载（带延迟）

### 优化建议

1. **合理设置超时时间**
   - API 拦截: 30 秒（推荐）
   - 文件下载: 60 秒（推荐）

2. **控制下载频率**
   - 使用 `COURT_DOCUMENT_DOWNLOAD_DELAY` 避免触发反爬
   - 推荐延迟: 1-2 秒

3. **数据库优化**
   - 使用 `bulk_create` 批量创建记录
   - 定期清理失败记录

4. **文件存储**
   - 定期归档旧文件
   - 使用对象存储（如 OSS）

## 🧪 测试

### 运行测试

```bash
cd backend

# 运行所有测试
python -m pytest tests/integration/automation/test_court_document_integration.py -v

# 运行属性测试
python -m pytest tests/property/automation/test_court_document_scraper_properties.py -v

# 运行单元测试
python -m pytest tests/unit/automation/test_court_document_service.py -v
```

### 测试覆盖

- ✅ API 拦截功能
- ✅ 直接下载功能
- ✅ 数据持久化
- ✅ 回退机制
- ✅ 错误处理
- ✅ Admin 管理

## 📝 最佳实践

### 1. 任务管理

- 为每个下载任务关联案件，便于后续查询
- 定期清理已完成的任务
- 失败任务及时重试

### 2. 文件管理

- 使用有意义的文件名（基于 `c_wsmc`）
- 定期备份重要文书
- 清理重复文件

### 3. 错误处理

- 监控错误日志
- 及时处理失败记录
- 记录回退机制触发频率

### 4. 性能监控

- 监控下载成功率
- 监控平均下载时间
- 监控 API 拦截成功率

## 🔗 相关文档

- **设计文档**: `.kiro/specs/court-document-api-optimization/design.md`
- **需求文档**: `.kiro/specs/court-document-api-optimization/requirements.md`
- **任务列表**: `.kiro/specs/court-document-api-optimization/tasks.md`
- **API 文档**: `backend/docs/api/API.md`
- **架构文档**: `backend/docs/architecture/ARCHITECTURE_TRAINING.md`

## 📞 技术支持

如遇到问题，请：

1. 查看错误日志
2. 查阅本文档的「错误处理」章节
3. 联系技术支持团队

---

**最后更新**: 2024-12
**维护者**: 开发团队
