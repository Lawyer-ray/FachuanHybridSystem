# Django Admin 稳定性测试

## 概述

这是一套使用 Playwright 对 Django Admin 后台进行全面稳定性测试的测试套件。

## 测试结构

```
backend/tests/admin/
├── README.md                    # 本文件
├── base_admin_test.py          # 测试基类（提供通用方法）
├── test_smoke.py               # 冒烟测试（页面访问）
├── test_case_admin.py          # 案件管理测试
├── test_contract_admin.py      # 合同管理测试（待创建）
├── test_preservation_quote_admin.py  # 财产保全询价测试（待创建）
├── run_admin_tests.py          # 主测试运行器
└── screenshots/                # 测试截图目录
```

## 前置条件

### 1. 安装依赖

```bash
# 激活虚拟环境
source /Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/venv312/bin/activate

# 安装 Playwright
pip install playwright pytest-playwright

# 安装浏览器
playwright install chromium
```

### 2. 准备测试数据

在运行测试前，需要创建一些基础测试数据：

```bash
cd backend

# 进入 Django shell
python manage.py shell
```

```python
# 在 Django shell 中执行
from apps.tests.factories import (
    LawyerFactory,
    LawFirmFactory,
    ClientFactory,
    ContractFactory,
    CaseFactory,
)

# 创建律所和律师
law_firm = LawFirmFactory(name="测试律所")
lawyer = LawyerFactory(
    username="test_lawyer",
    real_name="测试律师",
    law_firm=law_firm
)

# 创建客户
clients = [ClientFactory(name=f"测试客户{i}") for i in range(5)]

# 创建合同
contracts = [
    ContractFactory(
        name=f"测试合同{i}",
        law_firm=law_firm,
        assigned_lawyer=lawyer,
        case_type='civil',
        representation_stages=['first_trial', 'second_trial']
    ) for i in range(3)
]

# 创建案件
cases = [
    CaseFactory(
        name=f"测试案件{i}",
        contract=contract
    ) for i, contract in enumerate(contracts)
]

print(f"✅ 创建了 {len(clients)} 个客户")
print(f"✅ 创建了 {len(contracts)} 个合同")
print(f"✅ 创建了 {len(cases)} 个案件")
```

### 3. 启动 Django 开发服务器

```bash
# 在另一个终端窗口
cd backend
source venv312/bin/activate
python manage.py runserver
```

确保服务器运行在 `http://localhost:8000`

### 4. 确认测试账号

确保以下测试账号存在：
- **用户名**: 法穿
- **密码**: 1234qwer

如果不存在，创建超级用户：

```bash
python manage.py createsuperuser
```

## 运行测试

### 运行所有测试

```bash
cd backend/tests/admin
python run_admin_tests.py
```

### 运行单个测试套件

```bash
# 只运行冒烟测试
python -c "import asyncio; from test_smoke import TestAdminSmoke; from run_admin_tests import run_test_class; asyncio.run(run_test_class(TestAdminSmoke, '冒烟测试'))"

# 只运行案件管理测试
python -c "import asyncio; from test_case_admin import TestCaseAdmin; from run_admin_tests import run_test_class; asyncio.run(run_test_class(TestCaseAdmin, '案件管理测试'))"
```

### 使用 Playwright MCP（推荐）

如果你已经配置了 Playwright MCP，可以直接在 Kiro 中运行测试：

1. 打开 Kiro
2. 在聊天中输入：`运行 Admin 测试`
3. Kiro 会使用 Playwright MCP 执行测试

## 测试说明

### 冒烟测试 (test_smoke.py)

**目标**: 确保所有 Admin 页面可以访问，不返回 500 错误

**测试内容**:
- 访问所有模块的列表页
- 检查页面是否正常加载
- 检查是否有错误消息
- 测试登录和登出功能

**预期结果**: 所有页面返回 200 状态码

### 案件管理测试 (test_case_admin.py)

**目标**: 测试最复杂的 Admin 功能

**测试内容**:
1. **基础 CRUD**
   - 创建案件（基本字段）
   - 编辑案件
   - 删除案件
   - 搜索案件
   - 过滤案件

2. **内联表单**
   - 创建案件并添加当事人
   - 创建案件并添加多个内联（当事人、指派、编号）
   - 测试嵌套内联（案件日志 -> 附件）

3. **表单验证**
   - 阶段验证（当前阶段必须在代理阶段内）
   - 当事人唯一性验证（同一案件中当事人不能重复）

**复杂度**: ⭐⭐⭐⭐⭐

### 合同管理测试 (test_contract_admin.py) - 待创建

**目标**: 测试嵌套内联功能

**测试内容**:
- 创建合同
- 在合同中创建案件（嵌套内联）
- 在案件中添加当事人（二级嵌套）
- 代理阶段验证

**复杂度**: ⭐⭐⭐⭐⭐

### 财产保全询价测试 (test_preservation_quote_admin.py) - 待创建

**目标**: 测试自定义 Admin Action 和视图

**测试内容**:
- 创建询价任务
- 执行询价任务（Admin Action）
- 重试失败任务（Admin Action）
- 立即运行按钮（自定义视图）
- 查看报价详情（内联表单）

**复杂度**: ⭐⭐⭐⭐

