# 法传混合系统 - 后端服务

## 📖 项目概述

法传混合系统后端是一个基于 Django 5.2+ 和 django-ninja 的现代化 RESTful API 服务，专为法律行业设计，提供案件管理、合同管理、客户管理、自动化爬虫等核心功能。

### 核心特性

- **三层架构设计**：清晰的 API、Service、Model 分层
- **依赖注入**：提高代码可测试性和可维护性
- **接口解耦**：使用 Protocol 避免循环依赖
- **自动Token获取**：智能Token管理，无需人工干预 ⭐
- **异步任务**：基于 django-q2 的任务队列
- **浏览器自动化**：集成 Playwright 实现法院网站自动化
- **法院文书下载优化**：API 拦截方式，效率提升 3-5 倍 ⭐
- **验证码识别**：使用 ddddocr 进行验证码识别
- **JWT 认证**：基于 django-ninja-jwt 的安全认证
- **Property-Based Testing**：使用 hypothesis 进行属性测试

## 🏗️ 架构设计

### 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                      API Layer                          │
│  - 请求/响应处理                                         │
│  - 参数验证（Schema）                                    │
│  - 异常转换                                              │
│  - 不包含业务逻辑                                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    Service Layer                        │
│  - 业务逻辑封装                                          │
│  - 依赖注入                                              │
│  - 事务管理                                              │
│  - 权限检查                                              │
│  - 通过 Protocol 跨模块通信                              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                     Model Layer                         │
│  - 数据定义（Django ORM）                                │
│  - 简单的数据库操作                                      │
│  - 不包含复杂业务逻辑                                    │
└─────────────────────────────────────────────────────────┘
```

### 项目结构

```
backend/
├── apiSystem/                    # Django 项目配置（唯一的项目目录）
│   ├── apiSystem/
│   │   ├── settings.py          # 项目设置
│   │   ├── api.py               # API 路由汇总
│   │   ├── urls.py              # URL 配置
│   │   ├── wsgi.py              # WSGI 配置
│   │   └── asgi.py              # ASGI 配置
│   ├── manage.py
│   └── db.sqlite3
│
├── apps/                         # 所有 Django 应用
│   ├── core/                     # 核心模块
│   │   ├── config.py            # 集中配置管理
│   │   ├── exceptions.py        # 自定义异常
│   │   ├── interfaces.py        # Protocol 接口
│   │   └── validators.py        # 验证器
│   │
│   ├── cases/                    # 案件管理模块
│   │   ├── models.py            # 数据模型
│   │   ├── schemas.py           # Pydantic schemas
│   │   ├── admin/               # Admin 配置（按模型分文件）
│   │   ├── api/                 # API 路由（按资源分文件）
│   │   ├── services/            # 业务逻辑（按领域分文件）
│   │   ├── migrations/          # 数据库迁移
│   │   └── README.md            # 模块文档
│   │
│   ├── contracts/               # 合同管理模块（结构同上）
│   ├── client/                  # 客户管理模块（结构同上）
│   ├── organization/            # 组织管理模块（结构同上）
│   └── automation/              # 自动化爬虫模块（结构同上）
│
├── tests/                        # 集中的测试目录
│   ├── conftest.py              # pytest 配置
│   ├── unit/                    # 单元测试
│   ├── integration/             # 集成测试
│   ├── property/                # Property-based tests
│   ├── admin/                   # Admin 测试
│   ├── factories/               # Test factories
│   ├── mocks/                   # Mock objects
│   ├── structure/               # 结构验证测试
│   └── README.md                # 测试文档
│
├── scripts/                      # 工具脚本（按功能分类）
│   ├── testing/                 # 测试相关脚本
│   ├── development/             # 开发工具脚本
│   ├── automation/              # 自动化脚本
│   ├── refactoring/             # 重构工具
│   └── README.md                # 脚本使用说明
│
├── docs/                         # 项目文档
│   ├── README.md                # 文档索引
│   ├── api/                     # API 文档
│   ├── architecture/            # 架构文档
│   │   └── adr/                # Architecture Decision Records
│   ├── guides/                  # 开发指南
│   ├── operations/              # 运维文档
│   └── quality/                 # 质量文档
│
├── logs/                         # 日志文件
├── .hypothesis/                  # Hypothesis 缓存
├── .mypy_cache/                  # MyPy 缓存
├── .pytest_cache/                # Pytest 缓存
├── htmlcov/                      # 覆盖率报告
│
├── .env.example                  # 环境变量示例
├── .gitignore
├── .flake8
├── .pre-commit-config.yaml
├── conftest.py                   # 根级 pytest 配置
├── pytest.ini
├── mypy.ini
├── pyproject.toml
├── requirements.txt
├── Makefile
└── README.md                     # 项目主文档
```

### 目录结构说明

#### Django App 标准结构

每个 Django app 遵循统一的目录结构：

- **admin/** - Admin 配置，按模型分文件（如 `case_admin.py`）
- **api/** - API 路由，按资源分文件（如 `case_api.py`）
- **services/** - 业务逻辑，按领域分文件（如 `case_service.py`）
- **models.py** - 数据模型定义
- **schemas.py** - Pydantic schemas（请求/响应）
- **migrations/** - 数据库迁移文件
- **README.md** - 模块文档

#### 测试目录组织

测试文件集中在根级 `tests/` 目录，按类型组织：

- **unit/** - 单元测试（测试 Service 层业务逻辑）
- **integration/** - 集成测试（测试 API 端到端流程）
- **property/** - Property-based tests（使用 hypothesis）
- **admin/** - Admin 表单验证测试
- **factories/** - Test factories（使用 factory-boy）
- **mocks/** - Mock objects
- **structure/** - 项目结构验证测试

#### 脚本目录分类

工具脚本按功能分类：

- **testing/** - 测试相关脚本
- **development/** - 开发工具脚本
- **automation/** - 自动化脚本（如浏览器自动化）
- **refactoring/** - 重构和迁移工具

#### 文档目录组织

文档按类型分类存放：

- **api/** - API 文档和端点规范
- **architecture/** - 架构文档、设计决策（ADR）
- **guides/** - 开发指南、代码审查流程
- **operations/** - 运维文档（部署、监控、恢复）
- **quality/** - 代码质量审查和最佳实践

## 🚀 快速开始

### 前置要求

- Python 3.11+
- SQLite（开发环境）或 PostgreSQL（生产环境）
- Redis（用于缓存和任务队列）
- Playwright（用于浏览器自动化）

### 安装步骤

1. **克隆项目**
   ```bash
   git clone <repository-url>
   cd FachuanHybridSystem/backend
   ```

2. **激活虚拟环境**
   ```bash
   source venv311/bin/activate
   ```

3. **安装依赖**
   ```bash
   make install
   ```

4. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，配置数据库、Redis 等
   ```

