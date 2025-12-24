# 📄 法院文书下载爬虫使用指南

## 功能概述

法院文书下载爬虫支持两种链接格式，自动识别并下载司法文书。

## 支持的链接类型

### 1. zxfw.court.gov.cn（法院执行平台）

**链接格式示例**:
```
https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=xxx&sdbh=xxx&sdsin=xxx
```

**特点**:
- 直接进入文书列表页
- 可能包含多份文书
- 每份文书单独下载（PDF 格式）

**下载流程**:
1. 打开链接，等待页面加载
2. 检测文书数量（通过 XPath 定位）
3. 逐一点击下载按钮
4. 保存每份 PDF 文件

**XPath 定位**:
- 文书列表项: `/html/body/uni-app/uni-layout/uni-content/uni-main/uni-page/uni-page-wrapper/uni-page-body/uni-view/uni-view/uni-view/uni-view[1]/uni-view[1]/uni-view`
- 下载按钮: `//*[@id="download"]`

---

### 2. sd.gdems.com（广东电子送达）

**链接格式示例**:
```
https://sd.gdems.com/v3/dzsd/B0MBNGh
https://sd.gdems.com/v3/dzsd/VQSHrG
```

**特点**:
- 先进入封面页
- 需要点击"确认并预览材料"
- 打包下载为 ZIP 文件
- 自动解压 ZIP

**下载流程**:
1. 打开链接，进入封面页
2. 点击"确认并预览材料"按钮
3. 进入预览页，提取案件信息
4. 点击打包下载按钮
5. 下载 ZIP 文件
6. 自动解压 ZIP

**XPath 定位**:
- 确认按钮: `//*[@id="submit-btn"]`
- 案件信息: `/html/body/div/div[1]/div[1]/label/a`
- 下载按钮: `/html/body/div/div[1]/div[1]/label/a`

---

## 使用方法

### 方法 1: 通过 Django Admin

1. 访问 Django Admin -> 🕷️ 爬虫工具 -> 任务管理
2. 点击"添加任务管理"
3. 填写表单:
   - **任务类型**: 下载司法文书
   - **目标URL**: 粘贴法院发送的链接
   - **关联案件**: 选择对应的案件（可选）
   - **优先级**: 1-10（数字越小优先级越高）
4. 保存后，任务会自动提交到后台队列执行

### 方法 2: 通过 Python 代码

```python
from apps.automation.models import ScraperTask, ScraperTaskType
from django_q.tasks import async_task

# 创建任务
task = ScraperTask.objects.create(
    task_type=ScraperTaskType.COURT_DOCUMENT,
    url="https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=xxx",
    case_id=123,  # 关联案件 ID（可选）
    priority=5,
    config={}
)

# 提交到后台队列
async_task("apps.automation.tasks.execute_scraper_task", task.id)
```

### 方法 3: 通过 API（未来实现）

```bash
POST /api/automation/scraper-tasks/
{
    "task_type": "court_document",
    "url": "https://sd.gdems.com/v3/dzsd/B0MBNGh",
    "case_id": 123,
    "priority": 5
}
```

---

## 下载结果

### zxfw.court.gov.cn 返回格式

```python
{
    "source": "zxfw.court.gov.cn",
    "document_count": 3,           # 文书总数
    "downloaded_count": 3,         # 成功下载数
    "files": [                     # 文件路径列表
        "/media/case_logs/123/documents/document_1.pdf",
        "/media/case_logs/123/documents/document_2.pdf",
        "/media/case_logs/123/documents/document_3.pdf"
    ],
    "screenshot": "/media/automation/screenshots/zxfw_list_xxx.png",
    "message": "成功下载 3/3 份文书"
}
```

### sd.gdems.com 返回格式

```python
{
    "source": "sd.gdems.com",
    "case_info": "(2024)粤0106民初12345号",  # 案件信息
    "zip_file": "/media/case_logs/123/documents/documents.zip",
    "extracted_files": [           # 解压后的文件列表
        "/media/case_logs/123/documents/extracted/起诉状.pdf",
        "/media/case_logs/123/documents/extracted/证据1.pdf",
        "/media/case_logs/123/documents/extracted/证据2.pdf"
    ],
    "file_count": 3,
    "screenshots": [
        "/media/automation/screenshots/gdems_cover_xxx.png",
        "/media/automation/screenshots/gdems_preview_xxx.png"
    ],
    "message": "成功下载并解压 3 个文件"
}
```

