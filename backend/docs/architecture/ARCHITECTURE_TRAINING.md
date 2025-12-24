# 架构重构培训文档

## 培训目标

本培训旨在帮助团队成员理解和掌握重构后的架构原则、最佳实践和开发规范，确保所有开发人员能够：

1. 理解三层架构的职责边界
2. 掌握依赖注入的使用方法
3. 学会使用 Protocol 接口解耦模块
4. 编写符合规范的代码
5. 进行有效的代码审查

## 培训大纲

### 第一部分：架构原则（60分钟）

#### 1.1 三层架构概述（15分钟）

**核心概念**：
- API 层：请求/响应处理
- Service 层：业务逻辑封装
- Model 层：数据定义

**职责边界**：
```
API 层 → 只能做：参数验证、调用 Service、返回响应
       → 不能做：业务逻辑、数据库访问、权限检查

Service 层 → 只能做：业务逻辑、事务管理、权限检查
          → 不能做：HTTP 处理、返回 HTTP 响应

Model 层 → 只能做：数据定义、简单操作
        → 不能做：复杂业务逻辑、跨表查询
```

**实战演练**：
- 识别代码中的架构违规
- 重构一个包含业务逻辑的 API 函数

#### 1.2 依赖注入原则（20分钟）

**为什么需要依赖注入**：
- 提高可测试性
- 降低耦合度
- 提高可维护性

**实施方法**：
```python
# ❌ 错误：直接创建依赖
class CaseService:
    def create_case(self, data, user):
        contract_service = ContractService()  # 紧耦合
        # ...

# ✅ 正确：构造函数注入
class CaseService:
    def __init__(self, contract_service: IContractService):
        self.contract_service = contract_service
    
    def create_case(self, data, user):
        # 使用注入的依赖
        # ...
```

**实战演练**：
- 重构一个直接创建依赖的 Service
- 编写单元测试验证依赖注入

#### 1.3 接口解耦原则（25分钟）

**Protocol 接口的作用**：
- 避免循环依赖
- 降低模块耦合
- 支持多实现

**使用步骤**：
1. 在 `apps/core/interfaces.py` 定义 Protocol
2. 定义 DTO 数据传输对象
3. 在 Service 中依赖 Protocol 而非具体实现

**实战演练**：
- 解决 cases 和 contracts 模块的循环依赖
- 创建 Protocol 接口和 DTO

### 第二部分：代码规范（45分钟）

#### 2.1 API 层规范（15分钟）

**标准模板**：
```python
@router.post("/resources", response=ResourceSchema)
def create_resource(request, data: ResourceCreateSchema):
    """创建资源"""
    # 1. 创建 Service（注入依赖）
    service = ResourceService(
        dependency_service=DependencyService()
    )
    
    # 2. 调用 Service
    resource = service.create_resource(data, request.auth)
    
    # 3. 返回响应
    return ResourceSchema.from_orm(resource)
```

**常见错误**：
- 在 API 层写业务逻辑
- 在 API 层做权限检查
- 在 API 层直接访问数据库

#### 2.2 Service 层规范（15分钟）

**标准模板**：
```python
class ResourceService:
    def __init__(self, dependency_service: IDependencyService):
        self.dependency_service = dependency_service
    
    @transaction.atomic
    def create_resource(self, data: ResourceCreateSchema, user: User) -> Resource:
        # 1. 权限检查
        if not self._check_permission(user):
            raise PermissionDenied("无权限")
        
        # 2. 业务验证
        self._validate_data(data)
        
        # 3. 创建资源
        resource = Resource.objects.create(...)
        
        # 4. 记录日志
        logger.info("资源创建成功", extra={...})
        
        return resource
```

**最佳实践**：
- 使用 @transaction.atomic 管理事务
- 抛出自定义业务异常
- 记录结构化日志

#### 2.3 异常处理规范（15分钟）

**异常体系**：
- ValidationException (400)
- PermissionDenied (403)
- NotFoundError (404)
- ConflictError (409)

**使用规范**：
```python
# Service 层：抛出异常
if not user.has_perm('resource.add'):
    raise PermissionDenied("无权限创建资源")

# API 层：依赖全局异常处理器（不需要 try/except）
```

### 第三部分：性能优化（30分钟）

#### 3.1 避免 N+1 查询（15分钟）

**问题识别**：
```python
# ❌ N+1 查询
cases = Case.objects.all()
for case in cases:
    print(case.contract.name)  # 每次循环都查询
```

**解决方案**：
```python
# ✅ 使用 select_related
cases = Case.objects.select_related('contract').all()
for case in cases:
    print(case.contract.name)  # 不会额外查询
```

**实战演练**：
- 识别代码中的 N+1 查询
- 使用 select_related/prefetch_related 优化

#### 3.2 批量操作（15分钟）

**使用场景**：
- bulk_create：批量创建
- bulk_update：批量更新
- update()：批量更新字段

**示例**：
```python
# ❌ 循环创建
for data in data_list:
    Case.objects.create(**data)

# ✅ 批量创建
cases = [Case(**data) for data in data_list]
Case.objects.bulk_create(cases, batch_size=100)
```