5. **运行数据库迁移**
   ```bash
   make migrate
   ```

6. **创建超级用户**
   ```bash
   make superuser
   ```

7. **启动开发服务器**
   ```bash
   make run
   ```

8. **（可选）启动任务队列**
   ```bash
   # 在另一个终端
   make qcluster
   ```

### 访问服务

- **API 文档**: http://localhost:8000/api/docs
- **Admin 后台**: http://localhost:8000/admin/
- **健康检查**: http://localhost:8000/api/v1/health

## 📚 API 文档

### 认证

所有 API 端点（除了登录和健康检查）都需要 JWT 认证：

```bash
# 获取 Token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'

# 使用 Token 访问 API
curl http://localhost:8000/api/v1/cases \
  -H "Authorization: Bearer <your_token>"
```

### 主要 API 端点

#### 案件管理 (`/api/v1/cases`)
- `GET /api/v1/cases` - 列表查询
- `POST /api/v1/cases` - 创建案件
- `GET /api/v1/cases/{id}` - 获取案件详情
- `PUT /api/v1/cases/{id}` - 更新案件
- `DELETE /api/v1/cases/{id}` - 删除案件

#### 合同管理 (`/api/v1/contracts`)
- `GET /api/v1/contracts` - 列表查询
- `POST /api/v1/contracts` - 创建合同
- `GET /api/v1/contracts/{id}` - 获取合同详情
- `PUT /api/v1/contracts/{id}` - 更新合同
- `POST /api/v1/contracts/{id}/payments` - 添加支付记录

#### 客户管理 (`/api/v1/clients`)
- `GET /api/v1/clients` - 列表查询
- `POST /api/v1/clients` - 创建客户
- `GET /api/v1/clients/{id}` - 获取客户详情
- `PUT /api/v1/clients/{id}` - 更新客户

