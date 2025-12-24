# Django Admin 稳定性测试方案

## 测试目标

使用 Playwright MCP 对整个 Django Admin 后台进行全面的稳定性测试，确保：
1. 所有 Admin 页面可以正常访问
2. 核心功能（增删改查）正常工作
3. 复杂的内联表单和嵌套表单正常工作
4. 自定义 Admin Action 正常执行
5. 权限控制正常工作
6. 性能符合预期

## 测试环境

- **测试账号**: 法穿
- **测试密码**: 1234qwer
- **Admin URL**: http://localhost:8000/admin/
- **测试工具**: Playwright MCP
- **测试数据**: 使用 Factory 生成测试数据

## 测试模块分类

### 1. 核心业务模块（高优先级）

#### 1.1 案件管理 (Cases)
- **Admin 类**: `CaseAdmin`
- **复杂度**: ⭐⭐⭐⭐⭐ (最复杂)
- **特点**:
  - 使用 nested_admin (嵌套内联)
  - 5 个内联表单 (CaseParty, CaseAssignment, SupervisingAuthority, CaseNumber, CaseLog)
  - 自定义表单验证 (阶段验证)
  - 自定义 JavaScript
  - 复杂的 FormSet 验证 (当事人唯一性)

**测试用例**:
1. 列表页访问和过滤
2. 创建案件（包含所有内联）
3. 编辑案件（修改内联数据）
4. 删除案件
5. 搜索功能
6. 阶段验证逻辑
7. 当事人唯一性验证
8. 嵌套内联（CaseLog 下的 CaseLogAttachment）

#### 1.2 合同管理 (Contracts)
- **Admin 类**: `ContractAdmin`
- **复杂度**: ⭐⭐⭐⭐⭐ (最复杂)
- **特点**:
  - 使用 nested_admin
  - 4 个内联表单 (ContractParty, ContractAssignment, Case, ContractReminder)
  - Case 内联中嵌套 CaseParty 内联
  - 自定义表单 (多选代理阶段)
  - 阶段验证逻辑

**测试用例**:
1. 列表页访问和过滤
2. 创建合同（包含所有内联）
3. 在合同中创建案件（嵌套内联）
4. 编辑合同
5. 删除合同
6. 代理阶段验证
7. 案件阶段验证（在合同内联中）

#### 1.3 客户管理 (Clients)
- **Admin 类**: `ClientAdmin`
- **复杂度**: ⭐⭐⭐
- **特点**:
  - 自定义表单验证
  - 身份证件内联 (ClientIdentityDoc)

**测试用例**:
1. 列表页访问和搜索
2. 创建客户
3. 编辑客户
4. 删除客户
5. 上传身份证件

#### 1.4 律所和律师管理 (Organization)
- **Admin 类**: `LawFirmAdmin`, `LawyerAdmin`, `TeamAdmin`
- **复杂度**: ⭐⭐⭐
- **特点**:
  - 自定义表单 (LawyerAdminForm)
  - 账号凭证内联 (AccountCredential)

**测试用例**:
1. 创建律所
2. 创建律师（包含账号凭证）
3. 创建团队
4. 编辑和删除

### 2. 自动化模块（中优先级）

#### 2.1 财产保全询价 (PreservationQuote)
- **Admin 类**: `PreservationQuoteAdmin`
- **复杂度**: ⭐⭐⭐⭐
- **特点**:
  - 自定义列表显示（格式化金额、状态、统计）
  - 内联表单 (InsuranceQuote)
  - 自定义 Admin Action (execute_quotes, retry_failed_quotes)
  - 自定义 URL 和视图 (run_quote_view)
  - 异步任务集成

**测试用例**:
1. 列表页访问和过滤
2. 创建询价任务
3. 查看询价详情（内联报价）
4. 执行询价任务（Admin Action）
5. 重试失败任务（Admin Action）
6. 立即运行按钮
7. 报价汇总显示

#### 2.2 测试工具 (TestCourt)
- **Admin 类**: `TestCourtAdmin`
- **复杂度**: ⭐⭐⭐
- **特点**:
  - 自定义列表页（完全自定义模板）
  - 自定义 URL 和视图
  - 集成 Playwright 测试

