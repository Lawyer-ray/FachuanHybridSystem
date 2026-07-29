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
