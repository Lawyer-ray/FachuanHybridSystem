# 📑 合同管理（contracts）

法律服务合同全生命周期：合同 CRUD（simple_history 审计）、当事人/律师指派、收款与发票、财务日志与统计、补充协议、文件夹绑定/批量预设/自动捕获、归档材料全流程、OA 同步、客户回款、合同导入。

## 功能概述

- 合同 CRUD + `/contracts/full`；simple_history 历史记录；建档编号 filing_number（格式 `{年份}_{合同类型}_{HT}_{序号}`）、代理阶段 representation_stages
- 当事人（ContractParty，save 时自动校正 PRINCIPAL→OPPOSING）、律师指派（ContractAssignment，is_primary + order 即「主办/协办」）
- 收款（ContractPayment）与发票（Invoice，content_hash 去重、开票状态流转）、财务日志（ContractFinanceLog）、统计
- 补充协议体系（SupplementaryAgreement / SupplementaryAgreementParty）
- 文件夹：绑定（ContractFolderBinding）、批量根目录预设（ContractTypeFolderRootPreset）、自动捕获（ContractFolderScanSession）；新建合同页文件夹组件为 deferred 模式——选好文件夹随表单提交，保存后由 `response_add` 自动建绑定（云存储账号同 API 解析，失败仅提示不阻断保存）
- **归档材料全流程**：FinalizedMaterial + 检查清单、精简视图 compact_archive、A4 缩放、确认归档、reset-and-resync、从案件材料同步、归档学习规则（ArchiveClassificationRule + learn-rules）、占位符覆盖、监管卡提取
- OA 集成：ContractOASyncSession、law_firm_oa_url / oa_case_number / law_firm_oa_guid（律所ID，OA 案件 GUID）字段、OA 同步 Admin 模板（依赖 oa_filing）；「查询ID」按钮——按律所OA案件编号调 oa_filing 案号查 GUID（纯 HTTP 只读）自动填充律所ID，**新建页与变更页均可用**（新建页走无 id 路由 `/lookup-oa-guid/`，查询不依赖已保存合同；变更页保留 `/{id}/lookup-oa-guid/`；唯一命中自动填入、多命中点选）；详情页「申请开票」「打开OA」有律所ID 时浏览器/Playwright 直达 OA 开票申请页与归档申请页（keyid 直达，跳过查案件，无律所ID 回退原链路）
- 客户回款记录（ClientPaymentRecord + 回款图片）、合同导入（contract_import_service、JTN OA 导入模板）
- **AI 自动分析导入（新建页）**：拖拽一份合同（docx/pdf/txt）→ LLM 解析 → 自动回填表单草稿，取代人工对照录入。见下方专节

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
│                         #   contract/(domain,mutation,query,integrations,intake) folder/ party/ payment/ supplementary/
│                         #   + contract_import_service
├── admin/                # ContractAdmin、ContractPaymentAdmin、SupplementaryAgreementAdmin、
│                         #   ArchiveClassificationRuleAdmin、ClientPaymentRecordAdmin + mixins +
│                         #   templatetags/contract_tags + 模板（oa_sync、jtn_oa_import、batch_folder_binding 等）
└── signals.py            # post_delete 清理 FinalizedMaterial、Invoice 物理文件
```

## AI 自动分析导入合同（新建页拖拽）

入口：`/admin/contracts/contract/add/` 顶部「AI 智能导入合同」面板。
一次一份文件，用户可在面板内切换解析用的大模型（数据源即 `/admin/core/llmprovider/`）。

### 链路

```
上传 → MEDIA_ROOT/tmp/contract_intake/（落盘，不入库）
  → document_snapshot  （docx 段落+表格 / pdf 取字 / txt）
  → extract_service      （Pydantic schema + LLM，结构化失败回喂重试 3 次）
  → normalize            （金额换算、枚举白名单、日期解析、律所剔除、律师匹配）
  → 前端回填表单（select2 autocomplete 走 data API）
  → 用户逐项复核 → 手动点「保存」（走既有 save_model）
