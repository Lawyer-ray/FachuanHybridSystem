# Token 服务使用指南

## 概述

`TokenService` 提供了法院系统 Token 的统一管理功能，支持 Token 的保存、获取、删除等操作。

Token 采用 **Redis + 数据库双层存储**：
- **Redis**: 快速访问，支持自动过期
- **数据库**: 持久化存储，防止 Redis 重启丢失

## 功能特性

- ✅ 自动捕获登录接口的 Token
- ✅ Redis + 数据库双层存储
- ✅ 自动过期管理
- ✅ 支持多账号、多网站
- ✅ 线程安全

## 快速开始

### 1. 测试登录并捕获 Token

访问 Django Admin 后台：

```
http://localhost:8000/admin/automation/testcourt/
```

选择一个账号凭证，点击"测试登录"，系统会：
1. 自动打开浏览器
2. 执行登录操作
3. 拦截登录接口响应
4. 提取并保存 Token
5. 显示测试结果（包含捕获的 Token）

### 2. 在脚本中使用 Token

```python
from apps.automation.services.scraper.core.token_service import TokenService

# 创建服务实例
token_service = TokenService()

# 获取 Token
token = token_service.get_token("court_zxfw", "your_account")

if token:
    print(f"Token: {token}")
    
    # 使用 Token 调用 API
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get("https://api.example.com/data", headers=headers)
    print(response.json())
else:
    print("Token 不存在或已过期，请重新登录")
```

## API 文档

### TokenService

#### `save_token(site_name, account, token, expires_in=3600, token_type="Bearer")`

保存 Token 到 Redis 和数据库。

**参数**：
- `site_name` (str): 网站名称，如 "court_zxfw"
- `account` (str): 账号
- `token` (str): Token 字符串
- `expires_in` (int, 可选): 过期时间（秒），默认 3600（1小时）
- `token_type` (str, 可选): Token 类型，默认 "Bearer"

**示例**：
```python
token_service.save_token(
    site_name="court_zxfw",
    account="13800138000",
    token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    expires_in=7200  # 2 小时
)
```

#### `get_token(site_name, account)`

获取 Token（优先从 Redis，Redis 没有则从数据库）。

**参数**：
- `site_name` (str): 网站名称
- `account` (str): 账号

**返回**：
- `str | None`: Token 字符串，不存在或已过期返回 None

**示例**：
```python
token = token_service.get_token("court_zxfw", "13800138000")
if token:
    print(f"Token: {token}")
else:
    print("Token 不存在或已过期")
```

#### `delete_token(site_name, account)`

删除 Token（同时删除 Redis 和数据库）。

**参数**：
- `site_name` (str): 网站名称
- `account` (str): 账号

**示例**：
```python
token_service.delete_token("court_zxfw", "13800138000")
```

#### `get_token_info(site_name, account)`

获取 Token 详细信息。

**参数**：
- `site_name` (str): 网站名称
- `account` (str): 账号

**返回**：
- `dict | None`: Token 信息字典，包含 token, token_type, expires_at 等

**示例**：
```python
info = token_service.get_token_info("court_zxfw", "13800138000")
if info:
    print(f"Token: {info['token']}")
    print(f"类型: {info['token_type']}")
    print(f"过期时间: {info['expires_at']}")
    print(f"创建时间: {info['created_at']}")
    print(f"更新时间: {info['updated_at']}")
```

## 使用场景

### 场景 1: 自动化脚本调用法院 API

```python
from apps.automation.services.scraper.core.token_service import TokenService
import requests

def call_court_api(account: str, api_url: str):
    """调用法院 API"""
    # 获取 Token
    token_service = TokenService()
    token = token_service.get_token("court_zxfw", account)
    
    if not token:
        raise ValueError("Token 不存在或已过期，请先登录")
    
    # 调用 API
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    
    return response.json()

# 使用
try:
    data = call_court_api("13800138000", "https://zxfw.court.gov.cn/api/v1/cases")
    print(data)
except Exception as e:
    print(f"调用失败: {e}")
```

### 场景 2: 定时任务自动刷新 Token