### 第四部分：测试规范（30分钟）

#### 4.1 单元测试（15分钟）

**测试模板**：
```python
@pytest.mark.django_db
class TestResourceService:
    def setup_method(self):
        self.mock_dependency = Mock()
        self.service = ResourceService(
            dependency_service=self.mock_dependency
        )
    
    def test_create_resource_success(self):
        # Arrange
        user = UserFactory()
        data = ResourceCreateSchema(name="Test")
        
        # Act
        resource = self.service.create_resource(data, user)
        
        # Assert
        assert resource.name == "Test"
```

**最佳实践**：
- 使用 AAA 模式（Arrange, Act, Assert）
- 使用 Mock 隔离依赖
- 使用 Factory 生成测试数据

#### 4.2 Property-Based Testing（15分钟）

**使用场景**：
- 验证通用属性
- 测试边界条件
- 发现意外的 bug

**示例**：
```python
@given(st.text(min_size=1, max_size=200))
@pytest.mark.django_db
def test_resource_name_property(name):
    """Property: 资源名称长度应该在 1-200 之间"""
    service = ResourceService()
    resource = service.create_resource(
        ResourceCreateSchema(name=name),
        UserFactory()
    )
    assert 1 <= len(resource.name) <= 200
```

### 第五部分：实战案例（45分钟）

#### 5.1 重构案例分析（20分钟）

**案例 1：API 层包含业务逻辑**
- 问题识别
- 重构步骤
- 验证结果

**案例 2：循环依赖**
- 问题识别
- 使用 Protocol 解耦
- 验证结果

**案例 3：N+1 查询**
- 问题识别
- 查询优化
- 性能对比

#### 5.2 代码审查实战（25分钟）

**审查清单**：
- [ ] 架构分层是否正确
- [ ] 是否使用依赖注入
- [ ] 是否有 N+1 查询
- [ ] 异常处理是否规范
- [ ] 是否有单元测试

**实战演练**：
- 审查一段真实代码
- 识别问题并提出改进建议
- 讨论最佳实践

## 培训资料

### 必读文档

1. **架构规范**：`.kiro/steering/django-python-expert.md`
2. **设计文档**：`.kiro/specs/backend-architecture-refactoring/design.md`
3. **需求文档**：`.kiro/specs/backend-architecture-refactoring/requirements.md`

### 参考代码

1. **优秀示例**：
   - `apps/automation/services/captcha/captcha_recognition_service.py`
   - `apps/cases/services/case_service.py`
   - `apps/contracts/services/contract_service.py`

2. **测试示例**：
   - `apps/automation/tests/test_captcha_recognition_properties.py`
   - `apps/cases/tests/test_case_service_properties.py`
   - `apps/contracts/tests/test_contract_service_properties.py`

### 工具和资源

1. **代码审查清单**：`backend/docs/CODE_REVIEW_CHECKLIST.md`
2. **架构决策记录**：`backend/docs/adr/`
3. **测试工具**：pytest, hypothesis, factory-boy

## 培训后评估

### 理论测试（30分钟）

**选择题**（10题）：
1. API 层的职责是什么？
2. 依赖注入的好处有哪些？
3. 如何避免 N+1 查询？
4. 什么时候应该抛出 PermissionDenied 异常？
5. select_related 和 prefetch_related 的区别？

**简答题**（5题）：
1. 解释三层架构的职责边界
2. 说明如何使用 Protocol 解耦模块
3. 描述 Service 层的标准结构
4. 列举常见的架构反模式
5. 说明如何编写单元测试

### 实战测试（60分钟）

**任务 1：重构 API 函数**（20分钟）
- 给定一个包含业务逻辑的 API 函数
- 重构为符合规范的代码
- 编写单元测试

**任务 2：优化查询**（20分钟）
- 给定一个有 N+1 查询的代码
- 使用 select_related/prefetch_related 优化
- 验证查询次数

**任务 3：代码审查**（20分钟）
- 审查一段代码
- 识别问题并提出改进建议
- 使用代码审查清单

## 持续学习

### 每周分享会（1小时）

**主题轮换**：
- Week 1: 架构原则深入讨论
- Week 2: 性能优化案例分享
- Week 3: 测试最佳实践
- Week 4: 代码审查经验总结

### 代码审查机制

**流程**：
1. 开发者提交 PR
2. 至少 1 位 Reviewer 审查
3. 使用代码审查清单
4. 讨论并改进
5. 合并代码

**审查重点**：
- 架构分层
- 依赖注入
- 查询优化
- 异常处理
- 测试覆盖

### 知识库维护

**文档更新**：
- 每月更新架构规范
- 记录新的最佳实践
- 添加常见问题解答
- 更新代码示例

**经验分享**：
- 记录重构经验
- 分享踩坑经历
- 总结最佳实践
- 建立案例库

## 联系方式

**技术支持**：
- 架构问题：联系架构师
- 代码审查：提交 PR
- 培训咨询：联系培训负责人

**资源链接**：
- 内部文档：`backend/docs/`
- 代码仓库：Git Repository
- 问题追踪：Issue Tracker
