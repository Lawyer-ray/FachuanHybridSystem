# 📄 文书模块（documents）

文书模板 / 文件夹模板 / 占位符体系管理 + 多场景生成流水线（合同、诉讼文书、授权委托材料、财产保全材料、案件模板下载、外部模板批量填充）。

> 证据清单（EvidenceList/EvidenceItem）模型已迁出到 `apps.evidence`，本 app 仅保留兼容层（`models/__init__.py` 延迟转发、`tasks.py` 转发到 evidence 的任务）。`PromptVersion` 模型已删除。

## 功能概述

- 文书模板 / 文件夹模板 / 绑定关系管理（`complete_defaults.json` 是初始化默认模板唯一数据源，Admin 修改后需同步导出）
- 占位符体系：七大类（basic/case/contract/litigation/party/lawyer/supplementary/authorization_materials/archive）+ registry/fallback/context_builder；代码占位符自动发现（code_placeholders/autodiscover）
- 生成流水线：上下文构建 → 模板匹配 → 渲染 → 打包 → 预览 → 命名（`generation/pipeline/`）
- 诉讼文书 LLM 生成（`generation/litigation_llm_generator.py`）与模板流水线并存
- 授权委托材料 / 财产保全材料 / 补充协议生成
- 外部模板体系：指纹 / 匹配 / 分析 / 填充 + 批量填充任务（BatchFillTask / FillRecord）
- 委托事项规则（ProxyMatterRule）、判决书 PDF 提取器（judgment_pdf_extractor）、smart_fill、PDF 合并 infrastructure

## 目录结构

```
documents/
├── api/                # 9 个 router 挂 /documents 下：document、folder_template、placeholder、
│                       #   generation、litigation_generation、authorization_material、
│                       #   preservation_materials、case_template_download + /documents/external-templates
├── admin/              # 实际注册 6 个：DocumentTemplate、FolderTemplate、FolderBinding、
│                       #   ProxyMatterRule、ExternalTemplate、PlaceholderOverview
├── models/             # FolderTemplate、DocumentTemplate、DocumentTemplateFolderBinding、Placeholder、
│                       #   PlaceholderOverview、TemplateAuditLog、GenerationTask、GenerationConfig、
│                       #   ProxyMatterRule、ExternalTemplate、ExternalTemplateFieldMapping、
│                       #   BatchFillTask、FillRecord
├── services/           # document_template/、template/、folder_template/、placeholders/、code_placeholders/、
│                       #   generation/（各场景 service + pipeline + generators + prompts）、
│                       #   external_template/、smart_fill/、infrastructure/（PDF 合并）、extractors/
├── usecases/ + presenters/
├── management/commands # init_document_system、init_folder_templates、fix_folder_template_ids
└── docx_templates/     # 内置模板（0-用户自定义模板/1-合同模板/2-案件材料/3-归档模板 四个分类目录）
```

## 生成流水线

```
上下文构建（context_builder，含案件/合同/当事人/律师/占位符 fallback）
  → 模板匹配（services/template/template_matching_service.py）
  → 渲染（renderer，docxtpl）
  → 打包 / 预览 / 命名（packager / preview / naming）
```

## 默认模板数据同步

`services/document_template/complete_defaults.json` 由 `init_service.initialize_default_templates()` 消费。在 Admin 修改模板 / 文件夹 / 绑定后，需运行导出脚本（backend/scripts/export_template_defaults.py，本地工具）同步回 JSON，否则新环境初始化会用旧配置。

## 依赖模块

- `apps.core`（PDF 服务、占位符服务、LLM）、`apps.cases`、`apps.contracts`、`apps.client`、`apps.organization`、`apps.evidence`（兼容层）
