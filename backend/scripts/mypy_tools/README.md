# Mypy Tools - 类型错误修复工具包

## 概述

这个工具包提供了系统性修复 mypy 类型错误的基础设施，包括错误分析、批量修复和验证系统。

## 组件

### 1. ErrorAnalyzer - 错误分析器

分析和分类 mypy 错误输出。

```python
from mypy_tools import ErrorAnalyzer

analyzer = ErrorAnalyzer()
errors = analyzer.analyze(mypy_output)
by_type = analyzer.categorize_by_type(errors)
```

### 2. ValidationSystem - 验证系统

验证修复效果，运行 mypy 和测试。

```python
from mypy_tools import ValidationSystem

validator = ValidationSystem()
error_count, output = validator.run_mypy()
tests_passed = validator.run_tests()
```

### 3. BatchFixer - 批量修复基类

批量修复类型错误的抽象基类。

```python
from mypy_tools import BatchFixer, ErrorRecord, FixResult

class MyFixer(BatchFixer):
    def can_fix(self, error: ErrorRecord) -> bool:
        return error.error_code == 'type-arg'
    
    def fix_file(self, file_path: str, errors: list[ErrorRecord]) -> FixResult:
        # 实现修复逻辑
        pass

fixer = MyFixer(fix_pattern='my_pattern')
report = fixer.batch_fix(errors_by_file)
```

## 核心功能

### BatchFixer 提供的功能

1. **AST 解析**: `parse_ast(file_path)` - 解析 Python 代码为 AST
2. **文件备份**: `backup_file(file_path)` - 修复前自动备份
3. **文件恢复**: `restore_file(file_path)` - 失败时自动恢复
4. **错误恢复**: `fix_with_recovery()` - 带错误恢复的修复
5. **批量修复**: `batch_fix()` - 批量处理多个文件
6. **报告生成**: `generate_report()` - 生成修复报告

### 错误恢复机制

BatchFixer 自动处理修复失败的情况：

```python
# 自动备份 -> 尝试修复 -> 失败时恢复
result = fixer.fix_with_recovery(file_path, errors)
```

## 使用示例

完整的使用示例见 `test_batch_fixer.py`。

## 类型安全

所有代码都通过 `mypy --strict` 检查，确保完整的类型安全。
