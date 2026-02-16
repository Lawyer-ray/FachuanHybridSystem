# 工具脚本目录

本目录包含用于开发、测试、自动化和重构的工具脚本，按功能分类组织。

## 📁 目录结构

```
scripts/
├── README.md                # 本文件 - 脚本使用说明
├── testing/                 # 测试相关脚本
│   ├── run_admin_tests.py
│   ├── verify_migration.py
│   └── ...
├── development/             # 开发工具脚本
│   ├── check_admin_config.py
│   ├── analyze_performance.py
│   └── ...
├── automation/              # 自动化脚本
│   ├── court_captcha_userscript.js
│   └── ...
└── refactoring/             # 重构和迁移工具
    ├── migrate_structure.py
    ├── update_imports.py
    └── ...
```

## 🔧 脚本分类

### 测试脚本 (`testing/`)

用于运行测试、生成测试数据和测试自动化的脚本。

#### 主要脚本

**`run_admin_tests.py`** - Admin 测试运行器
```bash
# 运行所有 Admin 测试
python scripts/testing/run_admin_tests.py

# 运行特定测试
python scripts/testing/run_admin_tests.py --test test_case_admin
```

**`verify_migration.py`** - 迁移验证脚本
```bash
# 验证项目结构迁移
python scripts/testing/verify_migration.py

# 生成验证报告
python scripts/testing/verify_migration.py --report
```

**其他测试脚本**：
- `test_admin_login.py` - 测试 Admin 登录功能
- `test_company_list.py` - 测试公司列表功能
- `test_full_quote_flow.py` - 测试完整询价流程
- `test_premium_from_client.py` - 测试保费计算
- `test_quote_with_service.py` - 测试询价服务集成

**使用场景**：
- 快速运行特定测试
- 生成测试报告
- 验证功能正确性
- CI/CD 集成

### 开发工具脚本 (`development/`)

辅助开发和调试的工具脚本。

#### 主要脚本

**`check_admin_config.py`** - Admin 配置检查
```bash
# 检查所有 Admin 配置
python scripts/development/check_admin_config.py

# 检查特定 app
python scripts/development/check_admin_config.py --app cases
```

**`analyze_performance.py`** - 性能分析
```bash
# 分析 API 性能
python scripts/development/analyze_performance.py

# 生成性能报告
python scripts/development/analyze_performance.py --report
```

**`check_db_performance.py`** - 数据库性能检查
```bash
# 检查慢查询
python scripts/development/check_db_performance.py

# 分析查询优化建议
python scripts/development/check_db_performance.py --analyze
```

**其他开发工具**：
- `debug_token_capture.py` - 调试 Token 捕获
- `example_use_token.py` - Token 使用示例
- `quick_test.py` - 快速测试运行器

**使用场景**：
- 检查配置正确性
- 性能问题排查
- 调试功能问题
- 快速验证代码

### 自动化脚本 (`automation/`)

用于自动化与外部系统交互的脚本。

#### 主要脚本

**`court_captcha_userscript.js`** - 法院系统验证码处理
```javascript
// 浏览器用户脚本，用于自动处理法院系统验证码
// 安装方法：参见 USERSCRIPT_GUIDE.md
```

**使用场景**：
- 自动化法院系统操作
- 验证码自动识别
- 浏览器自动化测试

**详细文档**：
- 安装和使用说明：[`USERSCRIPT_GUIDE.md`](USERSCRIPT_GUIDE.md)

### 重构工具 (`refactoring/`)

用于代码重构和项目结构迁移的工具脚本。

#### 主要脚本

**`migrate_structure.py`** - 项目结构迁移
```bash
# Dry-run 模式（预览迁移）
python scripts/refactoring/migrate_structure.py --dry-run

# 执行迁移
python scripts/refactoring/migrate_structure.py

# 回滚迁移
python scripts/refactoring/migrate_structure.py --rollback
```

**`update_imports.py`** - 导入路径更新
```bash
# 扫描并更新导入路径
python scripts/refactoring/update_imports.py

# 只扫描不更新
python scripts/refactoring/update_imports.py --scan-only

# 更新特定目录
python scripts/refactoring/update_imports.py --path apps/cases
```

**`structure_validator.py`** - 结构验证器
```bash
# 验证项目结构
python scripts/refactoring/structure_validator.py

# 验证特定 app
python scripts/refactoring/structure_validator.py --app cases

# 生成验证报告
python scripts/refactoring/structure_validator.py --report
```

**`cleanup_files.py`** - 文件清理
```bash
# 清理临时文件和缓存
python scripts/refactoring/cleanup_files.py

# 清理特定类型文件
python scripts/refactoring/cleanup_files.py --type cache

# Dry-run 模式
python scripts/refactoring/cleanup_files.py --dry-run
```

