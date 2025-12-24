# 🏢 组织管理模块 (Organization)

组织管理模块，提供律所、律师、团队和账号凭证的管理功能。

## 📚 模块概述

本模块负责管理法律服务组织的完整信息，包括：
- 律所信息管理
- 律师信息管理
- 团队管理
- 账号凭证管理
- 用户认证
- 组织权限控制

## 📁 目录结构

```
organization/
├── admin/              # Django Admin 配置
│   ├── lawfirm_admin.py            # 律所 Admin
│   ├── lawyer_admin.py             # 律师 Admin
│   ├── team_admin.py               # 团队 Admin
│   └── accountcredential_admin.py  # 账号凭证 Admin
├── api/                # API 接口
│   ├── lawfirm_api.py              # 律所 API
│   ├── lawyer_api.py               # 律师 API
│   ├── team_api.py                 # 团队 API
│   ├── accountcredential_api.py    # 账号凭证 API
│   └── auth_api.py                 # 认证 API
├── services/           # 业务逻辑
│   ├── lawfirm_service.py          # 律所服务
│   ├── lawyer_service.py           # 律师服务
│   ├── team_service.py             # 团队服务 ✨ 新增
│   ├── auth_service.py             # 认证服务 ✨ 新增
│   ├── account_credential_service.py        # 账号凭证服务
│   └── account_credential_admin_service.py  # 账号凭证管理服务 ✨ 新增
├── models.py           # 数据模型
├── schemas.py          # Pydantic Schemas
├── middleware.py       # 组织权限中间件
└── migrations/         # 数据库迁移
```

## 🏗️ 架构设计

本模块遵循四层架构规范：

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer                               │
│  - 工厂函数 _get_xxx_service()                              │
│  - 参数提取 → 调用 Service → 返回结果                        │
│  - 不包含业务逻辑、权限检查、事务管理                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
│  - 业务逻辑、权限检查、事务管理                               │
│  - 抛出业务异常 (ValidationException, NotFoundError)         │
│  - TeamService, AuthService, AccountCredentialService 等     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Model Layer                             │
│  - 数据定义、简单属性                                        │
│  - 不包含业务方法                                            │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. Admin 后台

```bash
# 访问组织管理后台
open http://localhost:8000/admin/organization/
```

### 2. API 使用

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/organization"
headers = {"Authorization": "Bearer <your_jwt_token>"}

# 创建律所
response = requests.post(f"{BASE_URL}/lawfirms", json={
    "name": "XX律师事务所",
    "license_number": "12345678",
    "address": "北京市朝阳区",
    "phone": "010-12345678",
    "email": "contact@lawfirm.com"
}, headers=headers)

lawfirm_id = response.json()["data"]["id"]

# 创建律师
response = requests.post(f"{BASE_URL}/lawyers", json={
    "name": "张律师",
    "license_number": "11234567890",
    "law_firm_id": lawfirm_id,
    "phone": "13800138000",
    "email": "zhang@lawfirm.com"
}, headers=headers)

lawyer_id = response.json()["data"]["id"]

# 创建团队
response = requests.post(f"{BASE_URL}/teams", json={
    "name": "民事诉讼团队",
    "law_firm_id": lawfirm_id,
    "team_type": "lawyer"
}, headers=headers)

# 添加账号凭证
response = requests.post(f"{BASE_URL}/credentials", json={
    "platform": "court_zxfw",
    "account": "username",
    "password": "encrypted_password",
    "lawyer_id": lawyer_id
}, headers=headers)
```

### 3. Service 层使用

```python
# ✅ 正确：使用工厂函数获取 Service
def _get_team_service():
    from apps.organization.services import TeamService
    return TeamService()

def _get_auth_service():
    from apps.organization.services import AuthService
    return AuthService()

# 团队服务使用示例
team_service = _get_team_service()
teams = team_service.list_teams(law_firm_id=1, user=request.user)
team = team_service.create_team(data=TeamIn(...), user=request.user)

# 认证服务使用示例
auth_service = _get_auth_service()
user = auth_service.login(request, username="user", password="pass")
auth_service.logout(request)
```

## 📦 服务层详解

### TeamService（团队服务）

封装团队相关的所有业务逻辑，包括权限检查和事务管理。

```python
from apps.organization.services import TeamService
from apps.organization.schemas import TeamIn

service = TeamService()

# 列表查询（自动权限过滤）
teams = service.list_teams(law_firm_id=1, team_type="lawyer", user=user)

# 获取详情
team = service.get_team(team_id=1, user=user)

# 创建团队（带事务）
team = service.create_team(
    data=TeamIn(name="新团队", team_type="lawyer", law_firm_id=1),
    user=user
)

# 更新团队（带事务）
team = service.update_team(team_id=1, data=TeamIn(...), user=user)