#### 自动化服务 (`/api/v1/automation`)
- `POST /api/v1/automation/preservation-quotes` - 创建保全询价任务
- `GET /api/v1/automation/preservation-quotes` - 查询询价任务
- `POST /api/v1/automation/preservation-quotes/{id}/execute` - 执行询价（自动Token获取）⭐
- `POST /api/v1/automation/court-documents/download` - 下载法院文书 ⭐
- `GET /api/v1/automation/performance/metrics` - 获取Token获取性能指标
- `POST /api/v1/automation/performance/cache/warm-up` - 预热Token缓存

完整的 API 文档请访问：http://localhost:8000/api/docs

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
make test

# 运行带覆盖率的测试
make test-cov

# 运行特定模块的测试
pytest apps/cases/tests/

# 运行特定测试文件
pytest apps/cases/tests/test_case_service.py

# 运行特定测试
pytest apps/cases/tests/test_case_service.py::TestCaseService::test_create_case
```

### 测试类型

1. **单元测试**：测试 Service 层的业务逻辑
2. **集成测试**：测试 API 端到端流程
3. **Property-Based Testing**：使用 hypothesis 验证通用属性

### 测试覆盖率目标

- Service 层：80%+
- API 层：60%+
- 核心业务逻辑：90%+

## 🛠️ 开发指南

### 代码规范

项目遵循严格的代码规范，详见 `.kiro/steering/django-python-expert.md`。

**核心原则**：

1. **API 层**：只负责请求/响应处理，不包含业务逻辑
2. **Service 层**：封装所有业务逻辑，使用依赖注入
3. **Model 层**：只包含数据定义和简单操作

### 创建新功能

1. **定义 Model**（如果需要）
   ```python
   # apps/myapp/models.py
   class MyModel(models.Model):
       name = models.CharField(max_length=200)
       created_at = models.DateTimeField(auto_now_add=True)
   ```

2. **定义 Schema**
   ```python
   # apps/myapp/schemas.py
   from pydantic import BaseModel
   
   class MyModelCreateSchema(BaseModel):
       name: str
   
   class MyModelSchema(BaseModel):
       id: int
       name: str
       created_at: str
       
       class Config:
           from_attributes = True
   ```

3. **创建 Service**
   ```python
   # apps/myapp/services/mymodel_service.py
   class MyModelService:
       def __init__(self, dependency_service: IDependencyService):
           self.dependency_service = dependency_service
       
       def create_mymodel(self, data: MyModelCreateSchema, user: User) -> MyModel:
           # 权限检查
           if not user.has_perm('myapp.add_mymodel'):
               raise PermissionDenied("无权限")
           
           # 业务逻辑
           obj = MyModel.objects.create(name=data.name, created_by=user)
           return obj
   ```

4. **创建 API**
   ```python
   # apps/myapp/api/mymodel_api.py
   from ninja import Router
   from ninja_jwt.authentication import JWTAuth
   
   router = Router(tags=["MyModel"], auth=JWTAuth())
   
   @router.post("/", response=MyModelSchema)
   def create_mymodel(request, data: MyModelCreateSchema):
       service = MyModelService(dependency_service=DependencyService())
       obj = service.create_mymodel(data, request.auth)
       return MyModelSchema.from_orm(obj)
   ```

5. **编写测试**
   ```python
   # apps/myapp/tests/test_mymodel_service.py
   import pytest
   
   @pytest.mark.django_db
   class TestMyModelService:
       def test_create_mymodel_success(self):
           service = MyModelService(dependency_service=MockDependencyService())
           obj = service.create_mymodel(data, user)
           assert obj.id is not None
   ```

### 常用命令

```bash
# 开发
make run              # 启动开发服务器
make qcluster         # 启动任务队列
make shell            # Django shell

# 数据库
make migrate          # 运行迁移
make makemigrations   # 创建迁移
make resetdb          # 重置数据库（危险！）

# 测试
make test             # 运行测试
make test-cov         # 带覆盖率
make test-fast        # 快速测试

# 代码质量
make lint             # 代码检查
make format           # 代码格式化
make type-check       # 类型检查

