# 爬虫架构设计

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Django API Layer                         │
│  - 创建爬虫任务                                               │
│  - 查询任务状态                                               │
│  - 获取任务结果                                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Django-Q Task Queue                        │
│  - 任务调度                                                   │
│  - 重试机制                                                   │
│  - 优先级管理                                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Scraper Layer (任务层)                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  BaseScraper (基类)                                  │    │
│  │  - execute()      执行任务                           │    │
│  │  - _run()         具体逻辑（子类实现）                │    │
│  │  - _cleanup()     清理资源                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                     │
│         ┌───────────────┼───────────────┐                    │
│         ▼               ▼               ▼                    │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                │
│  │  立案爬虫 │   │  查询爬虫 │   │  下载爬虫 │                │
│  │ Filing   │   │  Query   │   │ Document │                │
│  └──────────┘   └──────────┘   └──────────┘                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Site Service Layer (网站服务层)              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  CourtZxfwService (全国法院"一张网")                  │    │
│  │  - login()              登录                         │    │
│  │  - file_case()          立案                         │    │
│  │  - query_case()         查询案件                     │    │
│  │  - download_document()  下载文书                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  其他网站服务 (未来扩展)                              │    │
│  │  - JusticeBureauService  司法局                      │    │
│  │  - PoliceService         公安局                      │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Services (核心服务)                   │
│  - BrowserService      浏览器管理                            │
│  - CaptchaService      验证码识别                            │
│  - CookieService       Cookie 管理                           │
│  - AntiDetection       反检测                                │
│  - SecurityService     加密解密                              │
│  - MonitorService      监控告警                              │
└─────────────────────────────────────────────────────────────┘
```

## 分层说明

### 1. API Layer (API 层)
**职责：** 接收用户请求，创建爬虫任务

**示例：**
```python
# 创建立案任务
POST /api/v1/automation/scraper/tasks
{
    "task_type": "court_filing",
    "url": "https://zxfw.court.gov.cn",
    "config": {
        "credential_id": 1,
        "case_data": {...}
    }
}
```

---

### 2. Task Queue Layer (任务队列层)
**职责：** 调度任务执行，管理重试

**特点：**
- 异步执行，不阻塞 API
- 支持优先级
- 自动重试失败任务

---

### 3. Scraper Layer (任务层)
**职责：** 定义具体的爬虫任务

**设计原则：**
- 每个任务一个 Scraper 类
- 继承 `BaseScraper`
- 实现 `_run()` 方法

**示例：**
```python
class CourtFilingScraper(BaseScraper):
    """立案爬虫"""
    
    def _run(self):
        # 1. 获取凭证
        credential = self._get_credential()
        
        # 2. 创建网站服务
        service = CourtZxfwService(self.page, self.context)
        
        # 3. 登录
        service.login(credential.account, credential.password)
        
        # 4. 执行立案
        result = service.file_case(self.task.config["case_data"])
        
        return result
```

---

### 4. Site Service Layer (网站服务层) ⭐ 核心创新
**职责：** 封装网站特定的操作逻辑

**设计原则：**
- 一个网站一个 Service 类
- 提供高层次的业务方法（login, file_case, query_case 等）
- 隐藏底层的页面操作细节
- 可被多个 Scraper 复用

**优势：**
1. **复用性**：登录逻辑只写一次，所有爬虫共享
2. **可测试性**：可以单独测试登录功能
3. **可维护性**：网站变化时只需修改一处
4. **扩展性**：新增功能只需添加方法

**示例：**
```python
class CourtZxfwService:
    """全国法院"一张网"服务"""
    
    def login(self, account, password):
        """登录（所有爬虫共享）"""
        # 登录逻辑
        pass
    
    def file_case(self, case_data):
        """立案（立案爬虫使用）"""
        # 立案逻辑
        pass
    
    def query_case(self, case_number):
        """查询案件（查询爬虫使用）"""
        # 查询逻辑
        pass
    
    def download_document(self, document_url):
        """下载文书（下载爬虫使用）"""
        # 下载逻辑
        pass
```

---

### 5. Core Services Layer (核心服务层)
**职责：** 提供通用的底层服务

**服务列表：**
- `BrowserService`: 浏览器管理（启动、关闭、反检测）
- `CaptchaService`: 验证码识别（ddddocr、付费服务）
- `CookieService`: Cookie 管理（保存、加载、过期检查）
- `AntiDetection`: 反检测（注入脚本、模拟人类行为）
- `SecurityService`: 加密解密（敏感信息保护）
- `MonitorService`: 监控告警（任务超时、失败告警）

---

## 目录结构

```
apps/automation/
├── services/
│   └── scraper/
│       ├── core/                    # 核心服务
│       │   ├── browser_service.py
│       │   ├── captcha_service.py
│       │   ├── cookie_service.py
│       │   ├── anti_detection.py
│       │   ├── security_service.py
│       │   └── monitor_service.py
│       │
│       ├── sites/                   # 网站服务 ⭐ 新增
│       │   ├── court_zxfw.py       # 全国法院"一张网"
│       │   ├── justice_bureau.py   # 司法局（未来）
│       │   └── police.py           # 公安局（未来）
│       │
│       └── scrapers/                # 具体爬虫
│           ├── base.py             # 基类
│           ├── court_filing.py     # 立案爬虫
│           ├── court_query.py      # 查询爬虫
│           └── court_document.py   # 文书下载爬虫
│
├── models.py                        # 数据模型
├── tasks.py                         # Django-Q 任务
└── tests/                           # 测试
    ├── test_court_zxfw_login.py    # 登录测试
    └── test_court_filing.py        # 立案测试
