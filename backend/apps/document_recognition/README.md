# 文书智能识别（document_recognition）

法院文书（传票 / 执行裁定书 / 财产清单等）上传 → 自动识别文书类型、案号、关键日期、当事人、联系人/地址 → 律师两步人工确认（选案件绑定 + 勾选日期写入重要日期提醒）→ 绑定成功发飞书群通知。

**入口**：

- 工作台：`/admin/document_recognition/documentrecognitiontool/`（上传、识别、绑定、日期确认；`?task=<id>` 装载历史任务）
- 任务列表：`/admin/document_recognition/documentrecognitiontask/`（状态/绑定/通知/确认进度列与筛选，详情含原始文本、联系人/地址、日期候选 inline）
- 前端「记一笔」QuickAdd 的 📎 上传也走同一套 API（未绑定任务 → 独立提醒）

## 架构

| 层 | 位置 | 职责 |
|---|---|---|
| API | `api/document_recognition_api.py` | Ninja 路由：上传/状态轮询/日期确认/撤销/待确认列表/案件搜索/手动绑定/改案号 |
| Service | `services/` | 识别编排（`recognition_service`）、结构化 LLM 分析（`document_analyzer`）、文本提取（`text_extraction_service`）、视觉转写（`vlm_ocr_service`）、日期候选（`date_candidate_service`）、绑定（`case_binding_service`）、联系人/地址（`contact_extraction_service`）、通知（`notification_service`） |
| Admin | `admin/` | 工作台模板 + 任务列表/详情 |
| Task | `tasks.py` | Django-Q 异步执行（`execute_document_recognition_task`，timeout=600s），提交即返回任务 ID，前端轮询 |

服务经 `ServiceLocator → CourtDocumentRecognitionServiceAdapter` 装配（**adapter 是独立转发签名**，改内部服务签名必须同步 adapter，否则异步执行期才爆 TypeError）。

## 文本提取阶梯（每档失败自动降级，任务不失败）

| 档 | extraction_method | 说明 |
|---|---|---|
| 文本 PDF 直接提取 | `pdf_direct` | PyMuPDF 提取内嵌文字 |
| VLM 视觉转写 | `vlm` | AI 平台配置 `vision_model` 即启用；扫描 PDF 逐页 150dpi 渲染 → 多模态模型转写（页数上限 5、单页超时 120s） |
| macOS Vision | `ocr` | darwin 平台自动优先（accurate 档 zh-Hans，~1s/页；`recognitionLevel` 坑：**0=accurate、1=fast，设反全乱码**） |
| RapidOCR | `ocr` | 跨平台本地兜底（Linux/CI） |
| 关键词+正则 | — | LLM 分析层不可用时的最终降级（任务 `degraded=True`） |

LLM 结构化分析（`document_analyzer`）为单次调用（分类+案号+日期+当事人），支持反馈重试；用户上传前可在工作台选分析模型（校验在 `/api/v1/llm/models` 列表内）。

## LLM 供给配置（换供给只改「AI 平台」一行）

运行时唯一供给来源是 **LLMProvider 表**（`/admin/core/llmprovider/`）：`base_url` + `api_keys`（多 key 轮转、支持 `key|model1,model2` 白名单）+ `default_model` + `extra_models` + `vision_model`（视觉转写模型，留空禁用视觉档走本地 OCR）。代码零模型名硬编码，离职/换供给只改这一个表单。

换供给 Runbook：改 AI 平台表单（地址/Key/模型/视觉模型）→ 模型列表缓存 TTL 1 小时自动刷新（或 admin 保存即失效）→ 上传一份测试文书验证（提取方式应显示 `vlm` 或正常 `ocr`，无降级标记）。

## 确定性提取层（不依赖 LLM，对任何转写引擎生效）

- **案号**（`_case_number_mixin`）：括号全半角归一化 → 全量枚举 → 位置/引用句式加权（文首贴标题加分；「根据/依据…（案号）裁定书/判决书」中的引用案号重降权）。正则命中优先于 LLM 并记交叉校验日志。
- **日期候选后处理**（`date_candidate_service`）：「从X起至Y止」期间的起始日不作为提醒候选；中文数字期间（如「壹年」）+ 起始日算术推算到期日，可校正 OCR 乱码年份；同上下文候选去重。
- **联系人/地址**（`contact_extraction_service`）：标签锚定正则（联系人/承办法官/书记员… + 联系电话/地址），**读时从 raw_text 现算、不落库**（存量任务即时生效）；展示于工作台结果卡、admin 详情、绑定日志正文。

## 数据模型与迁移

- `DocumentRecognitionTask`（表名 `automation_documentrecognitiontask`，与 automation 旧表共用，勿改表名——E028 坑）
- `DocumentRecognitionDateCandidate`（行级状态机 pending/confirmed/skipped，reminder 回链）
- 本 app 迁移：`0001`–`0004`；另有 core `0027_llmprovider_vision_model`（部署需 migrate）

## 部署依赖

- `pyobjc-framework-Vision`（`sys_platform == 'darwin'` 平台标记，Linux/CI 自动跳过）
- Django-Q worker（`qcluster`）必须运行，否则任务停在 pending
