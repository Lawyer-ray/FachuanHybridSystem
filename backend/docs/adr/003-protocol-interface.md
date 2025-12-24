# ADR-003: Protocol 接口解耦

## 状态

已接受 (2024-01-15)

## 背景

在重构前，模块间存在严重的耦合问题：

1. **循环依赖**：`cases` 模块导入 `contracts` 模块，`contracts` 模块也导入 `cases` 模块
2. **紧耦合**：直接依赖具体实现类，难以替换和测试
3. **传递 Model 对象**：跨模块传递 Django Model，导致模块边界模糊

示例问题代码：

```python
# apps/cases/services/case_service.py
from apps.contracts.services import ContractService  # ❌ 直接导入

class CaseService:
    def create_case(self, data, user):
        contract_service = ContractService()
        contract = contract_service.get_contract(data.contract_id)  # ❌ 返回 Model
        # ...

# apps/contracts/services/contract_service.py
from apps.cases.services import CaseService  # ❌ 循环依赖！

class ContractService:
    def get_contract_cases(self, contract_id):
        case_service = CaseService()
        # ...
```

这导致：
- 模块间循环依赖，导致导入错误
- 修改一个模块影响其他模块
- 难以独立测试
- 模块边界不清晰

## 决策

我们决定使用 **Protocol 接口** 和 **DTO（数据传输对象）** 实现模块解耦：

### 原则

1. **定义 Protocol 接口**：在 `apps/core/interfaces.py` 中定义跨模块接口
2. **使用 DTO 传递数据**：不直接传递 Model 对象
3. **依赖接口而非实现**：Service 依赖 Protocol 而非具体类
4. **单向依赖**：模块只依赖 `core` 模块，不相互依赖

### 架构图

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────┐
│ CaseService  │────────▶│  IContractService│◀────────│ContractService│
│  (cases 模块) │  依赖    │   (Protocol)     │  实现    │(contracts模块)│
└──────────────┘         └──────────────────┘         └──────────────┘
                                  │
                                  ▼
                            ContractDTO
                          (数据传输对象)
```

### 实施方式

```python
# 1. 在 apps/core/interfaces.py 定义 DTO
@dataclass
class ContractDTO:
    """合同数据传输对象"""
    id: int
    name: str
    status: str
    representation_stages: List[str]
    
    @classmethod
    def from_model(cls, contract) -> "ContractDTO":
        return cls(
            id=contract.id,
            name=contract.name,
            status=contract.status,
            representation_stages=contract.representation_stages or []
        )

# 2. 定义 Protocol 接口
class IContractService(Protocol):
    """合同服务接口"""
    def get_contract(self, contract_id: int) -> Optional[ContractDTO]:
        ...
    
    def validate_contract_active(self, contract_id: int) -> bool:
        ...

# 3. 实现接口
class ContractService:
    """合同服务实现"""
    def get_contract(self, contract_id: int) -> Optional[ContractDTO]:
        try:
            contract = Contract.objects.get(id=contract_id)
            return ContractDTO.from_model(contract)
        except Contract.DoesNotExist:
            return None

# 4. 使用接口
class CaseService:
    def __init__(self, contract_service: IContractService):
        """✅ 依赖接口，不依赖具体实现"""
        self.contract_service = contract_service
    
    def create_case(self, data, user):
        # ✅ 通过接口调用，返回 DTO
        contract = self.contract_service.get_contract(data.contract_id)
        if not contract:
            raise ValidationException("合同不存在")
        # ...
