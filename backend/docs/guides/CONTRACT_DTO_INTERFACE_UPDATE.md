# ContractDTO 和 IContractService 更新文档

## 概述

本文档记录了任务 10 的实现：更新 ContractDTO 和 IContractService 接口，以支持新的律师指派机制。

## 更新内容

### 1. ContractDTO 扩展

在 `apps/core/interfaces.py` 中扩展了 `ContractDTO`，添加了以下字段：

```python
@dataclass
class ContractDTO:
    # ... 现有字段 ...
    
    # 新增字段
    primary_lawyer_id: Optional[int] = None
    primary_lawyer_name: Optional[str] = None
```

#### from_model 方法更新

更新了 `from_model` 方法，使其使用 Contract 模型的 `primary_lawyer` 属性：

```python
@classmethod
def from_model(cls, contract) -> "ContractDTO":
    # 获取主办律师（使用 primary_lawyer 属性）
    primary_lawyer = contract.primary_lawyer if hasattr(contract, 'primary_lawyer') else None
    
    return cls(
        # ... 其他字段 ...
        primary_lawyer_id=primary_lawyer.id if primary_lawyer else None,
        primary_lawyer_name=primary_lawyer.real_name if primary_lawyer and hasattr(primary_lawyer, 'real_name') else None,
        # ...
    )
```

**特性：**
- 优先使用 `ContractAssignment` 中 `is_primary=True` 的律师
- 如果没有主办律师指派，回退到 `assigned_lawyer` 字段
- 保持向后兼容性

### 2. IContractService 接口更新

在 `apps/core/interfaces.py` 中更新了 `IContractService` 接口：

#### 2.1 更新 get_contract_assigned_lawyer_id 方法

```python
def get_contract_assigned_lawyer_id(self, contract_id: int) -> Optional[int]:
    """
    获取合同的主办律师 ID（使用 primary_lawyer）
    
    Args:
        contract_id: 合同 ID
    
    Returns:
        主办律师 ID，合同不存在或无主办律师时返回 None
    """
    ...
```

**变更：**
- 方法现在返回主办律师的 ID（通过 `primary_lawyer` 属性）
- 而非直接返回 `assigned_lawyer_id`

#### 2.2 新增 get_contract_lawyers 方法

```python
def get_contract_lawyers(self, contract_id: int) -> List[LawyerDTO]:
    """
    获取合同的所有律师
    
    Args:
        contract_id: 合同 ID
    
    Returns:
        律师 DTO 列表，按 is_primary 降序、order 升序排列
    
    Raises:
        NotFoundError: 合同不存在
    """
    ...
```

**特性：**
- 返回合同的所有律师（包括主办和协办）
- 按照 `is_primary` 降序、`order` 升序排列
- 返回 `LawyerDTO` 列表

### 3. ContractServiceAdapter 实现

在 `apps/contracts/services/contract_service.py` 中更新了 `ContractServiceAdapter`：

#### 3.1 更新 get_contract_assigned_lawyer_id 实现

```python
def get_contract_assigned_lawyer_id(self, contract_id: int) -> Optional[int]:
    """获取合同的主办律师 ID（使用 primary_lawyer）"""
    try:
        contract = self.contract_service.get_contract(contract_id)
        primary_lawyer = contract.primary_lawyer
        return primary_lawyer.id if primary_lawyer else None
    except NotFoundError:
        return None
```

#### 3.2 实现 get_contract_lawyers 方法

```python
def get_contract_lawyers(self, contract_id: int) -> List["LawyerDTO"]:
    """获取合同的所有律师"""
    from apps.core.interfaces import LawyerDTO
    
    contract = self.contract_service.get_contract(contract_id)
    all_lawyers = contract.all_lawyers
    
    return [LawyerDTO.from_model(lawyer) for lawyer in all_lawyers]
```

## 向后兼容性

### 保留的字段

`ContractDTO` 仍然保留以下字段以保持向后兼容：

```python
assigned_lawyer_id: Optional[int] = None
assigned_lawyer_name: Optional[str] = None
```

这些字段继续从 `Contract.assigned_lawyer` 获取值。

### 回退机制

`primary_lawyer` 属性实现了回退机制：