```

---

## 使用流程

### 场景 1：立案

```python
# 1. 用户通过 API 创建任务
POST /api/v1/automation/scraper/tasks
{
    "task_type": "court_filing",
    "config": {
        "credential_id": 1,
        "case_data": {...}
    }
}

# 2. Django-Q 调度任务
execute_scraper_task(task_id=123)

# 3. CourtFilingScraper 执行
scraper = CourtFilingScraper(task)
scraper.execute()

# 4. 调用 CourtZxfwService
service = CourtZxfwService(page, context)
service.login(account, password)      # 登录
service.file_case(case_data)          # 立案

# 5. 返回结果
{
    "success": True,
    "case_number": "(2024)粤01民初1234号",
    "message": "立案成功"
}
```

### 场景 2：查询案件

```python
# 1. 创建查询任务
POST /api/v1/automation/scraper/tasks
{
    "task_type": "court_query",
    "config": {
        "credential_id": 1,
        "case_number": "(2024)粤01民初1234号"
    }
}

# 2. CourtQueryScraper 执行
service = CourtZxfwService(page, context)
service.login(account, password)      # 复用登录逻辑
service.query_case(case_number)       # 查询

# 3. 返回案件信息
{
    "case_number": "(2024)粤01民初1234号",
    "status": "审理中",
    "court": "广州市中级人民法院",
    ...
}
```

---

## 设计优势

### 1. 解耦
- 登录逻辑独立于具体任务
- 网站服务独立于爬虫任务
- 核心服务独立于业务逻辑

### 2. 复用
- 所有爬虫共享登录逻辑
- 所有爬虫共享核心服务
- Cookie 可以跨任务复用

### 3. 可测试
- 可以单独测试登录功能
- 可以单独测试立案功能
- 可以单独测试查询功能

### 4. 可维护
- 网站变化时只需修改 Service
- 不影响其他爬虫
- 代码清晰，易于理解

### 5. 可扩展
- 新增网站：添加新的 Service
- 新增功能：在 Service 中添加方法
- 新增爬虫：继承 BaseScraper

---

## 对比：传统架构 vs 新架构

### 传统架构（耦合）

```python
class CourtFilingScraper(BaseScraper):
    def _run(self):
        # 登录逻辑（重复代码）
        self.page.goto("https://...")
        self.page.fill("#username", account)
        self.page.fill("#password", password)
        # ... 100 行登录代码
        
        # 立案逻辑
        # ... 立案代码

class CourtQueryScraper(BaseScraper):
    def _run(self):
        # 登录逻辑（重复代码）
        self.page.goto("https://...")
        self.page.fill("#username", account)
        self.page.fill("#password", password)
        # ... 100 行登录代码（重复！）
        
        # 查询逻辑
        # ... 查询代码
```

**问题：**
- ❌ 登录逻辑重复
- ❌ 难以测试
- ❌ 难以维护
- ❌ 网站变化需要修改多处

### 新架构（解耦）

```python
# 网站服务（登录逻辑只写一次）
class CourtZxfwService:
    def login(self, account, password):
        # 登录逻辑（只写一次）
        pass

# 立案爬虫（复用登录）
class CourtFilingScraper(BaseScraper):
    def _run(self):
        service = CourtZxfwService(self.page, self.context)
        service.login(account, password)  # 复用
        service.file_case(case_data)

# 查询爬虫（复用登录）
class CourtQueryScraper(BaseScraper):
    def _run(self):
        service = CourtZxfwService(self.page, self.context)
        service.login(account, password)  # 复用
        service.query_case(case_number)
```

**优势：**
- ✅ 登录逻辑只写一次
- ✅ 易于测试
- ✅ 易于维护
- ✅ 网站变化只需修改一处

---

## 总结

新架构通过引入 **Site Service Layer**，实现了：

1. **登录逻辑复用**：所有爬虫共享同一个登录实现
2. **功能模块化**：login、file_case、query_case 等功能独立
3. **易于测试**：可以单独测试每个功能
4. **易于维护**：网站变化时只需修改 Service
5. **易于扩展**：新增功能只需添加方法

这是一个**生产级别的架构设计**，适合长期维护和扩展。
