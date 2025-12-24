# Django Admin 稳定性测试执行计划

## 测试目标

使用 Playwright MCP 对整个 Django Admin 后台进行全面的稳定性测试，确保所有功能正常工作。

## 测试环境

- **测试账号**: 法穿
- **测试密码**: 1234qwer
- **Admin URL**: http://localhost:8000/admin/
- **测试工具**: Playwright MCP
- **浏览器**: Chromium (headless=False，方便观察)

## 测试模块清单

### 已发现的 Admin 类（共 22 个）

#### 1. Cases 模块（7 个）
- ✅ `CaseAdmin` - 案件管理（最复杂，5个内联）
- ✅ `CasePartyAdmin` - 案件当事人
- ✅ `CaseAssignmentAdmin` - 案件指派
- ✅ `CaseLogAdmin` - 案件日志
- ✅ `CaseLogAttachmentAdmin` - 案件日志附件
- ✅ `CaseNumberAdmin` - 案件编号
- ✅ `JudicialInfoAdmin` - 司法信息

#### 2. Contracts 模块（4 个）
- ✅ `ContractAdmin` - 合同管理（最复杂，4个内联+嵌套）
- ✅ `ContractFinanceLogAdmin` - 合同财务日志
- ✅ `ContractPaymentAdmin` - 合同支付
- ✅ `ContractReminderAdmin` - 合同提醒

#### 3. Client 模块（2 个）
- ✅ `ClientAdmin` - 客户管理
- ✅ `ClientIdentityDocAdmin` - 客户身份证件

#### 4. Organization 模块（4 个）
- ✅ `LawFirmAdmin` - 律所管理
- ✅ `LawyerAdmin` - 律师管理
- ✅ `TeamAdmin` - 团队管理
- ✅ `AccountCredentialAdmin` - 账号凭证

#### 5. Automation 模块（3 个）
- ✅ `PreservationQuoteAdmin` - 财产保全询价（复杂，自定义Action）
- ✅ `CourtTokenAdmin` - Token管理
- ✅ `TestCourtAdmin` - 测试工具（自定义视图）

#### 6. 其他（2 个）
- ✅ `TestToolAdmin` - 测试工具（已废弃）
- ✅ `InsuranceQuote` - 保险报价（内联）

## 测试阶段

### 阶段 1: 冒烟测试（预计 30 分钟）

**目标**: 确保所有 Admin 页面可以访问，不返回 500 错误

**测试内容**:
1. 登录 Admin
2. 访问所有模块的列表页（22 个）
3. 检查页面是否正常加载
4. 检查是否有错误消息

**测试文件**: `test_smoke.py` ✅ 已创建

**预期结果**: 所有页面返回 200 状态码，无错误消息

### 阶段 2: 核心 CRUD 测试（预计 2 小时）

**目标**: 测试核心模块的增删改查功能

**优先级模块**:
1. **CaseAdmin** - 案件管理
2. **ContractAdmin** - 合同管理
3. **ClientAdmin** - 客户管理
4. **LawyerAdmin** - 律师管理
5. **PreservationQuoteAdmin** - 财产保全询价

**测试内容**:
- 创建记录（填写必填字段）
- 编辑记录
- 删除记录
- 搜索功能
- 过滤功能

**测试文件**: 
- `test_case_admin.py` ✅ 已创建
- `test_contract_admin.py` ⏳ 待创建
- `test_client_admin.py` ⏳ 待创建
- `test_lawyer_admin.py` ⏳ 待创建
- `test_preservation_quote_admin.py` ⏳ 待创建

### 阶段 3: 内联表单测试（预计 2 小时）

**目标**: 测试复杂的内联表单功能

**测试模块**:
1. **CaseAdmin** - 5 个内联表单
   - CaseParty（当事人）
   - CaseAssignment（指派）
   - SupervisingAuthority（监管机关）
   - CaseNumber（案件编号）
   - CaseLog（案件日志，嵌套 CaseLogAttachment）

