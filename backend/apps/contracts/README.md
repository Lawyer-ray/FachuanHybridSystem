# 📄 合同管理模块 (Contracts)

合同管理模块，提供合同的创建、查询、更新和删除功能，支持合同支付、财务日志、合同提醒等功能。

## 📚 模块概述

本模块负责管理法律服务合同的完整生命周期，包括：
- 合同基本信息管理
- 合同支付管理
- 合同财务日志
- 合同提醒管理
- 合同状态管理

## 📁 目录结构

```
contracts/
├── admin/              # Django Admin 配置
│   ├── contract_admin.py           # 合同 Admin
│   ├── contractpayment_admin.py    # 支付 Admin
│   ├── contractfinancelog_admin.py # 财务日志 Admin
│   └── contractreminder_admin.py   # 提醒 Admin
├── api/                # API 接口
│   ├── contract_api.py             # 合同 API
│   ├── contractpayment_api.py      # 支付 API
│   ├── contractfinance_api.py      # 财务 API
│   └── contractreminder_api.py     # 提醒 API
├── services/           # 业务逻辑
│   ├── contract_service.py         # 合同服务
│   └── payment_service.py          # 支付服务
├── models.py           # 数据模型
├── schemas.py          # Pydantic Schemas
└── migrations/         # 数据库迁移
```

## 🚀 快速开始

### 1. Admin 后台

```bash
# 访问合同管理后台
open http://localhost:8000/admin/contracts/
```

### 2. API 使用

```python
import requests
from decimal import Decimal

BASE_URL = "http://localhost:8000/api/v1/contracts"
headers = {"Authorization": "Bearer <your_jwt_token>"}

# 创建合同
response = requests.post(BASE_URL, json={
    "name": "法律服务合同",
    "client_id": 1,
    "law_firm_id": 1,
    "assigned_lawyer_id": 1,
    "case_type": "civil",
    "fee_mode": "fixed",
    "fixed_amount": "50000.00",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "status": "active"
}, headers=headers)

contract_id = response.json()["data"]["id"]

# 获取合同详情
response = requests.get(f"{BASE_URL}/{contract_id}", headers=headers)
contract = response.json()["data"]

# 更新合同
response = requests.put(f"{BASE_URL}/{contract_id}", json={
    "status": "completed"
}, headers=headers)

# 添加支付记录
response = requests.post(f"{BASE_URL}/{contract_id}/payments", json={
    "amount": "10000.00",
    "payment_date": "2024-01-15",
    "payment_method": "bank_transfer",
    "notes": "首付款"
}, headers=headers)
```

### 3. Service 层使用

```python
from apps.contracts.services.contract_service import ContractService
from apps.contracts.schemas import ContractCreateSchema
from decimal import Decimal

service = ContractService(
    client_service=ClientService(),
    lawyer_service=LawyerService()
)

# 创建合同
contract = service.create_contract(
    data=ContractCreateSchema(
        name="法律服务合同",
        client_id=1,
        law_firm_id=1,
        assigned_lawyer_id=1,
        case_type="civil",
        fee_mode="fixed",
        fixed_amount=Decimal("50000.00")
    ),
    user=request.user
)

# 获取合同
contract = service.get_contract(contract_id=1, user=request.user)

# 添加支付
payment_service = PaymentService()
payment = payment_service.create_payment(
    contract_id=1,
    amount=Decimal("10000.00"),
    payment_date="2024-01-15",
    user=request.user
)
```

## 🔑 核心功能

### 合同管理
- ✅ 创建、查询、更新、删除合同
- ✅ 合同状态管理（草稿、生效、完成、终止）
- ✅ 合同类型管理（民事、刑事、行政）
- ✅ 收费模式管理（固定费用、风险代理、计时收费）
- ✅ 合同期限管理
- ✅ 合同当事人管理

### 支付管理
- ✅ 添加、编辑、删除支付记录
- ✅ 支付方式管理（银行转账、现金、支票等）
- ✅ 支付日期管理
- ✅ 支付备注
- ✅ 支付统计

### 财务日志
- ✅ 自动记录财务变动
- ✅ 日志类型（收款、退款、调整）
- ✅ 日志金额和余额
- ✅ 日志时间线

### 合同提醒
- ✅ 合同到期提醒
- ✅ 支付提醒
- ✅ 自定义提醒
- ✅ 提醒状态管理

## 📊 数据模型

### Contract (合同)
- `name`: 合同名称
- `client`: 关联客户
- `law_firm`: 关联律所
- `assigned_lawyer`: 指派律师
- `case_type`: 案件类型
- `fee_mode`: 收费模式
- `fixed_amount`: 固定金额
- `start_date`: 开始日期
- `end_date`: 结束日期
- `status`: 合同状态
- `created_by`: 创建人

