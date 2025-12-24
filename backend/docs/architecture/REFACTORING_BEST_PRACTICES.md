# 重构经验和最佳实践

## 文档目的

本文档总结了后端架构重构过程中的经验教训、最佳实践和常见陷阱，帮助团队成员在未来的开发中避免重复犯错，持续改进代码质量。

## 重构经验总结

### 1. 渐进式重构策略

**经验**：一次性重构整个系统风险太大，应该采用渐进式重构策略。

**实施方法**：
1. **按模块重构**：优先重构高优先级模块（automation, cases, contracts）
2. **保持向后兼容**：新旧接口并存一段时间
3. **充分测试**：每次重构后运行完整测试套件
4. **监控告警**：监控错误率和性能指标

**成功案例**：
- automation 模块重构：先重构 CaptchaRecognitionService，验证成功后再重构其他服务
- cases 模块重构：先解除循环依赖，再优化查询，最后添加测试

**教训**：
- ❌ 不要一次性重构多个模块
- ❌ 不要在没有测试的情况下重构
- ❌ 不要忽略性能监控

### 2. 规范文档先行

**经验**：在开始重构前，先完善开发规范文档，确保团队对架构原则有统一理解。

**实施方法**：
1. **更新规范文档**：`.kiro/steering/django-python-expert.md`
2. **添加代码模板**：提供 API、Service、Model 层的标准模板
3. **添加反模式警示**：列出常见错误和正确做法
4. **创建代码审查清单**：用于 PR Review

**成功案例**：
- 规范文档成为 Kiro AI 的"宪法"，自动生成的代码符合架构规范
- 代码审查清单帮助团队快速识别问题

**教训**：
- ❌ 不要在没有规范的情况下开始重构
- ❌ 不要假设团队成员都理解架构原则
- ❌ 不要忽视文档的重要性

### 3. 测试驱动重构

**经验**：在重构前先编写测试，确保重构不会破坏现有功能。

**实施方法**：
1. **编写单元测试**：覆盖核心业务逻辑
2. **编写集成测试**：测试 API 端到端流程
3. **编写 Property-Based Tests**：验证通用属性
4. **运行测试**：确保所有测试通过

**成功案例**：
- CaseService 重构：先编写测试，然后重构，测试全部通过
- ContractService 重构：使用 PBT 发现了边界条件的 bug

**教训**：
- ❌ 不要在没有测试的情况下重构
- ❌ 不要假设代码是正确的
- ❌ 不要忽略边界条件

### 4. 依赖注入的重要性

**经验**：依赖注入是提高代码可测试性和可维护性的关键。

**实施方法**：
1. **构造函数注入**：通过构造函数传递依赖
2. **接口依赖**：依赖 Protocol 接口而非具体实现
3. **在 API 层组装**：在 API 层创建 Service 实例并注入依赖
4. **测试时注入 Mock**：使用 Mock 对象隔离依赖

**成功案例**：
- CaseService 注入 IContractService：解除了循环依赖
- PreservationQuoteService 注入 TokenService：提高了可测试性

**教训**：
- ❌ 不要在 Service 内部直接创建依赖
- ❌ 不要使用全局变量
- ❌ 不要忽视依赖关系的清晰性

### 5. 查询优化的重要性

**经验**：N+1 查询是性能杀手，必须使用 select_related/prefetch_related 优化。

**实施方法**：
1. **识别 N+1 查询**：在循环中访问关联对象
2. **使用 select_related**：预加载外键关系
3. **使用 prefetch_related**：预加载多对多关系
4. **验证查询次数**：使用 Django Debug Toolbar 或 pytest

**成功案例**：
- CaseService.list_cases：从 N+1 查询优化到 1 次查询
- ContractService.list_contracts：查询时间从 2s 降到 200ms

**教训**：
- ❌ 不要在循环中访问关联对象
- ❌ 不要忽视查询性能
- ❌ 不要假设 ORM 会自动优化

## 最佳实践

### 1. API 层最佳实践

**原则**：API 层只负责请求/响应处理，不包含任何业务逻辑。

**最佳实践**：
```python
@router.post("/resources", response=ResourceSchema)
def create_resource(request, data: ResourceCreateSchema):
    """创建资源（标准模板）"""
    # 1. 创建 Service（注入依赖）
    service = ResourceService(
        dependency_service=DependencyService()
    )
    
    # 2. 调用 Service
    resource = service.create_resource(data, request.auth)
    
    # 3. 返回响应
    return ResourceSchema.from_orm(resource)
```

**避免的错误**：
```python
# ❌ 错误：在 API 层写业务逻辑
@router.post("/resources")
def create_resource(request, data):
    if not request.auth.has_perm('resource.add'):
        return {"error": "无权限"}, 403
    
    if Resource.objects.filter(name=data.name).exists():
        return {"error": "名称已存在"}, 400
    
    resource = Resource.objects.create(...)
    return ResourceSchema.from_orm(resource)
```

