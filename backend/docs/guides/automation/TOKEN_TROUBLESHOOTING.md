# Token 捕获问题排查指南

## 问题：登录成功后没有将 Token 记录在 Django 后台

### 快速诊断

运行调试脚本：

```bash
cd backend
make debug-token
```

或者：

```bash
cd backend
source venv311/bin/activate
python scripts/debug_token_capture.py
```

这个脚本会自动检查：
- ✅ Redis 连接
- ✅ 数据库连接
- ✅ 现有 Token 列表
- ✅ TokenService 功能
- ✅ 最近的日志

### 常见原因和解决方法

#### 1. 数据库迁移未执行

**症状**：
- Admin 后台看不到 Token 管理菜单
- 或者访问 Token 管理页面报错

**解决方法**：
```bash
cd backend
make migrate-token
```

**验证**：
```bash
python apiSystem/manage.py showmigrations automation
```

应该看到：
```
[X] 0005_add_court_token_and_testcourt
```

#### 2. Redis 服务未运行

**症状**：
- Token 保存失败
- 日志中有 Redis 连接错误

**解决方法**：
```bash
# 检查 Redis 是否运行
redis-cli ping

# 如果没有运行，启动 Redis
redis-server

# 或使用 Docker
docker run -d -p 6379:6379 redis:latest
```

**验证**：
```bash
redis-cli ping
# 应该返回: PONG
```

#### 3. 网络拦截器未捕获到 Token

**症状**：
- 登录成功
- 但日志中没有 "捕获到 Token" 的信息
- 日志中有 "未捕获到 Token" 的警告

**可能原因**：
1. 登录接口 URL 不匹配
2. 登录接口没有返回 Token
3. Token 字段名不匹配

**解决方法**：

**步骤 1**: 查看登录日志

```bash
tail -f backend/logs/api.log | grep -i token
```

登录时应该看到类似的日志：
```
🔍 拦截到请求: https://zxfw.court.gov.cn/...
📡 捕获到登录接口响应: https://zxfw.court.gov.cn/yzw/yzw-zxfw-yhfw/api/v1/login
📄 响应内容: {'data': {'token': 'xxx...', ...}}
✅ 从 data.token 捕获到 Token: xxx...
💾 准备保存 Token: court_zxfw - your_account
✅ Token 已成功保存到 Redis 和数据库
```

**步骤 2**: 如果看不到 "拦截到请求"

说明网络拦截器没有工作，可能是：
- Playwright 版本问题
- 浏览器上下文问题

尝试重启服务：
```bash
make run
```

**步骤 3**: 如果看到 "拦截到请求" 但没有 "捕获到 Token"

查看 "📄 响应内容" 部分，确认：
1. 响应中是否包含 token 字段
2. Token 字段的位置（data.token? result.token? 直接 token?）

如果字段名不同，需要修改代码。

#### 4. Token 字段名不匹配

**症状**：
- 日志显示 "📄 响应内容"
- 但没有 "✅ 从 xxx 捕获到 Token"
- 有 "⚠️ 未能从响应中提取 Token" 的警告

**解决方法**：

查看日志中的响应内容，找到 Token 字段的实际名称。

例如，如果响应是：
```json
{
  "code": 200,
  "data": {
    "userToken": "xxx..."
  }
}
```

需要修改 `court_zxfw.py` 中的 Token 提取逻辑，添加 `userToken` 的支持。

#### 5. TokenService 保存失败

**症状**：
- 日志显示 "💾 准备保存 Token"
- 但有 "❌ 保存 Token 失败" 的错误

**解决方法**：

查看完整的错误堆栈，可能是：
- 数据库连接问题
- Redis 连接问题
- 权限问题

手动测试 TokenService：
```bash
python apiSystem/manage.py shell
```

```python
from apps.automation.services.scraper.core.token_service import TokenService

ts = TokenService()
ts.save_token("test_site", "test_account", "test_token_123")
# 应该没有错误

token = ts.get_token("test_site", "test_account")
print(token)  # 应该输出: test_token_123

ts.delete_token("test_site", "test_account")
```

### 详细调试步骤

#### 步骤 1: 运行调试脚本

```bash
make debug-token
```

这会检查所有基础设施是否正常。

#### 步骤 2: 查看实时日志

打开一个新终端：
```bash
cd backend
tail -f logs/api.log
```

#### 步骤 3: 执行测试登录

在浏览器中访问：
```
http://localhost:8000/admin/automation/testcourt/
```

选择一个账号，点击"测试登录"。

#### 步骤 4: 观察日志输出

在日志中查找以下关键信息：

1. **网络拦截器设置**
   ```
   ✅ 已设置网络拦截器（拦截所有请求），准备捕获 Token
   ```

2. **请求拦截**
   ```
   🔍 拦截到请求: https://...
   ```

3. **登录接口响应**
   ```
   📡 捕获到登录接口响应: https://.../api/v1/login
   📄 响应内容: {...}
   ```

4. **Token 提取**
   ```
   ✅ 从 data.token 捕获到 Token: xxx...
   ```

5. **Token 保存**
   ```
   💾 准备保存 Token: court_zxfw - your_account
   ✅ Token 已成功保存到 Redis 和数据库
   ```

#### 步骤 5: 检查 Admin 后台

访问：
```
http://localhost:8000/admin/automation/courttoken/
```

应该能看到刚才保存的 Token。

### 手动验证

如果自动捕获不工作，可以手动保存一个测试 Token：

```bash
python apiSystem/manage.py shell
```

```python
from apps.automation.services.scraper.core.token_service import TokenService

ts = TokenService()
ts.save_token(
    site_name="court_zxfw",
    account="your_account",
    token="manual_test_token_12345",
    expires_in=3600
)

# 验证
token = ts.get_token("court_zxfw", "your_account")
print(f"Token: {token}")
```

然后访问 Admin 后台确认 Token 已保存。

### 获取帮助

如果问题仍然存在，请提供以下信息：

1. **调试脚本输出**
   ```bash
   make debug-token > debug_output.txt
   ```

2. **登录时的完整日志**
   ```bash
   tail -n 200 backend/logs/api.log > login_logs.txt
   ```

3. **登录接口的响应格式**
   - 从日志中复制 "📄 响应内容" 部分

4. **环境信息**
   - Python 版本
   - Django 版本
   - Redis 版本
   - Playwright 版本

### 相关命令

```bash
# 运行调试脚本
make debug-token

# 查看日志
tail -f backend/logs/api.log

# 测试 TokenService
make test-token

# 执行数据库迁移
make migrate-token

# 检查 Redis
redis-cli ping

# Django Shell
python apiSystem/manage.py shell
```

### 相关文档

- [Token 服务使用指南](./TOKEN_SERVICE_GUIDE.md)
- [Token Admin 管理指南](./TOKEN_ADMIN_GUIDE.md)
- [快速开始指南](./QUICK_START_TOKEN.md)

---

**提示**: 大多数问题都是因为数据库迁移未执行或 Redis 未运行导致的。
