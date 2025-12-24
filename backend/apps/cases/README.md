# 📁 案件管理模块 (Cases)

案件管理模块，提供案件的创建、查询、更新和删除功能，支持案件当事人、案件日志、案件指派等功能。

## 📚 模块概述

本模块负责管理法律案件的完整生命周期，包括：
- 案件基本信息管理
- 案件当事人管理
- 案件日志记录
- 案件指派管理
- 司法信息管理
- 案号管理

## 📁 目录结构

```
cases/
├── admin/              # Django Admin 配置
│   ├── case_admin.py           # 案件 Admin
│   ├── caseparty_admin.py      # 当事人 Admin
│   ├── caselog_admin.py        # 日志 Admin
│   ├── caseassignment_admin.py # 指派 Admin
│   ├── casenumber_admin.py     # 案号 Admin
│   └── judicialinfo_admin.py   # 司法信息 Admin
├── api/                # API 接口
│   ├── case_api.py             # 案件 API
│   ├── caseparty_api.py        # 当事人 API
│   ├── caselog_api.py          # 日志 API
│   ├── caseassignment_api.py   # 指派 API
│   ├── casenumber_api.py       # 案号 API
│   ├── caseaccess_api.py       # 访问权限 API
│   └── judicialinfo_api.py     # 司法信息 API
├── services/           # 业务逻辑
│   ├── case_service.py         # 案件服务
│   ├── case_log_service.py     # 日志服务
│   └── case_access_service.py  # 访问权限服务
├── models.py           # 数据模型
├── schemas.py          # Pydantic Schemas
├── validators.py       # 数据验证器
└── migrations/         # 数据库迁移
```

## 🚀 快速开始

### 1. Admin 后台

```bash
# 访问案件管理后台
open http://localhost:8000/admin/cases/
```

### 2. API 使用

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/cases"
headers = {"Authorization": "Bearer <your_jwt_token>"}

# 创建案件
response = requests.post(BASE_URL, json={
    "name": "张三诉李四合同纠纷案",
    "contract_id": 1,
    "current_stage": "first_trial",
    "case_type": "civil"
}, headers=headers)

case_id = response.json()["data"]["id"]

# 获取案件详情
response = requests.get(f"{BASE_URL}/{case_id}", headers=headers)
case = response.json()["data"]

# 更新案件
response = requests.put(f"{BASE_URL}/{case_id}", json={
    "current_stage": "second_trial"
}, headers=headers)

# 添加案件日志
response = requests.post(f"{BASE_URL}/{case_id}/logs", json={
    "content": "开庭审理",
    "log_type": "hearing"
}, headers=headers)
```

### 3. Service 层使用

```python
from apps.cases.services.case_service import CaseService
from apps.cases.schemas import CaseCreateSchema

service = CaseService(
    contract_service=ContractService()
)

# 创建案件
case = service.create_case(
    data=CaseCreateSchema(
        name="张三诉李四合同纠纷案",
        contract_id=1,
        current_stage="first_trial"
    ),
    user=request.user
)

# 获取案件
case = service.get_case(case_id=1, user=request.user)

