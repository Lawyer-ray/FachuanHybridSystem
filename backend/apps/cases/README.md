# ⚖️ 案件管理（cases）

案件全生命周期管理：案件 CRUD 与一键建档、当事人、律师指派、案件授权、案件日志（附件/版本/提醒）、案件群聊、材料管理（云盘绑定/上传/分组排序）、文件夹生成/绑定/浏览/自动捕获、模板绑定与统一文书生成、案由/法院基础数据、诉讼费计算。

## 功能概述

- 案件 CRUD + `/cases/full` 一键建档（建档编号序列 CaseFilingNumberSequence 按年发号）
- 当事人（CaseParty，legal_status 法律地位）、律师指派（CaseAssignment）、案件授权（CaseAccessGrant）
- 案件日志：附件（物理文件清理信号）、日志版本、提醒属性代理到 reminders app
- 案件群聊（CaseChat / ChatAuditLog，经 automation 的 ChatProviderFactory 发多平台通知）
- 材料管理：CaseMaterial 体系（category/side/type/group_order）、云盘绑定、folder-browse、cloud-storage-accounts
- 文件夹：生成（generate-folder）、绑定（CaseFolderBinding）、自动捕获（CaseFolderScanSession 状态机）
- 模板绑定（CaseTemplateBinding）与统一文书生成（unified-generate，对接 documents）
- 案由/法院基础数据（CauseCourtDataService）与诉讼费计算（LitigationFeeCalculatorService）
- 案号（CaseNumber）含执行计算字段（已付款金额、抵扣顺序、年基准天数）

## 目录结构

```
cases/
├── models/               # Case、CaseParty、CaseAssignment、CaseAccessGrant、CaseLog(Attachment/Version)、
│                         #   CaseChat、CaseMaterial 体系、CaseFolderBinding、CaseTemplateBinding、
│                         #   CaseNumber、SupervisingAuthority、枚举（从 core 重导出）
├── api/                  # case / party / assignment / grant / log / casenumber /
│                         #   cause_court / litigation_fee / folder_generation / folder_binding /
│                         #   case_material / folder_scan / template_binding
├── services/             # 18 个服务导出，内部按 case/ chat/ data/ log/ material/ number/ party/ template/ 分层
│                         #   （CaseService = CaseQueryService + CaseCommandService 兼容层）
├── admin/                # CaseAdmin、CaseChatAdmin、CaseAssignmentAdmin、CaseLogAdmin、
│                         #   CaseLogAttachmentAdmin、CasePartyAdmin + mixins + payment inline
├── dependencies.py       # 跨模块依赖注入（automation ChatProviderFactory、documents ContextBuilder）
├── utils.py / signals.py / models.pyi
└── management/commands/sync_case_assignments_from_contracts.py
```

## 数据模型（节选）

- `Case` — 案件（contract FK、is_filed/filing_number、status 仅 active/closed、case_type、current_stage、cause_of_action、target_amount、preservation_amount、previous_case）
- `CaseParty` — 当事人（case+client+legal_status 唯一约束）
- `CaseAssignment` — 律师指派（case+lawyer 唯一约束；「主办/协办」语义在 contracts 的 ContractAssignment 侧）
- `CaseAccessGrant` / `CaseLog` / `CaseLogAttachment` / `CaseLogVersion` — 授权与日志体系
- `CaseChat` / `ChatAuditLog` — 案件群聊
- `CaseMaterial` / `CaseMaterialCategory` / `CaseMaterialSide` / `CaseMaterialType` / `CaseMaterialGroupOrder` — 材料体系
- `CaseFolderBinding` / `CaseFolderScanSession` — 文件夹绑定与自动捕获
- `CaseTemplateBinding` — 模板绑定
- `CaseNumber` / `CaseFilingNumberSequence` / `SupervisingAuthority` — 案号与基础数据

## API 端点

前缀 `/api/v1/cases`（创建案件为 `POST /cases/cases`）：

| 端点组 | 说明 |
|--------|------|
| `/cases` CRUD + `/cases/search` + `/cases/full` | 案件管理与一键建档 |
| `/parties`、`/assignments`、`/grants` | 当事人 / 指派 / 案件授权 |
| `/logs` CRUD + `/logs/{id}/attachments` | 案件日志（body 含 case_id） |
| `/case-numbers`、`/upload-temp-document` | 案号与临时文书 |
| `/causes-data`、`/causes-tree`、`/courts-data`、`/calculate-fee` | 基础数据与诉讼费 |
| `/{case_id}/generate-folder`、`/folder-binding`、`/folder-browse`、`/cloud-storage-accounts` | 文件夹 |
| `/{case_id}/materials/*` | 材料绑定 / 上传 / 分组排序 |
| `/{case_id}/folder-scan*` | 自动捕获 |
| `/{case_id}/template-bindings`、`/generate-template`、`/unified-generate` | 模板与文书生成 |

## 异步任务与信号

- signals：post_delete 清理 CaseLogAttachment / CaseNumber 物理文件
- 管理命令 `sync_case_assignments_from_contracts`

## 依赖模块

- `apps.core`（最多）、`apps.cloud_storage`、`apps.documents`、`apps.contracts`、`apps.automation`、`apps.client`、`apps.contacts`、`apps.reminders`
