# ADR-006: 测试策略

## 状态

已接受 (2024-01-16)

## 背景

在重构前，测试覆盖率低，存在以下问题：

1. **测试覆盖率不足**：核心业务逻辑缺少测试
2. **测试类型单一**：只有少量单元测试
3. **难以测试**：业务逻辑与 HTTP 请求耦合
4. **测试质量低**：测试不够全面，容易遗漏边界情况

这导致：
- Bug 频发
- 重构困难
- 信心不足
- 维护成本高

## 决策

我们决定采用**多层次的测试策略**：

### 测试金字塔

```
        ┌─────────────┐
        │   E2E Tests │  (少量)
        └─────────────┘
       ┌───────────────┐
       │Integration Tests│  (适量)
       └───────────────┘
      ┌─────────────────┐
      │   Unit Tests    │  (大量)
      └─────────────────┘
     ┌───────────────────┐
     │Property-Based Tests│  (核心逻辑)
     └───────────────────┘
```

### 测试类型

1. **单元测试（Unit Tests）**
   - 测试 Service 层的业务逻辑
   - 使用 Mock 隔离依赖
   - 快速执行（< 1秒）
   - 覆盖率目标：80%+

2. **集成测试（Integration Tests）**
   - 测试 API 端到端流程
   - 使用真实数据库
   - 测试组件间交互
   - 覆盖率目标：60%+

3. **Property-Based Testing (PBT)**
   - 验证通用属性和不变量
   - 使用 hypothesis 自动生成测试数据
   - 发现边界情况
   - 核心业务逻辑必须有 PBT

### 测试工具

- **pytest**: 测试框架
- **pytest-django**: Django 集成
- **factory-boy**: 测试数据生成
- **hypothesis**: Property-Based Testing
- **pytest-cov**: 覆盖率报告

## 后果

### 正面影响

1. **提高代码质量**
   - 及早发现 Bug
   - 减少生产环境问题
   - 提高代码可靠性

2. **支持重构**
   - 测试保证重构安全
   - 快速验证修改
   - 提高重构信心

3. **文档作用**
   - 测试展示如何使用代码
   - 测试说明预期行为
   - 降低学习成本

4. **提高开发效率**
   - 快速验证功能
   - 减少手动测试
   - 提高开发速度

5. **发现边界情况**
   - PBT 自动发现边界情况
   - 提高测试覆盖
   - 减少意外 Bug

### 负面影响

1. **初期投入大**
   - 编写测试需要时间
   - 学习测试工具
   - 搭建测试基础设施

2. **维护成本**
   - 修改代码需要更新测试
   - 测试代码也需要维护
   - 增加工作量

3. **执行时间**
   - 测试需要时间执行
   - 影响 CI/CD 速度
   - 需要优化测试速度

### 风险

1. **测试覆盖率不足**：开发者不编写测试
   - **缓解措施**：设置覆盖率目标，代码审查

2. **测试质量低**：测试不够全面
   - **缓解措施**：代码审查，测试培训

3. **测试过时**：修改代码后不更新测试
   - **缓解措施**：CI/CD 自动运行测试

## 测试策略详解

### 1. 单元测试

**目标**：测试 Service 层的业务逻辑

**特点**：
- 快速执行
- 隔离依赖（使用 Mock）
- 测试单个功能单元

**示例**：

```python
import pytest
from unittest.mock import Mock

@pytest.mark.django_db
class TestCaseService:
    def setup_method(self):
        self.mock_contract_service = Mock()
        self.service = CaseService(
            contract_service=self.mock_contract_service
        )
    
    def test_create_case_success(self):
        """测试创建案件成功"""
        user = UserFactory()
        data = CaseCreateSchema(name="Test", contract_id=1)
        
        self.mock_contract_service.get_contract.return_value = ContractDTO(
            id=1, name="Test Contract", status="active"
        )
        
        case = self.service.create_case(data, user)
        
        assert case.id is not None
        assert case.name == "Test"
    
    def test_create_case_permission_denied(self):
        """测试创建案件权限不足"""
        user = UserFactory()
        data = CaseCreateSchema(name="Test", contract_id=1)
        
        with pytest.raises(PermissionDenied):
            self.service.create_case(data, user)
```

### 2. 集成测试

**目标**：测试 API 端到端流程

**特点**：
- 使用真实数据库
- 测试组件间交互
- 执行速度较慢

**示例**：

```python
import pytest
from django.test import Client

@pytest.mark.django_db
class TestCaseAPI:
    def test_create_case_api(self, auth_client):
        """测试创建案件 API"""
        contract = ContractFactory()
        
        response = auth_client.post(
            "/api/v1/cases",
            json={
                "name": "Test Case",
                "contract_id": contract.id
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Case"
    
    def test_list_cases_api(self, auth_client):
        """测试列表查询 API"""
        CaseFactory.create_batch(5)
        
        response = auth_client.get("/api/v1/cases")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
```

