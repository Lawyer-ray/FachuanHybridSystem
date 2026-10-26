# 📝 合同审查（contract_review）

合同（.docx）AI 审查流水线：上传 → 正则识别甲乙丙丁四方 → 用户确认代表方 → 异步 LLM 错别字 / 合同风险审查（OOXML Track Changes 修订）→ 格式与页码 / 标题序号标准化 → 下载；另有独立的「格式规范化」API。

## 功能概述

- 上传仅支持 .docx；提取段落（带索引映射）+ 正则识别四方当事人 + 标题提取，生成标准输出文件名 `{标题}[修订版]V1_{日期}_{短id}.docx`
- `confirm-party` 允许手动修正当事人名称、选择处理步骤（typo_check / contract_review / review_report / format_document）与修订人名（默认「法穿SI」）
- 异步流水线：启用修订模式 → TypoChecker 分批（20 段/批、≤4 线程并行）LLM 查错别字 → ContractReviewer（内置企业合同风险管控审核框架 prompt）审查 + 评估报告（两步并行）→ 字体/行距/缩进标准化 → 页码域标准化 → LLM 标题层级识别 + 编号重排
- 修订以 **Word 原生 Track Changes** 落盘（lxml 写 `w:ins`/`w:del`），用户可在 Word 中逐条接受/拒绝；应用修订不信任 LLM 段落索引，按原文遍历匹配
- LLM JSON 解析有截断修复（`_try_fix_truncated_json`）
- 「格式调整」独立功能：DocxFormatNormalizer 支持参考文档对齐（复制页面布局/页眉页脚/编号，路径必须在 MEDIA_ROOT 内防穿越）+ LLM 段落层级分析 + 纯规则分类兜底

## 目录结构

```
contract_review/
├── apps.py / tasks.py             # process_review 入口 + cleanup_old_files
├── models/                        # ReviewTask / FormatNormalize(proxy) / FormatNormalizeDetail
├── repositories/review_task_repository.py
├── schemas/                       # review_schemas / format_schemas
├── api/
│   ├── review_api.py              # 审查路由（8 端点）
│   └── format_api.py              # 格式规范化路由（2 端点）
├── services/
│   ├── review/                    # ReviewService 编排 + ContractReviewer + PartyIdentifier + TypoChecker
│   ├── extraction/                # 段落提取 / 标题提取 / 标题编号
│   ├── formatting/                # 字体格式 / Track Changes 工具 / 页码域
│   ├── format_normalizer/         # 格式规范化 + LLM 结构分析 + 规则分类
│   └── exceptions.py / wiring.py
└── admin/                         # ReviewTaskAdmin + FormatNormalizeAdmin
```

## 数据模型

- `ReviewTask` — 审查任务（UUID 主键、四方当事人、状态机 uploaded→parties_identified→confirmed→processing→completed/failed、selected_steps、review_report、reviewer_name、model_name、**client_note / client_demands / our_client_name / stance_basis**）
- `ReviewRevision` — 审查修订条目（律师决策的载体：kind / severity / title / original / suggested / reason / paragraph_index + status / reject_reason / decided_at）
- `DocumentVersion` — 文档版本链节点（kind=original/ai/lawyer/client、parent 指向改自的那版、task 内单调 version_no）

**为什么清单要单独落库**：docx 里的 Track Changes 是产物，没有等级、依据、驳回理由，也没有「律师已决策」这个状态。复审台左栏消费的是这张表。

**重跑语义**：`_persist_revisions` 只删 `pending` 行，`accepted`/`rejected` 一律保留——律师的判断不能因为 AI 重跑一次就被抹掉。

**采纳不改文档**：`resolve` 只改状态；文档侧的修订痕迹由 OnlyOffice 编辑器写入（前端驱动）。后端不碰 docx 产物，避免与编辑器互相覆盖。

**人工修订回流**：编辑器保存（DS status=2/6）时，`docx_revision_reader` 解析产物里的 `w:ins`/`w:del`，把它们以 `kind=manual` 落成清单条目——律师手工改的内容原本左栏看不见。解析会跳过作者等于 `reviewer_name` 的痕迹（那是 AI 自己写的，清单里已有一份）。

**版本链**：每次产出（流水线跑完 / 编辑器保存）追加一个 `DocumentVersion` 节点，`parent` 指向改自的那版。以前版本只活在文件名（`[修订版]V1_日期`）里，改名就断链、排序只对同一天有效。

**内容版本 vs 清单版本**：`content-version` 只看 `EditorSession.saved_version`（= 文档内容真的变了），`revisions` 看 `acceptedCount`。前端画布重建跟前者——逐条采纳不应整篇重载。

**业务域扩展**：`apps/onlyoffice/services/domain_registry.py` 声明业务域（路径正则 / 取文件钩子 / 保存回写钩子 / 属主判定）。新增起诉状等业务域只需 `register_domain`，不必改 file_proxy / callback_service。
- `FormatNormalize` — ReviewTask 代理模型（Admin「格式调整」独立菜单入口）
- `FormatNormalizeDetail` — 格式调整详情（方法 poi/python/auto、版本、批注 JSON、处理日志；当前仅实现 python 路径）

## API 端点

前缀 `/api/v1/contract-review` 与 `/api/v1/contract-review/format`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传合同并识别当事人/标题（限流 TASK） |
| POST | `/{task_id}/confirm-party` | 确认代表方 + 步骤 + 修订人 + **客户交代**，触发异步审查 |
| GET | `/{task_id}/revisions` | 结构化修订清单（含待决策/已采纳/已驳回计数） |
| POST | `/{task_id}/revisions/{revision_id}/resolve` | 单条决策：`accept` / `reject`（可带理由）/ `reset` |
| GET | `/{task_id}/content-version` | 文档内容版本（画布该不该重建：只有保存回写后才变） |
| GET | `/{task_id}/versions` | 文档版本链（客户来稿 → AI 修订版 → 律师编辑版 …） |
| GET | `/{task_id}/status` | 任务状态 / 当前步骤 |
| GET | `/{task_id}/download`、`/download-original` | 下载审查结果 / 原文件（限流 EXPORT） |
| GET | `/models` | 可用 LLM 模型列表 |
| POST | `/format/normalize` | 对已有任务执行格式规范化（可带 MEDIA_ROOT 内参考文档） |
| GET | `/format/{task_id}/download-normalized` | 下载规范化结果 |

## Admin

- `ReviewTaskAdmin`：状态/步骤展示、文件链接、报告 HTML 渲染；action：重新执行、删除任务及文件、格式规范化
- `FormatNormalizeAdmin`：proxy 只读列表 + upload / execute / 批注 / 批量执行 / 批量删除自定义视图

## 异步任务与信号

- `process_review`（Django-Q2，timeout 1800，幂等：终态跳过）
- `cleanup_old_files(days=30)`：清理 30 天前上传/输出文件并删任务记录（跳过 PROCESSING）

## 外部集成

- LLM（apps.core.llm，complete + 指定 model、fallback）
- python-docx + lxml 直接操作 OOXML；无 Playwright / 外部网络服务

## 依赖模块

- `apps.core`（llm、任务提交、异常、ServiceLocator）
