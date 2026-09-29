# 👥 当事人管理（client）

当事人（客户）主数据管理：客户 CRUD（含带证件一次创建）、文本解析提取当事人、身份证校验、证件管理（7 类证件 + OCR 识别 + 异步任务 + 身份证正反面合并）、财产线索管理、企业信息搜索/预填（enterprise_data 集成）、客户导入、客户删除工作流。

> app verbose_name 为「当事人管理」，模型表名为 `cases_client`（历史原因）。

## 功能概述

- 客户 CRUD、`/clients-with-docs` 带证件一次创建、文本解析（`parse_client_text` / `parse_multiple_clients_text` 模块级函数）提取姓名/电话/地址
- 身份证号校验（IdentityExtractionService 内部实现）、按主体类型校验证件类型
- 证件管理：7 类证件（身份证/护照/港澳通行证/居住证/户口本/营业执照/法定代表人身份证）、OCR 识别 + 有效期识别异步任务、身份证正反面合并（三种模式 + 绑定）
- 财产线索管理：银行/支付宝/微信/不动产/其他 + 附件 + 内容模板
- 企业信息搜索 / 预填：集成 enterprise_data（EnterpriseDataService）与 GSXT 工商报告（GsxtReportPort）
- 客户导入流水线（importer 子包：importer/mapper/persister/validator，挂在 `/api/v1` 根的 client_import_router）
- OA 凭证检查（check-oa-credential，依赖 oa_filing 利冲预检）
- 客户删除工作流（ClientDeletionWorkflow，统一文件清理）与管理命令 `normalize_client_media_paths`

## 目录结构

```
client/
├── models/               # Client、ClientIdentityDoc、PropertyClue(+Attachment)
├── api/                  # client / identity_doc / property_clue / enterprise / import 等
├── services/             # ClientAdminService、ClientIdentityDocService、ClientServiceAdapter、
│                         #   PropertyClueService + query/mutation 子包 + id_card_merge/、
│                         #   identity_extraction/、importer/ 子包
├── ports/ + adapters/    # 六边形端口（GsxtReportPort、CredentialPort、FileValidatorPort、
│                         #   FileUploadPort、TaskServicePort）
├── workflows/            # ClientDeletionWorkflow
├── admin/                # ClientAdmin、ClientIdentityDocAdmin、IdCardMergeViewAdmin、PropertyClueAdmin
├── tasks.py              # execute_identity_doc_recognition、recognize_expiry_date_task
└── signals.py + management/commands/normalize_client_media_paths.py
```

## 数据模型

- `Client` — 客户（name、phone、address、client_type=natural/legal/non_legal_org、id_number（unique）、legal_representative、legal_representative_id_number、is_our_client、simple_history）
- `ClientIdentityDoc` — 证件（doc_type 7 类、file_path、expiry_date、uploaded_at；按主体类型校验）
- `PropertyClue` / `PropertyClueAttachment` — 财产线索与附件

## API 端点

前缀 `/api/v1/client`：

| 端点组 | 说明 |
|--------|------|
| `/clients` CRUD、`/clients-with-docs`、`/parties/search`、`/clients/parse-text` | 客户管理与文本解析 |
| `/clients/validate-id-card`、`/clients/check-oa-credential`、`/{id}/related-items` | 校验 / OA 凭证 / 关联案件合同 |
| `/clients/enterprise/search`、`/clients/enterprise/prefill` | 企业信息搜索 / 预填 |
| `/identity-doc/recognize`（+task 轮询）、`/clients/{id}/identity-docs`、`/identity-doc/{id}` | 证件 OCR |
| `/identity-doc/merge-id-card`、`/identity-doc/bind-merged` | 身份证正反面合并 |
| `/clients/{id}/property-clues` CRUD + 附件 | 财产线索 |

## 依赖模块

- `apps.core`（最多）、`apps.organization`、`apps.automation`（GSXT 报告）、`apps.oa_filing`、`apps.enterprise_data`
