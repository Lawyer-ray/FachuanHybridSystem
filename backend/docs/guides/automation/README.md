# 🤖 自动化工具模块

> 提供文档处理、网络爬虫等自动化功能

## 🚀 快速导航

| 我想... | 查看文档 |
|---------|---------|
| 📖 了解整体架构 | [STRUCTURE.md](STRUCTURE.md) - 目录结构 |
| 🚀 快速开始测试 | [docs/QUICKSTART.md](docs/QUICKSTART.md) - 5分钟上手 |
| 📄 使用文书下载 | [docs/COURT_DOCUMENT_GUIDE.md](docs/COURT_DOCUMENT_GUIDE.md) - 详细指南 |
| 🧪 运行测试 | [tests/README.md](tests/README.md) - 测试说明 |
| 📚 查看所有文档 | [docs/INDEX.md](docs/INDEX.md) - 文档索引 |
| 🔍 代码审查报告 | [docs/REVIEW.md](docs/REVIEW.md) - 质量评估 |

---

## 📁 目录结构

```
automation/
├── admin/                      # Django Admin 配置
│   ├── auto_namer_admin.py         # 自动命名工具
│   ├── document_processor_admin.py # 文档处理
│   ├── quick_download_admin.py     # 快速下载文书
│   ├── scraper_admin_site.py       # 爬虫二级菜单
│   ├── scraper_cookie_admin.py     # Cookie 管理
│   ├── scraper_task_admin.py       # 任务管理
│   └── scraper_test_admin.py       # 功能测试
│
├── api/                        # API 接口
│   ├── auto_namer_api.py
│   ├── document_processor_api.py
│   └── main_api.py
│
├── services/                   # 业务逻辑层
│   ├── scrapers/                   # 爬虫模块
│   │   ├── base.py                     # 爬虫基类
│   │   ├── test_scraper.py             # 测试爬虫
│   │   ├── court_document.py           # 法院文书下载 ⭐
│   │   └── court_filing.py             # 法院自动立案
│   │
│   ├── anti_detection.py           # 反检测对抗
│   ├── browser_service.py          # 浏览器管理
│   ├── captcha_service.py          # 验证码识别
│   ├── cookie_service.py           # Cookie 管理
│   ├── document_processing.py      # 文档处理
│   ├── monitor_service.py          # 任务监控
│   ├── security_service.py         # 安全加密
│   └── validator_service.py        # 数据校验
│
├── docs/                       # 📚 文档
│   ├── README.md                   # 模块概述
│   ├── REVIEW.md                   # 代码审查报告
│   ├── COURT_DOCUMENT_GUIDE.md     # 文书下载使用指南
│   ├── IMPLEMENTATION_SUMMARY.md   # 实现总结
│   └── QUICKSTART.md               # 快速启动指南
│
├── tests/                      # 🧪 测试
│   ├── test_court_document.py      # 文书下载测试
│   └── debug_page_structure.py     # 页面结构调试工具
│
├── migrations/                 # 数据库迁移
├── models.py                   # 数据模型
├── tasks.py                    # Django-Q 后台任务
├── schemas.py                  # Pydantic 模式
├── checks.py                   # 系统检查
└── apps.py                     # 应用配置
```

## 🚀 快速开始

### 1. 查看文档

- **新手入门**: [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **完整文档**: [docs/README.md](docs/README.md)
- **文书下载**: [docs/COURT_DOCUMENT_GUIDE.md](docs/COURT_DOCUMENT_GUIDE.md)

### 2. 运行测试

```bash
# 测试文书下载
cd backend
python apps/automation/tests/test_court_document.py

# 调试页面结构
python apps/automation/tests/debug_page_structure.py "你的链接"
```

### 3. 使用 Admin 界面

访问 Django Admin:
- **🕷️ 爬虫工具** -> **⚡ 快速下载文书**
- **🕷️ 爬虫工具** -> **任务管理**
- **🕷️ 爬虫工具** -> **🧪 功能测试**

## 📦 功能模块

### 1. 文档处理
- PDF 文档解析
- 文件自动命名
- 文档内容提取

### 2. 爬虫工具 ⭐
- **法院文书下载** (最新)
  - 支持 zxfw.court.gov.cn
  - 支持 sd.gdems.com
  - 自动识别链接类型
  - 智能下载和解压
  
- **任务管理**
  - 优先级队列
  - 自动重试
  - 状态监控
  
- **Cookie 管理**
  - 自动保存和加载
  - 过期检测
  - 定期清理

## 🔧 核心服务

| 服务 | 功能 | 文件 |
|------|------|------|
| BrowserService | 浏览器管理（单例） | `services/browser_service.py` |
| CookieService | Cookie 管理 | `services/cookie_service.py` |
| CaptchaService | 验证码识别 | `services/captcha_service.py` |
| AntiDetection | 反检测对抗 | `services/anti_detection.py` |
| SecurityService | 敏感信息加密 | `services/security_service.py` |
| ValidatorService | 数据校验清洗 | `services/validator_service.py` |
| MonitorService | 任务监控告警 | `services/monitor_service.py` |

## 📊 数据模型

### ScraperTask (爬虫任务)
- 任务类型、状态、优先级
- URL、配置、结果
- 重试机制、定时执行

### ScraperCookie (Cookie 存储)
- 网站名称、账号
- Cookie 数据
- 过期时间

## 🎯 开发指南

### 添加新爬虫

1. 在 `services/scrapers/` 创建新文件
2. 继承 `BaseScraper` 类
3. 实现 `_run()` 方法
4. 在 `tasks.py` 注册爬虫
5. 在 `models.py` 添加任务类型

详见: [docs/README.md#开发新爬虫](docs/README.md)

## 📝 最近更新

### 2024-11-27
- ✅ 完成法院文书下载爬虫
- ✅ 支持两种链接格式
- ✅ 添加快速下载界面
- ✅ 优化选择器策略
- ✅ 添加调试工具

## 🐛 问题排查

### 常见问题

1. **浏览器启动失败**
   ```bash
   playwright install chromium
   ```

2. **任务一直等待**
   - 检查 Django-Q 是否运行
   - 查看日志: `backend/logs/api.log`

3. **下载超时**
   - 使用调试工具查看页面结构
   - 检查网络连接
   - 查看截图和 HTML 文件

详见: [docs/COURT_DOCUMENT_GUIDE.md#错误处理](docs/COURT_DOCUMENT_GUIDE.md)

## 📞 获取帮助

- 查看文档: `docs/` 目录
- 运行测试: `tests/` 目录
- 查看日志: `backend/logs/api.log`
- 查看截图: `media/automation/screenshots/`

## 🔗 相关链接

- [Django Admin](http://localhost:8000/admin/)
- [API 文档](http://localhost:8000/api/docs)
- [Django-Q 监控](http://localhost:8000/admin/django_q/)
