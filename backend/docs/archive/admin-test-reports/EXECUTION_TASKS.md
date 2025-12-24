# Django Admin 稳定性测试 - 执行任务清单

## 任务概览

本文档列出了所有需要执行的测试任务，按优先级和依赖关系排序。

## 前置任务（必须完成）

### ✅ Task 0.1: 环境准备
- [x] 确认 Django 服务器运行在 http://localhost:8000
- [x] 确认测试账号存在（法穿 / 1234qwer）
- [x] 确认 Playwright MCP 已配置
- [x] 创建测试截图目录

### ⏳ Task 0.2: 测试数据准备
- [ ] 检查数据库中是否有足够的测试数据
- [ ] 如果没有，使用 Factory 生成测试数据
- [ ] 确认至少有以下数据：
  - 1 个律所
  - 3 个律师
  - 10 个客户
  - 5 个合同
  - 10 个案件
  - 3 个财产保全询价

**执行命令**:
```bash
cd backend
source venv311/bin/activate
python manage.py shell < tests/admin/scripts/create_test_data.py
```

## 阶段 1: 冒烟测试（P0 - 最高优先级）

### ✅ Task 1.1: 运行冒烟测试
- [x] 测试文件已创建: `test_smoke.py`
- [ ] 执行冒烟测试
- [ ] 记录所有无法访问的页面
- [ ] 截图保存证据

**执行命令**:
```bash
cd backend/tests/admin
python -c "import asyncio; from test_smoke import TestAdminSmoke; from run_admin_tests import run_test_class; asyncio.run(run_test_class(TestAdminSmoke, '冒烟测试'))"
```

**预期结果**: 所有 22 个 Admin 页面可以访问，无 500 错误

**如果失败**: 
1. 记录失败的页面
2. 检查 Django 日志
3. 修复后重新测试

## 阶段 2: 核心 CRUD 测试（P0 - 最高优先级）

### ✅ Task 2.1: 案件管理测试
- [x] 测试文件已创建: `test_case_admin.py`
- [ ] 执行案件管理测试
- [ ] 记录所有失败的测试
- [ ] 截图保存证据

**测试内容**:
- [ ] 列表页访问
- [ ] 创建基本案件
- [ ] 创建案件并添加当事人
- [ ] 创建案件并添加多个内联
- [ ] 编辑案件
- [ ] 删除案件
- [ ] 搜索案件
- [ ] 过滤案件
- [ ] 阶段验证
- [ ] 当事人唯一性验证

**执行命令**:
```bash
cd backend/tests/admin
python -c "import asyncio; from test_case_admin import TestCaseAdmin; from run_admin_tests import run_test_class; asyncio.run(run_test_class(TestCaseAdmin, '案件管理测试'))"
```

### ⏳ Task 2.2: 合同管理测试
- [ ] 创建测试文件: `test_contract_admin.py`
- [ ] 实现测试方法
- [ ] 执行合同管理测试
- [ ] 记录所有失败的测试

**测试内容**:
- [ ] 列表页访问
- [ ] 创建基本合同
- [ ] 在合同中创建案件（嵌套内联）
- [ ] 在案件中添加当事人（二级嵌套）
- [ ] 编辑合同
- [ ] 删除合同
- [ ] 代理阶段验证

### ⏳ Task 2.3: 客户管理测试
- [ ] 创建测试文件: `test_client_admin.py`
- [ ] 实现测试方法
- [ ] 执行客户管理测试
- [ ] 记录所有失败的测试

**测试内容**:
- [ ] 列表页访问
- [ ] 创建客户
- [ ] 添加身份证件（内联）
- [ ] 编辑客户
- [ ] 删除客户
- [ ] 搜索客户

### ⏳ Task 2.4: 律师管理测试
- [ ] 创建测试文件: `test_lawyer_admin.py`
- [ ] 实现测试方法
- [ ] 执行律师管理测试
- [ ] 记录所有失败的测试

**测试内容**:
- [ ] 列表页访问
- [ ] 创建律师
- [ ] 添加账号凭证（内联）
- [ ] 编辑律师
- [ ] 删除律师
- [ ] 搜索律师

### ⏳ Task 2.5: 财产保全询价测试
- [ ] 创建测试文件: `test_preservation_quote_admin.py`
- [ ] 实现测试方法
- [ ] 执行财产保全询价测试
- [ ] 记录所有失败的测试