# 清理
make clean            # 清理临时文件
make clean-logs       # 清理日志
```

## 📊 性能监控

项目集成了性能监控功能，详见 `PERFORMANCE_MONITORING_IMPLEMENTATION.md`。

### 查看性能指标

```bash
# 分析性能数据
make analyze-performance

# 查看慢查询
make check-db-performance
```

### 监控指标

- API 响应时间（P50, P95, P99）
- 数据库查询次数
- 缓存命中率
- 任务队列状态

## 🤖 自动Token获取功能

### 功能概述

自动Token获取功能为财产保险询价服务提供了智能的Token管理能力。当系统检测到Token无效时，会自动触发法院一张网登录流程，获取新Token后继续执行业务操作，无需人工干预。

### 核心特性

- **智能Token检查**：自动检测Token有效性
- **自动登录获取**：Token失效时自动触发登录流程
- **账号选择策略**：优先使用最近成功登录的账号
- **错误处理重试**：网络错误和验证码失败的自动重试
- **并发控制**：避免多个任务同时触发登录
- **性能监控**：完整的性能指标和缓存统计
- **结构化日志**：详细的执行轨迹记录

### 使用方式

#### 1. 基本使用（API层自动处理）

```bash
# 执行询价任务（自动处理Token）
curl -X POST "http://localhost:8000/api/v1/automation/preservation-quotes/123/execute" \
  -H "Authorization: Bearer <your_jwt_token>"
```

#### 2. 在代码中集成

```python
from apps.core.interfaces import ServiceLocator

# 获取自动Token服务
service = ServiceLocator.get_auto_token_acquisition_service()

# 自动获取Token（自动选择账号）
token = await service.acquire_token_if_needed("court_zxfw")

# 使用指定凭证获取Token
token = await service.acquire_token_if_needed("court_zxfw", credential_id=1)
```

#### 3. 性能监控

```bash
# 获取性能指标
curl "http://localhost:8000/api/v1/automation/performance/metrics"

# 预热缓存
curl -X POST "http://localhost:8000/api/v1/automation/performance/cache/warm-up?site_name=court_zxfw"

