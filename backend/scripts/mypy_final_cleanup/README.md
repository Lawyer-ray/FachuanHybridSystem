# Mypy Final Cleanup - 修复工具基础设施

本目录包含用于修复剩余900个mypy类型错误的工具和脚本。

## 目录结构

```
mypy_final_cleanup/
├── __init__.py              # 包初始化
├── error_analyzer.py        # 错误分析器
├── backup_manager.py        # 文件备份和回滚管理
├── logger_config.py         # 日志配置
├── test_infrastructure.py   # 基础设施测试
└── README.md               # 本文档
```

## 核心组件

### 1. ErrorAnalyzer（错误分析器）

解析mypy输出，按错误类型分组，生成修复优先级报告。

**功能**：
- 解析mypy输出文件
- 按错误类型分组
- 生成P0-P3优先级报告
- 获取指定类型的可修复错误

**使用示例**：
```python
from scripts.mypy_final_cleanup.error_analyzer import ErrorAnalyzer

analyzer = ErrorAnalyzer()

# 解析mypy输出
errors = analyzer.parse_mypy_output("mypy_output.txt")

# 生成优先级报告
report = analyzer.generate_priority_report(errors)
print(report)

# 获取特定类型的错误
type_arg_errors = analyzer.get_fixable_errors("type-arg", errors)
```

### 2. BackupManager（备份管理器）

管理文件备份和回滚，确保修复失败时可以恢复。

**功能**：
- 备份文件（保持目录结构）
- 恢复单个文件
- 恢复所有文件
- 列出备份文件
- 清理备份

**使用示例**：
```python
from scripts.mypy_final_cleanup.backup_manager import BackupManager

manager = BackupManager()

# 备份文件
backup_path = manager.backup_file("apps/cases/models.py")

# 修改文件...

# 如果需要回滚
manager.restore_file("apps/cases/models.py")

# 或恢复所有文件
manager.restore_all()

# 清理备份
manager.clear_backups()
```

### 3. LoggerConfig（日志配置）

配置统一的日志记录器。

**功能**：
- 创建带时间戳的日志文件
- 同时输出到文件和控制台
- 统一的日志格式

**使用示例**：
```python
from scripts.mypy_final_cleanup.logger_config import setup_logger

logger = setup_logger("my_fixer")
logger.info("开始修复")
logger.error("修复失败")
```

## 错误优先级

### P0 - 高频基础错误（快速修复）
- `type-arg`: 泛型类型参数缺失
- `name-defined`: 名称未定义
- `redundant-cast`: 冗余类型转换
- `unused-ignore`: 无用的type: ignore

### P1 - 函数签名错误（中等修复）
- `no-untyped-def`: 函数缺少类型注解
- `assignment`: 赋值类型错误（如Optional默认值）
- `no-any-return`: 返回值类型为Any

### P2 - 属性访问错误（复杂修复）
- `attr-defined`: 属性未定义
- `union-attr`: Union类型属性访问

### P3 - 其他错误（按需修复）
- `no-redef`: 变量重定义
- 其他低频错误

## 测试

运行基础设施测试：

```bash
cd backend
source venv312/bin/activate
python -m scripts.mypy_final_cleanup.test_infrastructure
```

## 日志位置

日志文件保存在 `backend/logs/` 目录下，文件名格式：`{logger_name}_{timestamp}.log`

## 备份位置

备份文件保存在 `backend/.mypy_final_cleanup_backups/` 目录下，按会话时间戳分组。

## 注意事项

1. 所有修复操作前会自动备份文件
2. 修复失败时会自动回滚
3. 日志记录所有操作，便于追踪问题
4. 使用pathlib处理路径
5. 所有代码通过mypy --strict检查