2. **ContractAdmin** - 4 个内联表单 + 嵌套
   - ContractParty（合同当事人）
   - ContractAssignment（合同指派）
   - Case（案件，嵌套 CaseParty）
   - ContractReminder（合同提醒）

3. **ClientAdmin** - 1 个内联表单
   - ClientIdentityDoc（身份证件）

4. **LawyerAdmin** - 1 个内联表单
   - AccountCredential（账号凭证）

**测试内容**:
- 创建主记录并添加内联记录
- 编辑内联记录
- 删除内联记录
- 测试嵌套内联（Contract -> Case -> CaseParty）

### 阶段 4: 表单验证测试（预计 1.5 小时）

**目标**: 测试自定义表单验证逻辑

**测试场景**:
1. **CaseAdmin** - 阶段验证
   - 当前阶段必须在合同的代理阶段内
   - 测试无效阶段提交

2. **CaseAdmin** - 当事人唯一性验证
   - 同一案件中当事人不能重复
   - 测试重复当事人提交

3. **ContractAdmin** - 代理阶段验证
   - 案件阶段必须在代理阶段内
   - 测试无效阶段组合

4. **LawyerAdmin** - 自定义表单验证
   - 测试必填字段验证
   - 测试字段格式验证

### 阶段 5: Admin Action 测试（预计 1 小时）

**目标**: 测试自定义 Admin Action

**测试模块**:
1. **PreservationQuoteAdmin**
   - `execute_quotes` - 执行询价任务
   - `retry_failed_quotes` - 重试失败任务

**测试内容**:
- 选择记录
- 执行 Admin Action
- 验证操作结果
- 检查成功/错误消息

### 阶段 6: 自定义视图测试（预计 1 小时）

**目标**: 测试自定义 URL 和视图

**测试模块**:
1. **PreservationQuoteAdmin**
   - 立即运行询价（自定义按钮）
   - 查看报价详情

2. **TestCourtAdmin**
   - 测试登录功能
   - 查看测试结果

**测试内容**:
- 访问自定义 URL
- 执行操作
- 验证结果
- 检查重定向

### 阶段 7: 性能测试（预计 1 小时）

**目标**: 测试 Admin 页面性能

**测试指标**:
- 列表页加载时间 < 2 秒
- 详情页加载时间 < 1 秒
- 保存操作响应时间 < 3 秒

**测试场景**:
- 大量数据的列表页（100+ 记录）
- 复杂内联表单的保存
- 搜索和过滤性能

### 阶段 8: 边界条件测试（预计 1 小时）

**目标**: 测试边界条件和异常情况

**测试场景**:
1. 访问不存在的记录 ID
2. 提交空表单
3. 提交超长字符串
4. 删除被引用的记录
5. 并发编辑同一记录

## 测试数据准备

### 方案 1: 使用现有数据（推荐）

如果数据库中已有测试数据，直接使用。

### 方案 2: 使用 Factory 生成数据

```python
# 在 Django shell 中执行
from apps.tests.factories import *

# 创建律所和律师
law_firm = LawFirmFactory(name="测试律所")
lawyer = LawyerFactory(
    username="test_lawyer",
    real_name="测试律师",
    law_firm=law_firm
)

# 创建客户
clients = [ClientFactory(name=f"测试客户{i}") for i in range(10)]

# 创建合同
contracts = [
    ContractFactory(
        name=f"测试合同{i}",
        law_firm=law_firm,
        assigned_lawyer=lawyer,
        case_type='civil',
        representation_stages=['first_trial', 'second_trial']
    ) for i in range(5)
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

## 测试执行步骤

### 步骤 1: 准备环境

```bash
# 1. 激活虚拟环境
source /Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/venv311/bin/activate

# 2. 确保 Django 服务器运行
cd backend
python manage.py runserver