# 删除团队（带事务）
service.delete_team(team_id=1, user=user)
```

**异常处理：**
- `ValidationException`: 团队类型无效
- `NotFoundError`: 团队或律所不存在
- `PermissionDenied`: 权限不足

### AuthService（认证服务）

封装用户认证相关的业务逻辑。

```python
from apps.organization.services import AuthService

service = AuthService()

# 用户登录
try:
    user = service.login(request, username="user", password="pass")
except AuthenticationError:
    # 处理认证失败
    pass

# 用户登出
service.logout(request)
```

**异常处理：**
- `AuthenticationError`: 用户名或密码错误

### AccountCredentialAdminService（账号凭证管理服务）

封装 Admin 层的业务逻辑，包括自动登录功能。

```python
from apps.organization.services import AccountCredentialAdminService

service = AccountCredentialAdminService()

# 单个账号自动登录
result = service.single_auto_login(
    credential_id=1,
    admin_user="admin"
)
# result: LoginResult(success=True, duration=5.2, token="xxx")

# 批量自动登录
result = service.batch_auto_login(
    credential_ids=[1, 2, 3],
    admin_user="admin"
)
# result: BatchLoginResult(success_count=2, error_count=1, ...)
```

**数据类型：**
```python
@dataclass
class LoginResult:
    success: bool
    duration: float
    token: Optional[str] = None
    error_message: Optional[str] = None

@dataclass
class BatchLoginResult:
    success_count: int
    error_count: int
    total_duration: float
    message: str
```

## 🔑 核心功能

### 律所管理
- ✅ 创建、查询、更新、删除律所
- ✅ 律所执业许可证管理
- ✅ 律所联系方式管理
- ✅ 律所银行账户管理
- ✅ 律所律师列表

### 律师管理
- ✅ 创建、查询、更新、删除律师
- ✅ 律师执业证管理
- ✅ 律师联系方式管理
- ✅ 律师所属律所管理
- ✅ 律师团队管理

### 团队管理
- ✅ 创建、查询、更新、删除团队
- ✅ 团队成员管理
- ✅ 团队负责人管理
- ✅ 团队类型验证（lawyer/biz）
- ✅ 权限检查（律所隔离）

### 账号凭证管理
- ✅ 添加、编辑、删除账号凭证
- ✅ 凭证加密存储
- ✅ 凭证平台管理（法院、保险等）
- ✅ 凭证归属律师
- ✅ 自动登录功能
- ✅ 批量自动登录
- ✅ 登录历史记录

### 用户认证
- ✅ 用户登录
- ✅ 用户登出
- ✅ 认证失败异常处理

## 📊 数据模型

### LawFirm (律所)
- `name`: 律所名称
- `license_number`: 执业许可证号
- `address`: 地址
- `phone`: 电话
- `email`: 邮箱
- `bank_name`: 开户银行
- `bank_account`: 银行账号

### Lawyer (律师)
- `name`: 律师姓名
- `license_number`: 执业证号
- `law_firm`: 关联律所
- `phone`: 电话
- `email`: 邮箱
- `license_pdf`: 执业证PDF
- `teams`: 所属团队（多对多）

### Team (团队)
- `name`: 团队名称
- `team_type`: 团队类型（lawyer/biz）
- `law_firm`: 关联律所
- `leader`: 团队负责人
- `lawyers`: 团队成员（多对多）

### AccountCredential (账号凭证)
- `platform`: 平台名称
- `account`: 账号
- `password`: 密码（加密）
- `lawyer`: 关联律师
- `is_active`: 是否激活
- `login_count`: 登录次数
- `success_count`: 成功次数
- `last_login_at`: 最后登录时间

## 🔒 权限控制

### 功能级别权限
- `organization.add_lawfirm`: 创建律所
- `organization.view_lawfirm`: 查看律所
- `organization.change_lawfirm`: 修改律所
- `organization.delete_lawfirm`: 删除律所

### 对象级别权限
- 律所管理员可以管理本律所的所有信息
- 律师可以查看本律所的信息
- 律师可以修改自己的信息
- 超级管理员可以管理所有律所

### Service 层权限检查
```python
# TeamService 权限检查示例
def _check_read_permission(self, user, team) -> bool:
    if user is None:
        return True
    if user.is_superuser:
        return True
    return user.law_firm_id == team.law_firm_id

def _check_create_permission(self, user) -> bool:
    if user is None:
        return False
    return user.is_authenticated and (user.is_superuser or user.is_admin)
```

## 🧪 测试

```bash
# 运行单元测试
cd backend
source venv311/bin/activate
python -m pytest tests/unit/organization/ -v

# 运行集成测试
python -m pytest tests/integration/organization/ -v