1. 优先返回 `ContractAssignment` 中 `is_primary=True` 的律师
2. 如果没有主办律师指派，回退到 `assigned_lawyer` 字段
3. 如果两者都没有，返回 `None`

## 测试覆盖

创建了完整的测试套件 `tests/unit/contracts/test_contract_dto_update.py`：

### ContractDTO 测试

1. **test_contract_dto_has_primary_lawyer_fields**
   - 验证新字段存在
   - 验证回退到 `assigned_lawyer` 的逻辑

2. **test_contract_dto_primary_lawyer_with_assignment**
   - 验证使用 `ContractAssignment` 的主办律师
   - 验证 `assigned_lawyer` 字段仍然保留

3. **test_contract_dto_no_primary_lawyer**
   - 验证无主办律师时返回 `None`

### ContractServiceAdapter 测试

1. **test_get_contract_assigned_lawyer_id_uses_primary_lawyer**
   - 验证方法使用 `primary_lawyer` 而非 `assigned_lawyer`

2. **test_get_contract_lawyers**
   - 验证返回所有律师
   - 验证排序正确（主办律师在前）
   - 验证返回 `LawyerDTO` 类型

3. **test_get_contract_lawyers_empty**
   - 验证无律师指派时返回空列表

4. **test_get_contract_lawyers_not_found**
   - 验证合同不存在时抛出 `NotFoundError`

## 测试结果

所有测试通过：

```bash
$ python -m pytest tests/unit/contracts/ -x
============================== 38 passed in 9.81s ==============================
```

包括：
- 31 个现有测试（保持通过）
- 7 个新增测试（全部通过）

## 使用示例

### 获取主办律师 ID

```python
from apps.core.interfaces import ServiceLocator

contract_service = ServiceLocator.get_contract_service()

# 获取主办律师 ID（使用 primary_lawyer）
lawyer_id = contract_service.get_contract_assigned_lawyer_id(contract_id=1)
```

### 获取所有律师

```python
from apps.core.interfaces import ServiceLocator

contract_service = ServiceLocator.get_contract_service()

# 获取所有律师（按 is_primary 降序、order 升序）
lawyers = contract_service.get_contract_lawyers(contract_id=1)

for lawyer in lawyers:
    print(f"律师: {lawyer.real_name}, ID: {lawyer.id}")
```

### 使用 ContractDTO

```python
from apps.core.interfaces import ContractDTO
from apps.contracts.models import Contract

contract = Contract.objects.get(id=1)
dto = ContractDTO.from_model(contract)

# 访问主办律师信息
print(f"主办律师 ID: {dto.primary_lawyer_id}")
print(f"主办律师姓名: {dto.primary_lawyer_name}")

# 访问旧的 assigned_lawyer 信息（向后兼容）
print(f"指派律师 ID: {dto.assigned_lawyer_id}")
print(f"指派律师姓名: {dto.assigned_lawyer_name}")
```

## 相关需求

本实现满足以下需求：

- **Requirements 6.2**: 获取合同详情时返回 primary_lawyer 字段
- **Requirements 8.2**: Service 层使用 Protocol + DTO 模式

## 相关文档

- [合同律师指派重构指南](./CONTRACT_LAWYER_ASSIGNMENT_REFACTORING.md)
- [设计文档](.kiro/specs/contract-lawyer-assignment-refactoring/design.md)
- [需求文档](.kiro/specs/contract-lawyer-assignment-refactoring/requirements.md)

## 注意事项

1. **跨模块调用**：其他模块应通过 `IContractService` 接口访问合同信息，而非直接导入 `Contract` 模型

2. **DTO 转换**：始终使用 `ContractDTO.from_model()` 方法转换模型，确保所有字段正确填充

3. **主办律师逻辑**：主办律师的确定逻辑在 `Contract.primary_lawyer` 属性中实现，保持单一职责

4. **测试隔离**：测试使用 Factory 创建数据，确保测试之间相互独立

## 后续任务

- [ ] 任务 11: 更新 Admin 界面
- [ ] 任务 12: Checkpoint - 确保所有功能正确
- [ ] 任务 13: 运行迁移并验证

## 更新日期

2025-12-05
