# Contracts 模块类型错误分析

## 总体统计

- **总错误数**: 214 个
- **扫描时间**: 2024
- **模块**: apps/contracts/

## 错误类型分布

### 1. Django ORM 动态属性错误 (attr-defined) - 约 60 个

**问题**: Contract 模型的动态属性（如 id, contract_parties, assignments 等）导致类型检查失败

**示例**:
```python
# apps/contracts/services/contract_admin_service.py:48
for party in original.contract_parties.all():  # ❌ "Contract" has no attribute "contract_parties"

# apps/contracts/services/contract_admin_service.py:140
"contract_id": contract.id,  # ❌ "Contract" has no attribute "id"
```

**修复策略**: 使用 contracts/models.pyi 类型存根文件

### 2. 函数缺少类型注解 (no-untyped-def) - 约 40 个

**问题**: API 函数和服务方法缺少参数或返回类型注解

**示例**:
```python
# apps/contracts/api/contract_api.py:41
def list_contracts(request, case_type: Optional[str] = None, ...):  # ❌ 缺少返回类型和 request 类型

# apps/contracts/api/supplementary_agreement_api.py:28
def create_supplementary_agreement(request, payload: ...):  # ❌ 缺少返回类型和 request 类型
```

**修复策略**: 添加 `-> HttpResponse` 返回类型，添加 `request: HttpRequest` 参数类型

### 3. 泛型类型参数缺失 (type-arg) - 约 30 个

**问题**: QuerySet, dict, list 等泛型类型缺少类型参数

**示例**:
```python
# apps/contracts/services/contract_reminder_service.py:33
def get_reminders(self) -> QuerySet:  # ❌ 缺少泛型参数

# apps/contracts/api/contract_api.py:80
cases: Optional[list[dict]] = None  # ❌ dict 缺少类型参数

# apps/contracts/services/contract/contract_admin_service.py:144
org_access: dict | None = None  # ❌ dict 缺少类型参数
```

**修复策略**: 
- `QuerySet` → `QuerySet[ContractReminder]`
- `list[dict]` → `list[dict[str, Any]]`
- `dict` → `dict[str, Any]`

### 4. 返回 Any 类型 (no-any-return) - 约 25 个

**问题**: 函数声明返回具体类型，但实际返回 Any

**示例**:
```python
# apps/contracts/services/contract_service.py:206
def get_contract(self, contract_id: int) -> Contract:
    return self.query_facade.get_contract(contract_id)  # ❌ 返回 Any

# apps/contracts/services/contract_service.py:1020
def to_dto(self, contract: Contract) -> ContractDTO:
    return self._assemble_dto(contract)  # ❌ 返回 Any
```

**修复策略**: 使用 `cast()` 或修复被调用函数的返回类型

### 5. 方法签名不匹配 (signature mismatch) - 约 15 个

**问题**: 子类方法签名与父类不一致

**示例**:
```python
# apps/contracts/services/folder/folder_binding_service.py:72
# 父类: def create_binding(self, *, owner_id: int, folder_path: str, **kwargs: Any) -> Any
# 子类: def create_binding(self, contract_id: int, folder_path: str) -> Any
# ❌ 签名不匹配
```

**修复策略**: 调整子类方法签名以匹配父类，或使用 `**kwargs` 接收额外参数

### 6. 未定义的名称 (name-defined) - 约 15 个

**问题**: 使用了未导入或未定义的类型/变量

**示例**:
```python
# apps/contracts/services/contract_service.py:39
def __init__(self, ..., case_service: ICaseService | None = None):  # ❌ ICaseService 未定义

# apps/contracts/services/contract_service.py:963
def to_dto(self, contract: Contract) -> ContractDTO:  # ❌ ContractDTO 未定义
```

**修复策略**: 添加正确的导入语句

### 7. 抽象类实例化 (abstract) - 约 5 个

**问题**: 尝试实例化抽象类

**示例**:
```python
# apps/contracts/api/supplementary_agreement_api.py:23
client_service=ClientServiceAdapter()  # ❌ 抽象类不能实例化
```

**修复策略**: 使用具体实现类或修复抽象方法

### 8. 参数类型不兼容 (arg-type) - 约 15 个

**问题**: 传递的参数类型与期望类型不匹配

**示例**:
```python
# apps/contracts/api/contract_api.py:148
confirm_finance=confirm_finance,  # ❌ bool | None 传递给 bool 参数

# apps/contracts/api/contract_api.py:34
case_service=case_service,  # ❌ CaseServiceAdapter 传递给 ICaseService | None
```

**修复策略**: 添加类型检查或调整参数类型

### 9. 其他错误 - 约 9 个

包括：
- 缺少 self 参数 (misc)
- 列表推导式类型错误
- 类型注解需要显式声明 (var-annotated)

## 按文件分类的主要错误

### API 层 (apps/contracts/api/)

1. **contract_api.py** - 约 30 个错误
   - 所有 API 函数缺少类型注解
   - 抽象类实例化问题
   - 参数类型不兼容

2. **supplementary_agreement_api.py** - 约 12 个错误
   - 所有 API 函数缺少类型注解
   - 抽象类实例化问题

3. **contractfinance_api.py** - 约 2 个错误
   - 函数缺少类型注解

4. **folder_binding_api.py** - 1 个错误
   - 模块导入错误

### 服务层 (apps/contracts/services/)

1. **contract_service.py** - 约 35 个错误
   - Django ORM 动态属性
   - 未定义的类型名称
   - 返回 Any 类型

2. **contract_admin_service.py** - 约 10 个错误
   - Django ORM 动态属性
   - 缺少 self 参数

3. **contract/contract_query_service.py** - 约 8 个错误
   - QuerySet 泛型参数缺失
   - 返回 Any 类型

4. **contract/contract_display_service.py** - 约 8 个错误
   - 缺少 self 参数
   - 类型注解需要显式声明

5. **folder/folder_binding_service.py** - 约 6 个错误
   - 方法签名不匹配

6. **payment/contract_payment_service.py** - 约 15 个错误
   - QuerySet 泛型参数缺失
   - Django ORM 动态属性

### Schema 层 (apps/contracts/schemas/)

1. **contract_schemas.py** - 约 10 个错误
   - Django ORM 动态属性
   - 列表推导式类型错误
   - 泛型类型参数缺失

## 修复优先级

### 高优先级（快速修复）

1. **泛型类型参数缺失** - 可批量修复
   - `QuerySet` → `QuerySet[Model]`
   - `dict` → `dict[str, Any]`
   - `list[dict]` → `list[dict[str, Any]]`

2. **API 函数类型注解** - 可批量修复
   - 添加 `request: HttpRequest` 参数类型
   - 添加 `-> HttpResponse` 返回类型

### 中优先级（需要类型存根）

3. **Django ORM 动态属性** - 使用 models.pyi
   - Contract.id
   - Contract.contract_parties
   - Contract.assignments
   - Contract.reminders
   - Contract.supplementary_agreements

### 低优先级（需要手动修复）

4. **方法签名不匹配** - 需要重构
5. **抽象类实例化** - 需要使用具体实现
6. **未定义的名称** - 需要添加导入

## 预计修复时间

- 批量修复（泛型类型、API 注解）: 1-2 小时
- Django ORM 类型存根: 1 小时
- 手动修复复杂错误: 2-3 小时
- 验证和测试: 1 小时

**总计**: 5-7 小时
