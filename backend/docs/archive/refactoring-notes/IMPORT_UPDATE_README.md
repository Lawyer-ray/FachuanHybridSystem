# 导入路径更新脚本使用指南

## 概述

`update_imports.py` 脚本用于自动更新 Python 文件中的导入路径，以适应项目结构重构后的新路径。

## 主要功能

1. **自动扫描**：扫描所有 Python 文件（apps/, tests/, scripts/）
2. **模式匹配**：使用正则表达式匹配旧的导入路径
3. **自动替换**：将旧路径替换为新路径
4. **语法验证**：验证更新后的文件语法是否正确
5. **生成报告**：生成详细的更新报告

## 支持的导入路径更新

### 1. 测试文件导入

**旧路径：**
```python
from apps.cases.tests import CaseFactory
from apps.cases.tests.test_case_service import TestCaseService
import apps.cases.tests
```

**新路径：**
```python
from tests.unit.cases import CaseFactory
from tests.unit.cases.test_case_service import TestCaseService
import tests.unit.cases
```

### 2. Factories 导入

**旧路径：**
```python
from apps.tests.factories import CaseFactory
from apps.tests.factories.case_factories import CaseFactory
import apps.tests.factories
```

**新路径：**
```python
from tests.factories import CaseFactory
from tests.factories.case_factories import CaseFactory
import tests.factories
```

### 3. Mocks 导入

**旧路径：**
```python
from apps.tests.mocks import MockService
from apps.tests.mocks.service_mocks import MockService
import apps.tests.mocks
```

**新路径：**
```python
from tests.mocks import MockService
from tests.mocks.service_mocks import MockService
import tests.mocks
```

## 使用方法

### 1. Dry-run 模式（默认）

查看将要执行的更新，但不实际修改文件：

```bash
cd backend
python scripts/refactoring/update_imports.py
```

输出示例：
```
================================================================================
导入路径更新预览 (2 处更新)
================================================================================

📄 apps/tests/utils.py
   1 处更新

   行 20 [factories_imports]:
   - from apps.tests.factories import LawyerFactory
   + from tests.factories import LawyerFactory
```

### 2. 执行实际更新

```bash
cd backend
python scripts/refactoring/update_imports.py --execute
```

### 3. 只显示统计信息

```bash
cd backend
python scripts/refactoring/update_imports.py --stats-only
```

## 工作流程

1. **扫描阶段**
   - 扫描 `apps/`, `tests/`, `scripts/` 目录下的所有 `.py` 文件
   - 排除 `__pycache__`, `migrations`, `.hypothesis` 等目录

2. **分析阶段**
   - 逐行分析每个文件
   - 使用正则表达式匹配导入语句
   - 记录需要更新的导入

3. **更新阶段**（仅在 --execute 模式）
   - 按文件分组更新
   - 替换旧的导入路径为新路径
   - 保持文件的其他内容不变

4. **验证阶段**（仅在 --execute 模式）
   - 编译每个 Python 文件检查语法
   - 报告任何语法错误

5. **报告阶段**
   - 生成详细的更新报告
   - 保存到 `scripts/refactoring/import_update_report.md`

## 更新报告

脚本会生成一个详细的 Markdown 报告，包含：

- 统计信息（扫描文件数、更新文件数、更新总数）
- 更新模式统计（每种模式的更新次数）
- 详细更新列表（每个文件的具体更新内容）

报告位置：`backend/scripts/refactoring/import_update_report.md`

## 安全性

- **Dry-run 默认**：默认为 dry-run 模式，不会修改文件
- **语法验证**：更新后自动验证 Python 语法
- **详细日志**：显示每个更新的详细信息
- **错误处理**：捕获并报告所有错误

## 注意事项

### 1. 备份建议

虽然脚本有 dry-run 模式和语法验证，但建议在执行前：
- 提交当前更改到 Git
- 或创建项目备份

### 2. 手动检查

某些复杂的导入可能需要手动调整：
- Admin 文件的导入（需要知道具体模型名）
- API 文件的导入（需要知道具体资源名）
- Services 文件的导入（需要知道具体服务名）

### 3. 测试验证

更新后务必运行测试：
```bash
cd backend
pytest tests/ -v
```

### 4. 增量更新

如果项目很大，可以分批更新：
1. 先更新测试文件导入
2. 再更新 factories 导入
3. 最后更新 mocks 导入

## 扩展脚本

如果需要添加新的导入路径更新模式，编辑 `_define_import_patterns()` 方法：

```python
def _define_import_patterns(self) -> List[Tuple[str, str, str]]:
    return [
        # 添加新模式
        (
            "pattern_name",           # 模式名称
            r'old_pattern',           # 旧路径正则表达式
            r'new_pattern'            # 新路径替换模式
        ),
        # ...
    ]
```

## 故障排除

### 问题：脚本报告语法错误

**原因**：更新后的导入路径可能不正确

**解决**：
1. 检查报告中的具体错误
2. 手动修复有问题的导入
3. 重新运行脚本验证

### 问题：某些导入没有被更新

**原因**：导入格式不匹配预定义的模式

**解决**：
1. 检查导入语句的格式
2. 如果是新格式，添加新的匹配模式
3. 或手动更新这些导入

### 问题：更新后测试失败

**原因**：可能有循环导入或路径错误

**解决**：
1. 查看测试失败的具体错误
2. 检查相关文件的导入路径
3. 确保新路径指向正确的模块

## 相关文档

- [项目结构优化设计文档](../../.kiro/specs/backend-structure-optimization/design.md)
- [项目结构优化任务列表](../../.kiro/specs/backend-structure-optimization/tasks.md)
- [结构迁移脚本](./migrate_structure.py)
- [测试迁移脚本](./migrate_tests.py)

## 示例输出

### Dry-run 模式输出

```
================================================================================
导入路径更新脚本
================================================================================
模式: DRY RUN
根目录: /path/to/backend
================================================================================

扫描 Python 文件...
找到 287 个 Python 文件

分析导入路径...
扫描完成: 287 个文件
找到 2 处需要更新的导入

================================================================================
导入路径更新预览 (2 处更新)
================================================================================

📄 apps/tests/utils.py
   1 处更新

   行 20 [factories_imports]:
   - from apps.tests.factories import LawyerFactory
   + from tests.factories import LawyerFactory

================================================================================
总计: 2 个文件, 2 处更新
================================================================================

✅ Dry-run 完成！使用 --execute 参数执行实际更新。
```

### Execute 模式输出

```
================================================================================
导入路径更新脚本
================================================================================
模式: EXECUTE
根目录: /path/to/backend
================================================================================

扫描 Python 文件...
找到 287 个 Python 文件

分析导入路径...
扫描完成: 287 个文件
找到 2 处需要更新的导入

应用导入路径更新...
✓ 更新 apps/tests/utils.py (1 处)
✓ 更新 tests/admin/scripts/create_test_data.py (1 处)

✅ 成功更新 2 个文件

验证导入路径...
✅ 所有文件语法正确

✅ 报告已生成

================================================================================
✅ 更新完成！
   - 扫描文件: 287
   - 更新文件: 2
   - 更新总数: 2
================================================================================
```

## 总结

`update_imports.py` 脚本是项目结构重构的重要工具，它能够：

- ✅ 自动化导入路径更新
- ✅ 减少手动修改的错误
- ✅ 提供详细的更新报告
- ✅ 验证更新后的代码语法
- ✅ 支持 dry-run 模式安全预览

使用此脚本可以大大简化项目结构重构后的导入路径更新工作。
