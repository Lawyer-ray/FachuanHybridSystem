# Changelog - 案件处理工作流

所有对此工作流的更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/),

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