## 测试结果

测试运行后会输出详细的结果：

```
======================================================================
🚀 Django Admin 稳定性测试
======================================================================
开始时间: 2024-12-01 10:00:00
======================================================================

======================================================================
📋 冒烟测试 - 页面访问
======================================================================

发现 3 个测试用例

[1/3] All List Pages Accessible... ✅ PASSED
[2/3] Admin Home Page... ✅ PASSED
[3/3] Logout... ✅ PASSED

======================================================================
📋 案件管理 - 功能测试
======================================================================

发现 12 个测试用例

[1/12] List Page Access... ✅ PASSED
[2/12] Create Case Basic... ✅ PASSED
[3/12] Create Case With Parties... ✅ PASSED
...

======================================================================
📊 测试总结
======================================================================

总计测试: 15
  ✅ 通过: 13
  ❌ 失败: 1
  ⏭️  跳过: 1

成功率: 86.7%

======================================================================
各测试套件结果:
======================================================================

冒烟测试 - 页面访问:
  总计: 3
  ✅ 通过: 3
  ❌ 失败: 0
  ⏭️  跳过: 0
  成功率: 100.0%

案件管理 - 功能测试:
  总计: 12
  ✅ 通过: 10
  ❌ 失败: 1
  ⏭️  跳过: 1
  成功率: 83.3%

======================================================================
❌ 失败的测试详情:
======================================================================

1. TestCaseAdmin.test_stage_validation
   类型: AssertionError
   错误: 没有显示错误消息

======================================================================
结束时间: 2024-12-01 10:05:30
======================================================================
```

## 扩展测试

### 添加新的测试类

1. 创建新的测试文件（例如 `test_contract_admin.py`）
2. 继承 `BaseAdminTest`
3. 实现测试方法（以 `test_` 开头）
4. 在 `run_admin_tests.py` 中添加到测试套件

示例：

```python
# test_contract_admin.py
from base_admin_test import BaseAdminTest

class TestContractAdmin(BaseAdminTest):
    """合同 Admin 测试"""
    
    async def test_create_contract(self):
        """测试创建合同"""
        await self.navigate_to_model('contracts', 'contract')
        await self.click_add_button()
        
        # 填写表单
        await self.fill_field('name', '测试合同')
        await self.select_option('law_firm', '1')
        await self.select_option('assigned_lawyer', '1')
        
        # 提交
        await self.submit_form()
        
        # 检查成功
        self.assert_true(
            await self.check_success_message(),
            "没有显示成功消息"
        )
```

然后在 `run_admin_tests.py` 中添加：

```python
from test_contract_admin import TestContractAdmin

test_suites = [
    (TestAdminSmoke, "冒烟测试 - 页面访问"),
    (TestCaseAdmin, "案件管理 - 功能测试"),
    (TestContractAdmin, "合同管理 - 功能测试"),  # 新增
]
```

### 添加性能测试

```python
async def test_list_page_performance(self):
    """测试列表页加载性能"""
    url = f"{self.ADMIN_URL}cases/case/"
    load_time = await self.measure_page_load_time(url)
    
    # 断言加载时间 < 2 秒
    self.assert_true(
        load_time < 2.0,
        f"列表页加载时间过长: {load_time:.2f}秒"
    )
    
    print(f"    ✅ 列表页加载时间: {load_time:.2f}秒")
```

## 常见问题

### 1. 测试失败：找不到元素

**原因**: 页面结构可能与预期不同

**解决方法**:
- 检查选择器是否正确
- 使用 `await self.take_screenshot('debug')` 截图调试
- 增加等待时间 `await self.page.wait_for_timeout(1000)`

### 2. 测试失败：超时

**原因**: 页面加载时间过长

**解决方法**:
- 增加超时时间 `timeout=30000`
- 检查网络连接
- 检查 Django 服务器是否正常运行

### 3. 测试跳过：没有测试数据

**原因**: 数据库中没有必要的测试数据

**解决方法**:
- 按照"准备测试数据"部分创建数据
- 或者在测试中动态创建数据

### 4. 内联表单测试失败

**原因**: 内联表单的选择器可能不同

**解决方法**:
- 检查 HTML 源码，确认内联表单的 class 和 id
- 调整 `add_inline_row()` 方法中的选择器

## 最佳实践

1. **测试隔离**: 每个测试应该独立，不依赖其他测试的结果
2. **清理数据**: 测试后清理创建的数据（或使用事务回滚）
3. **有意义的断言**: 使用清晰的断言消息
4. **截图调试**: 在关键步骤截图，方便调试
5. **性能监控**: 记录页面加载时间，发现性能问题

## 下一步

1. ✅ 完成冒烟测试
2. ✅ 完成案件管理测试
3. ⏳ 创建合同管理测试
4. ⏳ 创建财产保全询价测试
5. ⏳ 创建客户管理测试
6. ⏳ 创建律师管理测试
7. ⏳ 添加性能测试
8. ⏳ 添加并发测试
9. ⏳ 集成到 CI/CD

## 参考资料

- [Playwright 文档](https://playwright.dev/python/)
- [Django Admin 文档](https://docs.djangoproject.com/en/stable/ref/contrib/admin/)
- [测试计划文档](../admin_stability_test_plan.md)
