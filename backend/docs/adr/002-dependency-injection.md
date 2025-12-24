# ADR-002: 使用依赖注入

## 状态

已接受 (2024-01-15)

## 背景

在重构前，Service 类存在以下问题：

1. **直接创建依赖**：在 Service 内部直接 `new` 其他 Service
2. **使用全局变量**：依赖全局状态，难以测试
3. **紧耦合**：Service 之间直接依赖具体实现
4. **难以测试**：无法 Mock 依赖进行单元测试

示例问题代码：

```python
class CaseService:
    def create_case(self, data, user):
        # ❌ 直接创建依赖
        contract_service = ContractService()
        email_service = EmailService()
        
        # 业务逻辑...
```

这导致：
- 无法独立测试 `CaseService`
- 修改 `ContractService` 影响所有使用它的地方
- 无法在测试中使用 Mock 对象

## 决策

我们决定在所有 Service 类中**使用构造函数注入**（Constructor Injection）：

### 原则

1. **所有依赖通过构造函数传递**
2. **依赖于接口（Protocol）而非具体实现**
3. **在 API 层组装依赖**
4. **测试时注入 Mock 对象**

### 实施方式

```python
# 1. 定义接口
class IContractService(Protocol):
    def get_contract(self, contract_id: int) -> Optional[ContractDTO]:
        ...

# 2. Service 通过构造函数注入依赖
class CaseService:
    def __init__(
        self,
        contract_service: IContractService,
        email_service: IEmailService
    ):
        self.contract_service = contract_service
        self.email_service = email_service
    
    def create_case(self, data, user):
        # ✅ 使用注入的依赖
        contract = self.contract_service.get_contract(data.contract_id)
        # ...

# 3. 在 API 层组装依赖
@router.post("/cases")
def create_case(request, data: CaseCreateSchema):
    service = CaseService(
        contract_service=ContractService(),
        email_service=EmailService()
    )
    return service.create_case(data, request.auth)

# 4. 测试时注入 Mock
def test_create_case():
    mock_contract = MockContractService()
    mock_email = MockEmailService()
    
    service = CaseService(
        contract_service=mock_contract,
        email_service=mock_email
    )
    
    # 测试...
```

## 后果

### 正面影响

1. **可测试性大幅提升**
   - 可以轻松 Mock 依赖进行单元测试
   - 测试不依赖外部服务（数据库、网络等）
   - 测试速度快

2. **降低耦合度**
   - Service 依赖接口而非具体实现
   - 可以轻松替换实现（如测试实现、生产实现）
   - 修改一个 Service 不影响其他 Service

3. **提高可维护性**
   - 依赖关系清晰，一目了然
   - 易于理解代码结构
   - 易于重构

4. **避免全局状态**
   - 减少隐式依赖
   - 提高代码可预测性
   - 避免并发问题

5. **支持多实现**
   - 同一接口可以有多个实现
   - 可以根据环境切换实现
   - 便于 A/B 测试

### 负面影响

1. **代码量增加**
   - 需要定义接口（Protocol）
   - 需要在 API 层组装依赖
   - 构造函数参数增多

2. **初期学习成本**
   - 开发者需要理解依赖注入概念
   - 需要学习如何使用 Protocol
   - 需要学习如何编写 Mock

3. **手动组装依赖**
   - 没有使用 DI 容器，需要手动组装
   - API 层代码略显冗长

### 风险

1. **依赖链过长**：Service 依赖太多其他 Service
   - **缓解措施**：重新审视职责划分，可能需要拆分 Service

2. **循环依赖**：Service A 依赖 Service B，Service B 依赖 Service A
   - **缓解措施**：使用 Protocol 接口打破循环，或重新设计

3. **忘记注入依赖**：开发者可能忘记在 API 层注入依赖
   - **缓解措施**：代码审查，编写测试

## 替代方案

### 方案 1: 使用 DI 容器

使用第三方 DI 容器（如 `dependency-injector`）自动管理依赖。

**优点**：
- 自动组装依赖
- 支持单例、工厂等模式
- 减少样板代码

**缺点**：
- 引入额外依赖
- 学习曲线陡峭
- 可能过度设计
- 调试困难

**为什么不选择**：
- 项目规模不大，手动注入足够
- 保持简单，避免过度设计
- 团队更熟悉手动注入

### 方案 2: 服务定位器模式

使用服务定位器（Service Locator）获取依赖。

**优点**：
- 实现简单
- 不需要修改构造函数

**缺点**：
- 隐藏依赖关系
- 难以测试
- 违反依赖倒置原则
- 被认为是反模式

**为什么不选择**：
- 隐藏依赖，降低代码可读性
- 难以测试
- 不符合最佳实践

### 方案 3: 单例模式

将 Service 实现为单例。

**优点**：
- 实现简单
- 全局访问

**缺点**：
- 全局状态，难以测试
- 并发问题
- 违反单一职责原则
- 难以 Mock

**为什么不选择**：
- 全局状态导致测试困难
- 不符合依赖注入原则
- 降低代码质量

## 实施

### 已完成

1. ✅ 更新开发规范文档，明确依赖注入原则
2. ✅ 重构所有 Service 类，使用构造函数注入
3. ✅ 创建 Protocol 接口定义
4. ✅ 更新 API 层，组装依赖
5. ✅ 编写单元测试，使用 Mock 对象
6. ✅ 代码审查，确保遵循原则

### 示例代码

完整示例请参考：
- `apps/cases/services/case_service.py`
- `apps/contracts/services/contract_service.py`
- `apps/automation/services/insurance/preservation_quote_service.py`

### 测试示例

完整测试示例请参考：
- `apps/cases/tests/test_case_service.py`
- `apps/contracts/tests/test_contract_service.py`

## 参考资料

- [Dependency Injection Principles, Practices, and Patterns](https://www.manning.com/books/dependency-injection-principles-practices-patterns)
- [Python Type Hints: Protocol](https://peps.python.org/pep-0544/)
- [Martin Fowler: Inversion of Control Containers and the Dependency Injection pattern](https://martinfowler.com/articles/injection.html)
- 项目规范文档：`.kiro/steering/django-python-expert.md`

## 更新历史

- 2024-01-15: 初始版本，决策已接受
- 2024-01-20: 完成所有 Service 重构
- 2024-01-25: 添加测试示例
