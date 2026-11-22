# TECH-DEBT.md —— AI 平台与检索的未完成项（唯一 backlog 入口）

> 本文件只记**已经确认、但这一轮没做**的技术债，每条都带「现象 / 证据 / 修法 / 代价」。
> 做完一条就把那一条删掉，并在 `changelog/` 写一条对应版本记录。
>
> 为什么放根目录：`docs/` 被 `.gitignore:257` 整个忽略（`git ls-files docs` 为空），
> 写在那里等于没写——其他 AI 会话与后来的人都看不到。本文件**在 git 里**。
>
> 最近一次更新：2026-11-23（后端全量审计 `v27.23.0` 带入 6 类遗留，见文末「2026-11-23 后端全量审计遗留」；此前 ①②③④⑤⑥ 均仍为已结清状态）。
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

## E. 门禁与配置债

| # | 现象 | 证据 |
|:-|:-|:-|
| E1 | mypy 全量 `BASELINE=47` 已过期（本地含 plugins 实测 0 错），棘轮只会「不超标」，不会收敛 | `backend-ci.yml`（本轮已把它改成 fail-closed，但基线数值未下调） |
| E2 | CI「Repository hygiene」有 2 个子检查因 job 级 `working-directory: backend` 导致路径恒不存在 → 永不触发（本地同款检查有效） | T12-02 |
| E3 | ruff ~60 条历史豁免（`C901`/`E501`/`B904`/`F841`/`TID252`…）的存量命中数未清点，取消豁免前需逐条评估 | T12 §3 |
| E4 | `.pre-commit-config.yaml` 的 `llm-privacy-guard` 在模型不可达时偶发判红（本轮实测一次 commit 被它拦下，重试即过） | 主会话实测 |

---

## F. agent 运行时（P03 重跑后已定级，报告：`tmp/backend-audit/reports/P03-agent.md`）

| # | 现象 | 证据 | 修法要点 |
|:-|:-|:-|:-|
| F1 | `POST /compact` 在对话运行中**另起第二个 pi 进程**写同一份 `--session-dir/--session-id`，直接违反 `live_sessions.py` 自己写的禁令 | `services/session_api.py:334-356`（零 live 判定）、`services/compact_service.py:71-76` | 该端点先查 `LiveSessionRegistry`，有在飞句柄即 409；或走「排队等当前轮结束」 |
| F2 | `ask_user` 的**跨 worker 答案永远唤不醒等待方**：等待方只在本地 event 被 set 后才读 Redis，而审批路径是 0.2s 轮询 | `services/question.py:340-363` vs `services/approval/waiter.py:172-187` | 统一成「轮询 Redis + 本地 event 快路径」，或改用 redis pubsub 唤醒 |
| F3 | `synthesis/pipeline.py` 用 `getattr(cluster, "lanes", [])` 读一个**不存在**的字段（`EquivalenceCluster` 只有 `member_ids`）→ 评审共识那行永远不出现且不报错 | `services/synthesis/pipeline.py:240-243` | 改读真实字段并加断言；补一条「共识行必须出现」的单测 |
| F4 | `pi/rpc_client._send` 同时用 `id` 与 `command` 双键做 pending，pi 不回显 id → **同命令并发时后者覆盖前者**，先到的 future 白等 30s | `pi/rpc_client.py:481-483,519-523` | 按 command 存 `deque[Future]` FIFO 取首个未完成，或给每类命令加序号 |
| F5 | `subtask_runner` 用 `asyncio.run` 不 `close_pool()`（三个后台入口里唯一不关的），但**真凶是模块级 `asyncio.Lock`** | `services/subtask_runner.py:110-135`、`services/chat/pool.py:20` | 池与锁按 loop 懒建；`close_pool()` 只是必要条件 |
| F6 | `_results` 无界增长：3 个后端只 pop 自己那个 run_id，`claude_agent_backend` 已用 `MAX_KEPT_RESULTS=256 + OrderedDict` 封顶 | `backends/{pi,dsh,openai_agents}_backend.py` | 把 claude 后端的封顶实现提成公共基类 |
| F7 | `services/chat/__init__.py` / `services/approval/__init__.py` 把十几个私有名写进 `__all__`，外部直接依赖（`chat_pool._resolve_model` 等） | 见报告 P03-06 | 提升为公开名或经 facade，逐个改调用点 |
| F8 | 环境变量数值解析与栏数上限**三处各一份**，靠注释约定必须手工同步 | `services/chat/budget.py:74-81` vs `pool.py:23-29`；`multi.MAX_ANSWERS` vs `aggregate.MAX_CANDIDATES` | 抽一个 `chat/config.py` 单源 |

> **已证伪，不要再报**：「多栏并答会撞 `SessionBusyError`」不成立——`services/chat/multi.py:206-214`
> 按 kind 去重，pi 单轮最多出现一次。残留真问题只是该异常没被 `errors._classify` 归类（用户看到
> 「Agent 运行失败」而非「会话已有运行中的对话」）。