### ContractPayment (合同支付)
- `contract`: 关联合同
- `amount`: 支付金额
- `payment_date`: 支付日期
- `payment_method`: 支付方式
- `notes`: 备注
- `created_by`: 创建人

### ContractFinanceLog (财务日志)
- `contract`: 关联合同
- `log_type`: 日志类型
- `amount`: 金额
- `balance`: 余额
- `notes`: 备注
- `created_at`: 创建时间

### ContractReminder (合同提醒)
- `contract`: 关联合同
- `reminder_type`: 提醒类型
- `reminder_date`: 提醒日期
- `content`: 提醒内容
- `is_sent`: 是否已发送
- `created_by`: 创建人

## 🔒 权限控制

### 功能级别权限
- `contracts.add_contract`: 创建合同
- `contracts.view_contract`: 查看合同
- `contracts.change_contract`: 修改合同
- `contracts.delete_contract`: 删除合同

### 对象级别权限
- 合同创建人可以查看和修改自己的合同
- 指派律师可以查看和修改合同
- 管理员可以查看和修改所有合同

## 🧪 测试

```bash
# 运行单元测试
cd backend
source venv311/bin/activate
python -m pytest tests/unit/test_contracts/ -v

# 运行集成测试
python -m pytest tests/integration/test_contract_api/ -v

# 运行属性测试
python -m pytest tests/property/test_contract_properties/ -v
```

## 📝 相关文档

- **[models.py](models.py)** - 数据模型定义
- **[schemas.py](schemas.py)** - API Schema 定义
- **[services/contract_service.py](services/contract_service.py)** - 合同服务
- **[services/payment_service.py](services/payment_service.py)** - 支付服务

## 🔗 依赖模块

- **client**: 客户模块（合同关联客户）
- **organization**: 组织模块（律所、律师）
- **cases**: 案件模块（案件关联合同）
- **core**: 核心模块（异常、接口、验证器）

## 🎯 最佳实践

### 1. 使用 Service 层
```python
# ✅ 正确：使用 Service 层
service = ContractService(
    client_service=ClientService(),
    lawyer_service=LawyerService()
)
contract = service.create_contract(data, user)

# ❌ 错误：直接操作 Model
contract = Contract.objects.create(name="合同", client_id=1)
```

### 2. 使用事务管理
```python
# ✅ 正确：使用事务确保数据一致性
from django.db import transaction

@transaction.atomic
def create_contract_with_payment(contract_data, payment_data, user):
    contract = contract_service.create_contract(contract_data, user)
    payment = payment_service.create_payment(
        contract.id, payment_data, user
    )
    return contract, payment
```

### 3. 计算合同余额
```python
# ✅ 正确：使用 Service 层计算
balance = contract_service.get_contract_balance(contract_id)

# ❌ 错误：手动计算
total_paid = sum(p.amount for p in contract.payments.all())
balance = contract.fixed_amount - total_paid
```

### 4. 发送合同提醒
```python
# ✅ 正确：使用提醒服务
from apps.contracts.services.reminder_service import ReminderService

reminder_service = ReminderService()
reminder_service.send_contract_expiry_reminders()
```

## 🐛 常见问题

### Q1: 如何处理风险代理合同？
**A**: 设置 `fee_mode="risk_agency"`，并设置 `risk_ratio` 字段。

### Q2: 如何计算合同已支付金额？
**A**: 使用 `contract_service.get_total_paid(contract_id)` 方法。

### Q3: 如何导出合同数据？
**A**: 使用 Django Admin 的导出功能，或调用 API 获取数据后处理。

## 📈 性能优化

- ✅ 使用 `select_related` 预加载关联对象
- ✅ 使用 `prefetch_related` 预加载支付记录
- ✅ 使用 `annotate` 计算聚合数据
- ✅ 使用索引优化查询（合同名称、状态、日期）
- ✅ 使用缓存减少数据库查询

## 💰 财务统计

```python
# 获取合同财务统计
from django.db.models import Sum, Count

stats = Contract.objects.aggregate(
    total_contracts=Count('id'),
    total_amount=Sum('fixed_amount'),
    total_paid=Sum('payments__amount')
)

print(f"合同总数: {stats['total_contracts']}")
print(f"合同总金额: {stats['total_amount']}")
print(f"已收款总额: {stats['total_paid']}")
```

## 🔄 版本历史

- **v1.0.0** (2024-01): 初始版本
- **v1.1.0** (2024-03): 添加支付管理
- **v1.2.0** (2024-06): 添加财务日志
- **v1.3.0** (2024-09): 添加合同提醒