```python
from apps.automation.services.scraper.core.token_service import TokenService
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
from apps.automation.services.scraper.core.browser_manager import BrowserManager
from apps.automation.services.scraper.config.browser_config import BrowserConfig

def refresh_token(account: str, password: str):
    """刷新 Token"""
    config = BrowserConfig.from_env()
    
    with BrowserManager.create_browser(config) as (page, context):
        service = CourtZxfwService(page, context)
        
        # 登录（会自动捕获并保存 Token）
        result = service.login(account, password)
        
        if result["success"]:
            print(f"✅ Token 刷新成功: {result.get('token', 'N/A')[:20]}...")
        else:
            print(f"❌ Token 刷新失败: {result['message']}")

# 在定时任务中调用
refresh_token("13800138000", "your_password")
```

### 场景 3: 检查 Token 是否有效

```python
from apps.automation.services.scraper.core.token_service import TokenService
from datetime import datetime

def check_token_validity(site_name: str, account: str):
    """检查 Token 是否有效"""
    token_service = TokenService()
    info = token_service.get_token_info(site_name, account)
    
    if not info:
        print("❌ Token 不存在")
        return False
    
    expires_at = info['expires_at']
    now = datetime.now(expires_at.tzinfo)
    
    if expires_at <= now:
        print("❌ Token 已过期")
        return False
    
    remaining = (expires_at - now).total_seconds()
    print(f"✅ Token 有效，剩余 {remaining:.0f} 秒")
    return True

# 使用
check_token_validity("court_zxfw", "13800138000")
```

## 数据库模型

### CourtToken

```python
class CourtToken(models.Model):
    """法院系统 Token 存储"""
    site_name = models.CharField(max_length=128)  # 网站名称
    account = models.CharField(max_length=128)    # 账号
    token = models.TextField()                    # Token
    token_type = models.CharField(max_length=32, default="Bearer")  # Token 类型
    expires_at = models.DateTimeField()           # 过期时间
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [["site_name", "account"]]
```

## Redis 缓存 Key 格式

```
court_token:{site_name}:{account}
```

示例：
```
court_token:court_zxfw:13800138000
```

## 注意事项

1. **Token 过期时间**：默认 1 小时，可以根据实际情况调整
2. **Redis 持久化**：建议配置 Redis 持久化（RDB 或 AOF），防止重启丢失
3. **并发安全**：TokenService 是线程安全的，可以在多线程环境中使用
4. **Token 格式**：目前支持 JWT 和 Bearer Token，其他格式需要调整代码
5. **网络拦截**：Token 捕获依赖 Playwright 的网络拦截功能，确保登录接口返回 Token

## 故障排查

### 问题 1: 未捕获到 Token

**可能原因**：
- 登录接口未返回 Token
- Token 字段名不匹配（不是 `token` 或 `access_token`）
- 网络拦截器未正确设置

**解决方法**：
1. 检查登录接口响应格式
2. 修改 `CourtZxfwService.login()` 中的 Token 提取逻辑
3. 查看日志确认拦截器是否触发

### 问题 2: Token 获取失败

**可能原因**：
- Token 已过期
- Redis 连接失败
- 数据库查询失败

**解决方法**：
1. 检查 Token 过期时间
2. 确认 Redis 服务正常运行
3. 查看日志获取详细错误信息

### 问题 3: Token 保存失败

**可能原因**：
- Redis 连接失败
- 数据库写入失败
- 权限不足

**解决方法**：
1. 检查 Redis 配置和连接
2. 确认数据库迁移已执行
3. 查看日志获取详细错误信息

## 相关文档

- [CourtZxfwService 使用指南](./COURT_ZXFW_SERVICE.md)
- [BrowserManager 使用指南](./BROWSER_MANAGER_GUIDE.md)
- [Admin 测试指南](./ADMIN_TEST_GUIDE.md)

## 更新日志

### v1.0.0 (2024-01-XX)
- ✅ 初始版本
- ✅ 支持 Token 保存、获取、删除
- ✅ Redis + 数据库双层存储
- ✅ 自动捕获登录接口 Token
- ✅ 支持多账号、多网站
