# BrowserManager 使用指南

## 概述

BrowserManager 提供统一的浏览器生命周期管理，通过上下文管理器接口确保资源正确清理。

## 快速开始

### 基本使用

```python
from apps.automation.services.scraper.core.browser_manager import BrowserManager

# 使用默认配置
with BrowserManager.create_browser() as (page, context):
    page.goto("https://example.com")
    # 浏览器会自动清理
```

### 使用自定义配置

```python
from apps.automation.services.scraper.config.browser_config import BrowserConfig
from apps.automation.services.scraper.core.browser_manager import BrowserManager

# 创建自定义配置
config = BrowserConfig(
    headless=True,
    slow_mo=0,
    viewport_width=1920,
    viewport_height=1080
)

# 使用自定义配置
with BrowserManager.create_browser(config) as (page, context):
    page.goto("https://example.com")
```

### 从环境变量加载配置

```python
from apps.automation.services.scraper.config.browser_config import BrowserConfig
from apps.automation.services.scraper.core.browser_manager import BrowserManager

# 从环境变量加载
config = BrowserConfig.from_env()

with BrowserManager.create_browser(config) as (page, context):
    page.goto("https://example.com")
```

## 配置选项

### 环境变量

```bash
# 基础配置
BROWSER_HEADLESS=false
BROWSER_SLOW_MO=500

# 视口配置
BROWSER_VIEWPORT_WIDTH=1280
BROWSER_VIEWPORT_HEIGHT=800

# 超时配置
BROWSER_TIMEOUT=30000
BROWSER_NAVIGATION_TIMEOUT=30000

# 调试配置
BROWSER_SAVE_SCREENSHOTS=true
BROWSER_SCREENSHOT_DIR=/path/to/screenshots
```

## 错误处理

```python
from apps.automation.services.scraper.core.browser_manager import BrowserManager
from apps.automation.services.scraper.core.exceptions import BrowserCreationError

try:
    with BrowserManager.create_browser() as (page, context):
        page.goto("https://example.com")
except BrowserCreationError as e:
    print(f"浏览器创建失败: {e}")
    print(f"配置: {e.config}")
    print(f"原始错误: {e.original_error}")
```

## 特性

### 自动资源清理

BrowserManager 确保即使发生错误，浏览器资源也会被正确清理：

```python
with BrowserManager.create_browser() as (page, context):
    page.goto("https://example.com")
    raise Exception("发生错误")
    # 浏览器仍然会被正确关闭
```

### 反检测支持

默认启用反检测功能：

```python
# 启用反检测（默认）
with BrowserManager.create_browser(use_anti_detection=True) as (page, context):
    page.goto("https://example.com")

# 禁用反检测
with BrowserManager.create_browser(use_anti_detection=False) as (page, context):
    page.goto("https://example.com")
```

## 最佳实践

1. **始终使用上下文管理器**：确保资源正确清理
2. **使用环境变量配置**：便于不同环境的配置管理
3. **捕获 BrowserCreationError**：提供更好的错误处理
4. **验证配置**：在创建浏览器前验证配置有效性

## 迁移指南

### 从手动管理迁移

**之前：**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=500)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    
    page.goto("https://example.com")
    
    browser.close()
```

**之后：**
```python
from apps.automation.services.scraper.core.browser_manager import BrowserManager
from apps.automation.services.scraper.config.browser_config import BrowserConfig

config = BrowserConfig.from_env()

with BrowserManager.create_browser(config) as (page, context):
    page.goto("https://example.com")
    # 自动清理
```

## 参考

- [BrowserConfig 文档](../services/scraper/config/browser_config.py)
- [异常处理文档](../services/scraper/core/exceptions.py)
