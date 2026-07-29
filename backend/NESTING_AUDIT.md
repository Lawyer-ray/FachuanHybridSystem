# Backend 嵌套控制流审计报告

扫描范围：`backend/apps/` + `backend/plugins/`，排除测试文件、migrations、`__pycache__`

---

## 一、HIGH 严重（5+ 层嵌套 / 三层 for 循环）

### 1. `apps/oa_filing/services/oa_scripts/jtn/case_import/detail_extractor.py`
- **L137-197**：`try > for > try > for > if > if > if` — **13 层嵌套**
- `_extract_case_info_tab` 等 3 个方法共享同一反模式：遍历 HTML 表格行 → 嵌套 try → 遍历 cell pairs → 长 if/elif 映射
- **修复**：抽取 `_parse_row_fields(cells) -> dict`，用字段分发 dict 替代 if/elif 链

### 2. `apps/oa_filing/services/oa_scripts/jtn/case_import/html_parser.py`
- **L292-371**：`for > for > if > if > ...` — **10 层嵌套**（3 个方法）
- `extract_customers_from_html` 等方法：外层遍历行 → 内层遍历 label/value pairs → 深层 if/elif 映射
- **修复**：引入 `field_matchers: dict[str, Callable]` 映射表，循环匹配替代 if/elif

### 3. `apps/core/cloud_storage/webdav_provider.py`
- **L193-224**：`for > if > for > if > for > if > for` — **4 层 for 循环**，深度 12
- 手动逐层解析 WebDAV PROPFIND XML 响应
- **修复**：用 `element.find()` / XPath 或提取 `_parse_webdav_response_element()` 递归解析器

### 4. `apps/automation/services/scraper/sites/guarantee/upload_mixin.py`
- **L210-489**：多处 `for > for > if > for > for > if` — **6 层嵌套**，15+ 高严重度
- 单体函数混杂 DOM 查询、文件匹配、上传逻辑
- **修复**：拆分为 `_resolve_label_text()`、`_pick_files_for_label()`、`_upload_single_input()`

### 5. `apps/automation/services/scraper/sites/guarantee/form_filling_mixin.py`
- **L433-440**：`except > for > for > for > if` — **三层 for-in-for**
- L60、L75、L283、L578 也各有 4 层嵌套
- **修复**：提取 `_fill_all_code_fields(code)` helper

### 6. `apps/oa_filing/services/oa_scripts/jtn/case_import/playwright_browser.py`
- **L293-317**：`for > try > for > try > if` — 6 层
- **L529-544**：`try > for > try > if > for > if` — 6 层

### 7. `apps/cases/services/log/email_folder_scan_service.py`
- **L277-286**：`try > for > for > if` — 4 层，同一文件 3 处高严重度

### 8. `apps/cases/services/case_import_service.py`
- **L259-269**：`for > for > if > if > with` — 5 层

### 9. `apps/cases/services/material/folder_scan_service.py`
- **L319-321**：`for > if > if > for > if` — 5 层

### 10. `apps/cases/admin/mixins/views.py`
- **L777-803**：`try > if > if > for > if` — 5 层

### 11. `apps/oa_filing/api/client_import_api.py`
- **L40-58**：`if > try > if > if > if > try` — 6 层

---

## 二、HIGH 严重（三层 for-in-for 循环）

| 文件 | 行号 | 结构 | 说明 |
|------|------|------|------|
| `apps/client/admin/client_admin.py` | L441-446 | `for > for > for > if` | 三层 for 循环 |
| `apps/cases/services/case/case_admin_export_bridge.py` | L44-52 | `for > for > for` | 三层 for 循环 |
| `apps/cases/services/case/case_contract_export_bridge.py` | L55-58 | `for > for > for` | 与 admin_export 共享模式，可统一 |
| `apps/oa_filing/services/case_import_service.py` | L189-202 | `for > try > if > for > for > if` | 三层 for + 条件 |
| `apps/contracts/services/archive/learning_service.py` | L196 | `for > for > for` | categories > codes > keywords |
| `apps/contracts/admin/contract_admin.py` | L634-641 | `for > for > for` | payments > invoices, parties > docs |
| `plugins/weike_api_private/law_verification.py` | L64-71 | `for > for > for` | stop chars > patterns > regex |

---

## 三、MEDIUM 严重（4 层 if 嵌套 / 可优化的 for-in-for）