**测试用例**:
1. 访问测试工具列表页
2. 选择凭证测试登录
3. 查看测试结果

#### 2.3 Token 管理 (CourtToken)
- **Admin 类**: `CourtTokenAdmin`
- **复杂度**: ⭐⭐
- **特点**:
  - 只读字段
  - 自定义显示

**测试用例**:
1. 列表页访问
2. 查看 Token 详情
3. 删除 Token

### 3. 辅助模块（低优先级）

#### 3.1 合同相关
- `ContractFinanceLogAdmin`
- `ContractPaymentAdmin`
- `ContractReminderAdmin`

#### 3.2 案件相关
- `CasePartyAdmin`
- `CaseLogAdmin`
- `CaseAssignmentAdmin`
- `CaseNumberAdmin`
- `JudicialInfoAdmin`

#### 3.3 组织相关
- `AccountCredentialAdmin`

## 测试策略

### 阶段 1: 基础访问测试（冒烟测试）

**目标**: 确保所有 Admin 页面可以访问

**测试步骤**:
1. 登录 Admin
2. 访问每个模块的列表页
3. 检查页面是否正常加载（无 500 错误）
4. 检查页面标题和基本元素

**预期结果**: 所有页面返回 200 状态码

### 阶段 2: CRUD 功能测试

**目标**: 测试核心的增删改查功能

**测试步骤**:
1. 创建记录（填写必填字段）
2. 验证记录出现在列表页
3. 编辑记录
4. 验证修改生效
5. 删除记录
6. 验证记录已删除

**测试模块**:
- Cases
- Contracts
- Clients
- Lawyers
- PreservationQuote

### 阶段 3: 内联表单测试

**目标**: 测试复杂的内联表单功能

**测试步骤**:
1. 创建主记录并添加内联记录
2. 验证内联记录保存成功
3. 编辑主记录，修改内联记录
4. 删除内联记录
5. 测试嵌套内联（Contract -> Case -> CaseParty）

**测试模块**:
- CaseAdmin (5 个内联)
- ContractAdmin (4 个内联，包含嵌套)
- ClientAdmin (1 个内联)

### 阶段 4: 表单验证测试

**目标**: 测试自定义表单验证逻辑

**测试步骤**:
1. 提交无效数据
2. 验证错误消息显示
3. 修正数据后重新提交
4. 验证保存成功

**测试场景**:
- 案件阶段验证（CaseAdmin）
- 合同代理阶段验证（ContractAdmin）
- 当事人唯一性验证（CaseAdmin）
- 案件阶段必须在代理阶段内（ContractAdmin 的 Case 内联）

### 阶段 5: Admin Action 测试

**目标**: 测试自定义 Admin Action

**测试步骤**:
1. 选择记录
2. 执行 Admin Action
3. 验证操作结果
4. 检查成功/错误消息

**测试场景**:
- 执行询价任务（PreservationQuoteAdmin）
- 重试失败任务（PreservationQuoteAdmin）

### 阶段 6: 自定义视图测试

**目标**: 测试自定义 URL 和视图

**测试步骤**:
1. 访问自定义 URL
2. 执行操作
3. 验证结果
4. 检查重定向

**测试场景**:
- 立即运行询价（PreservationQuoteAdmin）
- 测试登录（TestCourtAdmin）

### 阶段 7: 性能测试

**目标**: 测试 Admin 页面性能

**测试指标**:
- 列表页加载时间 < 2 秒
- 详情页加载时间 < 1 秒
- 保存操作响应时间 < 3 秒

**测试场景**:
- 大量数据的列表页（100+ 记录）
- 复杂内联表单的保存
- 搜索和过滤性能

### 阶段 8: 边界条件测试

**目标**: 测试边界条件和异常情况

**测试场景**:
1. 访问不存在的记录 ID
2. 提交空表单
3. 提交超长字符串
4. 并发编辑同一记录
5. 删除被引用的记录

## 测试数据准备

### 使用 Factory 生成测试数据

