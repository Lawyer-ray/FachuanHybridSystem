# 📁 自动化工具 - 目录结构

## ✅ 最终优化后的结构

```
automation/
├── README.md                   # 简洁入口
│
├── 📂 admin/                   # Django Admin（按功能分组）
│   ├── document/                   # 文档处理 Admin
│   │   ├── __init__.py
│   │   ├── document_processor_admin.py
│   │   └── auto_namer_admin.py
│   │
│   ├── scraper/                    # 爬虫 Admin
│   │   ├── __init__.py
│   │   ├── scraper_admin_site.py
│   │   ├── scraper_task_admin.py
│   │   ├── scraper_cookie_admin.py
│   │   ├── scraper_test_admin.py
│   │   └── quick_download_admin.py
│   │
│   ├── templates/                  # Admin 模板
│   └── __init__.py
│
├── 📂 api/                     # API 接口
│   ├── __init__.py
│   ├── main_api.py
│   ├── document_processor_api.py
│   └── auto_namer_api.py
│
├── 📂 services/                # 业务逻辑（按功能分组）
│   ├── scraper/                    # 爬虫服务
│   │   ├── core/                       # 核心服务
│   │   │   ├── __init__.py
│   │   │   ├── browser_service.py
│   │   │   ├── cookie_service.py
│   │   │   ├── anti_detection.py
│   │   │   ├── captcha_service.py
│   │   │   ├── security_service.py
│   │   │   ├── validator_service.py
│   │   │   └── monitor_service.py
│   │   │
│   │   ├── scrapers/                   # 爬虫实现
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── test_scraper.py
│   │   │   ├── court_document.py
│   │   │   └── court_filing.py
│   │   │
│   │   └── __init__.py
│   │
│   ├── document/                   # 文档处理服务
│   │   ├── __init__.py
│   │   └── document_processing.py
│   │
│   └── ai/                         # AI 服务
│       ├── __init__.py
│       ├── moonshot_client.py
│       ├── ollama_client.py
│       └── prompts.py
│
├── 📂 docs/                    # 📚 所有文档
│   ├── INDEX.md
│   ├── README.md
│   ├── QUICKSTART.md
│   ├── COURT_DOCUMENT_GUIDE.md
│   ├── IMPLEMENTATION_SUMMARY.md
│   ├── REVIEW.md
│   ├── STRUCTURE.md
│   └── CHANGELOG.md
│
├── 📂 tests/                   # 🧪 所有测试
│   ├── README.md
│   ├── test_court_document.py
│   └── debug_page_structure.py
│
├── 📂 migrations/              # 数据库迁移
│
├── models.py                   # 数据模型
├── tasks.py                    # Django-Q 后台任务
├── schemas.py                  # Pydantic 模式
├── checks.py                   # 系统检查
└── apps.py                     # 应用配置
```

## 🎯 设计原则