| 文件 | 行号 | 结构 | 建议 |
|------|------|------|------|
| `apps/documents/services/evidence/__init__.py` | L18-42 | `if > if > if × 8` | 用 dispatch dict 替代 9 层 elif |
| `apps/documents/services/placeholders/.../execution_request_interest.py` | L80-98 | `if > if × 8` | 用 early return + handler 函数替代 |
| `apps/legal_research/services/task/executor.py` | L260-300 | `for > if > if > if > if` | 抽取 `_process_candidate()` |
| `apps/legal_research/services/sources/weike/search.py` | L256-269 | `if > if > if > if` | 抽取 `_try_private_api_search()` |
| `plugins/court_automation/filing/playwright_filing/filing_steps.py` | L357-376 | `for > for` with retry | 抽取 `_upload_single_file()` |
| `apps/core/management/commands/scan_orphan_files.py` | L112-127 | `for > try > for > if` | 先收集 FileField，再批量查询 |
| `apps/core/config/manager.py` | L152 | `if × 6` | 用 guard clause 扁平化 |
| `apps/client/services/client_resolve_service.py` | L92 | `for > for` | 用 dict 查找替代内层循环 |
| `apps/client/admin/property_clue_admin.py` | L114 | `for > for` | 用 dict/defaultdict |
| `apps/cases/admin/case_forms_admin.py` | L47-51 | `try > if > if > if > if` | 用 guard clause 扁平化 |
| `plugins/court_filing_http/execution_validation_mixin.py` | L42-43 | `for > for` | 用 dict comprehension |
| `apps/contracts/services/contract/integrations/contract_oa_sync_service.py` | L651-653 | `for > for` | 用 `itertools.product()` |
| `apps/automation/admin/sms/court_sms_admin_actions.py` | L77, L109 | `if > else > try > if` | 抽取 `_process_single_sms()` |
| `apps/automation/management/commands/optimize_token_performance.py` | L85-109 | `except > try > if > for > if` | 5 层，用 guard clause 扁平化 |
| `apps/automation/management/commands/smoke_check.py` | L190 | `while > if > if > if` | 4 层，提取条件判断 |

---

## 四、按文件热点排名（高严重度数量）

| 文件 | HIGH 数 |
|------|--------|
| `automation/scraper/sites/guarantee/upload_mixin.py` | 15+ |
| `automation/scraper/sites/guarantee/form_filling_mixin.py` | 6 |
| `oa_filing/jtn/case_import/detail_extractor.py` | 3（13层） |
| `oa_filing/jtn/case_import/html_parser.py` | 3（10层） |
| `cases/services/log/email_folder_scan_service.py` | 3 |
| `core/cloud_storage/webdav_provider.py` | 1（12层） |
| `cases/services/case/case_admin_export_bridge.py` | 1（三层for） |
| `cases/services/case/case_contract_export_bridge.py` | 1（三层for） |
| `automation/admin/sms/court_sms_admin_actions.py` | 3 |
| `oa_filing/jtn/case_import/playwright_browser.py` | 2 |

---

## 补充：O(n²) 线性搜索（可预索引优化）

### HIGH — for > for > keyword 匹配，应建反向索引

| 文件 | 行号 | 问题 | 修复 |
|------|------|------|------|
| `contracts/services/contract/integrations/archive_classifier.py` | L453, L542, L562 | 3 个函数均 `for code > for keyword > if keyword in filename` — O(codes×keywords) | 预建 `{keyword: code}` dict，O(1) 查找 |
| `contracts/services/archive/checklist/material_mapping.py` | L142-145 | `for code > for keyword > if keyword in type_name` | 同上，建反向索引 |

### HIGH — N+1 查询反模式

| 文件 | 行号 | 问题 | 修复 |
|------|------|------|------|
| `contracts/services/archive/archive_query_service.py` | L38-52 | 内层循环逐个 `filter(pk=pk).first()` — N+1 查询 | 用 `filter(pk__in=all_pks)` 批量预取，字典查找 |

### MEDIUM — ORM 嵌套遍历

| 文件 | 行号 | 问题 | 修复 |
|------|------|------|------|
| `cases/services/case/case_admin_export_bridge.py` | L43-52 | `for party > for identity_doc`，每轮单独 DB 查询 | 加 `prefetch_related` 或批量预取 |
| `cases/services/case/case_contract_export_bridge.py` | L54-59 | 同上 | 同上 |
| `contracts/services/archive/checklist/case_material_sync.py` | L120-146 | `for case > for material`，内层调用 O(n*m) 的 `match_type_name_to_code` | 修复 material_mapping 的 O(n²) + 批量预取 |

