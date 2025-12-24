# 合同与补充协议集成指南

## 概述

合同 API 现在支持在创建和更新合同时同时管理补充协议，无需单独调用补充协议 API。

## 功能特性

### 1. 创建合同时添加补充协议

在创建合同时，可以通过 `supplementary_agreements` 字段同时创建多个补充协议。

**API 端点**: `POST /api/v1/contracts/contracts`

**请求示例**:
```json
{
  "name": "测试合同",
  "case_type": "civil",
  "assigned_lawyer_id": 1,
  "supplementary_agreements": [
    {
      "name": "补充协议1",
      "party_ids": [1, 2]
    },
    {
      "name": "补充协议2",
      "party_ids": [3]
    }
  ]
}
```

### 2. 更新合同时替换补充协议

在更新合同时，可以通过 `supplementary_agreements` 字段完全替换现有的补充协议。

**API 端点**: `PUT /api/v1/contracts/contracts/{contract_id}`

**请求示例**:
```json
{
  "name": "更新后的合同名称",
  "supplementary_agreements": [
    {
      "name": "新补充协议1",
      "party_ids": [1]
    },
    {
      "name": "新补充协议2",
      "party_ids": [2, 3]
    }
  ]
}
```

**注意**: 
- 提供 `supplementary_agreements` 字段会**完全替换**现有的所有补充协议
- 如果不提供该字段（或设为 `null`），则不会修改现有的补充协议
- 如果提供空数组 `[]`，则会删除所有现有的补充协议

## Schema 定义

### SupplementaryAgreementInput

用于嵌套在合同创建/更新请求中的补充协议数据结构：

```python
class SupplementaryAgreementInput(Schema):
    name: Optional[str] = None          # 补充协议名称（可选）
    party_ids: Optional[List[int]] = None  # 当事人 ID 列表（可选）
```

### ContractIn

```python
class ContractIn(ModelSchema):
    # ... 其他字段 ...
    supplementary_agreements: Optional[List[SupplementaryAgreementInput]] = None
```

### ContractUpdate

```python
class ContractUpdate(Schema):
    # ... 其他字段 ...
    supplementary_agreements: Optional[List[SupplementaryAgreementInput]] = None
```

## 使用场景

### 场景 1: 创建合同并添加补充协议

```python
# 前端代码示例
const contractData = {
  name: "劳动合同",
  case_type: "labor",
  assigned_lawyer_id: 1,
  supplementary_agreements: [
    {
      name: "工资调整补充协议",
      party_ids: [1, 2]  // 甲方和乙方
    }
  ]
};

const response = await fetch('/api/v1/contracts/contracts', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(contractData)
});
```

### 场景 2: 更新合同并添加新的补充协议

```python
# 前端代码示例
const updateData = {
  supplementary_agreements: [
    {
      name: "第一次补充协议",
      party_ids: [1, 2]
    },
    {
      name: "第二次补充协议",
      party_ids: [1, 2, 3]
    }
  ]
};

const response = await fetch(`/api/v1/contracts/contracts/${contractId}`, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(updateData)
});
```

### 场景 3: 删除所有补充协议

```python
# 前端代码示例
const updateData = {
  supplementary_agreements: []  // 空数组表示删除所有
};

const response = await fetch(`/api/v1/contracts/contracts/${contractId}`, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(updateData)
});
```

### 场景 4: 不修改补充协议

```python
# 前端代码示例
const updateData = {
  name: "更新合同名称",
  // 不包含 supplementary_agreements 字段
};

const response = await fetch(`/api/v1/contracts/contracts/${contractId}`, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(updateData)
});
```

## 事务保证

所有操作都在数据库事务中执行，确保数据一致性：

- 如果创建合同失败，补充协议也不会被创建
- 如果创建补充协议失败，整个合同创建操作会回滚
- 更新操作同样保证原子性

## 权限控制

补充协议的创建和更新遵循合同的权限控制：

- 需要有合同的创建/更新权限
- 财务相关操作需要管理员权限（不影响补充协议）

## 性能优化

- 使用批量创建减少数据库查询
- 在合同查询时自动预加载补充协议
- 使用 `select_related` 和 `prefetch_related` 优化关联查询

## 响应格式

创建或更新合同后，响应会包含完整的补充协议信息：

```json
{
  "id": 1,
  "name": "测试合同",
  "supplementary_agreements": [
    {
      "id": 1,
      "name": "补充协议1",
      "contract": 1,
      "parties": [
        {
          "id": 1,
          "client": 1,
          "client_name": "客户A",
          "is_our_client": true
        }
      ],
      "created_at": "2025-12-05T10:00:00Z",
      "updated_at": "2025-12-05T10:00:00Z"
    }
  ]
}
```

## 错误处理

### 常见错误

1. **客户不存在**
   - 错误码: 404
   - 消息: "部分客户不存在"

2. **重复添加客户**
   - 错误码: 400
   - 消息: "不能重复添加同一客户"

3. **合同不存在**
   - 错误码: 404
   - 消息: "合同不存在"

## 最佳实践

1. **创建合同时添加补充协议**
   - 如果已知需要补充协议，在创建合同时一并添加
   - 减少 API 调用次数

2. **更新补充协议**
   - 如果只需要添加/删除个别补充协议，使用专门的补充协议 API
   - 如果需要完全替换所有补充协议，使用合同更新 API

3. **查询优化**
   - 合同列表和详情 API 已自动预加载补充协议
   - 无需额外查询

4. **数据验证**
   - 确保 `party_ids` 中的客户 ID 存在
   - 补充协议名称可以为空或重复

## 技术实现

### Service 层

```python
# ContractService.create_contract_with_cases
@transaction.atomic
def create_contract_with_cases(self, contract_data, ...):
    # 提取补充协议数据
    supplementary_agreements_data = contract_data.pop("supplementary_agreements", None)
    
    # 创建合同
    contract = self.create_contract(contract_data)
    
    # 创建补充协议
    if supplementary_agreements_data:
        sa_service = SupplementaryAgreementService()
        for sa_data in supplementary_agreements_data:
            sa_service.create_supplementary_agreement(
                contract_id=contract.id,
                name=sa_data.get("name"),
                party_ids=sa_data.get("party_ids")
            )
```

### 更新逻辑

```python
# ContractService.update_contract_with_finance
@transaction.atomic
def update_contract_with_finance(self, contract_id, update_data, ...):
    # 提取补充协议数据
    supplementary_agreements_data = update_data.pop("supplementary_agreements", None)
    
    # 更新合同
    contract = self.update_contract(contract_id, update_data)
    
    # 更新补充协议（完全替换）
    if supplementary_agreements_data is not None:
        # 删除现有的所有补充协议
        SupplementaryAgreement.objects.filter(contract_id=contract_id).delete()
        
        # 创建新的补充协议
        for sa_data in supplementary_agreements_data:
            sa_service.create_supplementary_agreement(...)
```

## 测试验证

所有功能已通过测试验证：

- ✓ 创建合同时同时创建补充协议
- ✓ 更新合同时替换补充协议
- ✓ 补充协议的当事人关联正确
- ✓ 事务回滚正常工作
- ✓ 级联删除正常工作

## 相关文档

- [补充协议 API 文档](./SUPPLEMENTARY_AGREEMENT_TEST_SUMMARY.md)
- [合同 API 文档](../api/CONTRACT_API.md)
- [Django 项目规范](../../.kiro/steering/django-python-expert.md)
