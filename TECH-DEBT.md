# TECH-DEBT.md —— AI 平台与检索的未完成项（唯一 backlog 入口）

> 本文件只记**已经确认、但这一轮没做**的技术债，每条都带「现象 / 证据 / 修法 / 代价」。
> 做完一条就把那一条删掉，并在 `changelog/` 写一条对应版本记录。
>
> 为什么放根目录：`docs/` 被 `.gitignore:257` 整个忽略（`git ls-files docs` 为空），
> 写在那里等于没写——其他 AI 会话与后来的人都看不到。本文件**在 git 里**。
>
> 最近一次更新：2026-11-23（**第二轮**后端全量审计 `v27.23.1`：`v27.23.0` 遗留的 §F/§G 共 26 条全部结清，新增 P0 9 条 + P1 全量归档，见文末「第二轮后端全量审计」与 §H/§I/§J）。
>
> **已完成**（不在本清单里了）：
> - ① 成本归属缺 provider 维度 → `v27.20.11`（`LLMCallRecord` / `AgentRun` 加 provider + 写入 + `by_provider`）
> - ③ `fallback_models` 只解一半 → `v27.20.11`（非流式路径按降级链重试）
> - ⑥ agent 后端埋点缺口（dsh 无 `tool/result` 与 usage、openai-agents 无 usage 且单栏双 `done`、
>   平台解析在 async 上下文读同步 ORM）→ `v27.21.1`（三条全部补齐，真机四栏验收通过）

---

## ⑤ 主对话路径的精确在飞计数 —— **实测不需要，已关闭**

**原顾虑**：pi / dsh / openai-agents 在外部进程里直接跟网关说话，拿不到请求边界，
选 Key 只能轮转；担心高并发单栏提问会把同一把 Key 压过 `max_parallel_requests=3` → 429。

**实测（2026-11-21，真实网关，10 把 Key × 每把 3 并发 = 30 槽位）**

| 并发（同时在飞的请求） | 短请求（16 token，~0.4s） | 真实轮次（~250 字，~2s） |
|---|---|---|
| 10 | 10/10 成功 | 10/10 成功（总耗时 2.0s） |
| 20 | 20/20 成功 | 20/20 成功（1.9s） |
| 30 = 全部槽位 | 30/30 成功 | 30/30 成功（2.4s） |
| 40（超容量 133%） | **3 个 429**（`retry-after: 60`） | — |

**并且**：在 40 并发时，租约模式（模拟 ⑤ 的实现）拿到 **5 个 429**，比现状的 3 个更差——
因为 `KeyScheduler.allocate` 在饱和时是「循环复用、best-effort 不报错」，
它并不能凭空造出第 31 个槽位。

**结论**：如果出现 429，瓶颈是**总槽位 30**（= key 数 × 每 Key 并发），不是"选得不准"。
⑤ 解决不了容量问题，只增加租约泄漏、外部进程崩溃、TTL 兜底等真实风险。
**不做**。真要提高容量，正确的动作是加 Key（30 → 每加一把 +3 槽位）。

**重开条件**：若将来出现「并发 < 容量上限却仍频繁 429」，说明挑选确实偏斜，
届时再做（方案见 git 历史：租约 + 5 分钟 TTL + 失败回报冷却）。

## 怎么验证这些"还没做"

```bash
# ① 成本归属：应当无输出（说明确实没有 provider 字段）
rg -n "provider\s*=\s*models" backend/apps/agent/models/run.py

# ② rpm/tpm：应当无输出
rg -n "rpm|tpm" backend/apps/core/models/llm_provider.py

# ③ fallback_models 的运行时消费者：应当只有 pi/服务层，没有 openai_compatible
rg -ln "fallback_models" backend/apps --glob '!**/__pycache__/**'

# ④ 抽取依赖：应当「未引入」
rg -n "trafilatura|htmldate" backend/pyproject.toml

# ⑤ 选 Key 是否占槽：key_selector 里应当看不到 acquire
rg -n "acquire" backend/apps/core/llm/key_selector.py
```


---

# 2026-11-23 后端全量审计遗留（`v27.23.0`）