# 获取系统健康状态
curl "http://localhost:8000/api/v1/automation/performance/health"
```

### 配置要求

1. **账号凭证配置**：在Django Admin中配置法院一张网账号
2. **Redis缓存**：用于Token缓存和性能优化
3. **浏览器环境**：Playwright自动化环境

### 监控和维护

```bash
# 性能优化命令
python manage.py optimize_token_performance --health-check
python manage.py optimize_token_performance --cleanup-days 30
python manage.py optimize_token_performance --warm-cache court_zxfw
```

### 相关文档

- [API文档](docs/api/AUTO_TOKEN_ACQUISITION_API.md) - 完整的API接口文档
- [集成指南](docs/guides/AUTO_TOKEN_ACQUISITION_INTEGRATION_GUIDE.md) - 详细的集成步骤
- [示例代码](docs/examples/AUTO_TOKEN_ACQUISITION_EXAMPLES.md) - 各种使用场景的示例

## 🔒 安全

### 认证和授权

- 使用 JWT Token 进行认证
- 基于 Django Permission 的权限控制
- 所有 Service 方法都有权限检查

### 数据安全

- 密码使用 Django 的哈希存储
- 敏感信息加密存储
- SQL 注入防护（使用 ORM）
- XSS 防护（Django 内置）

### 最佳实践

- 不在日志中记录敏感信息
- 使用环境变量管理敏感配置
- 定期更新依赖包
- 使用 HTTPS（生产环境）

## 🐛 故障排查

### 常见问题

1. **端口被占用**
   ```bash
   lsof -i :8000
   kill -9 <PID>
   ```

2. **数据库迁移失败**
   ```bash
   make resetdb  # 重置数据库（会删除所有数据！）
   make migrate
   ```

3. **依赖安装失败**
   ```bash
   uv pip install -r requirements.txt
   ```

4. **Playwright 浏览器未安装**
   ```bash
   backend/venv311/bin/playwright install chromium
   ```

### 日志位置

- API 日志：`logs/api.log`
- SQL 日志：`logs/sql.log`
- 错误日志：`logs/error.log`

## 📖 文档和培训

### 架构决策记录（ADR）

项目的重要架构决策记录在 `docs/adr/` 目录下：

- [ADR-001: 采用三层架构](docs/adr/001-three-layer-architecture.md)
- [ADR-002: 使用依赖注入](docs/adr/002-dependency-injection.md)
- [ADR-003: Protocol 接口解耦](docs/adr/003-protocol-interface.md)
- [ADR-004: 统一异常处理](docs/adr/004-exception-handling.md)

### 培训和知识分享

**新成员必读**：

1. **快速开始**：[`docs/guides/QUICK_START.md`](docs/guides/QUICK_START.md)
   - 环境搭建和项目运行
   - 基本开发流程
   - 常见问题解答

1.5. **法院文书下载快速参考**：[`docs/guides/COURT_DOCUMENT_QUICK_REFERENCE.md`](docs/guides/COURT_DOCUMENT_QUICK_REFERENCE.md) ⭐
   - 5 分钟快速开始
   - 常用命令和配置速查
   - 常见问题快速解决

2. **架构规范**：[`.kiro/steering/django-python-expert.md`](.kiro/steering/django-python-expert.md)
   - 完整的开发规范和最佳实践
   - API、Service、Model 层的代码模板
   - 反模式警示和常见错误

3. **架构培训**：[`docs/architecture/ARCHITECTURE_TRAINING.md`](docs/architecture/ARCHITECTURE_TRAINING.md)
   - 5 周完整培训计划
   - 理论讲解和实战演练
   - 培训评估和测试

4. **文件组织**：[`docs/guides/FILE_ORGANIZATION.md`](docs/guides/FILE_ORGANIZATION.md)
   - 项目文件组织规范
   - 目录结构说明
   - 命名规范和最佳实践

5. **迁移指南**：[`docs/guides/MIGRATION_GUIDE.md`](docs/guides/MIGRATION_GUIDE.md)
   - 项目结构变化说明
   - 迁移步骤和清单
   - 常见问题解答

6. **最佳实践**：[`docs/architecture/REFACTORING_BEST_PRACTICES.md`](docs/architecture/REFACTORING_BEST_PRACTICES.md)
   - 重构经验总结
   - 常见陷阱和解决方案
   - 成功案例分析

7. **代码审查**：
   - [代码审查流程](docs/guides/CODE_REVIEW_PROCESS.md)
   - [代码审查清单](docs/guides/CODE_REVIEW_CHECKLIST.md)

8. **知识分享**：[`docs/guides/TEAM_KNOWLEDGE_SHARING.md`](docs/guides/TEAM_KNOWLEDGE_SHARING.md)
   - 每周技术分享会
   - 知识库建设
   - 持续改进机制

**快速参考**：

- 🏗️ 架构原则：三层架构、依赖注入、接口解耦
- 📝 代码规范：API/Service/Model 层职责边界
- 📁 文件组织：统一的目录结构和命名规范
- 🧪 测试规范：单元测试、Property-Based Testing
- 🚀 性能优化：避免 N+1 查询、批量操作
- 🔒 安全规范：权限检查、输入验证、敏感信息保护

**文档索引**：

完整的文档列表请查看 [`docs/README.md`](docs/README.md)

## 🤝 贡献指南

### 代码审查清单

在提交 PR 前，请确保：

- [ ] 遵循三层架构原则
- [ ] 使用依赖注入
- [ ] 添加类型注解
- [ ] 编写单元测试
- [ ] 更新文档
- [ ] 通过代码检查（`make lint`）
- [ ] 通过类型检查（`make type-check`）
- [ ] 测试覆盖率达标

完整的代码审查清单请参考 `.kiro/steering/django-python-expert.md`。

## 📝 更新日志

### v2.0.0 (2025-01)
- ✨ 完成架构重构，采用三层架构
- ✨ 实现依赖注入和接口解耦
- ✨ 添加 Property-Based Testing
- ✨ 完善性能监控
- 🐛 修复 N+1 查询问题
- 📚 完善文档和代码规范

### v1.0.0 (2025-12)
- 🎉 初始版本发布
- ✨ 实现案件、合同、客户管理
- ✨ 实现自动化爬虫功能
- ✨ 集成验证码识别

## 📄 许可证

[许可证信息]

## 👥 团队

[团队信息]

## 📞 联系方式

- 问题反馈：[Issue Tracker]
- 邮件：[Email]
- 文档：[Documentation Site]

---

**注意**：本项目正在积极开发中，API 可能会有变动。建议在生产环境使用前进行充分测试。
