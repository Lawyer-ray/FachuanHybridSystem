# Token 捕获功能实现文档

## 概述

本文档记录了法院系统 Token 自动捕获和管理功能的实现。

## 需求

1. **URL 重命名**：将 `/admin/automation/testtool/` 改为 `/admin/automation/testcourt/`
2. **Token 捕获**：在登录成功后，拦截并记录 `https://zxfw.court.gov.cn/yzw/yzw-zxfw-yhfw/api/v1/login` 接口的响应中的 token
3. **Token 共享存储**：将 token 保存到公共位置（Redis + 数据库），供其他脚本调用

## 技术方案

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      Django Admin                            │
│  /admin/automation/testcourt/                               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    TestService                               │
│  test_login(credential_id)                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 CourtZxfwService                            │
│  - 设置网络拦截器                                            │
│  - 执行登录流程                                              │
│  - 捕获 Token                                                │
│  - 调用 TokenService 保存                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                   TokenService                               │
│  - save_token()   → Redis + DB                              │
│  - get_token()    → Redis → DB                              │
│  - delete_token() → Redis + DB                              │
└─────────────────────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌──────────────┐          ┌──────────────┐
│    Redis     │          │   Database   │
│  (快速访问)   │          │  (持久化)     │
└──────────────┘          └──────────────┘
```

### 存储策略

采用 **Redis + 数据库双层存储**：

| 存储层 | 作用 | 优点 | 缺点 |
|--------|------|------|------|
| Redis | 快速访问 | 性能高、支持自动过期 | 重启可能丢失 |
| 数据库 | 持久化 | 可靠、可查询历史 | 访问较慢 |

**工作流程**：
1. 保存时：同时写入 Redis 和数据库
2. 获取时：优先从 Redis 读取，Redis 没有则从数据库读取并回填
3. 删除时：同时删除 Redis 和数据库

## 实现细节

### 1. 数据库模型

**文件**: `backend/apps/automation/models.py`

新增两个模型：

#### TestCourt（虚拟模型）
```python
class TestCourt(models.Model):
    """测试法院系统虚拟模型"""
    name = models.CharField(max_length=64, default="Test Court")

    class Meta:
        managed = False
        verbose_name = "⚖️ 测试法院系统"
        verbose_name_plural = "⚖️ 测试法院系统"
```

#### CourtToken（实体模型）
```python
class CourtToken(models.Model):
    """法院系统 Token 存储"""
    site_name = models.CharField(max_length=128)
    account = models.CharField(max_length=128)
    token = models.TextField()
    token_type = models.CharField(max_length=32, default="Bearer")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [["site_name", "account"]]
```

### 2. TokenService

**文件**: `backend/apps/automation/services/scraper/core/token_service.py`

核心服务类，提供 Token 管理功能：

```python
class TokenService:
    def save_token(self, site_name, account, token, expires_in=3600, token_type="Bearer")
    def get_token(self, site_name, account) -> Optional[str]
    def delete_token(self, site_name, account)
    def get_token_info(self, site_name, account) -> Optional[dict]
```

### 3. Token 捕获逻辑

**文件**: `backend/apps/automation/services/scraper/sites/court_zxfw.py`

在 `CourtZxfwService.login()` 方法中添加网络拦截器：

```python
def login(self, account: str, password: str, ...):
    captured_token = {"value": None}
    
    def handle_login_response(route):
        """拦截登录接口响应，提取 token"""
        response = route.fetch()
        
        if "api/v1/login" in route.request.url:
            response_body = response.json()
            
            # 尝试从不同位置提取 token
            if "data" in response_body:
                token = response_body["data"].get("token") or \
                        response_body["data"].get("access_token")
            else:
                token = response_body.get("token") or \
                        response_body.get("access_token")
            
            if token:
                captured_token["value"] = token
        
        route.fulfill(response=response)
    
    # 注册拦截器
    self.page.route("**/api/v1/login", handle_login_response)
    
    # ... 执行登录 ...
    
    # 保存 Token
    if captured_token["value"]:
        self.token_service.save_token(
            site_name=self.site_name,
            account=account,
            token=captured_token["value"]
        )
```

### 4. Admin 配置

**文件**: `backend/apps/automation/admin/test_admin.py`

新增 `TestCourtAdmin`：

```python
@admin.register(TestCourt)
class TestCourtAdmin(admin.ModelAdmin):
    def get_urls(self):
        custom_urls = [
            path(
                'test-login/<int:credential_id>/',
                self.admin_site.admin_view(self.test_credential_login_view),
                name='automation_testcourt_test_login',
            ),
        ]
        return custom_urls + super().get_urls()
```

**URL 变化**：
- 旧: `/admin/automation/testtool/test-login/<id>/`
- 新: `/admin/automation/testcourt/test-login/<id>/`

### 5. 模板文件

新增两个模板：

1. **列表页**: `backend/apps/automation/templates/admin/automation/test_court_list.html`
   - 显示所有账号凭证
   - 提供测试登录入口
   - 显示 Token 使用示例

2. **结果页**: `backend/apps/automation/templates/admin/automation/test_court_result.html`
   - 显示测试结果
   - 显示捕获的 Token
   - 提供 Token 使用代码示例

### 6. 缓存配置

**文件**: `backend/apps/core/cache.py`

新增缓存 key 定义：

```python
class CacheKeys:
    COURT_TOKEN = "court_token:{site_name}:{account}"
    
    @classmethod
    def court_token(cls, site_name: str, account: str) -> str:
        return cls.COURT_TOKEN.format(site_name=site_name, account=account)
