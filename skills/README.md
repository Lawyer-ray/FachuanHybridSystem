# Skills

Skills 目录，存放所有可复用的技能模块和工作流。

## 目录结构

```
skills/
├── CLAUDE.md                  # 开发规范
├── README.md                  # 本文件
└── {工作流名称}/              # 工作流目录
    ├── README.md              # 工作流说明
    ├── CHANGELOG.md           # 工作流变更日志
    └── {skill名称}/           # Skill 目录
        ├── README.md          # Skill 说明
        ├── CHANGELOG.md       # Skill 变更日志
        └── *.py               # 实现代码
```

## 工作流列表

| 工作流 | 说明 | Skills 数量 |
|--------|------|-------------|
| [合同处理](./合同处理/) | 合同文档处理工作流 | 2 |

## Skills 列表

| 工作流 | Skill | 说明 | 版本 |
|--------|-------|------|------|
| 合同处理 | [doc转docx](./合同处理/doc转docx/) | 将 .doc 转换为 .docx | 1.0.0 |
| 合同处理 | [合同自动编号](./合同处理/合同自动编号/) | 将手动编号转换为 Word 自动编号 | 1.1.0 |

## 使用方式

### 命令行调用

```bash
# doc转docx
python -m skills.合同处理.doc转docx /path/to/document.doc

# 合同自动编号
python -m skills.合同处理.合同自动编号 /path/to/document.docx

# 指定格式
python -m skills.合同处理.合同自动编号 /path/to/document.docx --format chinese
python -m skills.合同处理.合同自动编号 /path/to/document.docx --format decimal
```

### 在 Claude 中调用

```
/doc转docx /path/to/document.doc
/合同自动编号 /path/to/document.docx
```

## 创建新 Skill

### 目录结构

```
skills/
└── {工作流名称}/
    ├── README.md
    ├── CHANGELOG.md
    └── {skill名称}/
        ├── README.md
        ├── CHANGELOG.md
        ├── __init__.py
        ├── formats.py
        ├── detector.py
        ├── converter.py
        ├── utils.py
        └── cli.py
```

### 开发规范

详见 [CLAUDE.md](./CLAUDE.md)

## 命名规范

- **工作流目录**：中文，描述性名称（如 `合同处理`、`案件处理`）
- **Skill 目录**：中文，动词+名词（如 `合同自动编号`、`合同格式调整`）
- **Python 文件**：小写字母，单词用下划线分隔
- **版本号**：遵循 [语义化版本](https://semver.org/lang/zh-CN/)

## 变更日志

每个工作流和 Skill 都有独立的 CHANGELOG.md，记录所有变更。
