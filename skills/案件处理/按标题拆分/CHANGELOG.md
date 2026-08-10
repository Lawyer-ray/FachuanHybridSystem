# Changelog - 按标题拆分 Skill

所有对此 Skill 的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),

## [1.1.1] - 2026-08-10

### 修复

- 目录名由 `markdown-splitter/` 改回 `按标题拆分/`，与 `合同处理/` 下其它 skill 保持一致
- 模块执行入口回退为 `python -m skills.案件处理.按标题拆分.scripts`
- `SKILL.md` frontmatter 的 `name: markdown-splitter` 保留英文（与 `合同审查` 的 `name: contract-review` 一致）

## [1.1.0] - 2026-08-10

### 重构

- 符合 [Anthropic Agent Skills 规范](https://agentskills.io/specification) 的目录结构
- 新增 `SKILL.md`（含 YAML frontmatter：`name`、`description`、`metadata.author`、`metadata.version`），取代原 `README.md` 作为 skill 入口
- Python 代码迁移至 `scripts/` 子目录（`__init__.py` / `__main__.py` / `cli.py` / `converter.py` / `detector.py` / `formats.py` / `utils.py`）
- 模块执行入口更新为 `python -m skills.案件处理.markdown-splitter.scripts`
- 详细的拆分策略（三种模式工作原理、适用场景、`split_map.json` schema）拆分至 `references/SPLIT_STRATEGY.md`
- `tests/` 目录迁移至新结构
- 移除 `README.md`（由 `SKILL.md` 取代）

### 变更

- `__init__.py` 版本号升至 `1.1.0`

## [1.0.0] - 2026-08-10

### 新增

- 初始版本，将包含多份文书的 markdown 拆分为多个独立 .md 文件
- 三种工作模式:
  - **规则模式**(兜底):按 markdown 指定层级标题切分,适合标题规范的文档
  - **分析模式**(`--analyze`):输出候选标题结构 JSON,含标题文本/层级/上下文/噪音标记
  - **AI 映射模式**(`--apply-map`):接收 AI 生成的拆分方案,执行实际切分
- AI 辅助模式复用合同编号 skill 的成熟三步法(analyze → AI 判断 → apply-map)
- 候选标题检测:识别 markdown 标题行(`#`-`######`)和全行加粗的短行
- 噪音片段识别:EMS 封套、填写说明等单独标记,文件名加 `00_noise_` 前缀
- 21 类法律文书类型关键词(起诉状/传票/判决书等),供 AI 判断参考
- 文件名清洗:去除非法字符、压缩空白、限制长度
- 序号补零命名,便于文件管理器排序
- 输出目录默认 `{stem}_split/`,自动创建

### 设计决策

- **不内置 LLM 调用**:遵循项目约定(用 trae/claude code 的 token,不用后端 LLM)
- **AI 辅助模式与合同编号 skill 一致**:输出 JSON → AI 判断 → 应用映射
- **规则模式仅作兜底**:实测真实案件材料标题层级混乱,规则无法准确切分