> 来源：25 个只读 agent 的分簇审计（报告工件在 `tmp/backend-audit/reports/`，
> 逐条带 `file:line`）。本轮**已修**的 8 条 P0 不在本清单里，见 `changelog/v27/v27.23/v27.23.0.md` §3。
> 本清单只记「已确认、但这一轮故意没做」的项，按可执行性分 6 类。

## A. 需要产品/契约决策（不是纯技术债）

### A1 pdf_splitting `/reusable-job`、`/inflight-job` 回吐他人 OCR 正文
- **现象**：两个端点只按 `source_name(+total_pages)` 查任务，响应 `PdfSplitJobOut` 里含 `content_md`（整份 OCR 文本）与 `positioned`。service 层注释明确写「刻意不按 created_by 过滤」，理由是「同一材料包常由助理先跑、主办律师复用」。但端点侧没有做任何「材料包读权限」校验，等于**知道文件名就能拿到别人的识别结果**。
- **证据**：`apps/pdf_splitting/api/pdf_splitting_api.py:276-312`、`apps/pdf_splitting/services/job_service.py:250-268`（刻意不过滤）、`:319-330`（`build_job_payload`）、`:483`（`content_md`）。
- **修法**：二选一——① 命中但跨用户时只回 `job_id + 段数 + 状态`（新增 `ReusableHintOut`，**会改 openapi**）② 保留正文，但要求调用方带材料包/消息 id 并做读权限校验。
- **代价**：①要改前端消费与 openapi 产物；②要给两个端点加参数与权限链路，前端同步改。约 1-2 天含回归。

### A2 `apps.documents/docx_templates/` 用户上传模板落进源码树
- **现象**：用户上传的 docx 模板写到 `apps/documents/docx_templates/0-用户自定义模板/`（仓库内、靠 .gitignore 藏），不在 `MEDIA_ROOT`，不随容器持久化、不在 media 备份范围；目录里已积压 50 个测试上传文件。
- **证据**：P04-02（审计报告 `tmp/backend-audit/reports/P04-documents.md`）。
- **修法**：迁到 `MEDIA_ROOT` 下 + 数据迁移（存量文件搬移 + 字段/路径改写）。
- **代价**：要动数据与部署（media 目录、备份脚本），必须单独 PR + 迁移演练。

---

### A3 OA 归档超过 2 个附件时静默只传前 2 个，任务仍置 COMPLETED

- **现象**：`playwright_archive.py:265-275` 在 `len(file_paths) > 2` 时只上传前两个文件、仅打一条
  `logger.warning`，任务状态照样走 `COMPLETED` → 材料静默漏传，界面上看不出少东西。
- **证据**：`apps/oa_filing/services/oa_scripts/jtn/archive/playwright_archive.py:265-275`（审计 P08-03）。
- **修法**：二选一并写进 README/报错文案——① 入口直接拒绝 >2 个附件（`ScriptExecutionError`，
  任务置 FAILED）；② 实现「增加」按钮加行（OA 页面已预留 `file_inputs` 多行）。
- **代价**：①要改调用方调用约定（可能要限制前端选文件数）；②要对着真实 OA 页面调 Playwright
  加行流程，需真机验证 + 回归。约 0.5~2 天。

## B. plugins 子模块（私有仓库 FachuanPlugins）—— 必须另开两段式 PR

> 本 PR 按纪律**不改 plugins**（子模块指针与内容都未动）。以下 5 条 P0 已确认，证据在
> `tmp/backend-audit/reports/P13-plugins.md`。