```python
# 在测试前创建基础数据
from apps.tests.factories import (
    LawyerFactory,
    LawFirmFactory,
    ClientFactory,
    ContractFactory,
    CaseFactory,
)

# 创建律所和律师
law_firm = LawFirmFactory()
lawyer = LawyerFactory(law_firm=law_firm)

# 创建客户
clients = [ClientFactory() for _ in range(5)]

# 创建合同
contracts = [
    ContractFactory(
        law_firm=law_firm,
        assigned_lawyer=lawyer
    ) for _ in range(3)
]

# 创建案件
cases = [
    CaseFactory(contract=contract)
    for contract in contracts
]
```

## 测试脚本结构

### 1. 基础测试类

```python
# backend/tests/admin/base_admin_test.py
import asyncio
from playwright.async_api import async_playwright, Page, Browser

class BaseAdminTest:
    """Admin 测试基类"""
    
    ADMIN_URL = "http://localhost:8000/admin/"
    USERNAME = "法穿"
    PASSWORD = "1234qwer"
    
    async def setup(self):
        """设置测试环境"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
        # 登录
        await self.login()
    
    async def teardown(self):
        """清理测试环境"""
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()
    
    async def login(self):
        """登录 Admin"""
        await self.page.goto(self.ADMIN_URL)
        await self.page.fill('input[name="username"]', self.USERNAME)
        await self.page.fill('input[name="password"]', self.PASSWORD)
        await self.page.click('input[type="submit"]')
        
        # 等待登录成功
        await self.page.wait_for_url(f"{self.ADMIN_URL}**")
    
    async def navigate_to_model(self, app_label: str, model_name: str):
        """导航到指定模型的列表页"""
        url = f"{self.ADMIN_URL}{app_label}/{model_name}/"
        await self.page.goto(url)
        await self.page.wait_for_load_state('networkidle')
    
    async def click_add_button(self):
        """点击添加按钮"""
        await self.page.click('a.addlink')
        await self.page.wait_for_load_state('networkidle')
    
    async def fill_field(self, field_name: str, value: str):
        """填写表单字段"""
        await self.page.fill(f'input[name="{field_name}"]', value)
    
    async def submit_form(self):
        """提交表单"""
        await self.page.click('input[name="_save"]')
        await self.page.wait_for_load_state('networkidle')
    
    async def check_success_message(self) -> bool:
        """检查成功消息"""
        success_msg = await self.page.query_selector('.success')
        return success_msg is not None
    
    async def check_error_message(self) -> bool:
        """检查错误消息"""
        error_msg = await self.page.query_selector('.errorlist')
        return error_msg is not None
```

### 2. 模块测试类

```python
# backend/tests/admin/test_case_admin.py
from .base_admin_test import BaseAdminTest

class TestCaseAdmin(BaseAdminTest):
    """案件 Admin 测试"""
    
    async def test_list_page_access(self):
        """测试列表页访问"""
        await self.navigate_to_model('cases', 'case')
        
        # 检查页面标题
        title = await self.page.title()
        assert '案件' in title or 'Case' in title
        
        # 检查列表表格存在
        table = await self.page.query_selector('#result_list')
        assert table is not None
    
    async def test_create_case_basic(self):
        """测试创建基本案件"""
        await self.navigate_to_model('cases', 'case')
        await self.click_add_button()
        
        # 填写必填字段
        await self.fill_field('name', '测试案件')
        await self.fill_field('contract', '1')  # 假设已有合同
        
        # 提交表单
        await self.submit_form()
        
        # 检查成功消息
        assert await self.check_success_message()
    
    async def test_create_case_with_parties(self):
        """测试创建案件并添加当事人"""
        await self.navigate_to_model('cases', 'case')
        await self.click_add_button()
        
        # 填写主表单
        await self.fill_field('name', '测试案件（含当事人）')
        await self.fill_field('contract', '1')
        
        # 添加当事人（内联）
        await self.page.click('.add-row a')  # 点击添加内联
        await self.fill_field('parties-0-client', '1')
        await self.fill_field('parties-0-legal_status', 'plaintiff')
        
        # 提交表单
        await self.submit_form()
        
        # 检查成功消息
        assert await self.check_success_message()
    
    async def test_stage_validation(self):
        """测试阶段验证"""
        await self.navigate_to_model('cases', 'case')
        await self.click_add_button()
        
        # 填写表单，使用无效阶段
        await self.fill_field('name', '测试案件（无效阶段）')
        await self.fill_field('contract', '1')
        await self.page.select_option('select[name="current_stage"]', 'invalid_stage')
        
        # 提交表单
        await self.submit_form()
        
        # 检查错误消息
        assert await self.check_error_message()
```