---

## 文件存储路径

### 关联案件时

```
MEDIA_ROOT/
└── case_logs/
    └── {case_id}/
        └── documents/
            ├── document_1.pdf
            ├── document_2.pdf
            ├── documents.zip
            └── extracted/
                ├── 起诉状.pdf
                └── 证据1.pdf
```

### 未关联案件时

```
MEDIA_ROOT/
└── automation/
    └── downloads/
        └── task_{task_id}/
            ├── document_1.pdf
            └── documents.zip
```

---

## 错误处理

### 常见错误

1. **页面加载超时**
   - 原因: 网络问题或网站响应慢
   - 解决: 自动重试（最多 3 次）

2. **找不到下载按钮**
   - 原因: 页面结构变化或 XPath 失效
   - 解决: 检查截图，更新 XPath

3. **下载失败**
   - 原因: 文件过大或网络中断
   - 解决: 增加超时时间，自动重试

4. **ZIP 解压失败**
   - 原因: ZIP 文件损坏
   - 解决: 保留原始 ZIP 文件，手动解压

### 查看错误信息

1. 在 Django Admin 中查看任务详情
2. 查看 `error_message` 字段
3. 查看截图（保存在 `MEDIA_ROOT/automation/screenshots/`）
4. 查看日志文件（`backend/logs/api.log`）

---

## 测试

### 运行测试脚本

```bash
cd backend

# 测试所有类型
python test_court_document.py

# 只测试 zxfw.court.gov.cn
python test_court_document.py --type zxfw

# 只测试 sd.gdems.com
python test_court_document.py --type gdems
```

### 测试链接

**zxfw.court.gov.cn**:
```
https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=28938b642114470e80472ca62d5f622b&sdbh=97e29694bd324242bf4d50d00284e473&sdsin=83b0c4f5d938757e11b2cfd0292a1e31
```

**sd.gdems.com**:
```
https://sd.gdems.com/v3/dzsd/B0MBNGh
```

---

## 与其他模块的集成

### 1. 司法信息（JudicialInfo）

```python
# 从短信中提取链接后，创建下载任务
judicial_info = JudicialInfo.objects.get(id=1)
url = judicial_info.extract_url()  # 提取链接（待实现）

task = ScraperTask.objects.create(
    task_type=ScraperTaskType.COURT_DOCUMENT,
    url=url,
    case=judicial_info.case,
    config={"judicial_info_id": judicial_info.id}
)
```

### 2. 自动命名工具（AutoNamer）

```python
# 下载完成后，自动重命名文件
from apps.automation.services.document_processing import rename_documents

result = task.result
files = result.get("files", []) or result.get("extracted_files", [])

for file_path in files:
    new_name = rename_documents(file_path, case=task.case)
    # 更新文件路径
```

### 3. 案件日志（CaseLog）

```python
# 下载完成后，记录到案件日志
from apps.cases.services.case_log_service import CaseLogService

CaseLogService.create_log(
    case=task.case,
    log_type="document_received",
    content=f"收到法院送达文书 {result['downloaded_count']} 份",
    attachments=result.get("files", [])
)
```

---

## 注意事项

1. ✅ **链接有效期**: 法院发送的链接可能有时效性，建议及时下载
2. ✅ **网络环境**: 确保服务器能访问法院网站
3. ✅ **浏览器依赖**: 需要安装 Playwright 和 Chromium
4. ✅ **存储空间**: 确保有足够的磁盘空间存储文件
5. ✅ **权限管理**: 下载的文件包含敏感信息，注意权限控制

---

## 未来优化

- [ ] 支持更多法院网站
- [ ] 自动识别案号并关联案件
- [ ] 下载进度实时推送
- [ ] 文件自动命名
- [ ] 文件自动归档到案件日志
- [ ] OCR 识别文书内容
- [ ] 提取关键信息（开庭时间、判决结果等）