```

模块位于 `services/contract/intake/`：

| 文件 | 职责 |
|---|---|
| `document_snapshot.py` | 确定性文本提取。**必须抽表格**——签署页落款在 `<w:tbl>` 里，只取段落会丢「签约日期」 |
| `extract_schema.py` | LLM 输出契约（Pydantic）。数值以字符串承载，换算交给 normalize |
| `extract_service.py` | prompt 组装 + 结构化重试 + 模型列表（复用 `LLMProviderService` 缓存） |
| `normalize.py` | **闸门层**：任何要进 `Contract` 字段的值都必须过这里 |
| `intake_service.py` | 编排：临时落盘、库内 Client/Lawyer 匹配、响应组装 |

### 硬性设计约束

- **AI 只产出草稿，绝不写库**（单测 `TestNoPersistence` 锁定）。用户复核后才点保存。
- **临时文件不入库**：只进 `MEDIA_ROOT/tmp/contract_intake/`，由既有定时任务
  `cleanup_temp_files`（每小时，按 mtime 清 24h+）覆盖，**无需新增调度**；
  面板文案已告知用户「不会归档到合同材料」。
- **律师事务所必须剔除**：律所既非我方客户也非对方当事人，建 `Client` 会污染数据，
  且 `ContractParty.client` 是 `PROTECT`，建错后删不掉。模型即使漏标 `is_law_firm`，
  `is_law_firm_name()` 按「律师事务所」关键词兜底。
- **`is_primary` 排他**：合同常写「乙方1、2 各指派 A、B 律师」，模型易把多位都标主办。
  normalize 收敛为一位，且**优先落在已匹配到系统账号的律师**上——未匹配的人前端填不进去。
- **金额不接受比例**：「按回款额 20% 收取」必须先判为风险比例，否则 `20` 会被写进
  `fixed_amount`（单测 `test_risk_ratio_is_not_amount` 锁定）。
- **日期不猜**：「签订三日内」「至税务机关作出结论为止」「本合同生效后」一律返回
  `None` 并标记 `needs_review`，不写入 `DateField`。
- **select2 回填必须走 data API**：`client`/`lawyer` 是 `autocomplete_fields`，
  只改 DOM `value` 会导致提交值为空（前端 `selectAutocomplete()` 注释详述）。

### 已知边界

- 扫描版 PDF（无文字层）直接报错提示改用 Word 版，不走 OCR/视觉模型。
- 超长合同按「头部 + 关键词行」裁剪至 8 万字符，`truncated=true` 时前端提示重点核对。
- 律师姓名匹配不到时**留空**（不自动创建 Lawyer）；当事人匹配不到时提示先建客户。

## 数据模型（节选）

- `Contract` — 合同（name、case_type、status unsigned/active/archived、fee_mode FIXED/SEMI_RISK/FULL_RISK/CUSTOM、fixed_amount、risk_rate、custom_terms、representation_stages、compact_archive、law_firm_oa_url、law_firm_oa_case_number、law_firm_oa_guid、HistoricalRecords）
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
| `/finance/payments` CRUD + `/finance/stats` | 收款与统计（按合同访问范围过滤：管理员全量，普通律师仅可见自己可访问的合同） |
| `/supplementary-agreements` CRUD | 补充协议 |
| `/{id}/folder-binding`、`/folder-browse`、`/cloud-storage-accounts`、`/{id}/folder-scan*` | 文件夹 |
| `/{id}/archive/*` | checklist、generate-folder、scale-to-a4、sync-case-materials、confirm、upload、materials 管理、download、learn-rules |

## 异步任务与信号

- signals：post_delete 清理 FinalizedMaterial、Invoice 物理文件

## 依赖模块

- `apps.core`（最多）、`apps.cases`、`apps.cloud_storage`、`apps.documents`、`apps.client`、`apps.organization`、`apps.oa_filing`、`apps.reminders`