**P0（立即修复）**：
1. `detail_extractor.py` / `html_parser.py` — 13 层/10 层，引入字段分发 dict + 单行解析 helper
2. `upload_mixin.py`（guarantee）— 拆分为 3 个子函数

**P1（近期修复）**：
3. `webdav_provider.py` — 用 XML XPath 或递归解析器
4. `case_admin_export_bridge.py` + `case_contract_export_bridge.py` — 统一三层 for 循环
5. `evidence/__init__.py` — 9 层 elif 改 dict dispatch
6. `email_folder_scan_service.py` — 提取 inner loop body

**P2（逐步优化）**：
7. 其余 MEDIUM 级别问题，通过 guard clause 和 helper 函数逐步扁平化

---

# 第二轮深度扫描追加（opus agent 并行扫描）

---

## 六、HIGH 严重 — 新发现

### `plugins/court_automation/token/history_recorder.py` L69-102
- **结构**：`try > if > if/elif 链 > try > if > for > if > if` — **6 层**
- `record_acquisition_history()` 中错误类型用字符串 `if/elif` 匹配，应改 dict dispatch

### `plugins/court_automation/login/court_zxfw_service.py` L430-546
- **结构**：`for > try > if/elif > for > if` — 4 层，**~130 行单体方法**
- `_try_captcha_login()` 混杂验证码识别、JS 注入、按钮点击、token 轮询、截图保存
- **修复**：拆分为 `_recognize_captcha()`、`_inject_captcha_js()`、`_poll_for_token()` 等子步骤

### `plugins/court_automation/login/captcha_recognizer.py` L242-286 / L339-347
- **结构**：`try > while > if > with > if > try` — **5 层**（sync + async 各一处）
- while 轮询 + 文件读取 + 条件检查 + 资源清理交织
- **修复**：将轮询逻辑提取为独立方法

### `apps/workbench/services/chat_service.py` L468-534
- **结构**：`async for > if > async for > if > if` — **6 层**
- `_run_agent()` 单个 try 块内混合 agent 迭代、流处理、tool-call 分发、结果处理

### `apps/workbench/api/workbench_api.py` L560-601
- **结构**：`while True > for > if > if / elif > if` — **5 层**
- SSE 事件生成器中的 for-in-for + 条件分支

### `apps/litigation_ai/agent/factory.py` L153-184
- **结构**：`for > async for > if > if` — **4 层**
- `astream()` 方法中 LLM 迭代嵌套流式响应 + tool-call 处理
- L43-85 和 L96-138 的 `invoke()`/`ainvoke()` 也存在相同三层嵌套且近乎重复

### `apps/contracts/services/archive/generation/pdf_utils.py` L43-112
- **结构**：`for > try > for > if/else` — **4 层**
- `scale_pages_to_a4()` 中 `is_a4` 计算逻辑在两个 for 循环中重复

### `apps/contracts/services/archive/generation/folder_builder.py` L276-349
- **结构**：`for > if > if > for > with` — **5 层**
- `_compile_final_archive_pdf()` 中 temp-file 清理逻辑嵌套在条件+循环内

### `apps/automation/services/scraper/sites/guarantee/base_mixin.py` L238-261 / L517-541
- **结构**：`for > for > for > try/if/except > try/except` — **4 层 for + 双重 try**
- `_click_first_enabled_button()` sync/async 版本完全重复

### `apps/automation/services/scraper/sites/guarantee/dialog_property_clue.py` L14-182
- **结构**：`try > for > for(retry) > if/break` — **4 层**，3 个字段类型重复相同结构
- 170 行方法内三段几乎相同的 try/except + for + retry 模式

### `apps/organization/views.py` L34-75
- **结构**：`if POST > if action > try/except > else: if` — **4 层**
- `register()` 混杂请求方法分支、action 分发、表单验证、异常处理、角色检查

---

## 七、MEDIUM 严重 — 新发现