### 3. 主测试运行器

```python
# backend/tests/admin/run_admin_tests.py
import asyncio
from test_case_admin import TestCaseAdmin
from test_contract_admin import TestContractAdmin
from test_preservation_quote_admin import TestPreservationQuoteAdmin

async def run_all_tests():
    """运行所有 Admin 测试"""
    
    test_classes = [
        TestCaseAdmin,
        TestContractAdmin,
        TestPreservationQuoteAdmin,
    ]
    
    results = {
        'passed': 0,
        'failed': 0,
        'errors': []
    }
    
    for test_class in test_classes:
        print(f"\n{'='*60}")
        print(f"运行测试: {test_class.__name__}")
        print(f"{'='*60}\n")
        
        test = test_class()
        await test.setup()
        
        # 获取所有测试方法
        test_methods = [
            method for method in dir(test)
            if method.startswith('test_') and callable(getattr(test, method))
        ]
        
        for method_name in test_methods:
            try:
                print(f"  ▶ {method_name}...", end=' ')
                method = getattr(test, method_name)
                await method()
                print("✅ PASSED")
                results['passed'] += 1
            except AssertionError as e:
                print(f"❌ FAILED: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'test': f"{test_class.__name__}.{method_name}",
                    'error': str(e)
                })
            except Exception as e:
                print(f"💥 ERROR: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'test': f"{test_class.__name__}.{method_name}",
                    'error': str(e)
                })
        
        await test.teardown()
    
    # 打印总结
    print(f"\n{'='*60}")
    print(f"测试总结")
    print(f"{'='*60}")
    print(f"✅ 通过: {results['passed']}")
    print(f"❌ 失败: {results['failed']}")
    print(f"总计: {results['passed'] + results['failed']}")
    
    if results['errors']:
        print(f"\n失败的测试:")
        for error in results['errors']:
            print(f"  - {error['test']}: {error['error']}")
    
    return results

if __name__ == '__main__':
    asyncio.run(run_all_tests())
```

## 测试执行计划

### 第一轮：冒烟测试（1-2 小时）
- 测试所有 Admin 列表页访问
- 确保没有 500 错误
- 记录访问问题

### 第二轮：核心功能测试（3-4 小时）
- 测试 Cases, Contracts, Clients 的 CRUD
- 测试基本内联表单
- 记录功能问题

### 第三轮：复杂功能测试（4-6 小时）
- 测试嵌套内联
- 测试表单验证
- 测试 Admin Action
- 记录复杂问题

### 第四轮：性能和边界测试（2-3 小时）
- 测试大数据量场景
- 测试边界条件
- 记录性能问题

## 问题记录模板

```markdown
## 问题 #001

**模块**: CaseAdmin
**严重程度**: 高/中/低
**类型**: 功能/性能/UI
**描述**: 详细描述问题
**重现步骤**:
1. 步骤 1
2. 步骤 2
3. 步骤 3

**预期结果**: 应该发生什么
**实际结果**: 实际发生了什么
**截图**: [如果有]
**错误日志**: [如果有]
**修复建议**: [如果有]
```

## 成功标准

- ✅ 所有列表页可以访问（0 个 500 错误）
- ✅ 核心 CRUD 功能正常（Cases, Contracts, Clients）
- ✅ 内联表单功能正常
- ✅ 表单验证逻辑正确
- ✅ Admin Action 正常执行
- ✅ 自定义视图正常工作
- ✅ 列表页加载时间 < 2 秒
- ✅ 详情页加载时间 < 1 秒
- ✅ 保存操作响应时间 < 3 秒

## 下一步行动

1. **准备测试环境**
   - 确保 Django 开发服务器运行
   - 创建测试数据
   - 配置 Playwright MCP

2. **执行测试**
   - 按照测试计划逐步执行
   - 记录所有问题
   - 截图保存证据

3. **分析结果**
   - 统计问题数量和类型
   - 确定优先级
   - 制定修复计划

4. **修复问题**
   - 按优先级修复
   - 回归测试
   - 更新文档
