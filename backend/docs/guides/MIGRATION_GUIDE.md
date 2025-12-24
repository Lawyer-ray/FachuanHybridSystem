# 项目结构迁移指南

本指南帮助团队成员适应新的项目结构，快速了解变化并调整工作流程。

## 📋 目录

- [迁移概述](#迁移概述)
- [主要变化](#主要变化)
- [文件位置变化](#文件位置变化)
- [导入路径变化](#导入路径变化)
- [工作流程调整](#工作流程调整)
- [常见问题](#常见问题)
- [迁移清单](#迁移清单)

## 🎯 迁移概述

### 为什么要迁移？

项目结构优化的目标：

1. **提高一致性**：所有 Django app 遵循统一的目录结构
2. **改善可维护性**：测试、文档、脚本分类清晰
3. **降低复杂度**：简化根目录，只保留必要文件
4. **提升可读性**：文件组织更加直观和可预测

### 迁移范围

本次迁移涉及：

- ✅ Django app 结构统一化
- ✅ 测试文件集中化
- ✅ 文档文件分类化
- ✅ 脚本文件分类化
- ✅ 根目录简洁化
- ✅ 导入路径更新

## 🔄 主要变化

### 1. Django App 结构变化

#### 旧结构
```
apps/cases/
├── __init__.py
├── models.py
├── admin.py          # 单个文件
├── api.py            # 单个文件
├── tests.py          # 单个文件
├── schemas.py
└── migrations/
```

#### 新结构
```
apps/cases/
├── __init__.py
├── models.py
├── schemas.py
├── admin/            # 目录，按模型分文件
│   ├── __init__.py
│   ├── case_admin.py
│   ├── caseparty_admin.py
│   └── ...
├── api/              # 目录，按资源分文件
│   ├── __init__.py
│   ├── case_api.py
│   ├── caseparty_api.py
│   └── ...
├── services/         # 目录，按领域分文件
│   ├── __init__.py
│   ├── case_service.py
│   ├── case_log_service.py
│   └── ...
├── migrations/
└── README.md         # 模块文档
```

**影响**：
- Admin 配置需要从 `admin.py` 导入改为从 `admin/` 目录导入
- API 路由需要从 `api.py` 导入改为从 `api/` 目录导入
- 测试文件移到了根级 `tests/` 目录

### 2. 测试目录变化

#### 旧结构
```
apps/cases/tests.py
apps/cases/tests/
apps/contracts/tests.py
apps/tests/factories/
apps/tests/mocks/
```

#### 新结构
```
tests/
├── unit/                    # 单元测试
│   ├── test_cases/
│   ├── test_contracts/
│   └── ...
├── integration/             # 集成测试
│   ├── test_case_api/
│   └── ...
├── property/                # Property-based tests
│   ├── test_case_properties/
│   └── ...
├── admin/                   # Admin 测试
├── factories/               # Test factories
│   ├── case_factories.py
│   ├── contract_factories.py
│   └── ...
├── mocks/                   # Mock objects
└── structure/               # 结构验证测试
```

**影响**：
- 测试文件路径变化
- 导入 factories 和 mocks 的路径变化
- pytest 配置需要更新

### 3. 文档目录变化

#### 旧结构
```
backend/
├── README.md
├── CODE_QUALITY_REVIEW.md
├── DATA_RECOVERY_GUIDE.md
├── PERFORMANCE_MONITORING_IMPLEMENTATION.md
├── QUICK_START.md
└── docs/
    ├── API.md
    ├── ARCHITECTURE_TRAINING.md
    └── ...
```

#### 新结构
```
backend/
├── README.md                # 主文档
└── docs/
    ├── README.md            # 文档索引
    ├── api/
    │   └── API.md
    ├── architecture/
    │   ├── ARCHITECTURE_TRAINING.md
    │   └── adr/
    ├── guides/
    │   ├── QUICK_START.md
    │   ├── CODE_REVIEW_CHECKLIST.md
    │   └── ...
    ├── operations/
    │   ├── DATA_RECOVERY_GUIDE.md
    │   └── PERFORMANCE_MONITORING_IMPLEMENTATION.md
    └── quality/
        └── CODE_QUALITY_REVIEW.md
```

**影响**：
- 文档链接需要更新
- 文档查找路径变化

### 4. 脚本目录变化

#### 旧结构
```
scripts/
├── test_admin_login.py
├── check_admin_config.py
├── court_captcha_userscript.js
└── ...
```

#### 新结构
```
scripts/
├── testing/                 # 测试脚本
│   ├── run_admin_tests.py
│   └── ...
├── development/             # 开发工具
│   ├── check_admin_config.py
│   └── ...
├── automation/              # 自动化脚本
│   ├── court_captcha_userscript.js
│   └── ...
└── refactoring/             # 重构工具
    ├── migrate_structure.py
    └── ...
```

**影响**：
- 脚本路径变化
- 需要更新脚本调用路径

## 📂 文件位置变化

### Admin 文件

| 旧位置 | 新位置 |
|--------|--------|
| `apps/cases/admin.py` | `apps/cases/admin/case_admin.py` |
| `apps/contracts/admin.py` | `apps/contracts/admin/contract_admin.py` |

### API 文件

| 旧位置 | 新位置 |
|--------|--------|
| `apps/cases/api.py` | `apps/cases/api/case_api.py` |
| `apps/contracts/api.py` | `apps/contracts/api/contract_api.py` |

### 测试文件

| 旧位置 | 新位置 |
|--------|--------|
| `apps/cases/tests.py` | `tests/unit/test_cases/` |
| `apps/cases/tests/test_case_api.py` | `tests/integration/test_case_api/` |
| `apps/tests/factories/case_factories.py` | `tests/factories/case_factories.py` |

### 文档文件

| 旧位置 | 新位置 |
|--------|--------|
| `CODE_QUALITY_REVIEW.md` | `docs/quality/CODE_QUALITY_REVIEW.md` |
| `DATA_RECOVERY_GUIDE.md` | `docs/operations/DATA_RECOVERY_GUIDE.md` |
| `QUICK_START.md` | `docs/guides/QUICK_START.md` |
| `docs/API.md` | `docs/api/API.md` |

### 脚本文件

| 旧位置 | 新位置 |
|--------|--------|
| `scripts/test_admin_login.py` | `scripts/testing/test_admin_login.py` |
| `scripts/check_admin_config.py` | `scripts/development/check_admin_config.py` |
| `scripts/court_captcha_userscript.js` | `scripts/automation/court_captcha_userscript.js` |

## 🔗 导入路径变化

### Admin 导入

#### 旧代码
```python
from apps.cases.admin import CaseAdmin
```

#### 新代码
```python
from apps.cases.admin import CaseAdmin  # 从 __init__.py 导入
# 或
from apps.cases.admin.case_admin import CaseAdmin  # 直接导入
```

### API 导入

#### 旧代码
```python
from apps.cases.api import router as case_router
```

#### 新代码
```python
from apps.cases.api import case_router  # 从 __init__.py 导入
# 或
from apps.cases.api.case_api import router as case_router  # 直接导入
```

### 测试导入

#### 旧代码
```python
from apps.tests.factories import CaseFactory
from apps.tests.mocks import MockService
```

#### 新代码
```python
from tests.factories.case_factories import CaseFactory
from tests.mocks.service_mocks import MockService
```

### Service 导入

#### 旧代码
```python
# Service 可能在 models.py 或单独文件中
from apps.cases.models import CaseService
```

#### 新代码
```python
from apps.cases.services import CaseService  # 从 __init__.py 导入
# 或
from apps.cases.services.case_service import CaseService  # 直接导入
```

## 🛠️ 工作流程调整

### 1. 创建新功能

#### 旧流程
```bash
# 1. 在 app 目录下创建文件
touch apps/myapp/admin.py
touch apps/myapp/api.py
touch apps/myapp/tests.py
```

#### 新流程
```bash
# 1. 在相应子目录下创建文件
touch apps/myapp/admin/mymodel_admin.py
touch apps/myapp/api/mymodel_api.py

# 2. 在 tests/ 目录下创建测试
touch tests/unit/test_myapp/test_mymodel_service.py
touch tests/integration/test_myapp_api/test_mymodel_api.py

# 3. 更新 __init__.py
# apps/myapp/admin/__init__.py
# apps/myapp/api/__init__.py
```

### 2. 运行测试

#### 旧命令
```bash
# 运行特定 app 的测试
pytest apps/cases/tests/

# 运行特定测试文件
pytest apps/cases/tests/test_case_service.py
```

#### 新命令
```bash
# 运行特定模块的单元测试
pytest tests/unit/test_cases/

# 运行特定模块的集成测试
pytest tests/integration/test_case_api/

# 运行特定测试文件
pytest tests/unit/test_cases/test_case_service.py
```

### 3. 查找文档

#### 旧方式
```bash
# 文档散落在根目录和 docs/ 目录
ls *.md
ls docs/*.md
```

#### 新方式
```bash
# 查看文档索引
cat docs/README.md

# 按类型查找
ls docs/api/          # API 文档
ls docs/architecture/ # 架构文档
ls docs/guides/       # 开发指南
ls docs/operations/   # 运维文档
ls docs/quality/      # 质量文档
```

### 4. 使用脚本

#### 旧方式
```bash
# 脚本在根目录
python scripts/check_admin_config.py
```

#### 新方式
```bash
# 脚本按功能分类
python scripts/development/check_admin_config.py
python scripts/testing/run_admin_tests.py
python scripts/refactoring/migrate_structure.py
```

## ❓ 常见问题

### Q1: 我的代码导入失败了怎么办？

**A**: 检查以下几点：

1. **确认文件位置**：文件是否已迁移到新位置
2. **更新导入路径**：使用新的导入路径
3. **检查 __init__.py**：确保 `__init__.py` 正确导出
4. **运行导入更新工具**：
   ```bash
   python scripts/refactoring/update_imports.py
   ```

### Q2: 测试找不到 fixtures 怎么办？

**A**: 检查以下几点：

1. **conftest.py 位置**：确保 `tests/conftest.py` 存在
2. **fixtures 导入**：从正确的位置导入 fixtures
3. **pytest 配置**：检查 `pytest.ini` 配置是否正确

### Q3: 如何快速找到某个文件？

**A**: 使用以下方法：

1. **按类型查找**：
   - Admin 配置 → `apps/*/admin/`
   - API 路由 → `apps/*/api/`
   - Service → `apps/*/services/`
   - 测试 → `tests/`
   - 文档 → `docs/`
   - 脚本 → `scripts/`

2. **使用搜索工具**：
   ```bash
   # 查找文件
   find . -name "case_admin.py"
   
   # 搜索内容
   grep -r "CaseAdmin" apps/
   ```

### Q4: 旧的导入路径还能用吗？

**A**: 部分可以，但建议更新：

- **Admin/API 导入**：通过 `__init__.py` 仍然可以使用旧路径
- **测试导入**：需要更新为新路径
- **建议**：统一使用新路径，避免混淆

### Q5: 如何验证迁移是否成功？

**A**: 运行验证脚本：

```bash
# 验证项目结构
python scripts/refactoring/structure_validator.py

# 运行所有测试
make test

# 检查导入
python scripts/refactoring/update_imports.py --scan-only
```

## ✅ 迁移清单

使用此清单确保完成所有迁移步骤：

### 代码迁移

- [ ] 更新 Admin 导入路径
- [ ] 更新 API 导入路径
- [ ] 更新 Service 导入路径
- [ ] 更新测试导入路径（factories, mocks）
- [ ] 更新文档链接
- [ ] 更新脚本调用路径

### 测试验证

- [ ] 运行所有单元测试
- [ ] 运行所有集成测试
- [ ] 运行 Property-based tests
- [ ] 运行结构验证测试
- [ ] 检查测试覆盖率

### 文档更新

- [ ] 阅读新的 README.md
- [ ] 阅读 docs/README.md
- [ ] 阅读 scripts/README.md
- [ ] 阅读本迁移指南
- [ ] 更新个人笔记和文档

### 工作流程

- [ ] 熟悉新的目录结构
- [ ] 更新 IDE 配置（如果需要）
- [ ] 更新书签和快捷方式
- [ ] 更新团队文档

### 工具配置

- [ ] 更新 pytest 配置
- [ ] 更新 IDE 项目配置
- [ ] 更新 git hooks（如果有）
- [ ] 更新 CI/CD 配置（如果有）

## 📚 参考资源

### 文档

- [项目 README](../../README.md) - 项目概述和快速开始
- [文档索引](../README.md) - 所有文档的索引
- [脚本使用说明](../../scripts/README.md) - 脚本分类和使用
- [架构培训](../architecture/ARCHITECTURE_TRAINING.md) - 架构设计详解

### 工具

- [结构验证器](../../scripts/refactoring/structure_validator.py) - 验证项目结构
- [导入更新工具](../../scripts/refactoring/update_imports.py) - 更新导入路径
- [迁移工具](../../scripts/refactoring/migrate_structure.py) - 结构迁移工具

### 规范

- [Django Python 专家规范](../../../.kiro/steering/django-python-expert.md) - 完整的开发规范
- [代码审查清单](CODE_REVIEW_CHECKLIST.md) - 代码审查标准
- [重构最佳实践](../architecture/REFACTORING_BEST_PRACTICES.md) - 重构指导

## 🤝 获取帮助

如果在迁移过程中遇到问题：

1. **查看文档**：先查看相关文档和本指南
2. **运行验证工具**：使用验证脚本检查问题
3. **查看示例**：参考已迁移的模块
4. **寻求帮助**：联系团队负责人或技术负责人

### 联系方式

- **技术问题**：技术负责人
- **流程问题**：项目经理
- **紧急问题**：团队负责人

## 📝 反馈

欢迎提供反馈和建议：

- 发现文档错误或不清楚的地方
- 遇到迁移问题
- 有改进建议

请通过以下方式反馈：
- 提交 Issue
- 发送邮件
- 团队会议讨论

---

**最后更新**：2024-01

**维护者**：开发团队

**版本**：1.0