**其他重构工具**：
- `migrate_tests.py` - 测试文件迁移
- `migrate_docs.py` - 文档文件迁移
- `migrate_scripts.py` - 脚本文件迁移

**使用场景**：
- 项目结构重构
- 批量更新导入路径
- 文件迁移和清理
- 结构验证

## 🚀 使用指南

### 基本用法

大多数脚本可以直接从 backend 目录运行：

```bash
# 从 backend 目录运行
cd backend

# 运行测试脚本
python scripts/testing/run_admin_tests.py

# 运行开发工具
python scripts/development/check_admin_config.py

# 运行重构工具
python scripts/refactoring/migrate_structure.py --dry-run
```

### 虚拟环境

确保在虚拟环境中运行脚本：

```bash
# 激活虚拟环境
source venv312/bin/activate

# 运行脚本
python scripts/testing/run_admin_tests.py
```

### 常用命令

```bash
# 测试相关
make test                    # 运行所有测试
make test-cov                # 带覆盖率的测试
make test-fast               # 快速测试

# 性能分析
make analyze-performance     # 分析性能
make check-db-performance    # 检查数据库性能

# 代码质量
make lint                    # 代码检查
make format                  # 代码格式化
make type-check              # 类型检查
```

## 📝 添加新脚本

当添加新脚本时，请遵循以下规范：

### 1. 选择合适的目录

根据脚本功能选择目录：
- 测试相关 → `testing/`
- 开发工具 → `development/`
- 自动化 → `automation/`
- 重构工具 → `refactoring/`

### 2. 编写脚本文档

在脚本开头添加文档字符串：

```python
"""
脚本名称和简短描述

详细说明：
- 功能描述
- 使用场景
- 注意事项

使用方法：
    python scripts/category/script_name.py [options]

示例：
    # 基本用法
    python scripts/category/script_name.py
    
    # 带参数
    python scripts/category/script_name.py --option value

参数：
    --option: 参数说明
    --help: 显示帮助信息
"""
```

### 3. 添加命令行参数

使用 `argparse` 添加命令行参数：

```python
import argparse

def main():
    parser = argparse.ArgumentParser(description='脚本描述')
    parser.add_argument('--option', help='参数说明')
    parser.add_argument('--dry-run', action='store_true', help='预览模式')
    args = parser.parse_args()
    
    # 脚本逻辑
    pass

if __name__ == '__main__':
    main()
```

### 4. 更新 README

在本 README 中添加新脚本的说明：
- 脚本名称和用途
- 使用示例
- 参数说明

### 5. 编写测试

为脚本编写测试（如果适用）：

```python
# scripts/refactoring/test_script_name.py
import pytest
from .script_name import main_function

def test_main_function():
    result = main_function()
    assert result is not None
```

## 🔍 脚本索引

### 按功能查找

#### 我想...

**运行测试**
→ `testing/run_admin_tests.py`

**检查配置**
→ `development/check_admin_config.py`

**分析性能**
→ `development/analyze_performance.py`

**迁移项目结构**
→ `refactoring/migrate_structure.py`

**更新导入路径**
→ `refactoring/update_imports.py`

**验证项目结构**
→ `refactoring/structure_validator.py`

**清理临时文件**
→ `refactoring/cleanup_files.py`

**自动化法院系统**
→ `automation/court_captcha_userscript.js`

## ⚠️ 注意事项

### 安全提示

1. **不要提交敏感信息**：脚本中不要包含密码、Token 等敏感信息
2. **使用环境变量**：敏感配置通过环境变量传递
3. **权限控制**：确保脚本有适当的文件权限

### 最佳实践

1. **Dry-run 模式**：重要操作先使用 dry-run 模式预览
2. **备份数据**：执行破坏性操作前备份数据
3. **日志记录**：记录脚本执行日志便于排查问题
4. **错误处理**：添加适当的错误处理和提示

### 常见问题

**Q: 脚本运行失败怎么办？**
A: 检查以下几点：
- 是否在虚拟环境中运行
- 是否有必要的权限
- 依赖是否已安装
- 查看错误日志

**Q: 如何调试脚本？**
A: 使用以下方法：
- 添加 `print()` 语句
- 使用 Python 调试器 `pdb`
- 查看日志文件
- 使用 `--verbose` 参数（如果支持）

**Q: 脚本可以在生产环境运行吗？**
A: 取决于脚本类型：
- 测试脚本：仅在测试环境
- 开发工具：仅在开发环境
- 迁移工具：需要充分测试后才能在生产环境运行
- 自动化脚本：根据具体情况决定

## 📞 联系方式

如有脚本相关问题，请联系：

- 测试脚本：测试负责人
- 开发工具：技术负责人
- 重构工具：架构负责人
- 其他问题：团队负责人

---

**最后更新**：2024-01

**维护者**：开发团队