```

## 文件清单

### 新增文件

1. `backend/apps/automation/services/scraper/core/token_service.py` - Token 服务
2. `backend/apps/automation/templates/admin/automation/test_court_list.html` - 测试列表页
3. `backend/apps/automation/templates/admin/automation/test_court_result.html` - 测试结果页
4. `backend/apps/automation/docs/TOKEN_SERVICE_GUIDE.md` - 使用指南
5. `backend/apps/automation/docs/TOKEN_CAPTURE_IMPLEMENTATION.md` - 实现文档
6. `backend/apps/automation/tests/test_token_service.py` - 单元测试
7. `backend/apps/automation/migrations/0005_add_court_token_and_testcourt.py` - 数据库迁移

### 修改文件

1. `backend/apps/automation/models.py` - 添加 TestCourt 和 CourtToken 模型
2. `backend/apps/automation/admin/test_admin.py` - 添加 TestCourtAdmin
3. `backend/apps/automation/services/scraper/sites/court_zxfw.py` - 添加 Token 捕获逻辑
4. `backend/apps/core/cache.py` - 添加 COURT_TOKEN 缓存 key

## 使用方法

### 1. 执行数据库迁移

```bash
cd backend
source venv311/bin/activate
python apiSystem/manage.py migrate automation
```

### 2. 访问测试页面

```
http://localhost:8000/admin/automation/testcourt/
```

### 3. 测试登录

1. 选择一个账号凭证
2. 点击"测试登录"
3. 等待浏览器自动执行登录
4. 查看测试结果和捕获的 Token

### 4. 在脚本中使用 Token

```python
from apps.automation.services.scraper.core.token_service import TokenService

# 获取 Token
token_service = TokenService()
token = token_service.get_token("court_zxfw", "your_account")

if token:
    # 使用 Token 调用 API
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get("https://api.example.com/data", headers=headers)
    print(response.json())
```

## 测试

### 运行单元测试

```bash
cd backend
source venv311/bin/activate
pytest apps/automation/tests/test_token_service.py -v
```

### 测试覆盖

- ✅ Token 保存和获取
- ✅ Token 删除
- ✅ Token 详细信息获取
- ✅ 过期 Token 处理
- ✅ Token 更新
- ✅ 多账号支持
- ✅ 多网站支持
- ✅ 缓存 key 格式

## 注意事项

1. **Token 格式**：目前支持从 `data.token`、`data.access_token`、`token`、`access_token` 字段提取
2. **过期时间**：默认 1 小时，可根据实际情况调整
3. **Redis 配置**：确保 Redis 服务正常运行
4. **网络拦截**：依赖 Playwright 的 `page.route()` 功能
5. **并发安全**：TokenService 是线程安全的

## 故障排查

### 问题 1: 未捕获到 Token

**检查项**：
1. 登录接口是否返回 Token
2. Token 字段名是否匹配
3. 网络拦截器是否正确触发

**解决方法**：
- 查看日志确认拦截器是否触发
- 检查登录接口响应格式
- 必要时修改 Token 提取逻辑

### 问题 2: Token 获取失败

**检查项**：
1. Redis 服务是否正常
2. 数据库连接是否正常
3. Token 是否已过期

**解决方法**：
- 检查 Redis 连接配置
- 确认数据库迁移已执行
- 查看日志获取详细错误

## 性能优化

1. **Redis 优先**：优先从 Redis 读取，减少数据库查询
2. **自动过期**：利用 Redis 的 TTL 功能自动清理过期 Token
3. **批量操作**：如需批量获取 Token，可以扩展 TokenService 添加批量接口
4. **连接池**：Redis 和数据库都使用连接池，提高并发性能

## 扩展建议

1. **Token 刷新**：添加自动刷新机制，在 Token 即将过期时自动刷新
2. **Token 加密**：对敏感 Token 进行加密存储
3. **审计日志**：记录 Token 的创建、使用、删除等操作
4. **监控告警**：监控 Token 使用情况，异常时告警
5. **多 Token 支持**：支持一个账号同时保存多个 Token（不同用途）

## 相关文档

- [Token 服务使用指南](./TOKEN_SERVICE_GUIDE.md)
- [CourtZxfwService 使用指南](./COURT_ZXFW_SERVICE.md)
- [Admin 测试指南](./ADMIN_TEST_GUIDE.md)

## 更新日志

### v1.0.0 (2024-01-XX)
- ✅ 实现 Token 自动捕获
- ✅ 实现 Redis + 数据库双层存储
- ✅ 添加 TestCourtAdmin
- ✅ 创建 TokenService
- ✅ 添加单元测试
- ✅ 编写使用文档