```

## 后果

### 正面影响

1. **打破循环依赖**
   - 模块间不再相互导入
   - 依赖关系清晰
   - 避免导入错误

2. **降低耦合度**
   - 依赖接口而非具体实现
   - 可以轻松替换实现
   - 模块独立性强

3. **提高可测试性**
   - 可以轻松创建 Mock 实现
   - 测试不依赖其他模块
   - 测试速度快

4. **明确模块边界**
   - DTO 定义了模块间的数据契约
   - 接口定义了模块间的行为契约
   - 模块职责清晰

5. **支持多实现**
   - 同一接口可以有多个实现
   - 可以根据环境切换实现
   - 便于扩展

6. **类型安全**
   - Protocol 提供类型检查
   - IDE 自动补全
   - 减少运行时错误

### 负面影响

1. **代码量增加**
   - 需要定义 Protocol 接口
   - 需要定义 DTO 类
   - 需要实现 DTO 转换方法

2. **数据转换开销**
   - Model 转 DTO 有性能开销
   - 需要编写转换代码

3. **学习成本**
   - 开发者需要理解 Protocol 概念
   - 需要理解 DTO 模式
   - 需要学习如何定义接口

### 风险

1. **DTO 与 Model 不同步**：修改 Model 后忘记更新 DTO
   - **缓解措施**：编写测试验证转换，代码审查

2. **接口定义不合理**：接口方法过多或过少
   - **缓解措施**：遵循接口隔离原则，定期重构

3. **性能问题**：频繁的 DTO 转换影响性能
   - **缓解措施**：只在跨模块时使用 DTO，模块内部使用 Model

## 替代方案

### 方案 1: 直接传递 Model 对象

跨模块直接传递 Django Model 对象。

**优点**：
- 实现简单
- 无需转换
- 性能好

**缺点**：
- 模块边界模糊
- 紧耦合
- 难以测试
- 容易产生循环依赖

**为什么不选择**：
- 违反模块化原则
- 降低代码质量
- 难以维护

### 方案 2: 使用抽象基类（ABC）

使用 Python 的 `abc.ABC` 定义接口。

**优点**：
- Python 标准库
- 强制实现接口方法

**缺点**：
- 需要继承，增加耦合
- 不支持结构化类型（Structural Typing）
- 不如 Protocol 灵活

**为什么不选择**：
- Protocol 更灵活，支持结构化类型
- Protocol 不需要继承
- Protocol 是 Python 3.8+ 推荐方式

### 方案 3: 使用事件驱动

模块间通过事件通信，不直接调用。

**优点**：
- 完全解耦
- 异步处理
- 易于扩展

**缺点**：
- 实现复杂
- 调试困难
- 不适合同步场景
- 过度设计

**为什么不选择**：
- 对于同步业务逻辑过于复杂
- 增加系统复杂度
- 不符合当前需求

## 实施

### 已完成

1. ✅ 在 `apps/core/interfaces.py` 定义所有 Protocol 接口
2. ✅ 定义所有 DTO 类
3. ✅ 重构所有 Service，使用 Protocol 接口
4. ✅ 实现 DTO 转换方法
5. ✅ 更新测试，使用 Mock Protocol
6. ✅ 代码审查，确保遵循原则

### 接口列表

当前定义的 Protocol 接口：

- `IContractService` - 合同服务接口
- `ICaseService` - 案件服务接口
- `IClientService` - 客户服务接口
- `ILawyerService` - 律师服务接口
- `IPermissionService` - 权限服务接口

### DTO 列表

当前定义的 DTO：

- `ContractDTO` - 合同数据传输对象
- `CaseDTO` - 案件数据传输对象
- `ClientDTO` - 客户数据传输对象
- `LawyerDTO` - 律师数据传输对象

### 示例代码

完整示例请参考：
- `apps/core/interfaces.py` - 接口和 DTO 定义
- `apps/cases/services/case_service.py` - 使用接口
- `apps/contracts/services/contract_service.py` - 实现接口

## 参考资料

- [PEP 544 – Protocols: Structural subtyping](https://peps.python.org/pep-0544/)
- [Data Transfer Object Pattern](https://martinfowler.com/eaaCatalog/dataTransferObject.html)
- [Interface Segregation Principle](https://en.wikipedia.org/wiki/Interface_segregation_principle)
- 项目规范文档：`.kiro/steering/django-python-expert.md`

## 更新历史

- 2024-01-15: 初始版本，决策已接受
- 2024-01-20: 完成所有接口定义
- 2024-01-25: 完成所有模块重构
