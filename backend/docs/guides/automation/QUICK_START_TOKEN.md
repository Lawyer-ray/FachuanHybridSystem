# Token 功能快速开始

## 5 分钟快速上手

### 步骤 1: 执行数据库迁移

```bash
cd backend
make migrate-token
```

或者手动执行：

```bash
cd backend
source venv311/bin/activate
python apiSystem/manage.py migrate automation
```

### 步骤 2: 启动开发服务器

```bash
make run
```

或者：

```bash
source venv311/bin/activate
python apiSystem/manage.py runserver
```

### 步骤 3: 访问测试页面

打开浏览器访问：

```
http://localhost:8000/admin/automation/testcourt/
```

使用管理员账号登录（如果还没有，先创建）：

```bash
make superuser
```

### 步骤 4: 测试登录并捕获 Token

1. 在测试页面选择一个账号凭证
2. 点击"🔐 测试登录"按钮
3. 等待浏览器自动执行登录（约 30-60 秒）
4. 查看测试结果页面，确认 Token 已捕获

### 步骤 5: 在脚本中使用 Token

创建一个新的 Python 脚本：

```python
# my_script.py
import os
import sys
import django

# 设置 Django 环境
sys.path.insert(0, '/path/to/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.apiSystem.settings')
django.setup()

from apps.automation.services.scraper.core.token_service import TokenService

# 获取 Token
token_service = TokenService()
token = token_service.get_token("court_zxfw", "your_account")

if token:
    print(f"Token: {token}")
    
    # 使用 Token 调用 API
    import requests
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get("https://api.example.com/data", headers=headers)
    print(response.json())
else:
    print("Token 不存在或已过期")
```

运行脚本：

```bash
cd backend
source venv311/bin/activate
python my_script.py
```

## 使用示例脚本

我们提供了一个完整的示例脚本：

```bash
make token-example
```

或者：

```bash
cd backend
source venv311/bin/activate
python scripts/example_use_token.py
```

## 运行测试

验证 Token 服务是否正常工作：

```bash
make test-token
```

或者：

```bash
cd backend
source venv311/bin/activate
pytest apps/automation/tests/test_token_service.py -v
```

## 常用命令

### Makefile 命令

```bash
make migrate-token    # 执行 Token 数据库迁移
make token-example    # 运行 Token 使用示例
make test-token       # 测试 Token 服务
make run              # 启动开发服务器
```

### Django 管理命令

```bash
# 查看迁移状态
python apiSystem/manage.py showmigrations automation

# 进入 Django Shell
python apiSystem/manage.py shell

# 在 Shell 中测试
>>> from apps.automation.services.scraper.core.token_service import TokenService
>>> ts = TokenService()
>>> ts.get_token("court_zxfw", "your_account")
```

## 访问路径

| 功能 | URL |
|------|-----|
| 测试页面 | http://localhost:8000/admin/automation/testcourt/ |
| **Token 管理** | http://localhost:8000/admin/automation/courttoken/ |
| 旧测试页面 | http://localhost:8000/admin/automation/testtool/ |
| Admin 首页 | http://localhost:8000/admin/ |
| API 文档 | http://localhost:8000/api/v1/docs |

## 目录结构

```
backend/
├── apps/automation/
│   ├── models.py                          # CourtToken 模型
│   ├── admin/
│   │   └── test_admin.py                  # TestCourtAdmin
│   ├── services/
│   │   └── scraper/
│   │       ├── core/
│   │       │   └── token_service.py       # TokenService
│   │       └── sites/
│   │           └── court_zxfw.py          # Token 捕获逻辑
│   ├── templates/admin/automation/
│   │   ├── test_court_list.html           # 测试列表页
│   │   └── test_court_result.html         # 测试结果页
│   ├── tests/
│   │   └── test_token_service.py          # 单元测试
│   └── docs/
│       ├── TOKEN_SERVICE_GUIDE.md         # 使用指南
│       ├── TOKEN_CAPTURE_IMPLEMENTATION.md # 实现文档
│       ├── IMPLEMENTATION_SUMMARY.md      # 实现总结
│       └── QUICK_START_TOKEN.md           # 本文档
└── scripts/
    └── example_use_token.py               # 使用示例
```

## API 快速参考

### TokenService

```python
from apps.automation.services.scraper.core.token_service import TokenService

token_service = TokenService()

# 获取 Token
token = token_service.get_token(site_name, account)

# 保存 Token
token_service.save_token(site_name, account, token, expires_in=3600)

# 删除 Token
token_service.delete_token(site_name, account)

# 获取详细信息
info = token_service.get_token_info(site_name, account)
```

## 故障排查

### 问题 1: 数据库迁移失败

```bash
# 检查迁移状态
python apiSystem/manage.py showmigrations automation

# 如果有未应用的迁移，执行
python apiSystem/manage.py migrate automation
```

### 问题 2: Redis 连接失败

```bash
# 检查 Redis 是否运行
redis-cli ping

# 如果未运行，启动 Redis
redis-server

# 或使用 Docker
docker run -d -p 6379:6379 redis:latest
```

### 问题 3: 未捕获到 Token

1. 检查登录是否成功
2. 查看日志：`backend/logs/api.log`
3. 确认登录接口 URL 是否正确
4. 检查响应格式是否匹配

### 问题 4: Token 获取失败

```python
# 在 Django Shell 中调试
python apiSystem/manage.py shell

>>> from apps.automation.services.scraper.core.token_service import TokenService
>>> from apps.automation.models import CourtToken
>>> 
>>> # 检查数据库中的 Token
>>> CourtToken.objects.all()
>>> 
>>> # 检查 Redis
>>> from django.core.cache import cache
>>> cache.get("court_token:court_zxfw:your_account")
```

## 下一步

1. ✅ 阅读 [Token 服务使用指南](./TOKEN_SERVICE_GUIDE.md)
2. ✅ 查看 [实现详细文档](./TOKEN_CAPTURE_IMPLEMENTATION.md)
3. ✅ 运行示例脚本学习使用方法
4. ✅ 根据实际需求调整配置

## 获取帮助

- 查看文档：`backend/apps/automation/docs/`
- 查看日志：`backend/logs/`
- 运行测试：`make test-token`
- 查看示例：`make token-example`

## 相关文档

- [Token 服务使用指南](./TOKEN_SERVICE_GUIDE.md) - 详细的 API 文档和使用示例
- [Token Admin 管理指南](./TOKEN_ADMIN_GUIDE.md) - Admin 后台管理 Token
- [实现详细文档](./TOKEN_CAPTURE_IMPLEMENTATION.md) - 技术实现细节
- [实现总结](./IMPLEMENTATION_SUMMARY.md) - 功能总结和部署指南
- [CourtZxfwService 文档](./COURT_ZXFW_SERVICE.md) - 法院服务文档

---

**更新时间**: 2024-01-XX  
**版本**: v1.0.0
