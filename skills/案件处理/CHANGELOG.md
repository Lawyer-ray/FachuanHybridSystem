# Changelog - 案件处理工作流

所有对此工作流的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),

## [1.2.1] - 2026-08-10

### 修复

- skill 目录名改回中文(`文件识别/` / `按标题拆分/`),与 `合同处理/` 下其它 skill 保持一致
  - 1.2.0 曾将目录名改为 kebab-case 英文(`file-recognition` / `markdown-splitter`),破坏了仓库既有约定
  - `SKILL.md` frontmatter 的 `name` 字段保留英文(与 `合同审查` 的 `name: contract-review` 一致)
- 模块路径相应回退:
  - `python -m skills.案件处理.file-recognition.scripts` → `python -m skills.案件处理.文件识别.scripts`
  - `python -m skills.案件处理.markdown-splitter.scripts` → `python -m skills.案件处理.按标题拆分.scripts`
- 同步更新所有文档和代码中的模块路径引用(README/SKILL/references/config.example/scripts docstring)

## [1.2.0] - 2026-08-10

### 重构

- 全部 skill 改造为符合 [Agent Skills Specification](https://agentskills.io/specification)
  - 每个 skill 入口为 `SKILL.md`(YAML frontmatter + 精简正文)
  - 可执行代码迁移到 `scripts/` 子目录
  - 参考文档迁移到 `references/` 子目录
  - 静态资源迁移到 `assets/` 子目录
  - 目录名改为 kebab-case(`file-recognition` / `markdown-splitter`),与 `name` 字段一致
- HTTP 客户端从 `requests` 改为 `httpx`(与后端 `httpx[http2]==0.28.1` 一致)
  - 公共客户端迁移到 `_shared/http_client.py`,跨 skill 复用
  - `APIClient` 支持上下文管理器(`with` 语法)
- 模块路径更新:
  - `python -m skills.案件处理.文件识别` → `python -m skills.案件处理.file-recognition.scripts`
  - `python -m skills.案件处理.按标题拆分` → `python -m skills.案件处理.markdown-splitter.scripts`
- 工作流目录结构调整:
  - `utils.py` → `_shared/http_client.py`
  - `config.example.py` 保留在工作流根目录,file-recognition/assets/ 下也有副本

### 工作流变更

- README.md 更新为新结构,标注 SKILL.md 为入口
- CHANGELOG.md 新增 1.2.0 重构记录

## [1.1.0] - 2026-08-10

### 新增

- 按标题拆分 skill v1.0.0
  - 将包含多份法律文书的 markdown 拆分为多个独立 .md(每份文书一个)
  - AI 辅助模式:`--analyze` 输出候选标题结构 JSON,`--apply-map` 应用 AI 拆分方案
  - 规则模式(兜底):按 markdown 指定层级标题切分
  - 候选标题检测:识别 `#`-`######` 标题行和全行加粗短行
  - 噪音片段识别:EMS 封套、填写说明等单独标记
  - 21 类法律文书类型关键词(起诉状/传票/判决书等),供 AI 判断参考
  - 复用合同编号 skill 的 AI 辅助三步法(analyze → AI 判断 → apply-map)
  - 端到端测试通过:真实案件材料 PDF(148712 字符)→ 13 个独立 md 文件

### 工作流变更

- 工作流程更新:Step 1 新增"按标题拆分"环节
- README.md 更新 Skills 列表和目录结构

## [1.0.0] - 2026-08-10

### 新增

- 创建案件处理工作流目录结构
- 工作流级公共工具 `utils.py`:
  - `APIClient`:后端 API 客户端,支持 JWT Token 和 Session 登录两种认证方式
  - `DocumentParsingClient`:文档解析 API 客户端,自动处理同步/异步轮询
  - `build_api_client()`:基于环境变量/参数构建客户端的工厂函数
- 文件识别 skill v1.0.0
  - 接入 `http://127.0.0.1:8002/api/v1/document-parsing/` 文档解析服务
  - 支持 15+ 种文件格式(PDF/DOC/DOCX/PPT/PPTX/XLS/XLSX/图片/OFD/RTF/HTML/CSV/TXT)
  - 自动选择合适的解析后端(textin/mineru/local)
  - 支持单文件和批量目录扫描
  - 异步任务自动轮询,同步结果直接返回
  - 统一输出 Markdown 格式,为后续 AI 分析做准备

### 工作流变更

- 创建 README.md 工作流说明,明确终极目标:案件材料 → 全套可用案件材料
- 创建 CHANGELOG.md 变更日志
