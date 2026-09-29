# 📑 合同管理（contracts）

法律服务合同全生命周期：合同 CRUD（simple_history 审计）、当事人/律师指派、收款与发票、财务日志与统计、补充协议、文件夹绑定/批量预设/自动捕获、归档材料全流程、OA 同步、客户回款、合同导入。

## 功能概述

- 合同 CRUD + `/contracts/full`；simple_history 历史记录；建档编号 filing_number（格式 `{年份}_{合同类型}_{HT}_{序号}`）、代理阶段 representation_stages
- 当事人（ContractParty，save 时自动校正 PRINCIPAL→OPPOSING）、律师指派（ContractAssignment，is_primary + order 即「主办/协办」）
- 收款（ContractPayment）与发票（Invoice，content_hash 去重、开票状态流转）、财务日志（ContractFinanceLog）、统计
- 补充协议体系（SupplementaryAgreement / SupplementaryAgreementParty）
- 文件夹：绑定（ContractFolderBinding）、批量根目录预设（ContractTypeFolderRootPreset）、自动捕获（ContractFolderScanSession）
- **归档材料全流程**：FinalizedMaterial + 检查清单、精简视图 compact_archive、A4 缩放、确认归档、reset-and-resync、从案件材料同步、归档学习规则（ArchiveClassificationRule + learn-rules）、占位符覆盖、监管卡提取
- OA 集成：ContractOASyncSession、law_firm_oa_url / oa_case_number 字段、OA 同步 Admin 模板（依赖 oa_filing）
- 客户回款记录（ClientPaymentRecord + 回款图片）、合同导入（contract_import_service、JTN OA 导入模板）

## 目录结构

```
contracts/
├── models/               # Contract、ContractParty、ContractAssignment、ContractPayment、Invoice、
│                         #   ContractFinanceLog、SupplementaryAgreement、ContractFolderBinding、
│                         #   ContractTypeFolderRootPreset、ContractOASyncSession、FinalizedMaterial、
│                         #   ArchiveClassificationRule、ClientPaymentRecord 等
├── api/                  # contract / party / payment / finance / supplementary / folder_binding /
│                         #   folder_scan / archive 等
├── services/             # 11 个服务导出，子包 admin/ archive/ assignment/ client_payment/
│                         #   contract/(domain,mutation,query,integrations) folder/ party/ payment/ supplementary/
│                         #   + contract_import_service
├── admin/                # ContractAdmin、ContractPaymentAdmin、SupplementaryAgreementAdmin、
│                         #   ArchiveClassificationRuleAdmin、ClientPaymentRecordAdmin + mixins +
│                         #   templatetags/contract_tags + 模板（oa_sync、jtn_oa_import、batch_folder_binding 等）
└── signals.py            # post_delete 清理 FinalizedMaterial、Invoice 物理文件
```

## 数据模型（节选）

- `Contract` — 合同（name、case_type、status unsigned/active/archived、fee_mode FIXED/SEMI_RISK/FULL_RISK/CUSTOM、fixed_amount、risk_rate、custom_terms、representation_stages、compact_archive、HistoricalRecords）
- `ContractParty` — 当事人（contract+client+role）
- `ContractAssignment` — 律师指派（contract+lawyer+is_primary+order）
- `ContractPayment` — 收款（amount、received_at、invoice_status、invoiced_amount、note）
- `Invoice` — 发票（关联 payment，content_hash 去重）
- `ContractFinanceLog` — 财务日志（action/level/actor/payload）
- `SupplementaryAgreement` — 补充协议
- `ContractFolderBinding` / `ContractTypeFolderRootPreset` / `ContractFolderScanSession` — 文件夹体系
- `FinalizedMaterial`（+MaterialCategory）/ `ArchivePlaceholderOverride` / `ArchiveClassificationRule` — 归档体系
- `ContractOASyncSession` / `ClientPaymentRecord` — OA 同步与客户回款

## API 端点

前缀 `/api/v1/contracts`（创建合同为 `POST /contracts/contracts`；收款为 `POST /finance/payments`）：

| 端点组 | 说明 |
|--------|------|
| `/contracts` CRUD + `/contracts/full`、`/{id}/lawyers`、`/{id}/parties`、`/all-parties` | 合同与当事人 |
| `/finance/payments` CRUD + `/finance/stats` | 收款与统计 |
| `/supplementary-agreements` CRUD | 补充协议 |
| `/{id}/folder-binding`、`/folder-browse`、`/cloud-storage-accounts`、`/{id}/folder-scan*` | 文件夹 |
| `/{id}/archive/*` | checklist、generate-folder、scale-to-a4、sync-case-materials、confirm、upload、materials 管理、download、learn-rules |

## 异步任务与信号

- signals：post_delete 清理 FinalizedMaterial、Invoice 物理文件

## 依赖模块

- `apps.core`（最多）、`apps.cases`、`apps.cloud_storage`、`apps.documents`、`apps.client`、`apps.organization`、`apps.oa_filing`、`apps.reminders`