**测试内容**:
- [ ] 列表页访问
- [ ] 创建询价任务
- [ ] 查看询价详情（内联报价）
- [ ] 执行询价任务（Admin Action）
- [ ] 重试失败任务（Admin Action）
- [ ] 立即运行按钮（自定义视图）

## 阶段 3: 内联表单测试（P1 - 高优先级）

### ⏳ Task 3.1: CaseAdmin 内联表单测试
- [ ] 测试所有 5 个内联表单
- [ ] 测试嵌套内联（CaseLog -> CaseLogAttachment）
- [ ] 记录所有失败的测试

**测试内容**:
- [ ] CaseParty 内联
- [ ] CaseAssignment 内联
- [ ] SupervisingAuthority 内联
- [ ] CaseNumber 内联
- [ ] CaseLog 内联（包含嵌套）

### ⏳ Task 3.2: ContractAdmin 内联表单测试
- [ ] 测试所有 4 个内联表单
- [ ] 测试嵌套内联（Contract -> Case -> CaseParty）
- [ ] 记录所有失败的测试

**测试内容**:
- [ ] ContractParty 内联
- [ ] ContractAssignment 内联
- [ ] Case 内联（包含嵌套 CaseParty）
- [ ] ContractReminder 内联

### ⏳ Task 3.3: 其他内联表单测试
- [ ] ClientAdmin - ClientIdentityDoc 内联
- [ ] LawyerAdmin - AccountCredential 内联
- [ ] PreservationQuoteAdmin - InsuranceQuote 内联

## 阶段 4: 表单验证测试（P1 - 高优先级）

### ⏳ Task 4.1: CaseAdmin 验证测试
- [ ] 测试阶段验证逻辑
- [ ] 测试当事人唯一性验证
- [ ] 记录所有失败的测试

**测试场景**:
- [ ] 提交无效阶段
- [ ] 提交重复当事人
- [ ] 提交空必填字段
- [ ] 提交超长字符串

### ⏳ Task 4.2: ContractAdmin 验证测试
- [ ] 测试代理阶段验证
- [ ] 测试案件阶段验证（在内联中）
- [ ] 记录所有失败的测试

**测试场景**:
- [ ] 提交无效代理阶段组合
- [ ] 在内联案件中提交无效阶段
- [ ] 提交空必填字段

### ⏳ Task 4.3: LawyerAdmin 验证测试
- [ ] 测试自定义表单验证
- [ ] 记录所有失败的测试

**测试场景**:
- [ ] 提交无效手机号
- [ ] 提交重复用户名
- [ ] 提交空必填字段

## 阶段 5: Admin Action 测试（P1 - 高优先级）

### ⏳ Task 5.1: PreservationQuoteAdmin Action 测试
- [ ] 测试 execute_quotes Action
- [ ] 测试 retry_failed_quotes Action
- [ ] 记录所有失败的测试

**测试场景**:
- [ ] 选择单个询价任务执行
- [ ] 选择多个询价任务执行
- [ ] 重试失败的任务
- [ ] 检查成功消息
- [ ] 检查错误消息

## 阶段 6: 自定义视图测试（P2 - 中优先级）

### ⏳ Task 6.1: PreservationQuoteAdmin 自定义视图测试
- [ ] 测试立即运行按钮
- [ ] 测试报价详情页
- [ ] 记录所有失败的测试

### ⏳ Task 6.2: TestCourtAdmin 自定义视图测试
- [ ] 测试测试登录功能
- [ ] 测试查看测试结果
- [ ] 记录所有失败的测试

## 阶段 7: 性能测试（P2 - 中优先级）

### ⏳ Task 7.1: 列表页性能测试
- [ ] 测试所有核心模块的列表页加载时间
- [ ] 记录超过 2 秒的页面

**测试页面**:
- [ ] CaseAdmin 列表页
- [ ] ContractAdmin 列表页
- [ ] ClientAdmin 列表页
- [ ] LawyerAdmin 列表页
- [ ] PreservationQuoteAdmin 列表页

### ⏳ Task 7.2: 详情页性能测试
- [ ] 测试所有核心模块的详情页加载时间
- [ ] 记录超过 1 秒的页面

### ⏳ Task 7.3: 保存操作性能测试
- [ ] 测试复杂表单的保存时间
- [ ] 记录超过 3 秒的操作