| # | 现象 | 证据 |
|:-|:-|:-|
| B1 | 担保（财产保全）链路代理人载荷兜底写死假名 `"张三"`，无指派律师时该假名被组装进 `case_data["agents"]` **提交法院系统** | `plugins/court_automation/guarantee/helpers.py:1166`、`:1xxx`（见报告 P13-05） |
| B2 | `CourtTokenAdmin.token_full` 用 `<textarea readonly>` 把**完整 token 明文**渲染进 admin 详情页；token 按「全所各律师法院账号」存，任何有 view 权限的 staff 可直接读走 | 报告 P13-02 |
| B3 | `CookieService.save()` 把 `({},)` 空 tuple 序列化写文件，`load()` 按 dict 读 → 写出来的格式**永远解析不出** cookie，登录态持久化静默失效且无报错 | 报告 P13-03 |
| B4 | `TokenHistoryRecorder` 把 `result.token[:50]` 落库到 `token_preview`，而同仓库 `login/token_service.py` 在安全审计 E-18 下已改成「长度 + sha256」 | 报告 P13-04 |
| B5 | `weike_api_private` 的 HTML→文本清洗把转义写成 raw string 双反斜杠（`\\s`/`\\n`/`\\t`），正则实际匹配「反斜杠+s」，`<script>`/`<style>` 正文从未被剥离 → 脏文本进法条比对 | 报告 P13-01 |

修法与代价见报告逐条；建议一次插件 PR 全部修掉，再回主仓更新子模块指针。

---

## C. 巨石文件拆分（42 个 ≥800 行生产文件，**本轮一个都没拆**）

见 `tmp/backend-audit/reports/P*-*.md` 的「§3 巨石拆分方案」。本轮未拆的主要原因：拆分属跨文件大重构，需要多轮回归 + 独立 review 历史，单 PR 里做完全部会把回归风险
放大到不可评审。本轮只做了**同族死代码清理**（删空壳 Service 类与死 helper），没动任何文件的职责切分。

**优先级最高的 8 个**（都已有具体拆分方案）：

| 文件 | 行数 | 现状职责 | 方案出处 |
|:-|--:|:-|:-|
| `apps/automation/services/ocr/paddleocr_api_service.py` | 1799 | OCR 调用 + 重试 + 缓存 + 落库 | P05 §3 |
| `apps/document_parsing/services/backends/mineru_backend.py` | 1465 | 后端协议 + 轮询 + 结果解析 | P10 §3 |
| `mcp_server/server.py` | 1379 | 409 条注册 + 注解推导 + 异常翻译 + 观测 + 插件注册 + schema 瘦身 | P07 §3 |
| `apps/document_recognition/services/date_candidate_service.py` | 1312 | 候选生成 + 打分 + 时区处理 | P10 §3 |
| `apps/contracts/services/payment/invoice_intake_service.py` | 1273 | 扫描 + 解析 + 匹配 + 确认 + 冲红 | P02 §3 |
| `apps/pdf_splitting/services/split/service.py` | 1141 | 阶段编排 + 落库 + 打包 + 导出 + 预览 + 心跳 | P07 §3 |
| `apps/contracts/services/payment/invoice_file_service.py` | 1109 | 归档定位 + 镜像 + 改名 | P02 §3 |
| `apps/core/llm/backends/openai_compatible.py` | 1133 | 协议适配 + 重试 + 降级 + 埋点 | P01 §3 |

---

## D. 测试层结构债（数量级问题，不适合单 PR 硬做）

| # | 现象 | 量化 | 证据 |
|:-|:-|:-|:-|
| D1 | 测试文件以「指标」而非「被测行为」命名 | 401 / 1726 = 23%（`coverage/round*/batch*/final_85/deep/extended`） | T09-08 |
| D2 | 同一模块被 3~6 个文件重复覆盖（InvoiceParser 6 文件 / folder_scan 6 文件 3640 行 / ems_auth 5 文件 / McpToolClient 3 文件 1663 行） | 见报告 | T10-03、T04-03、T09-03 |
| D3 | `apps/workflow/tests/` 是全仓唯一 app 内自带测试目录（含 39 处 `print`），与 `tests/ci/{unit,integration,property,structure}` 分层冲突 | 1 个目录 | 主会话实测 |
| D4 | `apps/testing/` 不是 Django app（不在 INSTALLED_APPS），只是 `factories.py`，却被 40+ 测试以 `apps.testing` 导入 | 1 个模块 | 主会话实测 |
| D5 | message_hub **248/539（46%）** 测试被模块级 `skipif` 在 CI 整体跳过（私有插件恒不可用），仍计入「通过」 | 12 个文件 | T08-01 |
| D6 | `tests/` 下真实样本 fixture = 0（无 pdf/png/jpg/docx），OCR/身份证/日期三条链路全靠 mock | 0 个文件 | T08-02 |
| D7 | `pytest.raises(Exception)` 过宽断言 | 103 处 | T09-10 |
| D8 | 「恒真断言」（`assert x or len(x)>=0`、`assert r is not None or r is None`）出现在 OA 登录等关键路径 | ≥3 处 | T07-01 |
| D9 | core 测试零断言用例（既无 assert 也无 raises） | 74 个 | T02-07 |
| D10 | documents 测试未使用导入（F401，可 `--fix`） | 281 处 | T03 |

