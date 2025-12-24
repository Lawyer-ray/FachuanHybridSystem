# 文件组织规范

本文档定义了项目的文件组织规范，确保所有开发者遵循统一的文件结构和命名约定。

## 📋 目录

- [总体原则](#总体原则)
- [Django App 结构](#django-app-结构)
- [测试文件组织](#测试文件组织)
- [文档文件组织](#文档文件组织)
- [脚本文件组织](#脚本文件组织)
- [命名规范](#命名规范)
- [最佳实践](#最佳实践)

## 🎯 总体原则

### 核心原则

1. **一致性**：所有模块遵循相同的目录结构
2. **可预测性**：文件位置清晰可预测
3. **职责单一**：每个文件职责明确
4. **易于维护**：结构清晰便于维护

### 目录层级

```
backend/
├── apiSystem/          # Django 项目配置（1 级）
├── apps/               # 应用模块（1 级）
│   └── [app_name]/     # 具体应用（2 级）
│       ├── admin/      # Admin 配置（3 级）
│       ├── api/        # API 路由（3 级）
│       └── services/   # 业务逻辑（3 级）
├── tests/              # 测试目录（1 级）
│   ├── unit/           # 单元测试（2 级）
│   ├── integration/    # 集成测试（2 级）
│   └── property/       # Property tests（2 级）
├── scripts/            # 脚本目录（1 级）
│   ├── testing/        # 测试脚本（2 级）
│   ├── development/    # 开发工具（2 级）
│   └── automation/     # 自动化脚本（2 级）
└── docs/               # 文档目录（1 级）
    ├── api/            # API 文档（2 级）
    ├── architecture/   # 架构文档（2 级）
    └── guides/         # 开发指南（2 级）
```

## 🏗️ Django App 结构

### 标准结构

每个 Django app 必须遵循以下结构：

```
apps/[app_name]/
├── __init__.py              # 包初始化
├── models.py                # 数据模型
├── schemas.py               # Pydantic schemas
├── apps.py                  # App 配置
├── admin/                   # Admin 配置目录
│   ├── __init__.py         # 导出所有 Admin 类
│   ├── [model]_admin.py    # 按模型分文件
│   └── ...
├── api/                     # API 路由目录
│   ├── __init__.py         # 导出所有路由
│   ├── [resource]_api.py   # 按资源分文件
│   └── ...
├── services/                # 业务逻辑目录
│   ├── __init__.py         # 导出所有 Service
│   ├── [domain]_service.py # 按领域分文件
│   └── ...
├── migrations/              # 数据库迁移
│   ├── __init__.py
│   └── 0001_initial.py
└── README.md                # 模块文档
```

### Admin 目录

**规则**：

1. **按模型分文件**：每个模型一个 admin 文件
2. **命名规范**：`[model_name]_admin.py`（小写，下划线分隔）
3. **导出规范**：在 `__init__.py` 中导出所有 Admin 类

**示例**：

```python
# apps/cases/admin/__init__.py
from .case_admin import CaseAdmin
from .caseparty_admin import CasePartyAdmin
from .caselog_admin import CaseLogAdmin

__all__ = [
    'CaseAdmin',
    'CasePartyAdmin',
    'CaseLogAdmin',
]

# apps/cases/admin/case_admin.py
from django.contrib import admin
from apps.cases.models import Case

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'created_at']
    list_filter = ['status', 'current_stage']
    search_fields = ['name', 'contract__name']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'contract', 'current_stage')
        }),
        ('状态信息', {
            'fields': ('status', 'is_archived')
        }),
    )
```

### API 目录

**规则**：

1. **按资源分文件**：每个资源一个 api 文件
2. **命名规范**：`[resource_name]_api.py`（小写，下划线分隔）
3. **导出规范**：在 `__init__.py` 中导出所有路由

**示例**：

```python
# apps/cases/api/__init__.py
from .case_api import router as case_router
from .caseparty_api import router as caseparty_router
from .caselog_api import router as caselog_router

__all__ = [
    'case_router',
    'caseparty_router',
    'caselog_router',
]

# apps/cases/api/case_api.py
from ninja import Router
from ninja_jwt.authentication import JWTAuth
from apps.cases.services import CaseService
from apps.cases.schemas import CaseSchema, CaseCreateSchema

router = Router(tags=["Cases"], auth=JWTAuth())

@router.get("/", response=list[CaseSchema])
def list_cases(request, page: int = 1, page_size: int = 20):
    """列表查询"""
    service = CaseService()
    cases = service.list_cases(page, page_size, {}, request.auth)
    return [CaseSchema.from_orm(c) for c in cases]

@router.post("/", response=CaseSchema)
def create_case(request, data: CaseCreateSchema):
    """创建案件"""
    service = CaseService()
    case = service.create_case(data, request.auth)
    return CaseSchema.from_orm(case)
```

### Services 目录

**规则**：

1. **按领域分文件**：每个业务领域一个 service 文件
2. **命名规范**：`[domain]_service.py`（小写，下划线分隔）
3. **导出规范**：在 `__init__.py` 中导出所有 Service 类

**示例**：

```python
# apps/cases/services/__init__.py
from .case_service import CaseService
from .case_log_service import CaseLogService
from .case_access_service import CaseAccessService

__all__ = [
    'CaseService',
    'CaseLogService',
    'CaseAccessService',
]

# apps/cases/services/case_service.py
from typing import Optional
from django.db import transaction
from apps.core.exceptions import ValidationException, PermissionDenied
from apps.core.interfaces import IContractService

class CaseService:
    """案件服务"""
    
    def __init__(self, contract_service: Optional[IContractService] = None):
        """依赖注入"""
        self.contract_service = contract_service or ContractService()
    
    @transaction.atomic
    def create_case(self, data: CaseCreateSchema, user: User) -> Case:
        """创建案件"""
        # 权限检查
        if not user.has_perm('cases.add_case'):
            raise PermissionDenied("无权限创建案件")
        
        # 业务逻辑
        case = Case.objects.create(
            name=data.name,
            contract_id=data.contract_id,
            created_by=user
        )
        
        return case
```

### 模块文档

每个 app 必须包含 `README.md` 文档：

```markdown
# [App Name] 模块

## 概述

简要描述模块的功能和职责。

## 模型

### [Model Name]

- **用途**：模型用途说明
- **关键字段**：
  - `field1`: 字段说明
  - `field2`: 字段说明

## API 端点

### 列表查询
- **路径**：`GET /api/v1/[resource]`
- **权限**：需要认证
- **参数**：page, page_size

### 创建
- **路径**：`POST /api/v1/[resource]`
- **权限**：需要 add_[resource] 权限
- **请求体**：[Schema]

## 业务逻辑

### [Service Name]

- **职责**：Service 职责说明
- **依赖**：依赖的其他 Service

## 测试

- 单元测试：`tests/unit/test_[app]/`
- 集成测试：`tests/integration/test_[app]_api/`
- Property tests：`tests/property/test_[app]_properties/`

## 注意事项

- 特殊说明
- 已知问题
- 待办事项
```

## 🧪 测试文件组织

### 测试目录结构

```
tests/
├── conftest.py              # pytest 配置和 fixtures
├── README.md                # 测试文档
├── unit/                    # 单元测试
│   ├── test_cases/
│   │   ├── test_case_service.py
│   │   └── test_case_log_service.py
│   ├── test_contracts/
│   └── test_client/
├── integration/             # 集成测试
│   ├── test_case_api/
│   │   ├── test_case_crud.py
│   │   └── test_case_permissions.py
│   ├── test_contract_api/
│   └── test_client_api/
├── property/                # Property-based tests
│   ├── test_case_properties/
│   │   └── test_case_service_properties.py
│   ├── test_contract_properties/
│   └── test_client_properties/
├── admin/                   # Admin 测试
│   ├── test_form_validation.py
│   └── test_validation_detection.py
├── factories/               # Test factories
│   ├── __init__.py
│   ├── case_factories.py
│   ├── contract_factories.py
│   └── common.py
├── mocks/                   # Mock objects
│   ├── __init__.py
│   └── service_mocks.py
└── structure/               # 结构验证测试
    ├── test_app_structure_properties.py
    └── test_root_directory_properties.py
```

### 测试文件命名

**规则**：

1. **单元测试**：`test_[module]_[class].py`
2. **集成测试**：`test_[resource]_[operation].py`
3. **Property tests**：`test_[module]_properties.py`
4. **Factories**：`[module]_factories.py`

**示例**：

```python
# tests/unit/test_cases/test_case_service.py
import pytest
from apps.cases.services import CaseService

@pytest.mark.django_db
class TestCaseService:
    def test_create_case_success(self):
        """测试创建案件成功"""
        pass

# tests/integration/test_case_api/test_case_crud.py
import pytest

@pytest.mark.django_db
class TestCaseCRUD:
    def test_create_case_api(self, client, auth_headers):
        """测试创建案件 API"""
        pass

# tests/property/test_case_properties/test_case_service_properties.py
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=200))
@pytest.mark.django_db
def test_case_name_length_property(name):
    """
    Property: 案件名称长度应该在 1-200 之间
    
    Feature: backend-structure-optimization, Property 2: 测试文件集中性
    Validates: Requirements 2.1, 2.2
    """
    pass
```

### Factories 组织

```python
# tests/factories/__init__.py
from .case_factories import CaseFactory, CasePartyFactory
from .contract_factories import ContractFactory
from .client_factories import ClientFactory
from .organization_factories import LawyerFactory, LawFirmFactory

__all__ = [
    'CaseFactory',
    'CasePartyFactory',
    'ContractFactory',
    'ClientFactory',
    'LawyerFactory',
    'LawFirmFactory',
]

# tests/factories/case_factories.py
import factory
from apps.cases.models import Case, CaseParty

class CaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Case
    
    name = factory.Faker('sentence', nb_words=4)
    contract = factory.SubFactory('tests.factories.ContractFactory')
    created_by = factory.SubFactory('tests.factories.UserFactory')
```

## 📚 文档文件组织

### 文档目录结构

```
docs/
├── README.md                # 文档索引
├── api/                     # API 文档
│   └── API.md
├── architecture/            # 架构文档
│   ├── ARCHITECTURE_TRAINING.md
│   ├── REFACTORING_BEST_PRACTICES.md
│   └── adr/                # Architecture Decision Records
│       ├── 001-three-layer-architecture.md
│       ├── 002-dependency-injection.md
│       └── ...
├── guides/                  # 开发指南
│   ├── QUICK_START.md
│   ├── CODE_REVIEW_CHECKLIST.md
│   ├── CODE_REVIEW_PROCESS.md
│   ├── TEAM_KNOWLEDGE_SHARING.md
│   ├── MIGRATION_GUIDE.md
│   └── FILE_ORGANIZATION.md
├── operations/              # 运维文档
│   ├── DATA_RECOVERY_GUIDE.md
│   └── PERFORMANCE_MONITORING_IMPLEMENTATION.md
└── quality/                 # 质量文档
    └── CODE_QUALITY_REVIEW.md
```

### 文档分类规则

| 文档类型 | 存放位置 | 示例 |
|---------|---------|------|
| API 规范 | `docs/api/` | API.md |
| 架构设计 | `docs/architecture/` | ARCHITECTURE_TRAINING.md |
| 设计决策 | `docs/architecture/adr/` | 001-three-layer-architecture.md |
| 开发指南 | `docs/guides/` | QUICK_START.md |
| 运维文档 | `docs/operations/` | DATA_RECOVERY_GUIDE.md |
| 质量文档 | `docs/quality/` | CODE_QUALITY_REVIEW.md |
| 模块文档 | `apps/[app]/README.md` | apps/cases/README.md |

### ADR 命名规范

Architecture Decision Records 使用以下命名格式：

```
[序号]-[简短描述].md

示例：
001-three-layer-architecture.md
002-dependency-injection.md
003-protocol-interface.md
```

## 🔧 脚本文件组织

### 脚本目录结构

```
scripts/
├── README.md                # 脚本使用说明
├── testing/                 # 测试相关脚本
│   ├── run_admin_tests.py
│   ├── verify_migration.py
│   └── ...
├── development/             # 开发工具脚本
│   ├── check_admin_config.py
│   ├── analyze_performance.py
│   └── ...
├── automation/              # 自动化脚本
│   ├── court_captcha_userscript.js
│   └── ...
└── refactoring/             # 重构工具
    ├── migrate_structure.py
    ├── update_imports.py
    └── ...
```

### 脚本分类规则

| 脚本类型 | 存放位置 | 示例 |
|---------|---------|------|
| 测试脚本 | `scripts/testing/` | run_admin_tests.py |
| 开发工具 | `scripts/development/` | check_admin_config.py |
| 自动化脚本 | `scripts/automation/` | court_captcha_userscript.js |
| 重构工具 | `scripts/refactoring/` | migrate_structure.py |

### 脚本文档规范

每个脚本必须包含文档字符串：

```python
"""
脚本名称和简短描述

详细说明：
- 功能描述
- 使用场景
- 注意事项

使用方法：
    python scripts/category/script_name.py [options]

示例：
    # 基本用法
    python scripts/category/script_name.py
    
    # 带参数
    python scripts/category/script_name.py --option value

参数：
    --option: 参数说明
    --help: 显示帮助信息

作者：开发者名称
日期：2024-01
"""
```

## 📝 命名规范

### 文件命名

| 文件类型 | 命名规范 | 示例 |
|---------|---------|------|
| Python 模块 | 小写+下划线 | `case_service.py` |
| Admin 文件 | `[model]_admin.py` | `case_admin.py` |
| API 文件 | `[resource]_api.py` | `case_api.py` |
| Service 文件 | `[domain]_service.py` | `case_service.py` |
| 测试文件 | `test_[module].py` | `test_case_service.py` |
| Factory 文件 | `[module]_factories.py` | `case_factories.py` |
| 文档文件 | 大写+下划线 | `QUICK_START.md` |
| ADR 文件 | `[序号]-[描述].md` | `001-architecture.md` |

### 目录命名

| 目录类型 | 命名规范 | 示例 |
|---------|---------|------|
| App 目录 | 小写+下划线 | `cases`, `contracts` |
| 功能目录 | 小写 | `admin`, `api`, `services` |
| 测试目录 | 小写 | `unit`, `integration`, `property` |
| 文档目录 | 小写 | `api`, `architecture`, `guides` |
| 脚本目录 | 小写 | `testing`, `development` |

### 类命名

| 类类型 | 命名规范 | 示例 |
|--------|---------|------|
| Model | PascalCase | `Case`, `Contract` |
| Service | PascalCase + Service | `CaseService` |
| Admin | PascalCase + Admin | `CaseAdmin` |
| Schema | PascalCase + Schema | `CaseCreateSchema` |
| Factory | PascalCase + Factory | `CaseFactory` |
| Test 类 | Test + PascalCase | `TestCaseService` |

## ✅ 最佳实践

### 1. 保持一致性

- 所有模块遵循相同的结构
- 使用统一的命名规范
- 遵循相同的代码风格

### 2. 职责单一

- 每个文件只负责一个功能
- Admin 文件只包含一个 Model 的配置
- API 文件只包含一个资源的路由
- Service 文件只包含一个领域的逻辑

### 3. 易于查找

- 文件位置可预测
- 命名清晰表达用途
- 目录结构清晰

### 4. 便于维护

- 文件大小适中（< 500 行）
- 复杂逻辑拆分为多个文件
- 提供清晰的文档

### 5. 避免反模式

❌ **不要做**：
- 在 app 根目录放置 `admin.py`, `api.py`, `tests.py`
- 在根目录散落文档文件
- 在 `scripts/` 根目录放置脚本
- 混合不同类型的测试文件

✅ **应该做**：
- 使用子目录组织文件
- 按类型分类文档
- 按功能分类脚本
- 按类型组织测试

## 📋 检查清单

在提交代码前，检查以下项目：

### 文件组织

- [ ] 文件放在正确的目录
- [ ] 文件命名符合规范
- [ ] 目录结构符合标准

### 导入导出

- [ ] `__init__.py` 正确导出
- [ ] 导入路径正确
- [ ] 没有循环导入

### 文档

- [ ] 模块有 README.md
- [ ] 脚本有文档字符串
- [ ] 复杂逻辑有注释

### 测试

- [ ] 测试文件在正确位置
- [ ] 测试命名符合规范
- [ ] Factories 正确组织

## 📞 获取帮助

如有文件组织相关问题：

- 查看本文档
- 参考现有模块
- 咨询技术负责人

---

**最后更新**：2024-01

**维护者**：开发团队

**版本**：1.0