# 更新案件
case = service.update_case(
    case_id=1,
    data=CaseUpdateSchema(current_stage="second_trial"),
    user=request.user
)
```

## 🔑 核心功能

### 案件管理
- ✅ 创建、查询、更新、删除案件
- ✅ 案件阶段管理（侦查、起诉、一审、二审、执行）
- ✅ 案件类型管理（民事、刑事、行政）
- ✅ 案件状态管理（进行中、已结案、已归档）

### 当事人管理
- ✅ 添加、编辑、删除当事人
- ✅ 当事人类型（原告、被告、第三人）
- ✅ 当事人身份（自然人、法人）
- ✅ 当事人联系方式管理

### 案件日志
- ✅ 记录案件重要事件
- ✅ 日志类型分类（开庭、调解、判决等）
- ✅ 日志附件管理
- ✅ 日志时间线展示

### 案件指派
- ✅ 指派律师到案件
- ✅ 指派角色管理（主办律师、协办律师）
- ✅ 指派历史记录

### 司法信息
- ✅ 法院信息管理
- ✅ 法官信息管理
- ✅ 案号管理
- ✅ 开庭时间管理

## 📊 数据模型

### Case (案件)
- `name`: 案件名称
- `contract`: 关联合同
- `current_stage`: 当前阶段
- `case_type`: 案件类型
- `status`: 案件状态
- `created_by`: 创建人

### CaseParty (当事人)
- `case`: 关联案件
- `client`: 关联客户
- `party_type`: 当事人类型（原告/被告/第三人）
- `legal_status`: 法律地位（自然人/法人）

### CaseLog (案件日志)
- `case`: 关联案件
- `content`: 日志内容
- `log_type`: 日志类型
- `created_by`: 创建人
- `created_at`: 创建时间

### CaseAssignment (案件指派)
- `case`: 关联案件
- `lawyer`: 指派律师
- `assigned_by`: 指派人
- `assigned_at`: 指派时间

### JudicialInfo (司法信息)
- `case`: 关联案件
- `court_name`: 法院名称
- `judge_name`: 法官姓名
- `hearing_date`: 开庭日期

### CaseNumber (案号)
- `case`: 关联案件
- `number`: 案号
- `court_level`: 法院级别
- `year`: 年份

## 🔒 权限控制

### 功能级别权限
- `cases.add_case`: 创建案件
- `cases.view_case`: 查看案件
- `cases.change_case`: 修改案件
- `cases.delete_case`: 删除案件

### 对象级别权限
- 案件创建人可以查看和修改自己的案件
- 被指派的律师可以查看和修改案件
- 管理员可以查看和修改所有案件

## 🧪 测试

```bash
# 运行单元测试
cd backend
source venv311/bin/activate
python -m pytest tests/unit/test_cases/ -v

# 运行集成测试
python -m pytest tests/integration/test_case_api/ -v

# 运行属性测试
python -m pytest tests/property/test_case_properties/ -v
```

## 📝 相关文档

- **[SUPERVISING_AUTHORITY_FEATURE.md](SUPERVISING_AUTHORITY_FEATURE.md)** - 监管机关功能说明
- **[models.py](models.py)** - 数据模型定义
- **[schemas.py](schemas.py)** - API Schema 定义
- **[validators.py](validators.py)** - 数据验证器

## 🔗 依赖模块

- **contracts**: 合同模块（案件关联合同）
- **client**: 客户模块（当事人关联客户）
- **organization**: 组织模块（律师、律所）
- **core**: 核心模块（异常、接口、验证器）

## 🎯 最佳实践

### 1. 使用 Service 层
```python
# ✅ 正确：使用 Service 层
service = CaseService(contract_service=ContractService())
case = service.create_case(data, user)

# ❌ 错误：直接操作 Model
case = Case.objects.create(name="案件", contract_id=1)
```

### 2. 权限检查
```python
# ✅ 正确：在 Service 层检查权限
def get_case(self, case_id, user):
    case = Case.objects.get(id=case_id)
    if not self._can_access_case(user, case):
        raise PermissionDenied("无权限访问该案件")
    return case
```

### 3. 使用 Schema 验证
```python
# ✅ 正确：使用 Pydantic Schema
data = CaseCreateSchema(
    name="案件名称",
    contract_id=1,
    current_stage="first_trial"
)
case = service.create_case(data, user)
```

### 4. 记录案件日志
```python
# ✅ 正确：重要操作记录日志
case_log_service.create_log(
    case_id=case.id,
    content="案件已创建",
    log_type="system",
    user=user
)
```

## 🐛 常见问题

### Q1: 如何添加新的案件阶段？
**A**: 在 `models.py` 的 `CASE_STAGES` 中添加新阶段，然后运行迁移。

### Q2: 如何实现案件搜索？
**A**: 使用 `CaseService.list_cases()` 方法，传递搜索参数。

### Q3: 如何导出案件数据？
**A**: 使用 Django Admin 的导出功能，或调用 API 获取数据后处理。

## 📈 性能优化

- ✅ 使用 `select_related` 预加载关联对象
- ✅ 使用 `prefetch_related` 预加载多对多关系
- ✅ 使用索引优化查询（案件名称、案号、状态）
- ✅ 使用缓存减少数据库查询

## 🔄 版本历史

- **v1.0.0** (2024-01): 初始版本
- **v1.1.0** (2024-03): 添加司法信息管理
- **v1.2.0** (2024-06): 添加案号管理
- **v1.3.0** (2024-09): 添加监管机关功能