### 1. 按功能分组
- **admin/** - 按功能模块分组（document/speech/scraper）
- **services/** - 按业务领域分组（scraper/document/speech/ai）
- **docs/** - 所有文档集中管理
- **tests/** - 所有测试集中管理

### 2. 清晰的层次
- **一级目录** - 按技术层次（admin/api/services）
- **二级目录** - 按功能模块（document/speech/scraper/ai）
- **三级目录** - 按具体实现（core/scrapers）

### 3. 易于扩展
- 新增功能模块 → 在对应目录下创建新子目录
- 新增爬虫 → 在 `services/scraper/scrapers/` 添加
- 新增文档 → 在 `docs/` 添加

## 📊 目录职责

### admin/ - Django Admin 配置
```
admin/
├── document/       # 文档处理相关的 Admin
└── scraper/        # 爬虫相关的 Admin
```

**职责**: 提供 Web 管理界面，按功能模块分组

### services/ - 业务逻辑
```
services/
├── scraper/        # 爬虫相关服务
│   ├── core/           # 核心服务（浏览器、Cookie、安全等）
│   └── scrapers/       # 具体爬虫实现
├── document/       # 文档处理服务
└── ai/             # AI 相关服务
```

**职责**: 核心业务逻辑，独立于框架，可复用

### api/ - API 接口
```
api/
├── main_api.py                 # 主 API
├── document_processor_api.py   # 文档处理 API
└── auto_namer_api.py           # 自动命名 API
```

**职责**: RESTful API，供前端或其他服务调用

### docs/ - 文档
```
docs/
├── INDEX.md                    # 文档索引
├── README.md                   # 完整文档
├── QUICKSTART.md               # 快速开始
├── COURT_DOCUMENT_GUIDE.md     # 使用指南
├── IMPLEMENTATION_SUMMARY.md   # 实现总结
├── REVIEW.md                   # 代码审查
├── STRUCTURE.md                # 目录结构（本文件）
└── CHANGELOG.md                # 变更日志
```

**职责**: 所有文档集中管理，易于查找

### tests/ - 测试
```
tests/
├── README.md                   # 测试说明
├── test_court_document.py      # 功能测试
└── debug_page_structure.py     # 调试工具
```

**职责**: 测试脚本和调试工具

## 🔄 导入路径示例

### Admin 导入 Services
```python
# admin/document/document_processor_admin.py
from ...services.document.document_processing import process_uploaded_document
from ...models import AutomationTool

# admin/scraper/scraper_task_admin.py
from ...models import ScraperTask
```

### Services 内部导入
```python
# services/scraper/scrapers/base.py
from ..core.browser_service import browser_service
from ..core.cookie_service import CookieService

# services/scraper/scrapers/court_document.py
from .base import BaseScraper
```

### Tasks 导入 Services
```python
# tasks.py
from .services.scraper.scrapers import TestScraper, CourtDocumentScraper
from .services.scraper.core.cookie_service import CookieService
```

## 📈 扩展指南

### 添加新的功能模块（例如：邮件服务）

1. **创建目录结构**
```bash
mkdir -p services/email
mkdir -p admin/email
```

2. **创建服务文件**
```python
# services/email/email_service.py
class EmailService:
    def send_email(self, to, subject, body):
        pass
```

3. **创建 Admin**
```python
# admin/email/email_admin.py
@admin.register(EmailTool)
class EmailAdmin(admin.ModelAdmin):
    pass
```

4. **更新 __init__.py**
```python
# admin/__init__.py
from .email import EmailAdmin

# services/email/__init__.py
from .email_service import EmailService
```

### 添加新的爬虫

1. **创建爬虫文件**
```python
# services/scraper/scrapers/new_scraper.py
from .base import BaseScraper

class NewScraper(BaseScraper):
    def _run(self):
        # 实现爬虫逻辑
        pass
```

2. **注册爬虫**
```python
# services/scraper/scrapers/__init__.py
from .new_scraper import NewScraper

__all__ = [..., "NewScraper"]

# tasks.py
SCRAPER_MAP = {
    ScraperTaskType.NEW_TASK: NewScraper,
}
```

## 📝 文件统计

| 目录 | 文件数 | 说明 |
|------|--------|------|
| admin/ | 9 | Admin 配置（按功能分组）|
| api/ | 5 | API 接口 |
| services/scraper/ | 11 | 爬虫服务 |
| services/document/ | 1 | 文档处理 |
| services/ai/ | 3 | AI 服务 |
| docs/ | 8 | 文档 |
| tests/ | 3 | 测试 |
| 根目录 | 8 | 核心文件 |

**总计**: 49 个文件

## ✨ 优化效果

### 优化前
```
services/
├── browser_service.py
├── cookie_service.py
├── anti_detection.py
├── captcha_service.py
├── security_service.py
├── validator_service.py
├── monitor_service.py
├── document_processing.py
├── moonshot_client.py
├── ollama_client.py
├── prompts.py
└── scrapers/
    ├── base.py
    ├── test_scraper.py
    ├── court_document.py
    └── court_filing.py
```
❌ 文件混乱，难以管理

### 优化后
```
services/
├── scraper/
│   ├── core/           # 核心服务
│   └── scrapers/       # 爬虫实现
├── document/           # 文档处理
└── ai/                 # AI 服务
```
✅ 按功能分组，清晰明了

## 🎯 总结

- ✅ **按功能分组** - admin 和 services 都按功能模块组织
- ✅ **层次清晰** - 一级技术层次，二级功能模块，三级具体实现
- ✅ **易于扩展** - 新增功能只需在对应目录添加
- ✅ **导入规范** - 相对导入路径清晰
- ✅ **文档完善** - 每个目录都有说明

---

**最后更新**: 2024-11-27  
**维护者**: Kiro AI