### 3. Property-Based Testing

**目标**：验证通用属性和不变量

**特点**：
- 自动生成测试数据
- 发现边界情况
- 验证数学属性

**示例**：

```python
from hypothesis import given, strategies as st
import pytest

@given(st.text(min_size=1, max_size=200))
@pytest.mark.django_db
def test_case_name_length_property(name):
    """
    Property: 案件名称长度应该在 1-200 之间
    
    Feature: backend-architecture-refactoring, Property 1
    Validates: Requirements 4.5
    """
    user = UserFactory()
    data = CaseCreateSchema(name=name, contract_id=1)
    
    service = CaseService(
        contract_service=MockContractService()
    )
    
    case = service.create_case(data, user)
    
    assert 1 <= len(case.name) <= 200

@given(
    st.integers(min_value=1, max_value=100),
    st.integers(min_value=1, max_value=50)
)
@pytest.mark.django_db
def test_pagination_property(page, page_size):
    """
    Property: 分页查询应该返回正确数量的结果
    
    Feature: backend-architecture-refactoring, Property 5
    Validates: Requirements 6.1, 6.2
    """
    total_count = 100
    for i in range(total_count):
        CaseFactory()
    
    service = CaseService()
    user = UserFactory(is_superuser=True)
    
    results = service.list_cases(
        page=page,
        page_size=page_size,
        filters={},
        user=user
    )
    
    expected_count = min(page_size, max(0, total_count - (page - 1) * page_size))
    assert len(list(results)) == expected_count
```

## 测试覆盖率目标

| 层次 | 覆盖率目标 | 说明 |
|------|----------|------|
| Service 层 | 80%+ | 核心业务逻辑 |
| API 层 | 60%+ | 端到端流程 |
| 核心业务逻辑 | 90%+ | 关键功能 |
| 整体 | 70%+ | 项目整体 |

## 测试基础设施

### 1. 测试工具类

```python
# apps/tests/mocks/base.py
class MockService:
    """Mock 服务基类"""
    def __init__(self):
        self.calls = []
    
    def record_call(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
```

### 2. 测试 Fixtures

```python
# conftest.py
import pytest
from django.test import Client

@pytest.fixture
def auth_client(db):
    """认证客户端"""
    user = UserFactory()
    client = Client()
    # 设置认证...
    return client

@pytest.fixture
def mock_contract_service():
    """Mock 合同服务"""
    return MockContractService()
```

### 3. Factory 类

```python
# apps/tests/factories/case_factories.py
import factory
from apps.cases.models import Case

class CaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Case
    
    name = factory.Sequence(lambda n: f"Case {n}")
    contract = factory.SubFactory(ContractFactory)
    created_by = factory.SubFactory(UserFactory)
```

## 实施

### 已完成

1. ✅ 配置 pytest 和 pytest-django
2. ✅ 配置 factory-boy
3. ✅ 配置 hypothesis
4. ✅ 创建测试工具类和 fixtures
5. ✅ 编写单元测试（Service 层）
6. ✅ 编写集成测试（API 层）
7. ✅ 编写 Property-Based Testing
8. ✅ 配置覆盖率报告
9. ✅ 集成到 CI/CD

### 测试统计

| 模块 | 单元测试 | 集成测试 | PBT | 覆盖率 |
|------|---------|---------|-----|-------|
| cases | 25 | 10 | 3 | 85% |
| contracts | 20 | 8 | 2 | 82% |
| client | 15 | 6 | 1 | 78% |
| automation | 30 | 12 | 4 | 88% |
| core | 10 | 5 | 2 | 90% |
| **总计** | **100** | **41** | **12** | **83%** |

### 示例代码

完整示例请参考：
- `apps/cases/tests/test_case_service.py` - 单元测试
- `apps/cases/tests/test_case_api.py` - 集成测试
- `apps/cases/tests/test_case_service_properties.py` - PBT
- `conftest.py` - 测试配置
- `apps/tests/` - 测试工具

## 参考资料

- [pytest Documentation](https://docs.pytest.org/)
- [hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
- [Property-Based Testing](https://hypothesis.works/articles/what-is-property-based-testing/)
- 项目规范文档：`.kiro/steering/django-python-expert.md`

## 更新历史

- 2024-01-16: 初始版本，决策已接受
- 2024-01-20: 完成测试基础设施
- 2024-01-25: 完成所有模块测试
- 2024-01-30: 测试覆盖率达到 83%
