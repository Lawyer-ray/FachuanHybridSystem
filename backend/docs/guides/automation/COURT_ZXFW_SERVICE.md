# 全国法院"一张网"服务使用指南

## 概述

`CourtZxfwService` 是一个解耦的、模块化的服务类，用于操作全国法院"一张网"系统 (https://zxfw.court.gov.cn)。

## 架构设计

### 解耦设计原则

```
┌─────────────────────────────────────────┐
│  CourtZxfwService (网站服务层)           │
│  - login()          登录                 │
│  - file_case()      立案                 │
│  - query_case()     查询案件             │
│  - download_document() 下载文书          │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  具体的爬虫任务 (Scraper)                │
│  - CourtFilingScraper    立案爬虫        │
│  - CourtQueryScraper     查询爬虫        │
│  - CourtDocumentScraper  文书下载爬虫    │
└─────────────────────────────────────────┘
```

**优势：**
1. **复用登录逻辑**：所有爬虫共享同一个登录实现
2. **独立测试**：可以单独测试登录功能
3. **易于维护**：网站变化时只需修改一处
4. **功能扩展**：新增功能只需添加方法

## 功能模块

### 1. 登录功能 ✅

#### 使用方法

```python
from playwright.sync_api import sync_playwright
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    
    # 创建服务实例
    service = CourtZxfwService(page, context)
    
    # 登录
    result = service.login(
        account="your_account",
        password="your_password",
        max_captcha_retries=3,  # 验证码最大重试次数
        save_debug=True  # 保存调试信息
    )
    
    print(f"登录成功: {result['success']}")
    print(f"Cookie 数量: {len(result['cookies'])}")
```

#### 登录流程

1. 导航到登录页
2. 点击"密码登录"
3. 输入账号
4. 输入密码
5. 识别验证码（使用 ddddocr）
6. 输入验证码
7. 点击登录按钮
8. 检查登录结果
9. 保存 Cookie

#### 验证码识别

使用 `ddddocr` 库自动识别验证码：

```python
# 自动安装
pip install ddddocr

# 识别流程
1. 截取验证码图片
2. 使用 ddddocr 识别
3. 清理识别结果（去除空格）
4. 输入验证码
5. 如果失败，刷新验证码重试
```

#### 登录成功判断

多种方式判断登录是否成功：

1. **URL 检查**：登录后 URL 不再包含 "login"
2. **错误提示检查**：查找"验证码错误"、"账号或密码错误"等提示
3. **用户信息检查**：查找"退出登录"、"个人中心"等元素

#### 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `account` | str | 是 | - | 登录账号 |
| `password` | str | 是 | - | 登录密码 |
| `max_captcha_retries` | int | 否 | 3 | 验证码识别最大重试次数 |
| `save_debug` | bool | 否 | False | 是否保存调试信息（截图、验证码图片） |

#### 返回值

```python
{
    "success": True,
    "message": "登录成功",
    "cookies": [...],  # Cookie 列表
    "url": "https://..."  # 登录后的 URL
}
```

---

### 2. 立案功能 🚧（待实现）

```python
# 登录后调用
result = service.file_case({
    "case_name": "张三诉李四合同纠纷",
    "case_type": "民事",
    "plaintiff": "张三",
    "defendant": "李四",
    # ... 其他案件信息
})
```

---

### 3. 查询功能 🚧（待实现）

```python
# 登录后调用
result = service.query_case("(2024)粤01民初1234号")
```

---

### 4. 下载文书功能 🚧（待实现）

```python
# 登录后调用
result = service.download_document("https://...")
```

---

## 测试

### 快速测试

```bash
cd backend
python apps/automation/tests/test_court_zxfw_login.py
```

**前提条件：**
1. 后端服务已启动：`python manage.py runserver 0.0.0.0:8002`
2. 数据库中存在 ID=1 的凭证记录
3. 已安装 ddddocr：`pip install ddddocr`

### 测试流程

1. 从 API 获取账号密码
2. 启动浏览器（有头模式，方便观察）
3. 创建服务实例
4. 执行登录
5. 显示结果
6. 保存调试信息到 `media/automation/screenshots/` 和 `media/automation/debug/`

---

## 调试

### 启用调试模式

```python
result = service.login(
    account=account,
    password=password,
    save_debug=True  # 启用调试
)
```

### 调试文件位置

```
media/automation/
├── screenshots/          # 截图
│   ├── 01_login_page_*.png
│   ├── 02_password_tab_clicked_*.png
│   ├── 03_credentials_filled_*.png
│   ├── 04_captcha_filled_attempt_1_*.png
│   └── 05_after_login_attempt_1_*.png
└── debug/               # 验证码图片
    └── captcha_*.png
```

### 常见问题

#### 1. 验证码识别失败

**原因：**
- 验证码图片质量差
- ddddocr 识别率不是 100%

**解决：**
- 增加重试次数：`max_captcha_retries=5`
- 检查验证码图片：`media/automation/debug/captcha_*.png`
- 考虑使用付费 OCR 服务

#### 2. 登录超时

**原因：**
- 网络慢
- 页面加载慢

**解决：**
- 增加超时时间（修改代码中的 `timeout` 参数）
- 检查网络连接

#### 3. 元素定位失败

**原因：**
- 网站页面结构变化
- XPath 失效

**解决：**
- 查看截图，确认页面结构
- 使用浏览器开发者工具重新获取 XPath
- 更新代码中的 XPath

---

## 在爬虫中使用

### 示例：立案爬虫

```python
from apps.automation.services.scraper.scrapers.base import BaseScraper
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

class CourtFilingScraper(BaseScraper):
    """立案爬虫"""
    
    def _run(self):
        # 1. 创建"一张网"服务
        service = CourtZxfwService(self.page, self.context)
        
        # 2. 登录
        account = self.task.config.get("account")
        password = self.task.config.get("password")
        
        service.login(account, password)
        
        # 3. 执行立案
        case_data = self.task.config.get("case_data")
        result = service.file_case(case_data)
        
        return result
```

### 示例：查询爬虫

```python
class CourtQueryScraper(BaseScraper):
    """查询爬虫"""
    
    def _run(self):
        # 1. 创建服务
        service = CourtZxfwService(self.page, self.context)
        
        # 2. 登录
        service.login(
            self.task.config["account"],
            self.task.config["password"]
        )
        
        # 3. 查询案件
        case_number = self.task.config["case_number"]
        result = service.query_case(case_number)
        
        return result
```

---

## 依赖

```txt
# requirements.txt
playwright>=1.40.0
ddddocr>=1.4.0
```

安装：

```bash
pip install playwright ddddocr
playwright install chromium
```

---

## 路线图

- [x] 登录功能
- [ ] 立案功能
- [ ] 查询案件功能
- [ ] 下载文书功能
- [ ] Cookie 复用（避免重复登录）
- [ ] 验证码识别优化（使用付费服务）
- [ ] 错误重试机制
- [ ] 并发控制

---

## 贡献

如果网站页面结构变化，请更新以下内容：

1. XPath 路径
2. 登录成功判断逻辑
3. 测试用例
4. 文档

---

## 许可

内部使用
