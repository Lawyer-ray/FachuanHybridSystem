# Changelog - 合同自动编号 Skill

所有对此 skill 的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0)，

## [1.4.0] - 2026-08-07

### 修复

- **层级检测 Bug：（一）子标题后的内容段落全部被平铺到同一层级**
  - `detector.py`：`detect_chinese_sublevel()` 分离 `（一）`（中文数字带括号 → level 1）和 `（1）`（阿拉伯数字带括号 → level 2）的检测，原先共用一条正则导致 `（1）` 被误判为 level 1
  - `detector.py`：`detect_numbering_structure()` 中，`（一）` 型子标题检测为 level 1 后，`prev_level` 设为 `level + 1`（即 level 2），使后续无编号段落正确降为下一级，而非继承子标题的同级
  - `detector.py`：`has_level1_heading` 标志仅由 `（一）` 型子标题设置，不再被 `1.` 型内容段落误设（原先 `1.` 也会触发 `has_level1_heading = True`，导致后续 `1.` 段落错误降级）

### 新增

- `auditor.py`：新增 `validate_hierarchy()` 层级结构验证函数
  - 检测 `（一）` 子标题后的无编号内容段落是否错误地停留在同级（L1），应在下一级（L2）
  - `AuditReport` 新增 `hierarchy_issues` 字段
  - `audit_completeness()` 支持传入 `numbered_paras` 参数，执行层级结构验证

### 变更

- `converter.py`：`verify_numbering()` 将 `numbered_paras` 传给 `audit_completeness()`，审计发现的层级问题会覆盖 `all_valid` 为 False
- 版本号：`1.3.0` → `1.4.0`

## [1.3.0] - 2026-08-06

### 修复

- **致命 Bug：签名关键词误触发导致后续编号全部丢失**
  - `detector.py`：将子级编号检测移到签名检测**之前**，段落匹配到（一）（二）等子级编号时直接 `continue`，不再进入签名判断逻辑
  - `formats.py`：新增 `_has_number_prefix()` 函数 + 增强 `is_signature_section()`，行首有编号前缀（如"（四）"）的段落自动排除签名判定
  - 移除宽泛的 `'授权代表签字'` 关键词（长尾匹配导致正文条款被误判）
- **检查机制失效：遗漏的编号段落永远通过验证**
  - 旧 `verify_numbering()` 对"既不在编号列表也非签名"的段落设 `is_valid = True`
  - 新增 `auditor.py` 模块：对比原始文档和输出文档，**交叉验证**每个带手动编号前缀的段落是否在输出中设置了自动编号
  - `converter.py`：`verify_numbering()` 现在传入 `original_doc` 和 `format_type`，审计发现遗漏时主动报失败

### 新增

- `auditor.py`：自动审计模块
  - `audit_completeness()`：对比分析，检测"原文件有编号前缀但输出未设自动编号"的段落
  - `audit_numbering_gaps()`：检测编号序列连续性（如一、二、三 → 是否缺四）
  - 生成 AI 可读的审计摘要，方便进一步检查

### 变更

- `__init__.py`：`convert_contract_numbering()` 转换后自动运行审计，审计发现任何遗漏即标记为 `success=False`
- 版本号：`1.2.0` → `1.3.0`

## [1.2.0] - 2026-08-04

### 新增

- 支持纯数字格式：1. 1.1 1.1.1 1.1.1.1 1.1.1.1.1（五级标题）
- 用户选择功能：调用时询问用户选择编号格式
- 命令行参数 `--format` 支持直接指定格式

### 变更

- 重构代码结构，拆分为多个模块：
  - `formats.py`：格式定义
  - `detector.py`：编号检测
  - `converter.py`：编号转换
  - `utils.py`：工具函数
  - `cli.py`：命令行入口
- 更新 README 文档，说明两种格式的使用方法

## [1.0.0] - 2026-07-31

### 新增

- 初始版本发布
- 支持一、1.（1）① 四级编号格式
- 智能识别文档结构
  - 自动检测一级标题（一、二、三...）
  - 自动检测二级标题（（一）（二）...）
  - 自动检测三级编号（1. 2. 3...）
- 智能推断逻辑
  - 无编号段落自动推断为相应级别
  - 继承上一段落的编号级别
  - 检测"（一）"子标题后自动调整级别
- 排除规则
  - 签字盖章部分自动跳过
  - 以下无正文、签约页等关键词触发跳过
- 输出功能
  - 生成带自动编号的新文档
  - 显示转换映射供用户确认
  - 验证关键段落的编号设置

### 技术实现

- 使用 python-docx 库操作 Word 文档
- 使用 OOXML 自动编号格式
- 每个一级标题独立编号实例

### 已知限制

- 不支持扫描版 PDF（需要 OCR）
- 复杂的表格内编号可能需要手动调整
- 混合格式（如 1.1, 1.2, 2.）可能需要特殊处理