### 2. Service 层最佳实践

**原则**：Service 层封装所有业务逻辑，使用依赖注入，抛出自定义异常。

**最佳实践**：
```python
class ResourceService:
    """资源服务（标准模板）"""
    
    def __init__(self, dependency_service: IDependencyService):
        """构造函数注入依赖"""
        self.dependency_service = dependency_service
    
    @transaction.atomic
    def create_resource(self, data: ResourceCreateSchema, user: User) -> Resource:
        """创建资源"""
        # 1. 权限检查
        if not self._check_permission(user):
            raise PermissionDenied("无权限创建资源")
        
        # 2. 业务验证
        self._validate_data(data)
        
        # 3. 创建资源
        resource = Resource.objects.create(...)
        
        # 4. 记录日志
        logger.info("资源创建成功", extra={...})
        
        return resource
    
    def _check_permission(self, user: User) -> bool:
        """权限检查（私有方法）"""
        return user.has_perm('resource.add')
    
    def _validate_data(self, data: ResourceCreateSchema) -> None:
        """业务验证（私有方法）"""
        if Resource.objects.filter(name=data.name).exists():
            raise ValidationException("名称已存在")
```

**避免的错误**：
```python
# ❌ 错误：直接创建依赖
class ResourceService:
    def create_resource(self, data, user):
        dependency_service = DependencyService()  # 紧耦合
        # ...

# ❌ 错误：返回错误码
class ResourceService:
    def create_resource(self, data, user):
        if not user.has_perm('resource.add'):
            return None  # 应该抛出异常
        # ...
```

### 3. 查询优化最佳实践

**原则**：避免 N+1 查询，使用 select_related/prefetch_related 预加载。

**最佳实践**：
```python
def list_cases(self, user):
    """列表查询（优化版）"""
    from django.db.models import Count
    
    # 使用 select_related 预加载外键
    # 使用 prefetch_related 预加载多对多
    # 使用 annotate 在数据库层面计算
    cases = Case.objects.select_related(
        'contract',
        'created_by'
    ).prefetch_related(
        'parties',
        'logs'
    ).annotate(
        party_count=Count('parties')
    ).all()
    
    return cases
```

**避免的错误**：
```python
# ❌ 错误：N+1 查询
def list_cases(self, user):
    cases = Case.objects.all()  # 1 次查询
    
    for case in cases:
        print(case.contract.name)  # N 次查询
        print(case.parties.count())  # N 次查询
```

### 4. 异常处理最佳实践

**原则**：Service 层抛出自定义异常，API 层依赖全局异常处理器。

**最佳实践**：
```python
# Service 层：抛出异常
def create_resource(self, data, user):
    if not user.has_perm('resource.add'):
        raise PermissionDenied("无权限创建资源")
    
    if Resource.objects.filter(name=data.name).exists():
        raise ValidationException(
            message="名称已存在",
            code="DUPLICATE_NAME",
            errors={"name": "该名称已被使用"}
        )
    
    resource = Resource.objects.create(...)
    return resource

# API 层：不需要 try/except
@router.post("/resources")
def create_resource(request, data):
    service = ResourceService()
    resource = service.create_resource(data, request.auth)
    return ResourceSchema.from_orm(resource)

# 全局异常处理器
@api.exception_handler(PermissionDenied)
def handle_permission_denied(request, exc):
    return api.create_response(
        request,
        {"error": exc.message, "code": exc.code},
        status=403
    )
```

**避免的错误**：
```python
# ❌ 错误：返回错误码
def create_resource(self, data, user):
    if not user.has_perm('resource.add'):
        return {"error": "无权限"}  # 应该抛出异常
    # ...

# ❌ 错误：在 API 层处理异常
@router.post("/resources")
def create_resource(request, data):
    try:
        service = ResourceService()
        resource = service.create_resource(data, request.auth)
        return ResourceSchema.from_orm(resource)
    except PermissionDenied:
        return {"error": "无权限"}, 403  # 应该依赖全局处理器
```

### 5. 测试最佳实践

**原则**：编写单元测试和 Property-Based Tests，使用 Mock 隔离依赖。