## 阶段 8: 边界条件测试（P3 - 低优先级）

### ⏳ Task 8.1: 异常输入测试
- [ ] 测试访问不存在的记录 ID
- [ ] 测试提交空表单
- [ ] 测试提交超长字符串
- [ ] 记录所有失败的测试

### ⏳ Task 8.2: 数据完整性测试
- [ ] 测试删除被引用的记录
- [ ] 测试并发编辑同一记录
- [ ] 记录所有失败的测试

## 问题修复任务

### ⏳ Task 9.1: 修复高优先级问题
- [ ] 修复所有 P0 问题
- [ ] 回归测试
- [ ] 更新文档

### ⏳ Task 9.2: 修复中优先级问题
- [ ] 修复所有 P1 问题
- [ ] 回归测试
- [ ] 更新文档

### ⏳ Task 9.3: 修复低优先级问题
- [ ] 修复所有 P2 问题
- [ ] 回归测试
- [ ] 更新文档

## 文档任务

### ⏳ Task 10.1: 生成测试报告
- [ ] 汇总所有测试结果
- [ ] 生成测试报告
- [ ] 发送给项目负责人

### ⏳ Task 10.2: 更新测试文档
- [ ] 更新 README.md
- [ ] 更新 TESTING_PLAN.md
- [ ] 添加测试最佳实践

## 执行顺序建议

### 第一天（4 小时）
1. Task 0.1: 环境准备（30 分钟）
2. Task 0.2: 测试数据准备（30 分钟）
3. Task 1.1: 运行冒烟测试（30 分钟）
4. Task 2.1: 案件管理测试（2 小时）
5. 修复发现的问题（30 分钟）

### 第二天（4 小时）
1. Task 2.2: 合同管理测试（1.5 小时）
2. Task 2.3: 客户管理测试（1 小时）
3. Task 2.4: 律师管理测试（1 小时）
4. 修复发现的问题（30 分钟）

### 第三天（4 小时）
1. Task 2.5: 财产保全询价测试（1 小时）
2. Task 3.1: CaseAdmin 内联表单测试（1 小时）
3. Task 3.2: ContractAdmin 内联表单测试（1 小时）
4. Task 3.3: 其他内联表单测试（30 分钟）
5. 修复发现的问题（30 分钟）

### 第四天（4 小时）
1. Task 4.1: CaseAdmin 验证测试（1 小时）
2. Task 4.2: ContractAdmin 验证测试（1 小时）
3. Task 4.3: LawyerAdmin 验证测试（30 分钟）
4. Task 5.1: PreservationQuoteAdmin Action 测试（1 小时）
5. 修复发现的问题（30 分钟）

### 第五天（4 小时）
1. Task 6.1: PreservationQuoteAdmin 自定义视图测试（1 小时）
2. Task 6.2: TestCourtAdmin 自定义视图测试（30 分钟）
3. Task 7.1: 列表页性能测试（1 小时）
4. Task 7.2: 详情页性能测试（30 分钟）
5. Task 7.3: 保存操作性能测试（30 分钟）
6. 修复发现的问题（30 分钟）

### 第六天（4 小时）
1. Task 8.1: 异常输入测试（1 小时）
2. Task 8.2: 数据完整性测试（1 小时）
3. Task 9.1: 修复高优先级问题（2 小时）

### 第七天（2 小时）
1. Task 9.2: 修复中优先级问题（1 小时）
2. Task 10.1: 生成测试报告（30 分钟）
3. Task 10.2: 更新测试文档（30 分钟）

## 快速开始

如果你想立即开始测试，执行以下命令：

```bash
# 1. 进入测试目录
cd backend/tests/admin

# 2. 运行冒烟测试（最快，30 分钟）
python run_admin_tests.py --suite smoke

# 3. 运行核心功能测试（2 小时）
python run_admin_tests.py --suite crud

# 4. 运行完整测试（10 小时）
python run_admin_tests.py --all
```

## 注意事项

1. **测试隔离**: 每个测试应该独立，不依赖其他测试的结果
2. **数据清理**: 测试后清理创建的数据（或使用事务回滚）
3. **截图调试**: 在关键步骤截图，方便调试
4. **性能监控**: 记录页面加载时间，发现性能问题
5. **问题记录**: 及时记录所有发现的问题

## 联系方式

如有问题，请联系：
- **测试负责人**: Kiro AI
- **项目负责人**: 法穿