# 运行属性测试
python -m pytest tests/property/organization/ -v
```

## 📝 相关文档

- **[models.py](models.py)** - 数据模型定义
- **[schemas.py](schemas.py)** - API Schema 定义
- **[middleware.py](middleware.py)** - 组织权限中间件
- **[services/lawfirm_service.py](services/lawfirm_service.py)** - 律所服务
- **[services/lawyer_service.py](services/lawyer_service.py)** - 律师服务
- **[services/team_service.py](services/team_service.py)** - 团队服务
- **[services/auth_service.py](services/auth_service.py)** - 认证服务
- **[services/account_credential_service.py](services/account_credential_service.py)** - 账号凭证服务
- **[services/account_credential_admin_service.py](services/account_credential_admin_service.py)** - 账号凭证管理服务

## 🔗 依赖模块

- **cases**: 案件模块（律师指派案件）
- **contracts**: 合同模块（律师签订合同）
- **core**: 核心模块（异常、接口、验证器）
- **automation**: 自动化模块（自动登录服务）

## 🎯 最佳实践

### 1. 使用工厂函数获取 Service
```python
# ✅ 正确：使用工厂函数
def _get_team_service():
    from apps.organization.services import TeamService
    return TeamService()

@router.get("/teams")
def list_teams(request):
    service = _get_team_service()
    return service.list_teams(user=request.user)

# ❌ 错误：直接实例化
service = TeamService()  # 不要在模块级别实例化
```

### 2. API 层不包含业务逻辑
```python
# ✅ 正确：委托给 Service
@router.post("/teams")
def create_team(request, payload: TeamIn):
    service = _get_team_service()
    return service.create_team(data=payload, user=request.user)

# ❌ 错误：API 层包含业务逻辑
@router.post("/teams")
def create_team(request, payload: TeamIn):
    if payload.team_type not in ["lawyer", "biz"]:  # 不要在 API 层验证
        raise HttpError(400, "Invalid team type")
    team = Team.objects.create(...)  # 不要直接操作 Model
```

### 3. Service 层处理异常
```python
# ✅ 正确：Service 层抛出业务异常
class TeamService:
    def create_team(self, data, user):
        if not self._check_create_permission(user):
            raise PermissionDenied("无权限创建团队")
        self._validate_team_type(data.team_type)  # 抛出 ValidationException
        ...

# ❌ 错误：Service 层抛出 HTTP 异常
class TeamService:
    def create_team(self, data, user):
        raise HttpError(403, "无权限")  # 不要抛出 HTTP 异常
```

### 4. 凭证加密存储
```python
# ✅ 正确：使用加密存储密码
from cryptography.fernet import Fernet

def encrypt_password(password: str) -> str:
    key = settings.CREDENTIAL_ENCRYPTION_KEY
    f = Fernet(key)
    return f.encrypt(password.encode()).decode()
```

## 🐛 常见问题

### Q1: 如何切换律师所属律所？
**A**: 更新律师的 `law_firm` 字段，系统会自动处理相关权限。

### Q2: 如何管理团队成员？
**A**: 使用团队的 `lawyers` 多对多关系添加或移除成员。

### Q3: 如何保护账号凭证安全？
**A**: 使用 Fernet 加密存储密码，并限制访问权限。

### Q4: TeamService 支持哪些团队类型？
**A**: 支持 `lawyer`（律师团队）和 `biz`（业务团队）两种类型。

### Q5: 如何触发账号自动登录？
**A**: 使用 `AccountCredentialAdminService.single_auto_login()` 或 `batch_auto_login()` 方法。

## 📈 性能优化

- ✅ 使用 `select_related` 预加载律所信息
- ✅ 使用 `prefetch_related` 预加载团队成员
- ✅ 使用索引优化查询（律所名称、律师姓名、执业证号）
- ✅ 使用缓存减少数据库查询
- ✅ Service 层延迟加载依赖服务

## 🔐 安全考虑

### 凭证加密
```python
# 使用 Fernet 对称加密
from cryptography.fernet import Fernet

# 生成密钥（只需一次）
key = Fernet.generate_key()

# 加密
f = Fernet(key)
encrypted = f.encrypt(b"password")

# 解密
decrypted = f.decrypt(encrypted)
```

### 权限隔离
- 律所之间数据隔离
- 律师只能访问本律所数据
- 凭证只能由所有者访问
- 超级管理员可以访问所有数据

## 🔄 版本历史

- **v1.0.0** (2024-01): 初始版本
- **v1.1.0** (2024-03): 添加团队管理
- **v1.2.0** (2024-06): 添加账号凭证管理
- **v1.3.0** (2024-09): 添加组织权限中间件
- **v1.4.0** (2024-12): 架构合规性重构
  - ✨ 新增 TeamService（团队服务）
  - ✨ 新增 AuthService（认证服务）
  - ✨ 新增 AccountCredentialAdminService（账号凭证管理服务）
  - 🔧 重构 team_api.py 使用工厂函数
  - 🔧 重构 auth_api.py 使用工厂函数
  - 🔧 添加 lawyer_api.py 工厂函数
  - 🔧 添加 lawfirm_api.py 工厂函数
  - 🔧 增强 AccountCredentialService 权限检查
  - 🔧 清理 Model 层业务方法
  - 🔧 修复 LawFirmServiceAdapter 临时用户问题