**最佳实践**：
```python
@pytest.mark.django_db
class TestResourceService:
    """资源服务测试"""
    
    def setup_method(self):
        """每个测试前执行"""
        self.mock_dependency = Mock()
        self.service = ResourceService(
            dependency_service=self.mock_dependency
        )
    
    def test_create_resource_success(self):
        """测试创建资源成功"""
        # Arrange
        user = UserFactory()
        data = ResourceCreateSchema(name="Test")
        self.mock_dependency.get_data.return_value = {"key": "value"}
        
        # Act
        resource = self.service.create_resource(data, user)
        
        # Assert
        assert resource.name == "Test"
        self.mock_dependency.get_data.assert_called_once()
    
    def test_create_resource_permission_denied(self):
        """测试权限不足"""
        user = UserFactory(is_superuser=False)
        data = ResourceCreateSchema(name="Test")
        
        with pytest.raises(PermissionDenied):
            self.service.create_resource(data, user)

# Property-Based Test
@given(st.text(min_size=1, max_size=200))
@pytest.mark.django_db
def test_resource_name_property(name):
    """Property: 资源名称长度应该在 1-200 之间"""
    service = ResourceService(dependency_service=MockDependencyService())
    resource = service.create_resource(
        ResourceCreateSchema(name=name),
        UserFactory()
    )
    assert 1 <= len(resource.name) <= 200
```

**避免的错误**：
```python
# ❌ 错误：不使用 Mock
def test_create_resource(self):
    service = ResourceService()  # 依赖真实的 DependencyService
    resource = service.create_resource(...)  # 可能失败

# ❌ 错误：测试依赖其他测试
def test_create_resource(self):
    # 假设 test_setup 已经运行
    resource = Resource.objects.get(id=1)  # 可能不存在
```

## 常见陷阱

### 1. 架构陷阱

**陷阱 1：在 API 层写业务逻辑**
- 问题：导致代码难以测试和复用
- 解决：将业务逻辑移至 Service 层

**陷阱 2：循环依赖**
- 问题：模块间相互引用，难以维护
- 解决：使用 Protocol 接口解耦

**陷阱 3：紧耦合**
- 问题：直接创建依赖，难以测试
- 解决：使用依赖注入

### 2. 性能陷阱

**陷阱 1：N+1 查询**
- 问题：在循环中访问关联对象
- 解决：使用 select_related/prefetch_related

**陷阱 2：循环中执行数据库操作**
- 问题：性能极差
- 解决：使用批量操作（bulk_create, bulk_update）

**陷阱 3：查询所有字段**
- 问题：浪费带宽和内存
- 解决：使用 only/defer 只查询需要的字段

### 3. 安全陷阱

**陷阱 1：权限检查缺失**
- 问题：未授权访问
- 解决：在 Service 层添加权限检查

**陷阱 2：SQL 注入**
- 问题：字符串拼接 SQL
- 解决：使用 ORM 或参数化查询

**陷阱 3：敏感信息泄露**
- 问题：日志记录密码、Token
- 解决：敏感信息脱敏

### 4. 测试陷阱

**陷阱 1：测试依赖真实服务**
- 问题：测试不稳定
- 解决：使用 Mock 隔离依赖

**陷阱 2：测试覆盖率低**
- 问题：重构时容易破坏功能
- 解决：提高测试覆盖率（Service 80%+）

**陷阱 3：忽略边界条件**
- 问题：边界条件的 bug
- 解决：使用 Property-Based Testing

## 持续改进

### 1. 定期审查

**频率**：每月一次

**内容**：
- 审查代码质量
- 识别架构问题
- 更新规范文档
- 分享最佳实践

### 2. 知识分享

**频率**：每周一次

**形式**：
- 技术分享会
- 代码审查讨论
- 案例分析
- 经验总结

### 3. 工具支持

**自动化工具**：
- flake8：代码风格检查
- mypy：类型检查
- pytest-cov：测试覆盖率
- SonarQube：代码质量分析

**手动审查**：
- 使用代码审查清单
- 关注架构设计
- 验证业务逻辑
- 检查性能和安全

### 4. 文档维护

**更新频率**：持续更新

**维护内容**：
- 架构规范文档
- 最佳实践文档
- 代码审查清单
- ADR 文档

## 成功指标

### 1. 代码质量指标

- **测试覆盖率**：Service 层 80%+
- **代码重复率**：< 5%
- **圈复杂度**：< 10
- **技术债务**：持续降低

### 2. 性能指标

- **API 响应时间**：P95 < 500ms
- **数据库查询次数**：无 N+1 查询
- **错误率**：< 0.1%

### 3. 团队指标

- **代码审查参与率**：100%
- **培训完成率**：100%
- **规范遵守率**：> 95%

## 参考资源

- **架构规范**：`.kiro/steering/django-python-expert.md`
- **设计文档**：`.kiro/specs/backend-architecture-refactoring/design.md`
- **培训文档**：`backend/docs/ARCHITECTURE_TRAINING.md`
- **代码审查清单**：`backend/docs/CODE_REVIEW_CHECKLIST.md`
- **ADR 文档**：`backend/docs/adr/`

## 联系方式

**技术支持**：
- 架构问题：联系架构师
- 代码审查：提交 PR
- 培训咨询：联系培训负责人

**反馈渠道**：
- 提交 Issue
- 发起讨论
- 更新文档
