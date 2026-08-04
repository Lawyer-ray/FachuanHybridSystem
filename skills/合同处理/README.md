# 合同处理工作流

合同文档处理的完整工作流，包括格式转换、自动编号、格式调整、审查等步骤。

## 工作流程

1. **Step 0**: doc转docx - 将 .doc 转换为 .docx（如需要）
2. **Step 1**: 合同自动编号 - 将手动编号转换为 Word 自动编号
3. **Step 2**: 合同格式调整 - 调整合同格式（待实现）
4. **Step 3**: 合同审查 - 专业合同审查，输出三件套（✅ 可用）

## 使用方式

### 单独调用

```bash
# doc转docx（.doc → .docx）
python -m skills.合同处理.doc转docx /path/to/document.doc

# 合同自动编号
python -m skills.合同处理.合同自动编号 /path/to/document.docx

# 合同审查
/合同审查 /path/to/document.docx

# 在 Claude 中调用
/doc转docx /path/to/document.doc
/合同自动编号 /path/to/document.docx
/合同审查 /path/to/document.docx
```

### 工作流调用

```bash
# 调用整个工作流（待实现）
/合同处理 /path/to/document.doc
```

## Skills 列表

| Skill | 说明 | 版本 | 状态 |
|-------|------|------|------|
| [doc转docx](./doc转docx/) | 将 .doc 转换为 .docx | 1.0.0 | ✅ 可用 |
| [合同自动编号](./合同自动编号/) | 将手动编号转换为 Word 自动编号 | 1.1.0 | ✅ 可用 |
| 合同格式调整 | 调整合同格式 | - | 🚧 待实现 |
| [合同审查](./合同审查/) | 专业合同审查，输出三件套 | 1.0.0 | ✅ 可用 |

## 目录结构

```
合同处理/
├── README.md              # 本文件
├── CHANGELOG.md           # 工作流变更日志
├── doc转docx/           # Step 0: 格式转换
│   ├── README.md          # Skill 说明
│   ├── CHANGELOG.md       # Skill 变更日志
│   ├── __init__.py        # 入口文件
│   ├── converter.py       # 转换逻辑
│   ├── cli.py             # 命令行入口
│   └── __main__.py        # 模块执行入口
└── 合同自动编号/           # Step 1: 自动编号
    ├── README.md          # Skill 说明
    ├── CHANGELOG.md       # Skill 变更日志
    ├── __init__.py        # 入口文件
    ├── formats.py         # 格式定义
    ├── detector.py        # 编号检测
    ├── converter.py       # 编号转换
    ├── utils.py           # 工具函数
    ├── cli.py             # 命令行入口
    └── __main__.py        # 模块执行入口
└── 合同审查/               # Step 3: 合同审查
    ├── SKILL.md           # Claude 审查指令（核心）
    ├── README.md          # Skill 说明
    ├── references/        # 参考资料
    │   └── risk-categories.md  # 风险分类详细参考
    └── scripts/           # 辅助脚本
        └── generate_report.py  # .docx 报告生成
```

## 依赖

依赖已在 `backend/pyproject.toml` 中声明，通过 `uv sync` 统一管理：

```bash
cd backend && uv sync
```

| 包 | 版本 | 用途 |
|---|---|---|
| python-docx | 1.2.0 | 读写 .docx 文件 |
| lxml | >=6.1.0 | XML 解析（python-docx 底层依赖） |

> ⚠️ 不要使用 `pip install` 安装依赖，项目的包管理工具是 `uv`。

## 限制

- doc转docx需要后端服务运行且 LibreOffice 已安装
- 合同自动编号不支持扫描版 PDF（需要 OCR）
- 复杂的表格内编号可能需要手动调整

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