| 文件 | 行号 | 结构 | 说明 |
|------|------|------|------|
| `workbench/services/chat_service.py` | L340-385 | `async for > if/elif > if` | 事件分发循环，与 L468 逻辑重复 |
| `workbench/services/doc_extractor.py` | L96-104 | `for > for > if > if` | 表格/元数据提取，for-in-for |
| `workbench/api/workbench_api.py` | L418-462 | `with > for > if > if` | ZIP 导出构建，与 summary.py 逻辑重复 |
| `court_automation/preservation_quote/execution_mixin.py` | L75-128 | `try > if > try > if` | token 获取，字符串匹配错误类型 |
| `court_automation/preservation_quote/admin_service.py` | L348-369 | `try > for > try > if` | 批量操作，per-item try/except |
| `court_automation/login/court_zxfw_service.py` | L636-689 | `try > for > if` (×2) | 两段近乎重复的选择器可见性检查 |
| `litigation_ai/services/mock_trial/mock_trial_flow_service.py` | L758-778 | `for > if > if/elif(6分支)` | 文本配置解析，应用 dict dispatch |
| `finance/services/calculator/interest_calculator.py` | L296-309 | `for > for > if` | 本金期间 × 利率段的 O(n×m) 嵌套 |
| `contracts/services/archive/generation/pdf_utils.py` | L291-346 | `for > try > finally > try` | 清理逻辑 5 层嵌套 |
| `contracts/services/archive/supervision_card_extractor.py` | L59-93 | `for > try > if > if` | 监管卡检测提取 |
| `contracts/services/archive/generation/download_handler.py` | L192-248 | `for > try > finally > try` | 同 pdf_utils 的 try-for-try-cleanup 模式 |
| `automation/scraper/sites/guarantee/dialog_playwright_fill.py` | L36-76 | `for > try/if > for > for` | 三段重复的 iterate-try-filter |
| `automation/scraper/sites/guarantee/guarantee_service.py` | L133-167 | `for > if > if any` | 错误检测用 fragile 字符串匹配 |
| `automation/scraper/core/monitor_service.py` | L142-169 | `for > if > if > if/else` | queryset vs list 双路径分支 |
| `automation/scraper/scrapers/court_document/hbfy_scraper.py` | L182-202 | `for > if×4` | 12 次重试循环内 4 个顺序 guard |
| `mcp_server/tools/web_search/web_search.py` | L52-67 | `for > for > if > if` | CSS 选择器遍历 |
| `organization/admin/accountcredential_admin.py` | L105-122 | `if/elif/else > if/else` | 时间格式化，应提取 helper |
| `organization/views.py` | L34-75 | `if > if > try > if` | register 视图函数 |

---

## 八、跨文件重复模式（建议统一重构）

| 模式 | 出现位置 | 建议 |
|------|----------|------|
| `try > for > finally > try` temp-file 清理 | `pdf_utils.py`、`download_handler.py` | 抽取为 context manager |
| `for > for > keyword 匹配` | `archive_classifier.py`、`material_mapping.py` | 统一预建 `{keyword: code}` 反向索引 |
| sync/async 双版本完全重复嵌套 | `captcha_recognizer.py`、`base_mixin.py`、`guarantee_service.py` | 用 async 统一，或提取共享核心逻辑 |
| `for > if/elif 长链` 字段映射 | `detail_extractor.py`、`html_parser.py`、`mock_trial_flow_service.py` | 统一用 dict dispatch |
| ZIP 导出逻辑重复 | `workbench_api.py` L418 与 `summary.py` L131 | 去重，提取公共函数 |

---

## 九、最终热点文件排名（HIGH 数量，含两轮扫描）

| 文件 | HIGH 数 |
|------|--------|
| `automation/scraper/sites/guarantee/upload_mixin.py` | 15+ |
| `automation/scraper/sites/guarantee/form_filling_mixin.py` | 6 |
| `oa_filing/jtn/case_import/detail_extractor.py` | 3（13层） |
| `oa_filing/jtn/case_import/html_parser.py` | 3（10层） |
| `cases/services/log/email_folder_scan_service.py` | 3 |
| `core/cloud_storage/webdav_provider.py` | 1（12层） |
| `automation/admin/sms/court_sms_admin_actions.py` | 3 |
| `oa_filing/jtn/case_import/playwright_browser.py` | 2 |
| `automation/scraper/sites/guarantee/base_mixin.py` | 2（sync+async） |
| `automation/scraper/sites/guarantee/dialog_property_clue.py` | 1（170行） |
| `plugins/court_automation/login/court_zxfw_service.py` | 2 |
| `workbench/services/chat_service.py` | 2 |
| `litigation_ai/agent/factory.py` | 1（3方法重复） |
| `contracts/services/archive/generation/pdf_utils.py` | 1 |
| `contracts/services/archive/generation/folder_builder.py` | 1 |