修法：按 app 分批「合并重复测试 → 按行为重命名 → 归位到镜像目录」，每批一个 PR；D5/D6 需要插件桩与真实脱敏样本，单独立项。

---

## E. 门禁与配置债 —— 本轮**只核实、不改**（用户裁决）

复核结论（`docs/analysis/backend-audit-v2-2026-11-23/`）：
E1 mypy 基线已过期 → **本轮把存量唯一 error 修掉，`mypy apps mcp_server` 现为 0 error**，基线下调可另开一版；
E2 CI「Repository hygiene」两个子检查因 `working-directory: backend` 恒不命中；
E3 ruff 历史豁免的存量命中数仍未清点；
E4 `llm-privacy-guard` 偶发判红。四条本轮均未动代码。

---

# 2026-11-23 第二轮后端全量审计（`v27.23.1`）

> 全量报告与逐条证据：`docs/analysis/backend-audit-v2-2026-11-23/`（SUMMARY / ledger.tsv / 65 份分片报告 / 13 份复查报告）。
> 规模：4274 文件逐行读、1522 条发现、332 条 P0+P1 全部二轮证伪（属实 266 / 部分属实 54 / 驳回 12）。
> 本轮已修 40 条（P0 21 + P1 17 + P2 2），下列为**确认属实但本轮未修**的条目。

## F. agent 运行时（`v27.23.0` 遗留 8 条）—— **本轮全部结清**

| # | 断言 | 结局 |
|:--|:--|:--|
| F1 | `/compact` 与在飞对话并写同一 session 文件 | ✅ 已修（端点先查 `LiveSessionRegistry`，在飞即 409） |
| F2 | `ask_user` 跨 worker 答案唤不醒等待方 | ✅ 已修（本地 event 快路径 + 0.2s 轮询 Redis） |
| F3 | `getattr(cluster,"lanes",[])` 读不存在字段 | ✅ 已修（改读 `member_ids`，处理 `tie`） |
| F4 | `_pending` 双键互相覆盖 | ✅ 已修（id 索引 + command FIFO `deque`） |
| F5 | 模块级 `asyncio.Lock` 跨 loop | ✅ 已修（按 loop 懒建 `WeakKeyDictionary` + 兼容代理） |
| F6 | 三个后端 `_results` 无界 | ✅ 已修（抽 `BoundedResultStore`，256 封顶） |
| F8 | 槽位/栏数上限三处各一份 | ✅ 已修（新增 `apps/agent/services/chat/config.py` 单源） |
| F7 | `__all__` 暴露 31 个私有名 | ⏸ **保留不改**（P2；`chat_service.py` 用 `from .chat import *` 做兼容门面，改名要连带改门面 + 一批测试，收益为 0。真要收敛时按「先删 `__all__` 私有名 → 修调用点 → 跑定向测试」三步走） |

## H. 新 P0（按优先级，全部已二轮证实）

> 本轮已修掉其中 4 条：会话 SSE 越权 `chat_api.py:115`、收件箱搜索越权 `search_api.py:94`、
> `_persist_analysis` 分段丢失 `split/service.py:1014`，以及子模块内 `C02-01`（凭证缓存不存明文，
> 子模块提交 `e42260a`，**未 push、主仓指针未提交——待用户授权**）。下表是**仍未修**的。