# 3. 确认测试账号存在
# 用户名: 法穿
# 密码: 1234qwer
```

### 步骤 2: 运行冒烟测试

```bash
cd backend/tests/admin
python run_admin_tests.py --suite smoke
```

### 步骤 3: 运行核心功能测试

```bash
python run_admin_tests.py --suite crud
```

### 步骤 4: 运行完整测试

```bash
python run_admin_tests.py --all
```

## 测试文件结构

```
backend/tests/admin/
├── README.md                           # 测试说明
├── TESTING_PLAN.md                     # 本文件
├── base_admin_test.py                  # 测试基类 ✅
├── run_admin_tests.py                  # 主测试运行器 ✅
│
├── test_smoke.py                       # 冒烟测试 ✅
│
├── test_case_admin.py                  # 案件管理测试 ✅
├── test_contract_admin.py              # 合同管理测试 ⏳
├── test_client_admin.py                # 客户管理测试 ⏳
├── test_lawyer_admin.py                # 律师管理测试 ⏳
├── test_preservation_quote_admin.py    # 财产保全询价测试 ⏳
│
├── test_inline_forms.py                # 内联表单测试 ⏳
├── test_form_validation.py             # 表单验证测试 ⏳
├── test_admin_actions.py               # Admin Action 测试 ⏳
├── test_custom_views.py                # 自定义视图测试 ⏳
├── test_performance.py                 # 性能测试 ⏳
├── test_edge_cases.py                  # 边界条件测试 ⏳
│
└── screenshots/                        # 测试截图目录
```

## 问题记录模板

```markdown
## 问题 #001

**模块**: CaseAdmin
**严重程度**: 🔴 高 / 🟡 中 / 🟢 低
**类型**: 功能 / 性能 / UI / 安全
**发现时间**: 2024-12-01 10:30

**描述**: 
详细描述问题

**重现步骤**:
1. 步骤 1
2. 步骤 2
3. 步骤 3

**预期结果**: 
应该发生什么

**实际结果**: 
实际发生了什么

**截图**: 
[如果有]

**错误日志**: 
```
[如果有]
```

**影响范围**: 
影响哪些功能

**修复建议**: 
[如果有]

**状态**: 🔴 待修复 / 🟡 修复中 / 🟢 已修复
```

## 成功标准

### 必须达成（P0）
- ✅ 所有列表页可以访问（0 个 500 错误）
- ✅ 核心 CRUD 功能正常（Cases, Contracts, Clients）
- ✅ 内联表单基本功能正常
- ✅ 表单验证逻辑正确

### 应该达成（P1）
- ✅ Admin Action 正常执行
- ✅ 自定义视图正常工作
- ✅ 搜索和过滤功能正常
- ✅ 列表页加载时间 < 2 秒

### 可以达成（P2）
- ✅ 嵌套内联功能正常
- ✅ 详情页加载时间 < 1 秒
- ✅ 保存操作响应时间 < 3 秒
- ✅ 边界条件处理正确

## 测试报告模板

```markdown
# Django Admin 稳定性测试报告

**测试日期**: 2024-12-01
**测试人员**: Kiro AI
**测试环境**: macOS, Python 3.11, Django 5.2

## 测试总结

- **总测试数**: 150
- **通过**: 142
- **失败**: 5
- **跳过**: 3
- **成功率**: 94.7%

## 各阶段结果

### 阶段 1: 冒烟测试
- 总计: 22 个页面
- ✅ 通过: 22
- ❌ 失败: 0
- 成功率: 100%

### 阶段 2: 核心 CRUD 测试
- 总计: 50 个测试
- ✅ 通过: 48
- ❌ 失败: 2
- 成功率: 96%

### 阶段 3: 内联表单测试
- 总计: 30 个测试
- ✅ 通过: 28
- ❌ 失败: 2
- 成功率: 93.3%

### 阶段 4: 表单验证测试
- 总计: 20 个测试
- ✅ 通过: 19
- ❌ 失败: 1
- 成功率: 95%

### 阶段 5: Admin Action 测试
- 总计: 10 个测试
- ✅ 通过: 10
- ❌ 失败: 0
- 成功率: 100%

### 阶段 6: 自定义视图测试
- 总计: 8 个测试
- ✅ 通过: 8
- ❌ 失败: 0
- 成功率: 100%

### 阶段 7: 性能测试
- 总计: 5 个测试
- ✅ 通过: 5
- ❌ 失败: 0
- 成功率: 100%

