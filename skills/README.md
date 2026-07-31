# Skills

Skills 目录，存放所有可复用的技能模块。

## 目录结构

```
skills/
├── README.md                    # 本文件
├── contract-numbering/          # 合同编号转换 skill
│   ├── README.md               # skill 说明文档
│   ├── CHANGELOG.md            # 变更日志
│   └── contract_numbering.py   # 实现代码
└── ...                         # 其他 skills
```

## Skills 列表

| Skill | 说明 | 版本 |
|-------|------|------|
| [contract-numbering](./contract-numbering/) | 合同文档自动编号转换 | 1.0.0 |

## 使用方式

### 命令行调用

```bash
python skills/contract-numbering/contract_numbering.py /path/to/document.docx
```

### 在 Claude 中调用

```
/contract-numbering /path/to/document.docx
```

## 创建新 Skill

### 目录结构

```
skills/
└── {skill-name}/
    ├── README.md           # 说明文档
    ├── CHANGELOG.md        # 变更日志
    ├── {skill_name}.py     # 实现代码
    └── tests/              # 测试文件（可选）
```

### README.md 模板

```markdown
# {Skill Name}

简短描述。

## 功能

- 功能 1
- 功能 2

## 使用方式

\`\`\`bash
# 命令行
python {skill_name}.py <args>

# Claude
/{skill-name} <args>
\`\`\`

## 参数

| 参数 | 说明 | 必填 |
|------|------|------|
| arg1 | 参数1说明 | 是 |
| arg2 | 参数2说明 | 否 |

## 输出

输出说明。

## 限制

- 限制 1
- 限制 2

## Changelog

详见 [CHANGELOG.md](./CHANGELOG.md)
```

### CHANGELOG.md 模板

```markdown
# Changelog - {Skill Name}

所有对此 skill 的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，

## [1.0.0] - YYYY-MM-DD

### 新增

- 初始版本发布

### 变更

- 无

### 修复

- 无
```

## 命名规范

- 目录名：小写字母，单词用连字符分隔（如 `contract-numbering`）
- 文件名：小写字母，单词用下划线分隔（如 `contract_numbering.py`）
- 版本号：遵循 [语义化版本](https://semver.org/lang/zh-CN/)（如 `1.0.0`）

## 变更日志规范

每个 skill 的 CHANGELOG.md 应该记录：

1. **新增**：新功能
2. **变更**：现有功能的更改
3. **修复**：Bug 修复
4. **移除**：删除的功能
5. **安全**：安全相关的更改

每次修改 skill 时，都应该更新对应的 CHANGELOG.md。