| # | 现象 | 证据 | 为什么不本轮修 |
|:-|:-|:-|:-|
| H1 | 合同审查 LLM 异常被吞成空结果，任务仍标 `COMPLETED`（失败不可见） | `apps/contract_review/services/review/contract_reviewer.py:187` | 需产品定义「失败怎么展示」（`failed` vs 「完成了但内容为空」），前端也要跟着改 |
| H2 | Redis broker 下 `cancel()` 只删 OrmQ 行 → 排队任务「取消」静默失效，调用方已置 CANCELLED 但任务照跑 | `apps/core/tasking/submission.py:75` | 是运行时语义变更：真出队（要处理已弹出/正在执行的竞态）还是只置协作标记，**要人拍板** |
| H3 | 记忆 `promote_memory` 的 `get_or_create` 少 team/law_firm 维度 → 命中他团队/律所同行，越权回吐内容 | `apps/agent/services/memory/curation.py:156` | 多租户口径未定（同律所共享 vs 仅本人/本团队），错修会把同律所规则也挡掉 |
| H5 | 在 `EncryptedTextField` 列上做 `token__startswith=<明文前缀>` → 恒查不到，保全/一张网 Token 复用链路永久失效 | `plugins/court_automation/token/court_token_store_service.py:29` | 同上；且「删 `token_prefix` 形参」vs「加明文前缀列（要迁移）」需拍板 |
| H6 | 询价 API 四端点签名与适配器不符（`create_quote`/`credential_ids`/`aget_quote`）→ 全部必 500，且行级 ACL 参数根本没传到 service | `plugins/court_automation/preservation_quote/api_endpoint.py:104,155,248` | 同上（子模块）；修法牵扯「改适配层」vs「改前端契约」 |

## I. 新 P1（按 app 归档，逐条带 `file:line` 与修法）

全量 240+ 条在 `ledger.tsv`（`severity=P1`）。按模块的「先修这四条」选摘：

| app | 首修条目 |
|:--|:--|
| `apps/automation` | `paddleocr_api_service.py` 1800 行巨石；`court_sms_admin_base.py:526` 推荐卡片未转义拼 `innerHTML`（存储型 XSS）；`gsxt_report_service.py:27` 是 `gsxt_login_service` 的近逐行副本且已漂移 |
| `apps/cases` | `case_template_generation_service.py:299` 模板匹配/文件名两份实现（半角 vs 全角括号）；`cases/services/**` 仍有多处 `_internal()` 绕过 ServiceLocator |
| `apps/contracts` | `access_policy.py:58` ACL 同步/异步两套逐行重复；`archive_classifier.py` 995 行巨石；`_binding_mixin.py:60` 云存储解析失败按本地继续 |
| `apps/documents` | `external_template_api.py:333` preview-html 对「无律所且非 superuser」放开全库模板；`custom_values` 被占位符自动值覆盖 |
| `apps/agent` | `llm` 网关 `tpm` 记账恒 0（`LLMResponse` 无 `.usage`）；`_window` 无界且修剪入口被短路 |
| `mcp_server` | `fetch_url.py` 1093 行 + 单函数 267 行；`_resolve_sogou_redirect` 对任意页面生效（普通页含 `http-equiv`+`URL=` 即被判跳转） |
| `tests/` | 一批「假绿」测试：`assert expected == expected`、`patch.object(svc,"add_payments")` 后断言 mock 自身、整目录 `except ImportError: pytest.skip(module_level)` |

## J. 测试层（本轮改动带来的口径变化，已同步改写）

本轮 17 条历史测试断言的是**缺陷行为**，已按新契约改写并在注释里写明「原断言为什么是错的」：
`test_case_party_mutation_extra_coverage`（用不存在的 `*_side` 枚举）· `test_job_service_lifecycle::TestFindReusableJob`
（`test_刻意不按created_by过滤` 锁死越权）· `test_confirm_segments`（原断言 `atomic` 内派发）·
`test_analysis_service_v2::TestRetryAnalysis`（原断言先删后算）· `test_activities::TestRecordStep`（原断言 `started_at` 被抹）·
`test_qichacha_mcp_provider_unit`（原断言非法值回落）· `test_contracts_services_deep2`（原断言返回 lazy QuerySet）·
`test_calendar_feed_api`（原 fixture 把「无属主提醒对所有人可见」当契约）。