### 阶段 8: 边界条件测试
- 总计: 5 个测试
- ✅ 通过: 2
- ❌ 失败: 0
- ⏭️  跳过: 3
- 成功率: 100%

## 发现的问题

### 🔴 高优先级问题（2 个）

#### 问题 #001: CaseAdmin 阶段验证失败
- **模块**: CaseAdmin
- **描述**: 当前阶段验证逻辑不正确
- **状态**: 🔴 待修复

#### 问题 #002: ContractAdmin 嵌套内联保存失败
- **模块**: ContractAdmin
- **描述**: 在合同中创建案件时，嵌套的当事人无法保存
- **状态**: 🔴 待修复

### 🟡 中优先级问题（3 个）

#### 问题 #003: PreservationQuoteAdmin 列表页加载慢
- **模块**: PreservationQuoteAdmin
- **描述**: 列表页加载时间超过 3 秒
- **状态**: 🟡 修复中

#### 问题 #004: ClientAdmin 搜索功能不准确
- **模块**: ClientAdmin
- **描述**: 搜索客户名称时结果不准确
- **状态**: 🟡 修复中

#### 问题 #005: LawyerAdmin 账号凭证内联显示问题
- **模块**: LawyerAdmin
- **描述**: 账号凭证内联表单显示不完整
- **状态**: 🟡 修复中

## 性能指标

| 页面 | 加载时间 | 目标 | 状态 |
|------|---------|------|------|
| Case 列表页 | 1.2s | < 2s | ✅ |
| Contract 列表页 | 1.5s | < 2s | ✅ |
| Client 列表页 | 0.8s | < 2s | ✅ |
| PreservationQuote 列表页 | 3.2s | < 2s | ❌ |
| Case 详情页 | 0.6s | < 1s | ✅ |
| Contract 详情页 | 0.9s | < 1s | ✅ |

## 建议

1. **优化 PreservationQuoteAdmin 列表页查询**
   - 使用 select_related 预加载关联数据
   - 添加数据库索引

2. **修复 CaseAdmin 阶段验证逻辑**
   - 重新实现验证逻辑
   - 添加单元测试

3. **修复 ContractAdmin 嵌套内联问题**
   - 检查 nested_admin 配置
   - 添加集成测试

4. **改进 ClientAdmin 搜索功能**
   - 优化搜索字段配置
   - 添加全文搜索

5. **修复 LawyerAdmin 内联显示问题**
   - 检查内联表单配置
   - 调整字段显示

## 下一步行动

1. 🔴 修复高优先级问题（预计 2 天）
2. 🟡 修复中优先级问题（预计 3 天）
3. ✅ 回归测试（预计 1 天）
4. 📝 更新文档（预计 0.5 天）
5. 🚀 部署到生产环境

## 附录

### 测试环境详情
- Python: 3.11.5
- Django: 5.2.0
- Playwright: 1.40.0
- 浏览器: Chromium 120.0.6099.109

### 测试数据统计
- 律所: 1 个
- 律师: 5 个
- 客户: 10 个
- 合同: 5 个
- 案件: 10 个
- 财产保全询价: 3 个
```

## 时间估算

| 阶段 | 预计时间 | 实际时间 | 备注 |
|------|---------|---------|------|
| 阶段 1: 冒烟测试 | 30 分钟 | - | |
| 阶段 2: 核心 CRUD 测试 | 2 小时 | - | |
| 阶段 3: 内联表单测试 | 2 小时 | - | |
| 阶段 4: 表单验证测试 | 1.5 小时 | - | |
| 阶段 5: Admin Action 测试 | 1 小时 | - | |
| 阶段 6: 自定义视图测试 | 1 小时 | - | |
| 阶段 7: 性能测试 | 1 小时 | - | |
| 阶段 8: 边界条件测试 | 1 小时 | - | |
| **总计** | **10 小时** | - | |

## 联系方式

如有问题，请联系：
- **测试负责人**: Kiro AI
- **项目负责人**: 法穿
