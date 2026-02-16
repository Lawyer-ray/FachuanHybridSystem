# 📄 文书模块 (Documents)

文书模块负责文书模板管理、占位符渲染、证据材料处理与导出、文件夹模板/目录结构规则，以及面向案件/合同/诉讼场景的文书生成流水线。

## 📚 模块概述

本模块提供：
- 文书模板与文件夹模板管理（Admin + API）
- 占位符体系（placeholder registry、提取、渲染、使用统计）
- 证据材料管理、合并、导出与清单生成
- 生成流水线：上下文构建 → 模板匹配 → 渲染 → 打包 → 输出存储
- Prompt 版本与文书生成任务编排（部分与 LLM/诉讼文书链路协作）

## 📁 目录结构（简要）

```
documents/
├── api/                # Ninja API：模板/生成/证据/占位符/文件夹模板
├── admin/              # Django Admin：模板、证据、占位符、审计日志等
├── models/             # 模型：template/evidence/generation/placeholder/prompt_version...
├── services/           # 业务服务：模板、证据、文件夹模板、生成流水线、占位符
├── usecases/           # 用例编排（例如 folder_template）
├── presenters/         # 展示层辅助（例如模板名呈现）
├── management/commands # 初始化与修复命令
└── docx_templates/     # 内置 docx 模板资源（含示例与默认模板）
```

## 🔑 核心入口

- API
  - `api/document_api.py`、`api/generation_api.py`、`api/evidence_api.py`、`api/placeholder_api.py`
- 模板与占位符
  - `services/document_template/*`、`services/placeholders/*`、`services/template_matching_service.py`
- 生成流水线
  - `services/generation/pipeline/*`、`services/generation/*_generation_service.py`
- 证据与导出
  - `services/evidence/*`、`services/evidence_export_service.py`

## 🧪 测试建议

- 生成链路：优先对 context_builder/template_matcher/renderer 做单元测试（不依赖外部网络）  
- 占位符：对 registry 与 placeholder service 的输入输出做属性测试，保证幂等与可序列化  
- 证据导出：对合并/导出流程做最小回归测试（文件 IO 可使用临时目录）

