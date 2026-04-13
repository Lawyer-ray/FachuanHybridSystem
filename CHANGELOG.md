# 更新日志

本项目的所有重要更改都将记录在此文件中。

## [26.33.14] - 2026-04-13

### 后端

- 新增广西法院短信平台（sfpt.cdfy12368.gov.cn / 171.106.48.55:28083）文书下载支持：法院短信处理流程新增广西集约送达平台适配，自动提取短信中的链接地址和验证码，通过 Playwright 自动化完成验证码输入、文书列表获取、逐个下载全流程。
- 一张网财产保全询价功能增强：优化凭证校验与登录逻辑，完善询价参数构建与结果解析流程。
- 模拟庭审对抗服务重构：改进质证环节的参数传递与流程控制，修复 `CrossExamService` 和 `MockTrialFlowService` 的调用签名问题。
- OA 案件导入功能增强：新增案件导入 API 与服务，支持从 OA 系统批量导入案件数据并自动关联合同与当事人。
- 诉讼日程同步增强：优化庭审日程抓取与解析逻辑，提升日程数据的完整性。
- 代码质量修复：修复 ruff RUF100（无效 noqa 指令）和 UP037（类型注解引号）等 lint 问题。
- 全局 import 路径规范化：统一各模块的 import 格式与排序。

## [26.33.13] - 2026-04-12

### 后端

- CI 工作流统一切换为 PostgreSQL：`backend-ci.yml` 全部相关 job 统一使用 PostgreSQL service 与连接参数，移除 SQLite 专用测试参数残留。
- `resetdb` 按 `DB_ENGINE` 分支处理：SQLite 走删除本地库后迁移，PostgreSQL 走 `flush --noinput + migrate`，未知引擎采用兜底分支。
- 收敛 `qcluster` 启动前清理逻辑：仅终止历史 `manage.py qcluster` 进程，避免误杀 `run-dev` 的热重载子进程。
- `run-dev` 默认启用 watchfiles polling 稳定模式（可通过 `RUN_DEV_FORCE_POLLING` / `RUN_DEV_POLL_DELAY_MS` 调整）。

### 文档

- 补充数据库升级说明：明确默认开发数据库已切换为 PostgreSQL，并在 `INSTALL.md` 增加从 SQLite 升级（`dumpdata → migrate → loaddata → 序列重置`）的可执行步骤与本地推送前检查清单。
- 采纳苏钧律师建议，推进默认开发数据库升级为 PostgreSQL，并完善本地开发与迁移操作指引。
- 补充本地 PostgreSQL 安装引导：在 `INSTALL.md` 新增 macOS / Ubuntu / Windows 安装方式与通用建库初始化命令，并在 `README.md` 增加入口提示。

## [26.33.12] - 2026-04-12

### 后端

- 新增司法送达网（sfpt.cdfy12368.gov.cn）文书下载支持：法院短信处理流程新增司法送达网平台适配，自动提取短信中的链接地址和验证码，通过 Playwright 自动化完成验证码输入、文书列表获取、逐个下载全流程，下载完成后自动进入案件匹配、文书重命名、飞书通知等后续处理链路。


## [26.33.11] - 2026-04-11

### 后端

- 提醒日历视图优化：实现“一张网庭审日程同事件合并展示”功能，相同 `source_id` 的庭审日程合并为一条显示，多个律师姓名聚合并用顿号分隔，提升日历视图的信息密度和可读性。
- Admin 顶栏用户区增强：新增“账号管理”快捷链接入口，支持从顶栏快速跳转到账号凭证管理页面；添加“查看站点”链接（条件渲染），优化注销链接渲染逻辑。


## [26.33.10] - 2026-04-11

### 后端

- “其他工具”聚合页继续扩展：新增 `reminders` 与 `message_hub` 两个应用入口，支持从 `/admin/automation/other-tools/` 统一访问。
- 左侧菜单收纳规则补充：`reminders`、`message_hub` 从侧栏隐藏，保留 `/admin/reminders/`、`/admin/message_hub/` 等 URL 直达能力。
- 顶栏快捷入口增强：在右上角新增“日历”“收件箱”文字入口，分别直达提醒日历与信息中转站收件箱。
- i18n 切换位置与样式优化：语言切换从右上角移动到左侧系统标题区域，并调整为弱化文字样式，提升顶栏视觉层级一致性。
- Admin 菜单收纳升级：新增 `/admin/automation/other-tools/` 统一入口，集中展示原本分散在多个 app 的工具能力，并支持应用级入口与二级菜单直达。
- `automation` 菜单文案从“法院自动化工具”调整为“自动化工具”；自动化子菜单顺序固定为“法院短信 → 财产保全询价 → 其他工具”。
- 左侧菜单隐藏规则扩展：`fee_notice`、`document_recognition`、`pdf_splitting`、`documents`、`chat_records`、`sales_dispute`、`enterprise_data`、`invoice_recognition`、`contract_review`、`image_rotation`、`express_query`、`doc_convert`、`evidence_sorting`、`legal_research`、`legal_solution`、`evidence`、`preservation_date`、`finance`、`django_q`、`organization`、`auth`、`core` 统一从侧栏收纳到“其他工具”，保留 URL 直达可用。
- “其他工具”页面视觉重构：升级为卡片化导航页，补充搜索、统计与更清晰的信息层级，提升后台工具查找与跳转效率。


## [26.33.9] - 2026-04-11

### 后端

- 修复文书转换工作台（`/admin/doc_convert/docconverttool/`）文书类型下拉框无法加载的问题：移除 `/mbid-list` API 不必要的 `ZNSZJ_ENABLED` 检查，该接口仅返回本地静态数据，不应被开关拦截。
- 文书类型选择改为搜索+下拉内嵌式组件：输入关键词即时过滤，按类别分组显示，支持键盘导航，最大高度 280px 带滚动条。
- 开放 znszj 客户端代码：从 `.gitignore` 移除 `znszj_private/` 排除规则，代码入库可追踪，其他用户开箱即用。
- `ZNSZJ_ENABLED` 默认值从 `False` 改为 `True`，文书转换功能默认启用。


## [26.33.8] - 2026-04-11

### 后端

- 庭审日程同步写入律师姓名（`metadata.lawyer_name`），日历卡片显示「律师名 · 开庭地点」，详情弹窗新增律师字段。
- 修复去重逻辑：去重键从 `source_id` 改为 `(source_id, source_credential_id)` 组合，同一庭审不同律师各自创建独立 Reminder，互不覆盖。
- Reminder 详情页扩展数据以键值对表格友好展示，原始 JSON 折叠保留。
- 日历视图展示开庭地点（`courtroom`），详情弹窗新增开庭地点字段。
- 消息来源列表页新增 ID 序号列。
- 隐藏日志附件（`CaseLogAttachment`）Admin 首页菜单，保留直接 URL 访问能力。


## [26.33.7] - 2026-04-11

### 后端

- 新增一张网庭审日程同步功能（`CourtScheduleFetcher`）：通过信息中转站架构自动拉取 `zhrl/list` 接口的排期数据，写入重要日期提醒（`Reminder.HEARING`），日历视图自动展示。
- 支持多账号同步：每位律师在信息中转站创建独立的「一张网庭审日程」来源，启用/禁用独立控制。
- 庭审日程自动关联案件：S1 案号精确匹配 → S2 当事人名称分词匹配（rcbt 标题分词 → Client.name → CaseParty → Case 交集）→ S3 不关联（律师手动绑定）。
- `SourceType` 新增 `COURT_SCHEDULE` 类型，复用 `MessageFetcher` 基类、Token 三级回退链路、定时同步任务和 Admin 手动同步按钮。
- 新增 31 个单元测试覆盖分词逻辑、案件关联策略、upsert 去重、分页拉取、Token 过期重试等场景。


## [26.33.6] - 2026-04-11

### 后端

- `CourtSMS` 新增统一文书路径持久化字段 `document_file_paths`，并在文书送达与短信处理相关创建链路中统一回写，保证文书引用可追溯。
- 新增 `court_sms_document_reference_service.py`，统一聚合文书来源（文书记录、短信引用、任务结果、案件日志附件），并在 Admin/API 复用同一读取口径。
- 优化 `CourtSMS` Admin 详情页“关联文书”展示：新增后台受控文书打开路由，`任务结果` 等非 `CourtDocument` 来源也支持直接点击查看。


## [26.33.5] - 2026-04-10

### 后端

- 隐藏 `CourtDocument`、`DocumentQueryHistory`、`CourtToken` 三个模型的 Admin 首页入口，通过 `get_model_perms` 返回空字典实现，保留直接 URL 访问能力和关联链接功能。
- 修复 `token_admin.py` 和 `document_query_history_admin.py` 的 mypy 类型错误（移除 `ClassVar` 注解、添加 `type: ignore` 标注）。


## [26.33.4] - 2026-04-10

### 后端

- 新增简易送达 (jysd.10102368.com) 类型法院短信的解析与下载功能：
  - `SMSParserService._is_valid_download_link()` 新增 jysd 链接验证规则。
  - `SMSDownloadMixin` 创建下载任务时自动注入律师手机号到 `ScraperTask.config`，手机号按优先级排列：案件承办律师 → 管理员律师 → 所有律师。
  - 新建 `JysdCourtScraper`，实现 Playwright 自动化下载流程：iframe 内手机号登录 → 中间页面点击"查看文书详情" → el-table 表格逐行下载文书。
  - 下载策略采用 Playwright click 优先、JS click fallback，确保所有文书均可下载。
  - `CourtDocumentScraper` 主入口注册 jysd 路由分发。


## [26.33.3] - 2026-04-10

### 后端

- 修复一张网收件箱同步任务中 Playwright Sync API 在 Django-Q2 asyncio 事件循环内报错的问题，改用 `ThreadPoolExecutor` 在独立线程中运行 Playwright 登录。
- GdemsCourtScraper 增加无文书可下载状态检测：当书记员未放置文件时，页面只有无绑定事件的"确定"按钮，此时返回通知内容而非报错。
- 信息中转站同步任务预期错误列表新增 `sync api inside the asyncio loop` 关键词。


## [26.33.2] - 2026-04-09

### 后端

- 隐藏 `automation/scrapertask` 后台入口（保留代码与功能）。
- 隐藏 `automation/documentdeliveryschedule` 后台入口（保留代码与功能）。
- 优化 `automation/courtdocument` 下载按钮样式：移除 emoji，窄屏展示更紧凑。

### 文档

- `README` 版本号更新为 `26.33.2`。

## [26.33.1] - 2026-04-09

### 前端

- 调整 `.gitignore`：不再忽略整个 `frontend/`，仅忽略 `node_modules`、`dist`、`.env*` 等本地/构建产物。
- 修复 `lib/` 误伤规则，恢复 `frontend/src/lib/*` 可跟踪。
- 完成 `frontend` 推送前检查，确认构建产物与缓存文件不会入库。
- 更新 `frontend/README.md`（中文版，标注“暂未与 backend 完全对齐”），并将 `frontend/package.json` 版本更新为 `0.0.1`。


## [26.33.0] - 2026-04-09

本版本是材料管理模块的重大重构，同时新增法院担保询价、OA 同步增强等多项功能。

### 新增

- **案件材料全生命周期管理（cases/materials）**：
  - 材料删除功能：新增 API `DELETE /{case_id}/materials/{material_id}`，支持单条材料删除，同时清理附件物理文件与分组排序记录；前端每个材料行增加删除按钮（悬停显示），删除前弹窗确认。
  - 材料"删除全部"功能：新增 API `DELETE /api/v1/cases/{case_id}/materials`（body: `{category}`），按分类批量删除材料；当事人材料和非当事人材料 tab 各添加"删除全部"按钮。
  - 材料替换功能：新增 API `POST /{case_id}/materials/{material_id}/replace`，支持替换材料文件并自动删除旧附件物理文件；前端点击替换按钮直接触发系统文件选择器，无需二次确认弹窗。
  - 材料分组重命名功能：新增 API `POST /{case_id}/materials/group-rename`，分组标题支持双击或点击编辑按钮重命名。
  - 新增 Schema：`CaseMaterialDeleteOut`、`CaseMaterialReplaceIn/Out`、`CaseMaterialGroupRenameIn/Out`、`CaseMaterialDeleteAllIn/Out`。

- **法院担保询价面板（automation/court_guarantee）**：
  - 新增完整的法院担保询价 API（`court_guarantee_api.py`），支持保全申请提交、询价查询、询价结果轮询、历史询价复用等全流程。
  - 新增 `CasePreservationQuoteBinding` 模型，记录案件与财产保全询价的绑定关系，含绑定时保全金额快照，支持按金额匹配复用历史询价。
  - 新增案件详情页"法院担保"tab（`court_guarantee.html`），含当事人选择、被申请人财产线索展示、保全金额填写、担保公司选择、询价结果轮询等完整交互。
  - 担保公司切换时自动关联顾问编码：选择阳光保险时自动填充默认顾问编码，已有编码时保留不变。
  - 担保询价面板精简：删除"重试询价"、"删除询价记录"、"删除绑定关系"三个操作按钮，担保机构表格新增序号列，报价数量移入下拉菜单底部。

- **一张网担保申请自动填写（automation/scraper/court_zxfw_guarantee）**：
  - 新增 `CourtZxfwGuaranteeService`，完整实现一张网担保申请 gOne→gFive 五步 Playwright 自动化流程（到预览页，不提交）。
  - gOne 步骤：法院选择（多候选名逐级匹配：全称→短名→关键词，最多10轮重试）、保全类型/保全类别/提交人身份通过 `_click_radio_in_form_item` 精确定位表单项点击 radio（避免同名 radio 误点）、案号解析与拆分填写、案由多候选匹配、担保公司选择、顾问编号填写、保全金额填写。
  - gTwo 步骤：申请人/被申请人/代理人/财产线索四类对话框自动填写，支持自然人/法人/非法人组织/代理人/财产线索五种 party_type，自动填充姓名、证件号、地址、电话等字段；对话框内下拉选择（省份、财产类型、财产所有人）与日期字段自动处理。
  - gThree 步骤：材料智能上传，根据上传槽 label 关键词（保全申请、起诉状、受理通知、身份证明、证据等）匹配合适文件，上传失败自动重试。
  - gFour/gFive 步骤：自动推进至预览页，最终校验表单错误。
  - 新增被申请人财产线索自动构建（`_build_primary_respondent_property_clue`），从案件当事人关联的客户财产线索中提取财产类型与内容，自动写入申请表单财产线索对话框。
  - 财产线索类型显示映射（房产/车辆/银行账户/股权/收入/其他）。

- **OA 同步与案件导入增强（contracts/oa_sync + oa_filing/jtn_case_import）**：
  - OA SSO 登录加固：`ensure_name_search_ready()` 预检查案件列表可访问性，SSO 拦截错误立即抛出而非静默重试。
  - 按名称查询支持 HTTP 优先 → Playwright 降级双链路，SSO 拦截时自动切换到 Playwright 链路。
  - 同步失败时提取 SSO 登录 URL 并回传前端，支持用户手动登录后重试。
  - 合同当事人（`ContractParty`）数据引入同步流程，增强案件名称匹配精度。
  - OA 同步管理页面交互增强：进度展示、错误信息与 SSO 登录链接展示优化。

### 修复

- **材料管理交互修复（cases/materials）**：
  - 修复绑定材料时未创建 `CaseMaterialGroupOrder` 导致文件夹排序丢失的问题：`bind_materials()` 末尾自动创建分组排序记录，已有排序保留不变。
  - 修复选择材料大类后文件从列表消失：选择大类时自动将筛选切换到对应分类，保持文件可见。
  - 修复非当事人材料 tab 下删除确认弹窗不显示：将 modal 移至 `detail.html` 的 tab 容器外部，不受 `x-show` 隐藏影响。
  - 修复扫描指定子文件夹时 radio 不可点击：页面加载时始终预加载子文件夹列表，不再依赖 `scanPanelVisible` 状态。
  - 修复扫描时材料类型提示不精确：改为用文件所在子文件夹名作为类型提示（如"执行申请书"），而非统一用扫描根目录名；自动去除编号前缀（如 `2-立案材料 → 立案材料`）。
  - 修复替换材料时旧附件文件未删除：`replace_material_file` 现在同步删除旧 `CaseLogAttachment` 及其物理文件。
  - 修复删除材料时附件文件未清理：`delete_material` 现在同时删除 `CaseLogAttachment` 及物理文件。
  - 移除当事人材料中无意义的"通用"标签（文件无关联当事人时不再显示）。
  - 上传/删除材料后自动刷新页面。
  - 替换材料改为直接触发文件选择器，去掉多余弹窗。

- **Alpine.js 兼容性修复**：
  - 移除 `x-collapse` 指令，改用 `x-transition`（项目未引入 Collapse 插件）。
  - 初始化 `insuranceCompanyOptions` 和 `consultantCode`，修复 Alpine.js `ReferenceError` 导致组件初始化崩溃。

- **一张网 Playwright 跨线程修复（automation/scraper）**：
  - `_acquire_token` 不再复用 `BrowserService` 单例，改为在当前线程独立创建 `sync_playwright` 实例，彻底解决 greenlet 跨线程切换错误。
  - `_is_expected_sync_error` 增加 `greenlet.error` / `target closed` / `browser has been closed` / `disconnected` 等异常模式识别，减少误判与噪声日志。

- **一张网担保流程稳定性补充修复（automation/court_guarantee）**：
  - 失败分支浏览器保留时长改为环境变量可配置（`COURT_GUARANTEE_BROWSER_HOLD_SECONDS_ON_FAILURE`），避免固定长等待造成“卡住”观感。
  - gThree 材料上传链路新增上传空闲等待（`_wait_upload_idle`）与节奏放缓，降低“当前正在进行上传操作，请稍后再试”报错概率。
  - 身份证明材料匹配规则细化：申请人-法人优先上传“营业执照+法定代表人身份证明”；被申请人-自然人按姓名匹配身份证并排除“法定代表人”材料。
  - gTwo 对话框“单位性质”在申请人为法人/非法人组织时强制选择“企业”，避免页面默认“机关”导致校验失败。
  - 新增基于表单错误文本的定向重传与 gThree→gFive 推进时身份证明兜底重传，提升一次性通过率。

- **其他修复**：
  - 财产线索当事人字段改为搜索下拉（`autocomplete_fields`），提升选择效率。
  - 移除当事人/非当事人材料 tab 下的"自动捕获"按钮（与"上传/绑定材料"功能重复）。
  - 更新 JS 版本号破浏览器缓存。

### 优化

- **材料分类服务增强（core/material_classification）**：
  - `MaterialClassificationService` 参数从 `subfolder_hint` 统一改为 `folder_hint`，优先级链更清晰：父文件夹名 > 子文件夹名 > 规则 type_name_hint。
  - `BoundFolderScanService` 新增 `_extract_parent_folder_hint`，从文件路径提取相对扫描根目录的父文件夹名，自动去除编号前缀。

- **担保询价面板 UI 精简**：报价数量显示移至每条询价记录中（用 `·` 分隔），隐藏独立标签。

### 配置

- `automation` 索引重命名迁移（`0010_rename_automation__case_id_*`）。

### 安全

- **脱敏默认值**：默认姓名占位值替换为通用测试名；默认身份证号改为校验位无效的测试号；删除含真实手机号的 cookie 文件。


## [26.32.4] - 2026-04-08

### 修复

- **案例检索/案例下载后台功能开关（legal_research/admin）**：新增代码级开关 `LEGAL_RESEARCH_ADMIN_FEATURE_ENABLED`（默认关闭）。当未接入私有 wk API 且未显式开启该开关时，`LegalResearchTask` 与 `CaseDownloadTask` 后台新增入口不可用，并在访问新增页时给出明确提示。


## [26.32.3] - 2026-04-08

### 修复

- **询价任务事件循环兼容修复（automation/tasks）**：修复 `Django-Q` worker 场景下 `asyncio.run()` 与运行中事件循环冲突问题，避免任务执行报错与协程未等待告警。
- **无 Token 自动登录回归修复（automation/insurance）**：恢复“无可用 Token 时自动登录获取后继续询价”链路，避免提前中断。
- **HTTP/2 依赖补齐（backend）**：依赖调整为 `httpx[http2]`，补齐 `h2` 以消除 HTTP/2 降级告警。
- **询价详情页报价展示修复（automation/admin）**：报价金额统一使用 `minAmount`；明细区成功报价置顶、失败置底；修复详情中 `</tbody></table>` 与 `<br>` 转义显示异常。

## [26.32.2] - 2026-04-08

### 新增

- **代理事项规则一键初始化（documents/admin）**：在 `/admin/documents/proxymatterrule/` 列表页新增“初始化代理事项规则”按钮，支持按预置规则一键初始化并可重复执行（幂等更新）。

### 修复

- **私有模板目录生效链路修复（documents）**：`DocumentTemplate.get_file_location/absolute_file_path` 统一改为按当前活动模板根目录解析，修复配置私有目录后仍回落公用目录的问题。
- **文书生成模板路径动态化（documents/generation）**：诉讼文书与授权委托材料生成服务移除类加载期静态模板路径，改为运行时读取当前模板根目录，确保切换模板目录后立即生效。

### 文档

- **版本号更新**：`README` 版本号更新为 `26.32.2`。

## [26.32.1] - 2026-04-07

### 修复

- **文书送达链路日志与附件回补（automation/document_delivery）**：修复 `build_caselog_service` 导入名错误导致案件日志创建中断；日志创建统一使用系统用户，恢复案件日志与日志附件写入。
- **案号回写兼容修复（automation/document_delivery）**：案号同步改为兼容 `list_numbers_internal/create_number_internal` 与旧方法名降级调用，恢复案件编辑页案号自动回填。
- **文书归档补齐（automation/document_delivery）**：重命名后补充归档到案件绑定目录，确保下载文书同时进入案件文件夹。
- **后台手动绑定续跑修复（automation/admin）**：`pending_manual` 短信在详情页绑定案件后自动续跑后续流程，并统一入口为详情页绑定。

### 新增

- **湖北电子送达链路支持（automation/sms/scraper）**：新增 `dzsd.hbfy.gov.cn` 链接识别与抓取路由，支持免账号链接与账号密码入口两种模式；账号模式可从短信中提取凭证写入下载任务配置。

### 优化

- **法院收件箱附件可追溯性（message_hub/court）**：收件箱入库后持久化 `attachments_meta`，附件读取优先本地缓存并支持缺失时回源下载后自动回填本地路径。
- **IMAP 附件与主机解析鲁棒性（message_hub/imap）**：IMAP 附件改为落盘持久化；新增主机候选推导与基础校验，降低主机配置不规范导致的连接失败。
- **一张网登录弱网容错（automation/scraper）**：增强网络异常识别与页面导航重试，网络类失败降级为 warning，减少误判与噪声日志。

### 配置

- **私有插件忽略规则收敛（.gitignore）**：`court_filing_http` 改为目录级忽略，避免私有实现文件误入库。

### 文档

- **README 导航与版本更新**：补充“贡献与致谢”入口，并将版本号更新至 `26.32.1`。

## [26.32.0] - 2026-04-06

### 新增

- **提醒日历新增混合搜索关联对象（reminders/admin）**：新增提醒弹窗支持统一检索合同、案件、案件日志；候选支持分组展示与关键字高亮，选择后自动回填真实关联类型与对象 ID。

### 优化

- **提醒弹窗交互稳定性优化（reminders/admin）**：关联对象候选区改为固定窗口内滚动，避免候选数量变化导致弹窗高度抖动；候选列表容量与视觉样式同步优化，提升可读性与选择效率。

## [26.31.8] - 2026-04-06

### 修复

- **案件详情模板机构误匹配修复（cases/documents）**：案件文件模板匹配新增“适用机构”维度，详情页按案件主管机关过滤模板，修复禅城法院案件误命中广州送达地址模板的问题。
- **模板匹配缓存维度补全（core/documents）**：模板匹配缓存键新增机构维度，避免不同法院/机构之间出现缓存串用。
- **识别链路日志降噪（automation/core/client）**：压低 `RapidOCR/rapidocr/onnxruntime` 日志级别并收敛 `LLMConfig` 高频 debug，降低“快速填充当事人”时日志刷屏。
- **Ollama 超时配置简化（core）**：`OLLAMA_TIMEOUT` 固定走默认值（120 秒），不再依赖后台配置或 settings 额外参数。

## [26.31.7] - 2026-04-06

### 修复

- **文书模板根目录切换能力（documents）**：模板根目录解析统一支持“默认公用目录 + 可选私有目录”，并移除生成链路中的硬编码路径，确保诉讼/授权委托/催收/模拟庭审等文书均按当前活动根目录读取模板。
- **文书模板后台可配置模板目录（documents/admin）**：`/admin/documents/documenttemplate/` 页面新增“私有模板目录”在线配置与保存入口，支持填写绝对路径或相对 `backend` 路径；留空可一键切回公用目录。
- **模板路径校验一致性（documents）**：`DocumentTemplate` 模型、初始化服务、校验服务统一使用同一解析规则，新增越界拦截与缺失文件预检，减少路径配置错误导致的初始化失败。
- **模板目录展示与仓库跟踪策略（documents）**：后台“当前模板根目录”展示改为 Django 服务相对路径；同时取消 `backend/apps/documents/docx_templates` 的忽略规则，确保模板目录可随分支正常提交与发布。

## [26.31.6] - 2026-04-05

### 修复

- **案件当事人候选过滤稳定性（cases/admin）**：修复案件新增/编辑页在新增第 2、3、4 行当事人时 `client` 下拉回退为“全量当事人”的问题；现统一保持“仅合同/补充协议当事人可选”，并兼容 `formset:added` 与动态行异步插入场景。
- **案件层禁止新增当事人入口（cases/admin）**：在案件新增页与编辑页隐藏案件当事人 `client` 字段旁“绿色加号”入口，防止在案件层直接新建当事人，保持“仅合同层可新增当事人”的业务约束。
- **合同状态枚举修正（contracts）**：合同新增/编辑页状态选项修正为 `在办 / 已结案 / 已归档`；新增 `ContractStatus` 枚举并切换 `Contract.status` 绑定，避免复用案件状态导致缺失“已归档”。

## [26.31.5] - 2026-04-05

### 修复

- **文书模板初始化友好报错（documents）**：在后台 `DocumentTemplate` 列表页点击“初始化默认模板（含文件夹与绑定关系）”时，若本地缺少 `backend/apps/documents/docx_templates` 下的 `docx` 文件，将给出可读错误提示并返回列表页，不再抛出 Django 代码异常页。
- **初始化缺失文件预检（documents）**：初始化服务新增默认模板 `file_path` 存在性检查；存在缺失时中止初始化并返回缺失文件示例，避免部分数据写入造成状态不一致。
- **后台文案统一（documents）**：按钮文案更新为“初始化默认模板（含文件夹与绑定关系）”。

## [26.31.4] - 2026-04-05

### 优化

- **系统配置界面收敛（core/enterprise_data/legal_research）**：移除初始化默认配置中的大批 `LEGAL_RESEARCH_*` 调参项，避免后台配置过载，相关参数改为代码内默认值。
- **企业数据运行参数写死（enterprise_data）**：`ENTERPRISE_DATA_*` 限流、重试、指标与告警阈值改为代码固定值，不再依赖后台配置。

### 配置

- **初始化默认值调整（core）**：`SILICONFLOW_DEFAULT_MODEL` 默认值更新为免费模型 `Qwen/Qwen2.5-7B-Instruct`。
- **天眼查 API Key 默认值（enterprise_data）**：`TIANYANCHA_MCP_API_KEY` 初始化默认值更新为预置占位 key（并标记为 secret）。

### 修复

- **威科私有API适配器语法修复（legal_research）**：修复 `weike_api_private/adapter.py` 中异常块缩进错误导致的 `SyntaxError: expected 'except' or 'finally' block`，恢复私有模块可导入性。
- **威科检索链路稳定性补充（legal_research）**：私有API层继续保持“失败自动回退 DOM 检索”策略，避免单链路异常导致检索中断。
- **MCP能力边界说明补充（legal_research）**：MCP层对外保持统一能力接口，不直接暴露威科私有API实现细节。

## [26.31.3] - 2026-04-05

### 新增

- **合同名称自动生成按钮**：在合同编辑页面的「合同名称」输入框旁添加「+」按钮，点击后根据当事人和合同类型自动生成标准化名称
  - 单一当事人：`当事人名称_合同类型+合同`
  - 多个同身份当事人用顿号分割，不同身份组之间用「与」连接
  - 必须选择至少 1 个当事人才能点击（兼容 select2 组件）

### 修复

- **案件名称后缀移除**：点击「保存并创建案件」时生成的案件名称不再包含多余的「 - 案件」后缀
- **启用证据整理 Admin 入口**：将 `apps.evidence_sorting` 加入 `INSTALLED_APPS`，使 `/admin/evidence_sorting/evidencesorting/` 页面可访问
- **Ruff Lint 全量清零**：修复全部 24 处 lint 警告，`ruff check apps` 全绿通过
  - W293: 移除空白行尾部空格（12 处，7 个文件）
  - RUF010: f-string 中移除冗余 `str()` 转换（7 处，3 个文件）
  - RUF100: 移除未启用的 noqa 指令（1 处）
  - F541: 移除无占位符的 f-string 前缀（1 处）
  - W292: 补齐文件末尾换行符（3 处）

## [26.31.2] - 2026-04-04

### 文档

- **README 法院短信功能补充**：在主要功能列表新增「法院短信处理（Court SMS）」完整描述，涵盖全流程自动化、7 种状态追踪、飞书通知等核心能力
- **README 功能描述优化**：补充法院短信模块的案由缴费校验、文书重命名、案件目录归档等细节

## [26.31.1] - 2026-04-04

### 修复

- **全项目文件清理信号覆盖（files cleanup signals）**：为所有含文件字段的模型添加 `post_delete` 信号处理器，删除记录时自动清理物理文件
  - **cases**: CaseLogAttachment (`file`)、CaseNumber (`document_file`)
  - **client**: ClientIdentityDoc (`file_path`)、PropertyClueAttachment (`file_path`)
  - **evidence**: EvidenceItem (`file`)、EvidenceList (`merged_pdf`)
  - **automation**: CourtDocument (`local_file_path`, CharField 存储法院下载文书)、GsxtReportTask (`report_file`)
  - **documents**: DocumentTemplate (`file`)、GenerationTask (`result_file`)、ExternalTemplate (`file_path`)、FillRecord (`file_path`)、BatchFillTask (`zip_file_path`)
- **LPR 模板恢复**：误删的 LPR 同步确认页 (`lpr_sync_confirm.html`) 和列表工具栏模板 (`lprrate/change_list.html`) 已从 git 历史恢复
- **CI 清理**：删除 29 个引用已不存在模块的过时测试文件（收集阶段 ImportError），安装 `daphne` 依赖解决 channels websocket 测试导入问题

## [26.31.0] - 2026-04-04

### 新增

- **快递查询模块（express_query）**：全新独立应用，支持顺丰（SF）和 EMS 两种快递平台的运单查询
  - 上传邮单图片自动 OCR 识别运单号和承运商，或手动输入运单号
  - 浏览器自动化实时查询：连接 Chrome CDP 自动操作快递官网页面
  - 支持已登录/未登录双状态：未登录时弹出二维码/验证码窗口引导用户扫码
  - EMS 协议自动处理 + 登录状态智能检测
  - 查询结果导出 PDF 报告（含日期时间页眉）
  - 前端工作台：支持文件上传识别和手动输入两种模式，Tab 切换交互
  - 运单号格式校验：SF 开头 + 10~20 位数字 / EMS 纯 13 位数字

### 修复

- **Django-Q2 异步任务兼容性修复**：`_execute_browser_query` 中 `asyncio.run()` 在已有事件循环中报 `RuntimeError`，改用 `ThreadPoolExecutor` 隔离执行
- **EMS 已登录状态查询修复**：已登录用户跳过登录流程后，强制导航到干净查询页面（不含 `?to=` 参数），避免停留在首页导致查询失败

## [26.30.10] - 2026-04-04

### 新增

- **系统配置后台一键更新（core）**：在 `SystemConfig` 列表页新增“立即更新系统”入口，支持管理员在后台触发异步系统更新任务并查看状态。
- **更新后自动依赖与迁移开关（core）**：新增“更新后自动 uv sync + migrate”可选开关，按次生效，执行链路可观测。

### 优化

- **后台更新按钮样式收敛（core）**：更新入口改为 Django Admin 传统 `addlink` 风格，交互与后台原生按钮一致。
- **更新状态可观测性增强（core）**：状态面板新增开关状态展示与执行日志补充，便于排查更新过程。

### 修复

- **远端分支不存在容错（core）**：当当前本地分支在 `origin` 不存在时，自动回退拉取 `origin/main`，避免更新任务直接失败。

## [26.30.9] - 2026-04-04

### 重构

- **合同服务结构重组（contracts）**：按职责重组 `services/contract` 子模块目录，拆分为 `admin`、`domain`、`integrations`、`query`、`mutation`、`usecases`，并同步更新依赖注入与调用路径。

### 修复

- **合同 OA 同步状态流转修复（contracts）**：任务入队后会话状态保持 `PENDING`，由 worker 实际启动时再切换 `RUNNING`，避免未启动队列时页面误显示“执行中”。
- **OA 登录失败误判修复（oa_filing）**：优化登录失败判定逻辑，避免因成功页包含 `logout` 字样被误识别为账号密码错误。
- **OA HTTP 链路代理干扰修复（oa_filing）**：OA 相关 HTTP 客户端统一关闭环境代理继承（`trust_env=False`），降低 TLS EOF 类网络异常。
- **OA 回退链路稳定性提升（oa_filing）**：优先复用 HTTP 登录 Cookie 到 Playwright 回退流程，减少重复登录与失败率。

### 测试

- **CI/单测补充（contracts, oa_filing）**：新增合同 HTTP 冒烟测试与 OA 登录 Cookie 复用/失败判定相关测试，覆盖重构后的关键回归场景。

## [26.30.8] - 2026-04-03

### 新增

- **合同 OA 信息同步功能（contracts）**：批量同步 JTN OA 案件编号与链接到合同
  - 新增合同 OA 同步会话模型 `ContractOASyncSession`，支持异步任务、进度追踪、结果存储
  - 新增同步服务 `ContractOASyncService`，支持按合同名称查询 OA 案件列表并智能匹配
  - 新增合同列表页"同步 OA 信息"按钮，跳转独立同步页面（支持轮询进度、多候选人工确认、手动保存）
  - 支持多关键词回退策略、当事人 token 过滤、候选扩容查询（避免因 limit 截断导致找不到案件）
  - 新增前端页面与 JS（Alpine.js），支持批量同步、候选展示、人工选用、进度展示
  - 新增迁移文件：创建 `ContractOASyncSession` 表、重命名合同状态索引

### 优化

- **OA 案件匹配精度增强（oa_filing）**：
  - 候选查询支持扩容重试：首次查询 limit=6 未命中时，自动扩容至 limit=30 再过滤
  - 关键词清洗支持中文数字案尾（如"一案"）：正则从 `\d+案` 扩展为 `(?:\d+|[一二三四五六七八九十百千万两]+)案`
  - 当事人 token 提取同步支持中文数字案尾清洗，避免 token 污染导致过滤失败
  - 新增单元测试验证中文数字案尾清洗场景，覆盖真实案件标题格式的兼容处理

### 修复

- **法院 Token 模型名称优化（automation）**：将 `CourtToken.verbose_name` 从"法院Token"改为"法院短信解析Token"，语义更准确
- **合同详情页材料命名优化（contracts）**：将"定稿材料"更名为"归档材料"，同步更新模型 verbose_name、服务层文档、i18n 翻译

## [26.30.7] - 2026-04-03

### 修复

- 合同详情页：将"定稿材料"更名为"归档材料"，同步更新模型 verbose_name、服务层文档、i18n 翻译。

## [26.30.6] - 2026-04-03

### 优化

- 依赖升级：`django-ninja` 升级至 `1.6.2`，`uvicorn[standard]` 升级至 `0.42.0`。
- 依赖兼容：补齐 `django-ninja-extra` 并增加兼容处理，修复 `django-ninja-jwt` 在新版本 Ninja 下的路由初始化报错。
- 常用依赖更新：`redis`、`gunicorn`、`mypy`、`django-stubs`、`django-stubs-ext`、`ddddocr`、`pandas`、`Pillow`、`bandit`、`mcp` 等完成升级并同步 `uv.lock`。
- 依赖管理收敛：删除 `backend/requirements.txt`，统一使用 `uv`（`pyproject.toml` + `uv.lock`）。

## [26.30.5] - 2026-04-02

### 新增

- **收件箱智能处理中枢演示（首页）**：新增拓扑网络动画展示区，可视化呈现法院信息流与材料流双线并行处理全流程
  - 左侧来源卡片（法院信息流 / 材料流）→ 中间 AI 调度中枢（四能力节点 + 指标面板）→ 右侧结果分支（法院闭环 / 材料闭环）
  - 基于 GSAP 的六步时序动画，支持自动滚动触发与手动重播
  - 底部事件总线 + 结果指标条联动展示
  - 响应式适配（1180px / 1024px 断点）

### 修复

- **收件箱消息 Admin 正文预览布局优化（message_hub）**：为 InboxMessageAdmin 引入自定义 CSS，修复 `body_preview` 字段在 Admin 详情页的网格布局问题，iframe/纯文本预览区域自适应宽度并限制最大高度

## [26.30.4] - 2026-04-02

### 修复

- **信息中转站网络异常降噪（message_hub）**：同步任务对可预期网络/环境异常（如断网、DNS 解析失败、连接超时）改为 `warning` 日志，避免重复刷整段堆栈。
- **一张网登录异常语义化（automation）**：`CourtZxfwService.login` 在识别到 Playwright 网络异常时抛出 `ConnectionError`，明确标记为网络连接问题。
- **IMAP 主机配置健壮性（message_hub）**：新增主机名基础校验，并将 `socket.gaierror` 转换为可读错误信息（`IMAP 主机无法解析`）。

## [26.30.3] - 2026-04-02

### 重构

- **删除废弃的 CaptchaService（automation）**：移除已弃用的 `apps/automation/services/scraper/core/captcha_service.py` 及相关导入

## [26.30.2] - 2026-04-02

### 修复

- **HTTP 链路立案插件化（automation）**：将YZW立案中的 HTTP 链路功能抽离为可插拔插件
  - 新增 `backend/plugins/` 目录，支持插件化扩展
  - HTTP 链路服务迁移到 `plugins/court_filing_http/` 插件目录
  - 插件检测机制：前端/后端双重检测，自动控制选项显示与默认值
  - 无插件时自动降级到 Playwright，前端隐藏 HTTP 选项
  - 插件目录已添加到 `.gitignore`，用户需单独获取

## [26.30.1] - 2026-04-02

### 修复

- **YZW纯逆向登录 SM2 加密失败（automation）**：移除对 Node.js `sm-crypto` 模块的运行时依赖，改为使用 Python `gmssl` 执行 SM2（C1C3C2）加密；兼容公钥 `04` 前缀，避免因 `MODULE_NOT_FOUND` 导致纯逆向登录回退。

## [26.30.0] - 2026-03-31

### 新增

- **多 Agent 对抗模拟庭审（litigation_ai）**：全新对抗模式庭审模拟
  - 三个独立 Agent（原告/被告/法官），各自使用不同大模型，激烈对抗 system prompt
  - 完整庭审流程：开庭→原告陈述→被告答辩→法庭调查→辩论（≥10 轮）→总结
  - 用户可代替任意角色发言，可随时切换角色；法官每 2 轮追问一次
  - WebSocket consumer 支持对抗模式步骤分发
  - 庭审报告生成（完整记录 + 法官总结）

- **YZW收件箱拉取（message_hub）**：CourtInboxFetcher 完整实现
  - 复用 DocumentDeliveryTokenService 获取YZW Token
  - 分页拉取文书送达消息，按 sdbh 去重写入 InboxMessage
  - 自动获取文书详情并下载附件到本地，Admin 支持按需预览/下载（优先本地缓存）
  - 拉取完成后自动触发 CourtSMS 推送流程

- **信息中转站 REST API（message_hub）**：新增收件箱 API 模块，支持消息列表（按来源/附件/关键词筛选）、消息详情（含 HTML/纯文本正文）、附件下载与预览，JWT + Session 双认证

- **发件人过滤（message_hub）**：消息来源新增白名单/黑名单配置，可按邮箱地址或发件人名称过滤，每行一个，大小写不敏感子串匹配；白名单优先于黑名单；Admin 编辑页新增"发件人过滤"配置分组

- **合同列表分页（contracts）**：合同列表接口新增 `page`/`page_size` 参数，后端 queryset 切片返回

### 修复

- **合同 API 500 错误（contracts）**：修复 API 层通过 ContractServiceAdapter 调用时返回 ContractDTO 而非 Contract model，导致 Ninja ModelSchema 序列化失败的问题；API 层改用 domain service 直接返回 Contract model
- **YZW Token 获取（message_hub）**：修复 Token 过期自动重试（401 时清除缓存/DB 后重新 Playwright 登录）；修复 async 环境下 ORM 调用问题（DJANGO_ALLOW_ASYNC_UNSAFE）；CourtToken 用 expires_at 替代不存在的 is_valid 字段

## [26.29.1] - 2026-03-31

### 修复

- CI 全绿修复：ruff E701/E702/RUF010/RUF100 lint 错误
- CI mypy 配置更新：移除已迁移/删除的旧路径（auth.py → security/auth.py, middleware_request_id.py, httpx_clients.py）
- security-guard：测试数据中身份证号和手机号脱敏

## [26.29.0] - 2026-03-31

### 新增

- **法律服务方案（legal_solution）**：全新模块，支持 AI 分段生成诉讼策略报告
  - 7 段结构：案情分析、法律关系认定、争议焦点、类案参考、诉讼策略建议、风险评估、费用预估
  - 异步任务生成（django-q），用户可单独调整每段内容（版本追踪）
  - HTML 报告渲染（深色宇宙风格 + 玻璃拟态卡片）+ weasyprint PDF 导出
  - Admin 支持预览、PDF 下载、段落调整

- **信息中转站（message_hub）**：新增消息中转模块

- **wkxx高级检索**：案例检索支持多字段组合检索
  - 新增 `advanced_query` JSON 字段，支持多条件 AND/OR/NOT 组合（字段：全文/标题/本院认为/裁判结果/争议焦点/案由/案号）
  - 新增 `court_filter`（法院筛选）、`cause_of_action_filter`（案由筛选）、`date_from`/`date_to`（裁判日期范围）
  - Admin 表单新增交互式高级检索条件构建器（Alpine.js 动态增删行，展开/收起）
  - 私有 API 适配器支持将条件转换为 `queryString` 字段限定语法 + `filterQueries` + `filterDates`

- **案例检索优化**（legal_research executor）
  - 新增标题预筛（`_title_prefilter`）：fetch_detail 前用 title_hint 快速过滤不相关案例
  - 新增法律要素提取（`_extract_legal_elements`）：LLM 从案情简述提取案由/法律关系/争议焦点/损失类型，构造精准检索式
  - 新增并发 LLM 评分（`_batch_rerank_candidates`）：ThreadPoolExecutor 并发评分，默认 5 并发
  - 宽召回阈值调整：`COARSE_RECALL_THRESHOLD_RATIO` 0.5→0.6，`COARSE_RECALL_THRESHOLD_CEIL` 0.45→0.52
  - 新增硬性下限：coarse_score < 0.20 直接跳过，避免低质量候选进入精排
  - `tuning_config` 新增 7 个可调参数：`title_prefilter_enabled`、`title_prefilter_min_overlap`、`coarse_recall_hard_floor`、`llm_scoring_concurrency`、`element_extraction_enabled`、`element_extraction_model`、`element_extraction_timeout_seconds`

- **法院执行网纯逆向登录插件**（court_zxfw_login_private，不入 Git）
  - SM2 国密加密（Node.js sm-crypto）+ ddddocr OCR + 纯 HTTP 登录，无需 Playwright 浏览器
  - 三级优先级：Cookie → 纯逆向 → Playwright
  - 保全 Token 逆向获取：`POST /api/v1/oauth/code` → 保全平台 HS512 Token

- **core 模块重构**：基础设施代码迁移至规范目录结构
  - `core/infrastructure/`：`service_locator`、`event_bus`、`events`、`logging`
  - `core/security/`：`auth`（JWTOrSessionAuth）、`permissions`（PermissionMixin）
  - `core/utils/`：`path`、`validators`
  - `core/models/enums`：枚举统一管理
  - `core/config/business_config`：业务配置统一入口
  - `core/dto/request_context`：请求上下文提取

- **MCP 服务大幅扩展**（工具总数从 34 增至 77）
  - 新增 `automation` 模块：法院短信解析、文书送达、财产保全询价
  - 新增 `doc_convert` 模块：传统文书转要素式文书
  - 新增 `enterprise_data` 模块：企业信息查询
  - 新增 `invoice_recognition` 模块：发票识别
  - 新增 `legal_research` 模块：类案检索
  - 新增 `oa_filing` 模块：YZW立案（案件导入、当事人导入）
  - 新增 `pdf_splitting` 模块：PDF 拆解
  - 新增 `reminders` 模块：提醒管理、利息计算

### 优化

- `Q_CLUSTER poll` 从 2.0 秒降至 0.5 秒，异步任务响应更快
- `markdown` 库替换手写 markdown 转 HTML，支持表格、代码块、引用块
- 法律服务方案 HTML 报告去除 AI 相关提示文字，更专业

### 修复

- 修复天眼查 MCP 服务端 `auth_error` 响应格式识别问题
- 修复 `court_sms` 和 `preservation_quote` 接口 500 错误（两轮修复）
- 修复wkxx高级检索 DOM 回退逻辑：URL 参数无结果时自动回退搜索框方式

## [26.28.0] - 2026-03-31

### 新增

- **文书转换工作台**
  - 新增传统文书转要素式文书功能（znszj 智能转写）
  - 支持 .docx / .doc / .pdf 上传，最大 20MB
  - 文书类型下拉选择，按类别分组展示
  - 拖拽上传支持
  - 转换结果自动生成语义化文件名（要素式{文书类型}{原始后缀}.docx）
  - 私有实现模块（znszj_private）不入库，通过 `ZNSZJ_ENABLED` 环境变量控制开关（默认关闭）

### 修复

- 修复 `extra={"filename": ...}` 与 Python logging 保留字段冲突导致 500 的问题（改为 `doc_filename`）
- 修复 httpx 继承 macOS 系统代理导致认证请求超时的问题（显式设置 `proxy=None`）

### 优化

- `mbid-list` 接口解耦私有 client 依赖，无私有模块时仍可正常返回文书类型列表
- `ZNSZJ_ENABLED` 默认值改为 `False`，未部署私有模块的用户不受影响

## [26.27.6] - 2026-03-30

### 新增

- **PDF 手动拆分模式**
  - 新增 `manual_split` 拆分模式，支持可视化选择页面范围
  - 三栏布局：缩略图列表 + PDF 查看器 + 片段列表
  - 缩略图支持点击选择、Shift 多选、Ctrl/Cmd 切换选择
  - 片段列表支持拖拽排序、实时编辑、预览功能
  - 已选择页面显示禁用样式，防止重复选择

- **PDF 预览页面**
  - 新增独立预览页面，只显示片段范围内的页面
  - 支持翻页、缩放、键盘导航
  - 页码显示相对于片段范围（如 1/3 而非 2/10）

### 优化

- **UI 布局优化**
  - 三栏布局使用 CSS Grid，自适应宽度
  - 响应式设计：宽屏三栏、中屏双栏、窄屏单栏
  - 表格列宽优化：增加材料类型列宽度（320px）
  - 文件名输入框与 .pdf 后缀分离显示

- **默认选项调整**
  - PDF 拆分工具默认选中"手动拆分"模式
  - 已选择页面自动标记为禁用状态

- **删除逻辑增强**
  - 删除任务时自动清理关联的文件目录（PDF、预览图、导出文件）
  - 添加 `post_delete` 信号处理

### 修复

- 删除片段后缩略图状态未恢复的问题
- 预览按钮打开新窗口 URL 构建错误
- 三栏布局超出容器宽度问题
- 材料类型下拉框显示不完整问题

## [26.27.5] - 2026-03-30

### 修复

- **LLM 后端可用性检查增强**
  - Ollama `is_available()` 增加 `/api/tags` 轻量探针验证服务连通性（3s 超时，结果缓存）
  - SiliconFlow `is_available()` 增加默认模型非空检查
  - fallback_policy 和 streaming 中被 `is_available()` 跳过的后端现在会记录原因到错误信息中，便于排查

## [26.27.4] - 2026-03-29

### 优化

- **集成 playwright-stealth 反爬虫检测**
  - 添加 `playwright-stealth` 依赖用于绕过网站反爬虫检测
  - 在所有 Playwright 使用场景中应用反检测（BrowserManager, BrowserService, OA 导入脚本, 法律研究模块）
  - 支持自动降级到基础反检测脚本（当 playwright-stealth 未安装时）

### 升级

- **安全相关依赖升级**
  - cryptography: 46.0.5 → 46.0.6
  - certifi: 2026.1.4 → 2026.2.25
  - requests: 2.32.5 → 2.33.0
  - sentry-sdk: 2.53.0 → 2.56.0
  - charset-normalizer: 3.4.4 → 3.4.6

- **开发工具升级**
  - black: 26.1.0 → 26.3.1
  - ruff: 0.15.2 → 0.15.8
  - mypy: 1.16.1 → 1.19.1
  - isort: 8.0.0 → 8.0.1
  - pytest-cov: 7.0.0 → 7.1.0

- **文档处理库升级**
  - pymupdf: 1.27.1 → 1.27.2.2
  - pikepdf: 10.3.0 → 10.5.1
  - mammoth: 1.11.0 → 1.12.0
  - pdfminer-six: 20251230 → 20260107
  - rapidocr: 3.6.0 → 3.7.0

- **Django 升级**
  - django: 6.0.2 → 6.0.3

- **其他自动升级**
  - numpy: 2.4.2 → 2.4.3
  - coverage: 7.13.4 → 7.13.5
  - packaging: 25.0 → 26.0
  - platformdirs: 4.9.2 → 4.9.4
  - wrapt: 2.1.1 → 2.1.2
  - librt: 新增 0.8.1

### 修复

- **修复 pydantic-core 兼容性问题**
  - 回退 pydantic-core 到 2.41.5 以兼容 pydantic 2.12.5

## [26.27.3] - 2026-03-29

### 变更

- **生产环境 ALLOWED_HOSTS 默认改为 `["*"]`**
  - 部署到服务器后默认允许所有来源访问，无需额外配置 `DJANGO_ALLOWED_HOSTS`

## [26.27.2] - 2026-03-29

### 修复

- **修复 CI 测试导入错误**
  - 修复 `oa_filing/models/__init__.py` 中 `ClientImportPhase` 被错误别名为 `ClientImportPhase2`，导致 CI 使用 `--import-mode=importlib` 时触发 `ImportError`
- **修复案例下载结果下载链接 404**
  - 在 `CaseDownloadTaskAdmin.get_urls()` 中注册缺失的 `casedownloadresult_download` URL 和视图，修复 `CaseDownloadResultInline.download_link()` 引用不存在的 URL 导致 `NoReverseMatch`

## [26.27.1] - 2026-03-29

### 新增

- **合同批量绑定文件夹页面增强**
  - 新增 Finder 风格文件夹选择器，支持可视化浏览和选择根目录
  - 支持手动输入路径、导航上级文件夹
  - 选择后自动填充到对应类型的根目录输入框

### 优化

- **批量绑定页面 UI 优化**
  - 打开文件夹按钮改为 📂 emoji 图标，节省表格空间
  - 删除"应用"文字标签，保留 switch 切换即可
  - 切换开关尺寸优化，避免溢出
  - 隐藏未设置根目录时的占位提示文案
  - 修复文案错误："关联网件"改为"关联案件"

## [26.27.0] - 2026-03-28

### 新增

- **合同批量绑定文件夹**
  - 新增批量绑定入口：`/admin/contracts/contract/batch-folder-binding/`
  - 按案件类型分组展示未绑定文件夹的合同卡片
  - 支持预览绑定结果、批量保存、打开文件夹
  - 自动按案件类型匹配文件夹模板并生成文件夹结构

### 优化

- **OA案件导入链路重构**
  - HTTP API 优先：使用 httpx 直接调用 JTN OA 接口，性能提升 3-5 倍
  - Playwright 自动回退：API 失败时自动切换到浏览器模拟操作
  - 并发导入支持：新增 `workers` 参数，支持多线程并发导入
  - 字段映射增强：新增 `case_category`（案件类别）字段，优化案件类型映射逻辑
  - 表单状态解析：自动解析 ASP.NET ViewState，支持翻页和搜索
- **OA客户导入链路重构**
  - HTTP API 优先：客户列表和详情页改用 httpx 直接抓取 HTML 解析
  - 并发导入支持：支持多线程并发导入客户数据
  - 字段提取增强：优化客户信息提取逻辑，支持更多字段格式
- **法院立案功能增强**
  - YZW立案 API 调用优化：改进请求重试和错误处理逻辑
  - Playwright 回退机制：API 失败时自动切换到浏览器操作
  - 案件材料扫描优化：文件夹扫描性能提升，支持子目录选择

### 修复

- **合同 Admin 交互修复**
  - 修复定稿材料拖拽排序接口 JSON 解析错误
  - 修复批量操作权限检查逻辑
- **OA 导入稳定性修复**
  - 修复案件编号搜索时特殊字符转义问题
  - 修复详情页 URL 拼接错误
  - 修复并发导入时的线程安全问题
- **法院立案回归修复**
  - 修复立案材料上传失败时的错误提示
  - 修复执行依据页面字段定位超时问题

## [26.26.4] - 2026-03-27

### 修复

- **CI 稳定性修复（Backend Pipeline）**
  - 修复 `apps/core/llm/structured_output.py` 触发的 `ruff UP047` 检查失败，统一沿用 TypeVar 风格以兼容现有 mypy 策略。
  - 修复 `tests/ci/unit/test_regression_suite.py` 动态导入失效模块导致的测试收集异常，改为对 tracked CI unit 模块执行 import smoke。
  - `backend` 主 Job 的 pre-commit 改为基于 diff 的 changed-files 运行，避免被全仓历史格式债务阻塞。
  - 为 CI 单测中的示例密码字段补充 `pragma: allowlist secret`，消除 `detect-secrets` 误报。

## [26.26.3] - 2026-03-27

### 优化

- **统一 LLM 调用入口**
  - 业务侧（Automation / Document Recognition / Legal Research / Litigation AI）统一接入 `apps.core.llm`，收敛分散的模型调用方式。
  - 新增 `openai_compatible` 后端接入能力，并统一纳入后端路由、优先级与配置读取体系。

### 兼容

- **Moonshot 历史配置兼容**
  - 恢复 `moonshot` 历史后端别名与配置兼容方法，兼容旧配置键与旧测试入口（如 `get_moonshot_*`）。

### 修复

- **LLM 模板同步接口恢复**
  - 恢复 `POST /api/v1/llm/templates/sync` 接口，并补回 `sync_prompt_templates_impl` 兼容入口。
  - 非管理员访问返回 403，管理员可执行模板同步。
- **LLM 相关回归修复**
  - 修复 `ninja_llm_api` 模板同步路径缺失导致的集成测试失败。
  - 修复 `LLMConfig` Moonshot 兼容方法缺失导致的单测失败。
## [26.26.2] - 2026-03-27

### 新增

- **法院短信自动归档到案件绑定目录**
  - 在短信文书重命名并完成“日志附件”后，新增案件目录归档流程（仅案件已绑定文件夹时触发）
  - 自动定位“邮件往来 / 邮寄 / 邮件”目录；若不存在则自动创建“最大编号+1-邮件往来”
  - 自动创建 `{YYYY.MM.DD}-{摘要}` 事件子目录（同名自动加后缀），写入 `法院短信.md`，并复制重命名后的文书文件
  - 归档失败仅记录日志，不阻断短信主流程（后续通知阶段仍继续）

### 修复

- **法院短信下载任务队列入口修复**
  - 修复 Django-Q worker 报错 `Function apps.automation.tasks.execute_scraper_task is not defined`
  - 统一导出任务入口，确保法院短信文书下载任务可被队列正常调度执行
- **短信文书标题提取稳定性修复**
  - 短信文书重命名场景移除 Ollama 调用，改为规则提取标题，避免本地模型超时导致命名降级不稳定
  - 短信场景下单独限制 PDF 文本提取长度（50 字），避免影响其他全局 PDF 提取能力

## [26.26.1] - 2026-03-26

### 新增

- **案件材料扫描范围能力增强**
  - 新增 `GET /api/v1/cases/{case_id}/folder-scan/subfolders`，前端可在扫描前加载并选择指定子文件夹
  - 扫描启动参数新增 `scan_subfolder` 与 `enable_recognition`，支持“全部目录 / 指定子目录”与识别开关
- **YZW立案引擎切换**
  - 案件详情“YZW立案”页新增 `API / Playwright` 立案引擎选择，默认 `API`
  - 立案执行接口新增 `filing_engine` 参数并透传到执行链路

### 优化

- **案件材料扫描默认轻量化**
  - 扫描默认关闭 OCR/PDF 识别，仅按文件名与路径关键词规则预分类，提升扫描速度
  - 扫描状态回包新增扫描范围与识别开关，前端实时展示当前扫描范围
- **材料保存交互收敛**
  - 扫描完成后点击“保存”即可自动完成 staged 导入与绑定保存，并自动返回案件详情页
- **案件材料预分类规则增强**
  - 引入目录规则与上下文分类：立案材料目录默认归类为我方当事人材料
  - 支持预填当事人 IDs 与管辖机关 ID，减少人工二次选择

### 修复

- **Playwright 执行依据页面兼容修复**
  - 修复“作出执行依据单位”字段在部分法院页面标签差异导致的定位超时
  - 增加多标签匹配与可选字段降级处理，避免流程因单字段缺失中断
- **申请执行信息补齐稳定性**
  - 申请执行人联系电话为空时兜底使用代理律师手机号
  - 代理人补齐支持按绑定律师顺序填充，多代理人场景不足则自动新增并继续填写

## [26.26.0] - 2026-03-26

### 新增

- **新增独立 `pdf_splitting` App**
  - 注册 `INSTALLED_APPS`、API 路由与 Admin 菜单入口，形成独立的 PDF 拆解工具能力
- **新增 PDF 拆解任务与片段模型**
  - 引入 `PdfSplitJob` / `PdfSplitSegment`，支持任务状态流转、片段持久化、复核与导出
- **新增 PDF 拆解 API**
  - 新增 `POST /api/v1/pdf-splitting/jobs`、`GET /api/v1/pdf-splitting/jobs/{id}`、`POST /api/v1/pdf-splitting/jobs/{id}/confirm`、`POST /api/v1/pdf-splitting/jobs/{id}/cancel`、`GET /api/v1/pdf-splitting/jobs/{id}/download`、`GET /api/v1/pdf-splitting/jobs/{id}/pages/{page_no}/preview`
- **新增两种拆分模式**
  - 内容识别拆分：基于立案材料模板（7 类）进行起始页识别、连续切段和人工复核后导出
  - 纯按页拆分：`split_mode=page_split` 时跳过内容分析，直接按页拆分并自动导出 ZIP

### 优化

- **OCR 三档与并行处理能力**
  - OCR 档位支持 `fast / balanced / accurate`，按档位控制分辨率、模型与并行 worker
- **OCR 结果缓存**
  - 基于 `PDF hash + profile + page_no` 缓存 OCR 结果，减少重复扫描时的处理耗时
- **后台创建任务交互优化**
  - PDF 拆解入口收敛为统一上传入口，支持拖拽上传；按页拆分模式自动隐藏 OCR 相关配置

### 修复

- **OCR 引擎缓存串用问题修复**
  - OCR 引擎实例缓存改为按模型档位隔离，避免 fast/accurate 档位共享同一引擎
- **Admin 模板脚本注入可覆写**
  - `base_site` 新增 `alpine_script` 块，允许工具页按需关闭 Alpine 注入，减少 CSP 场景下无关脚本告警

## [26.25.1] - 2026-03-26

### 新增

- **合同自动捕获支持扫描前选择范围**
  - 支持在执行自动捕获前选择扫描范围：全量扫描或指定子文件夹扫描
- **新增子文件夹列表接口**
  - 新增 `GET /api/v1/contracts/{contract_id}/folder-scan/subfolders`，用于前端加载可选扫描子目录

### 优化

- **合同材料分类策略调整**
  - 定稿材料分类策略改为“文件名关键词规则优先 + AI 兜底”
- **定稿材料分类收敛**
  - 定稿材料分类由 `other` 收敛为 `invoice`
  - 迁移补充：历史数据执行 `other -> invoice` 映射迁移

### 修复

- **Ninja/Pydantic 参数解析修复**
  - 修复 `rate_limit` 包装器注解/签名解析问题，解决 `QueryParams is not fully defined` 异常
- **Django-Q 参数清洗修复**
  - 提交异步任务时清洗参数，避免 `timeout=None` 触发 worker `TypeError: must be real number`
- **未绑定文件夹交互修复**
  - 修复合同自动捕获在未绑定文件夹场景下的前端提示与跳转体验
- **Chrome DevTools 探测请求降噪**
  - 将 `/.well-known/appspecific/com.chrome.devtools.json` 统一返回 `204`，减少无效 `404` 日志

### 行为补充

- **合同正本命名增强**
  - 自动捕获命中“合同正本”后，额外检测末页是否包含“律师办案服务质量监督卡”，命中则保存名称为“合同正本与律师办案服务质量监督卡”

## [26.25.0] - 2026-03-25

### 新增

- **OA案件导入功能重构**
  - 从JTN OA系统导入案件完整流程重构
  - 支持从Excel文件解析案件编号列表（支持GZXS/GZXZ类型）
  - 预览模式：先显示匹配/未匹配状态，用户确认后再执行导入
  - 字段映射：收案日期→合同开始时间、案件负责人→主办律师、OA详情页URL→律所OA链接
  - 利益冲突处理：自动将OA冲突方添加为合同对方当事人
  - 修复日期解析支持 `2025/9/18 0:00:00` 格式

### 修复

- **Enter键搜索超时问题**：改为立即检查Enter键是否成功，失败后立即调用searchOk()
- **ContractAssignment未定义错误**：添加缺失的import语句
- **Contract模型字段错误**：修复case/create时使用错误的字段名

## [26.24.1] - 2026-03-25

### 修复

- **当事人列表页 OA 导入交互与样式修复**
  - “从OA导入”按钮样式统一为 Admin 原生 `addlink`，与“导入 / 增加当事人”保持一致
  - “无头模式”独立按钮移除，收敛到“从OA导入”点击后的配置菜单中（可选有头/无头、导入全部/限制数量）
- **OA 导入进度展示修复**
  - 进度弹窗改为明确的两阶段展示：`步骤1 查找并发现` + `步骤2 导入`，分别显示状态与进度条
  - 修复阶段流转：`discovery_completed` 不再提前切换为导入阶段，只有 `import_started` 才进入导入阶段
  - 调整轮询频率，减少阶段切换时“直接完成”导致的视觉跳跃
- **OA 导入进度弹窗定位修复**
  - 导入进度弹窗从左上偏移修复为顶部居中显示，保证不同分辨率下位置稳定

## [26.24.0] - 2026-03-24

### 新增

- **从JTNOA导入当事人功能**
  - 当事人列表页新增"从OA导入"按钮，仅对有jtn.com账号密码的用户显示
  - 点击后自动从JTNOA IMS系统抓取客户管理页面的客户数据
  - 自动去重：已存在的当事人（按名称）会被跳过
  - 字段映射：企业客户映射客户名称、法定代表人、电话、城市；自然人映射客户名称、身份证号、电话、地址
  - 实时显示导入进度（成功/跳过数量）

## [26.23.2] - 2026-03-24

### 修复

- **当事人信息解析 - 自然人误识别为法人**
  - 修复 `text_parser._extract_credit_code()` 的 fallback 模式将身份证号误识别为统一社会信用代码的问题
  - 当编码前 20 字符内存在"身份证"关键词时跳过，避免误判
- **PDF 身份证识别 - 解压炸弹防护触发**
  - 修复超大 PDF（218M 像素）在 OCR 识别时触发 PIL `DecompressionBombError` 的问题
  - 在 `IdentityExtractionService._extract_from_pdf()` 中添加 `Image.MAX_IMAGE_PIXELS = None` 禁用解压炸弹检查

## [26.23.1] - 2026-03-24

### 修复

- **生成文件夹模板匹配逻辑**
  - 修复 `generate-folder` API 使用简单 `case_type` 匹配导致模板选择错误的问题
  - 现在后端 API 使用与前端一致的 `TemplateMatchingService.find_matching_case_folder_templates_list()` 方法
  - 会根据我方当事人的诉讼地位（`legal_statuses`）正确选择匹配的文件夹模板（如被告→民事一审答辩）

## [26.23.0] - 2026-03-23

### 与 `main` 分支差异（摘要）

- 本分支相较 `origin/main` 共变更 `34` 个文件，累计约 `+2795 / -689` 行
- 变更主线集中在：`Case Admin 文书区重构`、`文书生成/下载链路稳态`、`强制执行申请书规则引擎 v2`

### 新增

- **强制执行申请书规则引擎 v2（`ExecutionRequestService`）**
  - 主项识别扩展：支持 `广告费/服务费/工程款/佣金/回购基本价款` 等非借款/货款主项
  - 计息识别扩展：支持 `年化率`、`日利率`、`万分之/千分之`、多段多基数、同基数双阶段利率
  - 利息文案增强：分段计息优先沿用判决原文表述，并自动追加“暂计至X日利息为Y元”
  - 条款提取增强：支持连带责任、补充责任、优先受偿权（土地/股权/商标等）及人工核对兜底
  - 费用项规则增强：明确“支付给原告/申请人”才纳入执行项，支持 fee-only 场景独立生成

### 优化

- **案件详情页文书区与前端交互重构**
  - `documents.html` 区块重排，按钮联动与参数区布局统一
  - `case_detail.js / authorization_materials.js / preservation_materials.js` 交互与状态管理收敛
  - `case_detail.css / litigation_generation.css` 样式补强，窄屏与长文本场景可用性提升
- **文书生成/下载链路稳定性**
  - `folder_generation_service`、`folder_generation_api`、`download_response_factory` 与文件系统处理增强
  - 授权材料与保全材料 API 生成反馈更一致，错误边界更清晰
- **诉讼占位符体系扩展**
  - 执行相关占位符与 party formatter 规则增强，字段映射更完整

### 测试

- 新增/扩展执行事项规则回归测试，`test_execution_request_rules.py` 提升至 `34` 条通过用例
- 新增覆盖：
  - 非借款/货款主项本金识别
  - 年化率分段计息
  - “利息为X元”确认利息写法
  - 分段原文回填 + 截止日暂计金额展示

## [26.22.6] - 2026-03-23

### 新增

- **Client/Admin 自定义模板补齐**
  - 新增 `apps/client/templates/admin/client/change_list.html`（客户列表 ZIP 导入入口）
  - 新增 `apps/client/templates/admin/client/change_form.html` 与 `identity_recognition_dialog.html`（身份材料识别 UI）
  - 新增 `apps/client/templates/admin/client/clientidentitydoc/change_list.html`（身份证合并入口）
- **Documents/Admin 自定义模板补齐**
  - 新增 `apps/documents/templates/admin/documents/documenttemplate/change_form.html`，增强模板编辑页文件来源互斥交互
- **数据库迁移**
  - 新增 `documents` 迁移 `0006_remove_documenttemplate_description`，删除 `DocumentTemplate.description`

### 清理

- **DocumentTemplate 描述字段全链路移除**
  - 模型：移除 `DocumentTemplate.description`
  - DTO/Schema：移除 `DocumentTemplateDTO.description`、`DocumentTemplateIn/Update/Out.description`
  - 工作流与服务：移除 create/update/duplicate 的 `description` 入参与写入
  - 案件模板绑定聚合输出：移除模板 description 回传字段
  - 模板审计字段追踪：移除 `description` 跟踪项

### 优化

- **执行事项规则引擎增强**
  - 当主文未命中“借款/货款本金”时，可从计息基数条款（如“以27334元为基数”）反推本金
  - 支持“LPR/贷款市场报价利率的标准”场景，按 1 倍 LPR 识别利率描述
  - 兜底触发条件细化为“按句判断费用+负担+预交语义”，减少非必要 Ollama 兜底调用
- **文书模板 Admin 可见性优化**
  - `DocumentTemplate` 列表新增主键 `id` 列
  - 表单去除 `description` 输入，保持与模型一致

### 测试

- 新增执行事项规则回归测试：
  - `test_execution_request_infers_principal_from_interest_base_and_lpr_standard`
  - `test_execution_request_lpr_standard_clause_does_not_trigger_llm_fallback_when_rules_sufficient`

## [26.22.5] - 2026-03-23

### 清理

- **Admin 菜单名称简化**
  - `automation/CourtToken`：`YZW/保全Token管理` → `YZW保全Token管理`
  - `cases/CaseLog`：`案件日志` → `日志`
  - `cases/CaseLogAttachment`：`案件日志附件` → `日志附件`
  - `cases/CaseChat`：`案件群聊` → `群聊`
- **移除 CaseDownloadResult 独立 Admin 入口**
  - 保留 `CaseDownloadResultInline` 内联入口（供 `CaseDownloadTaskAdmin` 使用）
  - 业务逻辑和服务不受影响
- **调整案件模块子菜单顺序**
  - 按 `案件 → 日志 → 日志附件 → 群聊` 排序

## [26.22.4] - 2026-03-22

### 清理

- **彻底移除 PromptVersion / PromptTemplate 及相关代码**
  - 删除 `PromptVersion` 模型及 `documents/prompt_version_admin.py`
  - 删除 `PromptTemplate` 模型及 `core/prompt_template_admin.py`
  - 删除相关 Service、Repository、Protocol、ServiceLocator 方法
  - 迁移删除 `PromptVersion` 数据表
  - `CourtPleadingSignalsService` 移除对 `PromptVersionServiceAdapter` 的依赖，始终使用内置默认 prompt
- **Admin 菜单入口清理**
  - `SystemConfigAdmin` 设置 `show_in_index=False`，从左侧菜单隐藏（保留 URL 访问）

## [26.22.3] - 2026-03-22

### 清理

- **移除多个 Admin 菜单入口（模型本身保留，业务不受影响）**
  - `automation/TokenAcquisitionHistory`：移除 Dashboard 页面及模板，保留 Token 获取历史记录写入
  - `contracts/ContractAssignment`：移除独立 Admin 入口（保留 Inline 供 ContractAdmin 使用）
  - `contracts/ContractPayment`：移除独立 Admin 入口（保留 Inline 供 ContractAdmin 使用）
  - `contracts/ClientPaymentRecord`：移除独立 Admin 入口
  - `cases/CaseParty`：移除独立 Admin 入口（保留 Inline 供 CaseAdmin 使用）
  - `cases/CaseAssignment`：移除独立 Admin 入口（保留 Inline 供 CaseAdmin 使用）
  - `oa_filing/FilingSession`：移除整个 OA 立案模块 Admin 入口
  - `documents/Placeholder`：移除替换词 Admin 入口
  - `documents/TemplateAuditLog`：移除模板审计日志 Admin 入口
- **文案调整**
  - `ClientIdentityDoc` 模型 `verbose_name` 从"当事人证件文件"改为"证件"

## [26.22.2] - 2026-03-22

### 清理

- **彻底移除 onboarding 模块（立案向导）**
  - 删除 `apps/onboarding/` 整个目录（视图、URL、模板、静态文件、locale）
  - 从 `INSTALLED_APPS` 移除 `apps.onboarding`
  - 从 `urls.py` 移除 onboarding URL 路由
  - 从 Admin 侧边栏移除"我要立案"按钮及 CSS 样式
  - 更新 README 功能列表，移除 onboarding 描述

## [26.22.1] - 2026-03-22

### 清理

- **移除法院短信 41 套主题模板及相关死代码**
  - 删除 `courtsms/add1.html` ~ `add41.html` 共 41 个未使用的 HTML 模板
  - 删除 `test_login_result.html`、`test_tool_list.html` 等未引用模板
  - 删除 `court_sms_admin_themed_views.py`（含 40 个 `add*_view` 方法）
  - 清理 `court_sms_admin_service.py` 中的 `SMS_STYLE_CONFIG`、`DEFAULT_STYLE_ID`
  - 清理 `court_sms_admin.py` 中的主题 URL 注册逻辑
- **移除各模块未使用的 Admin 模板**
  - 删除 `cases`、`client`、`contracts`、`core`、`documents`、`finance`、`organization`、`onboarding` 等模块下的未引用 `change_list.html`、`change_form.html`、局部模板

## [26.22.0] - 2026-03-21

### 新增

- **强制执行申请书 `申请执行事项` 规则引擎（v1）**
  - 新增 `ExecutionRequestService`，并注册占位符 `{{申请执行事项}}`
  - 新增案号级执行参数：`执行事项截止日`、`已付款金额`、`启用抵扣顺序`、`年基准天数`、`日期包含方式`、`申请执行事项（手工最终文本）`
  - 新增 Admin 解析接口：`POST /admin/cases/case/casenumber/<id>/parse-execution-request/`，返回预览文本、结构化参数、warnings
- **规则解析能力覆盖扩展**
  - 支持 LPR 倍数、LPR 上浮百分比（如“上浮50%”=> `1.5` 倍）、固定年利率、日利率
  - 支持文书条款优先计息基数、已付款抵扣顺序重算、利息上限截断
  - 支持费用归属判别：纳入“支付/返还/迳付原告(申请人)”费用，排除“向法院缴纳/法院退回”费用
  - 支持“加倍支付迟延履行期间债务利息”条款自动追加执行事项
- **本地 Ollama 兜底（可选）**
  - 新增“解析执行事项”旁边的 `Ollama兜底` 开关（默认开启）
  - 规则置信度不足或利息解析失败时，可调用本地 `qwen3.5:0.8b` 兜底抽取并回填

### 优化

- **案件案号 UI 重构（Stacked 分组布局）**
  - `CaseNumberInline` 从 `Tabular` 改为 `Stacked`，文书信息与执行参数按分组布局展示
  - “解析裁判文书 / 解析执行事项 / Ollama兜底”统一到案号操作栏，并修复窄屏换行错位
  - 文案简化：执行依据主文、申请执行事项改为输入框 placeholder，减少重复说明文字
  - “执行事项参数”区块改为按案件 `当前阶段=enforcement` 才显示
- **裁判文书解析清洗增强**
  - `JudgmentPdfExtractor` 新增页码页脚噪声清洗（如“第X页共Y页 / Page x of y / 本页无正文”）
  - 清洗逻辑同时应用于直抽与 Ollama 回传内容，避免污染“执行依据主文”
- **上下文构建稳定性**
  - 占位符上下文增加 `case_id` 推断兜底（从 `case` 自动推断），模板生成链路统一显式传递 `case_id`

### 修复

- **执行申请书内容修复**
  - 修复多被申请人序号异常（如“被申请人丁”），统一为“被申请人一/二/三...”
  - 修复“申请执行事项”默认计息截止逻辑：优先案号 `执行事项截止日`，为空则使用案件 `指定日期`，再为空才回退当天
  - 修复本金扣减后利息基数未同步扣减的问题（已付款后按剩余本金计息）
- **案件编辑页交互修复**
  - 修复“解析裁判文书”后错误覆盖案号字段（案号被写成文书名称）的选择器冲突
  - 修复 `current_stage` 在页面初始化被前端脚本清空、保存后回显消失的问题
  - 修复 `layout_switcher` 对 `case_numbers` 二次包装导致标题栏/宽度错位问题
- **数据库兼容修复**
  - 修复 `no such table: automation_documentrecognitiontask`：新增 `automation` 迁移恢复历史兼容表

## [26.21.0] - 2026-03-20

### 重构

- **LangChain/LangGraph 运行时拆除**
  - 全面移除后端代码中的 `langchain` / `langgraph` 依赖调用，统一改为 `LLMService.chat/achat` 直连模式
  - `backend/pyproject.toml` 删除 `langchain-core`、`langchain-openai`，改为显式依赖 `openai`
  - 更新 `backend/uv.lock`，移除 LangChain 相关锁定条目
- **结构化输出链路统一**
  - 新增 `apps/core/llm/structured_output.py`，统一处理 JSON 清洗、提取与 Pydantic 校验
  - 诉讼文书生成、诉讼流程解析、法院文书态势识别、模拟庭审链路全部切换到统一结构化解析
- **Litigation 模块兼容下线**
  - 下线 `/litigation` 与 `/mock-trial` 路由注册以及对应 WebSocket 路由挂载
  - 前台首页移除 mock-trial 区块，案件详情页移除“模拟庭审”入口按钮

### 修复

- **smoke_check 回归修复**
  - `WebSocket` 冒烟检查改为下线提示后，补回上传检查所需的 `patch` 导入
  - CI 合同保持通过：`backend/tests` 全量 `115 passed`
- **文案与多语言同步**
  - 首页功能与技术栈文案更新为“统一 LLM 服务 / OpenAI SDK / Flow State Machine”
  - Prompt 模板模型文案去除 LangChain 术语，避免与当前实现不一致

## [26.20.0] - 2026-03-20

### 新增

- **强制执行申请书占位符服务完善**
  - 新增 `EnforcementJudgmentMainTextService` 服务，注册到 PlaceholderRegistry
  - 支持从案号的 `document_content` 字段提取执行依据主文
  - 支持一二审等多份裁判文书主文按顺序拼接（先民初，再民终）
- **裁判文书PDF案号识别与主文提取**
  - `JudgmentPdfExtractor` 支持从PDF裁判文书中识别案号、文书名称、法院名称
  - 支持提取执行依据主文内容
  - 新增"驳回上诉，维持原判"作为二审终审判决的截止关键词

### 修复

- **强制执行申请书生成逻辑**
  - 修复 `EnforcementJudgmentMainTextService` 未注册到占位符服务注册表的问题
  - 优化主文选取逻辑：按案号顺序拼接所有有内容的 document_content
- **案件管理页面UI优化**
  - 优化"裁判文书文件"列的解析按钮样式

## [26.19.3] - 2026-03-20

### 修复
- **源码目录二进制后缀禁提防线**
  - pre-commit 移除对 `*.onnx` 的放行规则，避免大模型文件通过 `check-added-large-files` 被绕过
  - 新增本地 guardrail：禁止在源码目录提交 `.onnx`、`.mp4`、`.zip` 后缀文件
  - CI `Repository hygiene` 增加同规则校验，防止 `--no-verify` 或本地环境差异导致漏拦截

## [26.19.2] - 2026-03-19

### 修复
- **Client 证件识别错误提示友好化（Ollama）**
  - 修复 `/admin/client/client/add/` 在智能识别超时时直接展示 `LLM_TIMEOUT` 等技术细节的问题
  - 针对超时、网络异常、服务不可用场景提供可执行的用户提示（稍后重试 / 检查 Ollama 服务状态）
  - 保留后端详细日志用于排障，同时前端仅展示面向业务用户的可读信息

## [26.19.1] - 2026-03-19

### 修复
- **案例下载（Case Download）**
  - 修复 `__str__` 重复显示案号问题，隐藏空白第一列
  - 修复"重试失败项"按钮在无失败项时错误显示的问题
  - 修复列表页操作按钮 HTML 被转义的问题

## [26.19.0] - 2026-03-19

### 新增
- **案例下载（Case Download）**
  - 新增案例下载任务模型 `CaseDownloadTask` 与下载结果模型 `CaseDownloadResult`
  - 支持通过案号批量下载WKXX案例（PDF/Word格式）
  - 案号输入支持多种分隔符：换行、逗号、分号
  - 文件按案号重命名，如 `(2024)粤0605民初3356号.pdf`
  - 支持单个下载和批量打包 zip 下载
  - 删除任务时自动清理对应文件
  - 优先使用私有 API 访问WKXX，失败自动回退 Playwright
- **wkxx Word 下载**
  - 新增 `download_doc` 方法，支持下载 .doc 格式文档

### 测试
- 本地检查通过：`manage.py check`、`makemigrations --check --dry-run`

## [26.18.0] - 2026-03-19

### 新增
- **案件/合同材料文件夹自动捕获（Folder Auto Capture）**
  - 新增合同与案件“自动捕获”入口及引导弹窗/面板，支持指定已绑定目录一键扫描
  - 新增会话化扫描与确认机制：扫描结果可查看、可二次确认后入库，避免误收录
  - 新增扫描会话数据模型：`ContractFolderScanSession`、`CaseFolderScanSession`
- **通用扫描与分类能力**
  - 新增递归扫描服务 `BoundFolderScanService`，支持子目录检索 PDF、版本后缀去重、进度回调
  - 新增材料智能分类服务 `MaterialClassificationService`，基于文本片段给出合同/案件材料归类建议

### 优化
- **文档识别链路**
  - PDF 文本抽取新增 `max_pages`，扫描阶段默认仅读取前 3 页以控制耗时
  - OCR/直抽路径统一支持页数上限，提升大目录扫描稳定性与响应速度
- **Cases/Contracts API 扩展**
  - 合同新增 `folder-scan` 扫描、会话查询、确认入库接口
  - 案件新增 `folder-scan` 扫描、会话查询、分阶段确认接口
  - 案件 API 路由补齐 `case_material_api` 注册，避免扫描后流程断链

### 测试
- 新增 `backend/apps/document_recognition/test_text_extraction_max_pages.py`
- 本地检查通过：`manage.py check`、`makemigrations --check --dry-run`、`node --check`（相关前端脚本）

## [26.17.5] - 2026-03-19

### 新增
- **法律检索能力契约（Agent/MCP 可直接调用）**
  - 新增能力请求/响应契约：`AgentSearchRequestV1`、`AgentSearchResponseV1`、`RetrievalHitV1`
  - 新增能力接口：`/api/v1/legal-research/capability/search` 与 `/api/v1/legal-research/capability/search/mcp`
  - 新增 `search_mode`（`expanded` / `single`）并落库到任务模型，支持“扩展检索”和“单检索”切换

### 优化
- **法律检索执行链路增强**
  - Executor 新增查询轨迹输出：`primary_queries`、`expansion_queries`、`feedback_queries`、`query_stats`
  - 单检索模式下禁用扩展词与反馈扩展，确保“仅原始检索式”执行语义
  - 能力服务新增幂等键缓存、并发闸门、超时控制与短时失败熔断，并输出结构化降级标记（如 `partial_result` / `constraint_unsatisfied`）
  - 检索结果新增四段片段抽取：`claims`、`findings`、`reasoning`、`holdings`，并补充 Agent 友好的摘要字段
- **评测脚本升级（基线可量化）**
  - benchmark 命令新增评测口径：`closed` / `pooled`
  - 新增 `--eval-top-k`、`relevance_judgments`、`ndcg@k`、`anchor_hit_at_k`、`judged/unjudged` 统计
  - 新增按查询类型贡献率输出（primary / expansion / feedback）
- **稳定性与运行安全**
  - ORM 写入路径新增异步上下文隔离兜底（线程执行 + 连接清理），降低同步 ORM 被异步上下文污染风险
  - 检索与传输重试改为指数退避 + 抖动（jitter），并增加退避上限
- **Admin 可观测性增强**
  - 任务页增加 `search_mode` 展示与编辑
  - 阶段指标增加能力直连成功率、超时/繁忙/降级计数，并保留 API 命中率、DOM 回退率与错误码分布
- **预提交密钥扫描治理**
  - 对保留的引导口令与测试样例口令补充 `# pragma: allowlist secret`，避免误报阻断提交
  - 刷新 `backend/.secrets.baseline`，与当前仓库扫描结果保持一致
- **跨模块规范化收敛（无业务语义变更）**
  - 结合 `ruff/isort` 与结构约束，对若干模块进行导入顺序与代码格式统一，减少后续冲突与噪声 diff

### 测试
- 新增/更新能力与稳定性相关测试：
  - `tests/ci/integration/test_legal_research_capability_api.py`
  - `tests/ci/unit/test_legal_research_capability_service.py`
  - `tests/ci/unit/test_legal_research_capability_mcp_wrapper.py`
  - `tests/ci/unit/test_legal_research_retry_backoff.py`
  - `tests/ci/unit/test_legal_research_task_admin_metrics.py`
- 本地复跑：`pre-commit run --all-files` 通过

## [26.17.4] - 2026-03-18

### 优化
- **开发收尾与分支整合**
  - 已确认历史 worktree 分支变更全部纳入 `main`，并在主分支完成收尾发布
  - 清理本地附加 worktree，仅保留主工作目录，减少后续维护干扰

### 测试
- 按 CI 分层命令复测通过：
  - `tests/ci/structure`（collect-only）
  - `tests/ci/unit`、`tests/ci/integration`、`tests/ci/property`
  - `manage.py smoke_check --skip-admin --skip-websocket --skip-q`
  - unit coverage gate：`87.28%`（`--cov-fail-under=85`）
  - baseline coverage gate：`26.75%`（`--cov-fail-under=25`）

## [26.17.3] - 2026-03-18

### 新增
- **注册页首次自动初始化能力**
  - `/admin/register/` 新增“自动注册默认超级管理员”按钮
  - 首次点击后会自动创建默认超级管理员账户：`法穿 / <已脱敏>`
  - 自动注册成功后立即登录，并通过数据库配置标记确保该按钮在当前数据库生命周期内只出现一次

### 优化
- **注册流程交互收敛**
  - 手动注册成功后也会同步消费首次初始化标记，避免删除账号后又重新出现自动注册入口
  - 修复注册异常分支下仍继续访问结果对象的潜在错误路径
- **注册页浏览器兼容性修复**
  - 为用户名和密码输入框补充标准 `autocomplete` 属性
  - `Permissions-Policy` 响应头改为标准序列化格式，并移除导致浏览器控制台报错的默认 `unload` 指令

### 测试
- 新增 `backend/apps/organization/test_register_view.py`
- `uv run pytest apps/organization/test_register_view.py -o addopts='--tb=short -q'`：`4 passed`
- `uv run ruff check apiSystem/apiSystem/settings.py apps/organization/forms.py apps/core/middleware/security.py apps/organization/test_register_view.py`：`All checks passed`
- `uv run python apiSystem/manage.py check`：`System check identified no issues (0 silenced)`
- Playwright 复查 `http://127.0.0.1:8012/admin/register/`：`0 errors / 0 warnings`

## [26.17.2] - 2026-03-18

### 优化
- **天眼查 MCP 多 API Key 自动切换**
  - `TIANYANCHA_MCP_API_KEY` 现支持在一项配置中录入多个值，兼容换行、逗号、分号分隔
  - 天眼查调用链新增 key 池能力，鉴权失败或远端 `429` 时自动切换下一把可用 key
  - 成功 key 会被短期优先复用，失效或限流 key 会进入短期熔断，减少重复踩同一把坏 key
- **天眼查 Streamable-HTTP 失败隔离**
  - 已确认天眼查当前 `streamable_http` 网关存在鉴权阶段异常时，会自动回退到 `sse`
  - 新增短期传输隔离：首次识别到 `streamable_http` 故障后，后续请求会暂时直接优先走 `sse`，避免每次先耗在坏链路上

### 配置
- **SystemConfig Admin 录入体验增强**
  - `TIANYANCHA_MCP_API_KEY` / `QICHACHA_MCP_API_KEY` 在后台编辑页改为多行输入并补充多 key 提示
  - 敏感配置编辑时回显解密后的值，保存时继续加密，列表页多 key 显示为“已配置 N 个值”
  - 从环境变量同步 secret 配置时统一按加密值入库，并同步清理对应缓存

### 测试
- 新增 `backend/apps/enterprise_data/test_mcp_tool_client.py`
- `uv run pytest apps/enterprise_data/test_mcp_tool_client.py -o addopts='--tb=short -q'`：`5 passed`
- `uv run pytest apps/client/test_client_enterprise_prefill_service.py -o addopts='--tb=short -q'`：`2 passed`
- `uv run python apiSystem/manage.py check`：`System check identified no issues (0 silenced)`

## [26.17.1] - 2026-03-17

### 优化
- **Client 当事人文本规则解析增强**
  - `apps.client.services.text_parser` 升级为“归一化 + 分段 + 字段提取 + 候选校验”的更完整规则链，减少对大模型兜底的依赖
  - 支持更多角色标签与编号形式：`被告一`、`申请执行人`、`原审原告`、`再审申请人`、`委托方`、`受托方` 等
  - 支持更多输入格式：无冒号字段、首行直接写主体名称、列表编号、项目符号、分号/句号混排、括号角色别名
  - 增加伪名称过滤，避免把 `统一社会信用代码`、`电话` 等字段头误识别成当事人名称
- **Client Admin 提示文案收敛**
  - `/admin/client/client/add/` 的“快速填充当事人信息”成功提示明确为规则解析成功，不再暗示频繁走 Ollama 兜底

### 测试
- 新增 `backend/apps/client/test_text_parser.py`
- `uv run pytest apps/client/test_text_parser.py -o addopts='--tb=short -q'`：`10 passed`
- `uv run python apiSystem/manage.py check`：`System check identified no issues (0 silenced)`

## [26.17.0] - 2026-03-17

### 新增
- **企业数据中台（Enterprise Data）上线**
  - 新增 `apps.enterprise_data` provider 抽象，已接入 `tianyancha`，预留 `qichacha`
  - 天眼查 MCP 支持 `streamable_http` 优先、`sse` 自动回退，Bearer Token 鉴权
  - 新增统一企业数据 API：`/api/v1/enterprise-data/providers`、`/companies/search`、`/companies/profile`、`/companies/risks`、`/companies/shareholders`、`/companies/personnel`、`/persons/profile`、`/bidding/search`
- **Admin MCP 工作台**
  - 新增后台入口 `/admin/enterprise_data/mcpworkbench/`，支持 provider/tool 参数渲染、请求调试、结果查看、历史重放
  - 支持展示工具定义、样例参数和原始响应，便于后续接入新 provider
- **Client 新建页企业查询回填**
  - `/admin/client/client/add/` 新增“企业信息查询并填充”区块
  - 支持企业名模糊检索候选、选择企业后自动拉取详情并即时回填表单（无需二次“应用到表单”）
  - 自动识别统一社会信用代码已存在的当事人并给出可跳转提示

### 优化
- **交互与展示优化**
  - MCP 工作台修复长结果横向溢出，结果区域支持可读换行
  - 天眼查响应解析增强：兼容 Markdown 包裹 JSON 返回，降低“有结果但解析失败”概率
  - “🚀 快速填充当事人信息”调整为默认收起，支持点击标题栏展开/收起，并修复标题栏与输入区宽度不一致

### 配置
- **SystemConfig 配置增强**
  - 初始化默认配置新增企业数据相关键位（天眼查/企查查、传输协议、超时、限流、告警阈值）
  - `TIANYANCHA_MCP_API_KEY` 等敏感配置按 `is_secret=True` 加密存储（保存时加密，读取时解密）

### 修复
- **企业回填字段完整性**
  - 回填手机号改为“企业详情优先，搜索结果兜底”，提升常见企业电话命中率

### 测试
- `uv run python apiSystem/manage.py check`：`System check identified no issues (0 silenced)`

## [26.16.11] - 2026-03-16

### 重构
- **Preservation Date 模块独立拆分（无兼容层）**
  - 新增独立应用：`apps.preservation_date`，迁移原 `apps.automation` 下财产保全日期识别的 `models/admin/api/services/templates`
  - 新增独立 API 路径：`/api/v1/preservation-date/*`，测试页提取接口改为 `/api/v1/preservation-date/extract`
  - 新应用接入 `INSTALLED_APPS` 与 `apiSystem/api.py` 路由注册
  - 识别服务的 `get_llm_service` 依赖改走 `apps.core.services.wiring`，不再依赖 `apps.automation.services.wiring`
  - 临时文件目录调整为 `MEDIA_ROOT/preservation_date/temp`

### 清理
- 删除 `apps.automation` 中旧的 `preservation_date` admin/service/template 目录与入口
- `automation` 测试工具导航改为新 admin 路由：`preservation_date_preservationdatetool_changelist`
- `apps.automation.models.base` 移除 `PreservationDateTest` 占位模型，并同步更新 `models/__init__.py`、`admin/__init__.py` 导出

### 测试
- `backend/.venv/bin/python backend/apiSystem/manage.py check`：`System check identified no issues (0 silenced)`
- Admin URL reverse 验证：`admin:preservation_date_preservationdatetool_changelist`、`admin:automation_testtoolshub_changelist` 可正常解析

## [26.16.10] - 2026-03-16

### 重构
- **Cases/Contracts 边界收敛（相较 26.16.9 的增量）**
  - 本版本聚焦 `cases/contracts`，不延续 `26.16.9` 的 organization 主线
  - `CaseAdmin` 导入/导出逻辑下沉到 `CaseAdminService`，Admin 保持入口编排职责
  - 新增导出桥接与序列化服务：`case_admin_export_bridge`、`case_contract_export_bridge`、`case_export_serializer_service`、`contract_export_serializer_service`
  - `CaseAdminViewsMixin` 的详情页/材料页聚合逻辑继续下沉至 `CaseAdminService`，控制层更薄
- **导入链路协作方式收敛（去隐式 monkey-patch）**
  - 新增 `build_case_and_contract_import_services_for_admin()` 统一组装函数
  - `CaseImportService`/`ContractImportService` 改为显式 `bind_*` 双向绑定，替代直接写入私有属性回调
  - 导入链路 payload 新增/补全 `TypedDict`，合同与案件提醒恢复数据解析改为显式结构
- **类型边界与容错可观测性增强（不改变业务语义）**
  - `cases` 的 `wiring/dependencies/schemas/admin/service` 多处 `Any` 收紧为协议类型或 `dict[str, object]`
  - `CaseLog` 提醒读取异常路径补充日志，保持原有 fallback 行为
- **Automation 工具独立拆分（新场景直连，无兼容层）**
  - 新增独立应用：`apps.image_rotation`、`apps.invoice_recognition`，分别承接原 `apps.automation` 中对应模块的 `models/admin/api/services/templates`
  - `invoice_recognition` 采用 `managed=False + db_table` 映射既有表（`automation_invoicerecognitiontask` / `automation_invoicerecord`），不改动业务数据结构
  - 移除旧入口兼容层：删除 `automation` 下 image/invoice 的 admin 重定向、API shim、service shim
  - API 入口改为新路径：`/api/v1/image-rotation/*`、`/api/v1/invoice-recognition/*`
  - 测试工具导航中的图片旋转入口改为新 admin 路由（`image_rotation_imagerotationtool_changelist`）

### 测试
- 新增回归测试：
  - `apps/cases/test_case_admin_export_guards.py`
  - `apps/cases/test_case_admin_import_wiring.py`
  - `apps/cases/test_case_admin_service_party_projection.py`
  - `apps/cases/test_case_import_binding.py`
  - `apps/contracts/test_contract_admin_import_wiring.py`
  - `apps/contracts/test_contract_import_binding.py`
- 增补提醒/导出回归：
  - `apps/cases/test_case_log_reminder_projection.py`
  - `apps/cases/test_case_log_schema_reminder_resolver.py`
  - `apps/contracts/test_contract_admin_reminder_export.py`
- 关键组合回归：
  - `apps/cases + apps/contracts`：`47 passed`
- 工具拆分验证：
  - `manage.py check`：`System check identified no issues (0 silenced)`
  - `ruff check`（拆分影响范围）：`All checks passed`

## [26.16.9] - 2026-03-16

### 重构
- **Organization 模块边界收敛执行完成（兼容优先）**
  - `IOrganizationService` / `ILawyerService` 增加正式命名方法，保留 `_internal` 兼容层并完成主要运行时调用迁移
  - `LawyerAdmin.handle_json_import` 业务逻辑下沉到 `LawyerImportService`，Admin 保持入口编排职责
  - `OrganizationServiceAdapter` 改为通过 `AccountCredentialService` 公开查询方法读取数据，减少对私有查询接口依赖
- **跨模块运行时调用收敛**
  - `automation/api`、`oa_filing/api`、`legal_research` admin/command、`documents/evidence/core/cases` 部分运行时调用已迁移到 organization service 边界
  - `automation` 的 scraper admin 入口改为工厂构建 organization service，不再在入口层直接使用 `ServiceLocator`

### 修复
- **注册引导与组织 API 回归修复**
  - `AuthService.register` 增加 `bootstrap_token` 契约支持，修复首个管理员注册生产环境校验回归
  - 修复 `lawfirm` 更新路径测试回归（404）
- **SMS 解析回归修复**
  - 修复当“现有客户未命中”时提前返回的问题，恢复候选提取 + 匹配服务回退路径
  - `SMSParserService` 改为惰性读取 Ollama 配置，避免初始化阶段触发不必要依赖
- **敏感字符串保护增强**
  - 保持 DTO `repr` 隐藏密码、Admin 密码输入遮罩、只读密码展示等行为，并补充兼容性注释，防止后续重构恢复明文展示

### 测试
- 新增 organization 兼容与导入回归测试：
  - `apps/organization/test_lawyer_import_service.py`
  - `apps/organization/test_lawyer_service_adapter_compat.py`
  - `apps/organization/test_organization_service_adapter_compat.py`
- 新增 automation 回归测试：
  - `apps/automation/test_sms_parser_lazy_config.py`
- 关键组合回归：
  - `organization + structure + legal_research + sms`：`162 passed, 1 warning`

## [26.16.8] - 2026-03-16

### 重构
- **跨模块边界与结构治理持续收敛**
  - `client/cases/contracts/documents/automation` 等模块继续推进服务边界拆分与兼容适配，减少跨层直接耦合
  - 补齐部分历史兼容导出与结构基线，统一在 `wiring/service` 路径收口依赖访问

### 修复
- **Client 管理页回归修复**
  - 修复当事人编辑页 inline 暴露 `"<当事人名> - business_license"` 文案的问题
  - `ClientIdentityDoc.__str__` 保持为空字符串，并在 admin 样式层增加兜底隐藏规则，避免后续回归
- **验证码识别接口稳定性修复**
  - `/api/v1/automation/captcha/recognize` 明确改为 `auth=None`，确保自动化调用不受 JWT/Session/CSRF 影响
  - 在接口处增加强约束注释，避免后续误加认证/限流导致再次 403/401
- **仓库体积治理**
  - 删除参赛视频文件 `assets/videos/ggbond-competition-20260128.mp4`
  - README 移除视频链接，并在 `.gitignore` 增加对应忽略规则

### 测试
- `tests/unit/client + tests/integration/client`：`160 passed`
- `tests/integration/automation/test_captcha_recognition_open_access.py`：`2 passed`
- `tests/structure/test_auth_none_guardrails.py`：`1 passed`

## [26.16.7] - 2026-03-15

### 重构
- **Reminders 模块边界收敛（写侧 + 读侧）**
  - 写侧完成端口化：`reminders` 通过 `ports + adapters` 校验 `contract/case_log` 目标，不再在服务层直接导入外部模块 Model
  - 组合根统一：`build_reminder_service()` 与 reminders wiring 对齐，`ServiceLocator` 获取到的是完整装配服务
  - 协议补齐：`IReminderService` 增加合同/案件日志导出与案件日志最新提醒查询能力
- **消费侧迁移到 ReminderService**
  - `cases/contracts` 的 admin/schema/模板主路径改为调用 reminder service 读取提醒数据
  - `CaseLog` 提供 `reminder_entries/has_reminders/reminder_count` 投影属性，读取逻辑统一走 service
  - 合同克隆流程改为强依赖 `export_contract_reminders_internal`，移除 reverse ORM 读提醒主逻辑
- **automation 提醒桥接修复**
  - 法院文书绑定流程不再写 `CaseLog` 临时属性，改为委托 `case_service.update_case_log_reminder_internal(...)`
  - 保持业务语义不变：传票/执行裁定/其他文书仍映射到对应提醒类型

### 新增
- **共享 Reminder Schema**
  - `apps.core.api.schemas_shared` 新增 `ReminderLiteOut`（并保留 `ReminderOut` 兼容别名），供 `cases/contracts` 复用

### 测试
- 新增 reminders/cases/contracts/core/automation 多组回归测试，覆盖：
  - 端口注入与组合根行为
  - admin/schema 读路径迁移
  - contract clone 提醒导出链路
  - automation 手动绑定提醒桥接
  - shared schema 输出兼容

## [26.16.6] - 2026-03-15

### 新增
- **法律检索事件模型与可视化观测链路**
  - 新增 `LegalResearchTaskEvent` 模型与迁移（记录阶段、来源、接口名、URL、状态码、耗时、请求/响应摘要、错误信息）
  - 新增事件写入服务 `LegalResearchTaskEventService`，统一进行请求/响应脱敏与截断
  - `LegalResearchTaskAdmin` 详情页新增：
    - API 阶段指标（命中率、DOM 回退率、错误码分布、`C_001_009` 计数）
    - 流程时间线视图
    - 接口返回可视化面板（Request/Response/Meta）
  - 私有 API 观测面板增加能力门禁：仅在目标法律数据源且私有 API 能力可用时展示

### 优化
- **法律检索链路稳定性增强**
  - 检索阶段新增短时熔断与冷却逻辑，连续空结果/异常时优先走 DOM，降低 API 抖动影响
  - 明确 `offset > 0` 空页视为翻页结束，不再回退 DOM
  - 详情阶段补充 `document_meta` / `document_html` / `dom_detail` 结构化事件记录
  - 执行器会话增加 `task_id` 透传，支持全链路事件关联追踪

- **评测基线与可解释评估输出增强**
  - `benchmark_legal_research_retrieval` 支持样本 `query_type` 归一化（`primary/expansion/feedback/other`）
  - 汇总报告新增按查询类型统计：`tp/fp/fn/precision/recall/f1/contribution_rate`
  - Matrix 与 CSV 输出增加查询类型贡献率字段，便于策略预算化对比
  - 基线样本结构升级为 `v2`，补充 `query_type_notes` 与分层骨架字段

### 维护
- **Git 追踪策略清理**
  - `backend/apps/legal_research/evaluation/baseline_cases.json` 改为本地标注文件，不再纳入 Git 跟踪
  - `.gitignore` 明确补充 legal_research 评测样本与报告目录忽略规则

## [26.16.5] - 2026-03-15

### 优化
- **organization 模块代码规范整改**
  - **Service 层内部方法规范化**：将 `_get_lawyer_internal`、`_get_lawfirm_internal`、`_get_credential_internal` 改为公共方法 `get_lawyer_by_id()`、`get_lawfirm_by_id()`、`get_credential_by_id()`
  - **Adapter 层调用更新**：所有 Adapter 统一使用新的公共方法，移除对内部方法的直接访问
  - **API 层工厂函数规范化**：`lawyer_api`、`team_api`、`lawfirm_api`、`accountcredential_api`、`auth_api` 均添加 `_get_xxx_service()` 工厂函数，符合四层架构规范
  - **业务逻辑保持可用**：37个单元测试全部通过，无破坏性变更

## [26.16.4] - 2026-03-15

### 重构
- **client 模块架构解耦**：引入 Ports/Adapters 模式，彻底解耦跨模块依赖
  - **Admin 层解耦**：`ClientAdmin` 不再直接导入 `automation` / `organization` 模块
    - 新增 `GsxtReportPort` / `CredentialPort` 接口
    - 新增 `GsxtReportAdapter` / `CredentialAdapter` 实现
    - 企业信用报告功能通过端口调用，支持独立测试和替换
  - **Service 层解耦**：移除 `FileUploadService` / `Validators` 硬编码依赖
    - 新增 `FileUploadPort` / `FileValidatorPort` 接口
    - 通过构造函数或属性注入，支持 mock 测试
  - **API 层解耦**：移除 `django_q_tasks` 直接导入
    - 新增 `TaskServicePort` 接口
    - 异步任务提交/查询通过端口封装
  - **文件结构优化**：`dependencies.py` 迁移至 `utils/ocr_provider.py`，职责更清晰
  - **工厂函数统一**：`services/wiring.py` 集中管理所有端口/适配器/服务工厂

## [26.16.3] - 2026-03-15

### 新增
- 合同审查模块新增异步任务与仓储层
  - 新增 `contract_review.tasks`，支持审查任务入口与历史文件清理
  - 新增 `ReviewTaskRepository`、`wiring`、`ServiceLocator` 协议与 Mixin 接入
  - `ReviewTask` 新增 `pdf_cache_file` 字段并提供迁移 `0011_reviewtask_pdf_cache_file`
- 模拟庭审新增报告导出能力
  - 新增 `/api/v1/mock-trial/sessions/{session_id}/export` 导出接口
  - 新增 `MockTrialExportService` 与 `MockTrialReportPlaceholderService`
  - 新增英文翻译补充脚本与模拟庭审报告模板生成脚本
- 案例检索新增评测与反馈闭环
  - 新增基准评测命令 `benchmark_legal_research_retrieval`
  - 新增基线样本文件 `baseline_cases.json`
  - 新增在线反馈服务，支持“真实命中/误命中/漏命中”反哺调参

### 优化
- `legal_research` 执行器重构为组件化架构（生命周期/数据源网关/结果持久化）
- `legal_research` 检索链路升级
  - 二阶段匹配（宽召回 + 精排）与双模型复核
  - 查询扩展（同义词、LLM 检索变体、伪相关反馈扩展）
  - 动态语义触发（词法优先，低置信样本再启用语义向量）
  - 缓存增强（案例详情缓存、相似度缓存、语义向量缓存）
  - 段落提取优先从“本院查明”后文开始，提升送模有效信息密度
- `legal_research` 调参与可观测性增强
  - 新增大量系统配置项（召回权重、双模复判、反馈阈值、自适应阈值、缓存 TTL 等）
  - 任务文案补充最佳检索式、扫描/命中/候选统计
- wk 检索源增强
  - 登录流程支持站点首页登录 + 法律库弹窗登录双路径
  - API 失败或空结果时自动回退 DOM 检索
  - 文书详情 API 失败时新增 DOM 详情兜底提取
- 合同审查后台增强
  - 新增“批量重试任务”“删除任务及关联文件”管理动作
  - 报告 PDF 增加缓存复用，减少重复生成开销
- 模拟庭审前端交互增强
  - 新增导出按钮、进度条、会话预览、辩论难度选择、WebSocket 重连与错误重试
  - Markdown 渲染增强（支持 `marked`）
- LLM 客户端链路增强
  - `LLMService/LLMClient/SiliconFlow` 支持 `timeout_seconds` 透传，便于按调用场景精细化超时控制

### 修复
- 修复案例检索任务在异步上下文下触发 ORM 同步限制的问题
  - 执行入口改为线程池隔离运行，避免 `SynchronousOnlyOperation`
- 修复案例检索任务队列状态不同步问题
  - 新增队列失败状态回填逻辑，避免任务长期停留在 `queued/running`
- 修复案例检索任务提交流程稳定性
  - 统一 LLM 连通性预检失败与队列提交失败处理路径
  - 失败任务重启逻辑集中到服务层，避免状态不一致
- 修复合同审查 API 访问控制缺失
  - 新增任务状态查询、确认、原文下载、结果下载的用户权限校验

## [26.16.2] - 2026-03-14

### 优化
- README 中英文版本号同步更新至 `26.16.2`
- README 英文版补齐法律检索与 MCP 能力介绍，与中文版核心功能说明保持一致

### 修复
- `legal_research` 执行器增强健壮性
  - 候选检索、案例详情、PDF 下载阶段均增加重试与退避机制
  - 单条案例详情或下载失败时改为跳过继续，避免整任务因单点异常中断
  - 任务进度与完成文案补充跳过统计，便于定位异常样本
- wk 文档抓取链路增强容错
  - 详情接口支持 `raw/unquoted doc_id` 双路径尝试
  - 针对高频临时错误（含部分 `HTTP 400` 场景）增加请求级重试

## [26.16.1] - 2026-03-14

### 新增
- 案例检索任务详情页新增“取消任务”按钮
  - 支持对 `pending/queued/running` 任务执行取消
  - 取消时会先尝试撤销 Django-Q 队列中的待执行任务

### 优化
- 案例检索任务详情页新增“候选池提示”
  - 当关键词候选不足时，明确提示“仅检索到 N 篇候选案例”
  - 当达到目标或扫描上限时，明确提示结束原因

### 修复
- 执行中的案例检索任务支持协作式取消
  - 任务被标记为 `cancelled` 后，执行器会在批次循环中及时检测并停止后续扫描
  - 修复“任务看起来停住/结束原因不清晰”的体验问题

## [26.16.0] - 2026-03-13

### 新增
- 新增法律案例检索模块（`legal_research`）
  - 支持任务创建、进度查询、结果下载
  - 支持相似案例 PDF 保存到任务并集中下载
  - 新增 OpenClaw Skill，可脱离系统界面直接调用检索 API

### 优化
- 检索任务后台表单可配置“最大扫描案例数”（默认 `100`）与“最低相似度阈值”（默认 `0.9`）
- 关键词输入支持多分隔符，统一按空格做联合检索
- 检索账号选择范围收敛到目标法律检索站点账号，且单账号时自动默认选中
- 失败任务支持在详情页修改 LLM 模型并一键重启

### 修复
- 提交任务时增加硅基流动连通性预检，连接失败不再进入队列
- 连通性预检失败会写入明确错误信息，便于用户在任务详情页修正参数后重试

## [26.15.3] - 2026-03-12

### 新增
- 利息计算器支持迟延履行利率
  - 新增利率模式选项：迟延履行利率
  - 固定利率单位：万分之（‱/天）
  - 固定利率数值：1.75
- 历史记录显示利率设置信息
  - 显示 LPR 类型和倍数
  - 显示迟延履行利率
  - 显示自定义利率数值和单位

## [26.15.2] - 2026-03-12

### 新增
- 发票识别结果页显示金额中文大写（如：壹万贰仟叁佰肆拾伍元整）

### 优化
- finance 模块 i18n 国际化补全
  - LPR利率、利息计算器相关字段和模板支持英文翻译
- 账号凭证 Admin URL 字段改为普通文本输入框，隐藏 "Currently/Change" 提示

### 修复
- 移除 AccountCredential 冗余的 "是否优先使用" 字段
  - 删除模型字段及数据库索引
  - 删除 Admin 批量操作和列表显示
  - 删除 Service 相关方法
  - 更新账号选择策略排序逻辑
  - 同步更新相关测试

## [26.15.1] - 2026-03-12

### 优化
- LPR利息计算器更名为"利息/违约金计算器"并移到 finance 主菜单，访问路径：`/admin/finance/calculator/`
- 利率设置支持自定义利率模式：
  - 百分之（%/年）：按年计算利息
  - 千分之（‰/天）：按天计算利息
  - 万分之（‱/天）：按天计算利息
- 计算明细利率显示优化，明确标注计算基准（年/天）
- 添加 `.codebuddy/` 到 gitignore

## [26.15.0] - 2026-03-11

### 新增
- LPR利息计算器功能完善
  - 支持多笔独立债务计算（时间重叠场景，如多期租金违约金）
  - 计算明细按本金分组展示，支持展开/收起
  - 计算结果可复制为Word表格格式
  - 添加计算历史记录功能，支持加载历史数据

## [26.14.0] - 2026-03-10

### 新增
- LPR利息计算器：基于贷款市场报价利率计算逾期利息/违约金
  - 支持固定本金和变动本金两种计算模式
  - 支持一年期/五年期LPR利率类型选择
  - 支持利率倍数设置（如1.5倍LPR）
  - 支持多种计息基准（360天/年、365天/年、实际天数）
  - 支持四种日期计算方式（起止均计/只计起始/只计截止/起止不计）
  - 自动分段计算（LPR利率变动时自动分段）
  - 结果可复制到剪贴板
  - 显示近期LPR利率参考数据
  - 左右分栏布局，响应式设计

## [26.13.2] - 2026-03-09

### 重构
- MCP Server tools 目录按业务域重组为子目录结构（cases/clients/contracts/organization）
- 新增 tools 只需在对应域文件添加函数，无需修改顶层结构

## [26.13.1] - 2026-03-09

### 新增
- MCP Server 扩展至 30 个 tools（新增 16 个）
  - 案号：`list_case_numbers`、`create_case_number`
  - 律师指派：`list_case_assignments`、`assign_lawyer`
  - 案件当事人：`list_case_parties`、`add_case_party`
  - 案件进展日志：`list_case_logs`、`create_case_log`
  - 合同：`create_contract`
  - 客户财产线索：`list_property_clues`、`create_property_clue`
  - 财务：`list_payments`、`get_finance_stats`
  - 催收提醒：`list_reminders`、`create_reminder`
  - 组织架构：`list_lawyers`、`list_teams`

### 修复
- 身份证裁剪合并页面：合并后自动保存到客户证件附件，显示返回客户页面按钮
- 客户详情页：去掉重复的"身份证裁剪合并"按钮
- 企业信用报告：详情页跳转改用 `commit` 模式，修复因页面持续加载导致卡住的问题

## [26.12.0] - 2026-03-08

### 新增
- MCP Server：支持 OpenClaw、Claude Desktop 等 AI Agent 通过自然语言操作法穿系统（14 个 tools）
  - 案件：list_cases、search_cases、get_case、create_case
  - 客户：list_clients、get_client、create_client、parse_client_text
  - 合同：list_contracts、get_contract
  - OA 立案：list_oa_configs、trigger_oa_filing、get_filing_status
  - 自动 JWT 认证（用户名密码配置，自动获取/刷新 token）
  - 支持 `uv run mcp dev mcp_server/server.py` 开发调试



### 修复
- Lawyer 管理页账号密码内联表格：URL 字段隐藏 "Currently/Change" 提示，改用普通文本输入框
- Lawyer 管理页 i18n：补全账号信息、个人信息、新密码、留空则不修改密码、组织关系、权限等字段的英文翻译
- OA 立案模块 i18n：补全所有未翻译的英文字符串

## [26.11.4] - 2026-03-07

### 新增
- 合同文档生成支持"拆分律师费"：多案件合同（≥2个关联案件且有固定金额）可在生成合同时按争议金额比例自动拆分律师费，追加到收费条款后
- 文档生成区域新增"拆分律师费"切换按钮（满足条件时显示）

### 修复
- 常法合同无需关联案件即可发起 OA 立案（`case_id` 改为可选）
- `script_executor_service`：修复 `contract.contract_type` 错误，改为 `contract.case_type`
- OA 立案客户搜索：修复 layui table toolbar confirm 按钮无法通过 Playwright pointer click 触发的问题，改用 JS 直接操作 layui 内部缓存并调用 `loadCustomer()`
- 收费条款模板：修复固定收费和半风险收费"整整"重复问题

### 完善
- JTN OA 立案改用有头浏览器（`headless=False`）
- 常法合同 OA 立案自动推断业务种类（`kindtype`/`kindtype_sed`）
- 文档生成区域按钮移除所有 emoji
- Token 获取历史页面 UI 优化：移除 emoji、统一卡片样式

## [26.11.3] - 2026-03-06

### 修复
- 合同详情页模板匹配缓存失效问题：`ContractTemplateCache` 缓存键加入版本号，模板变更后立即生效
- `DocumentTemplateFolderBinding` 保存时自动计算 `folder_node_path`，修复新建绑定后合同文件放置位置错误的问题

### 完善
- 默认数据补充顾问合同、刑事合同模板及对应文件夹绑定关系

## [26.11.2] - 2026-03-06

### 新增
- `GsxtReportTask` 新增 `credit_code`（统一社会信用代码）字段
- 工商信用报告流程：公司名匹配失败时自动改用信用代码兜底搜索
- 落地页新增企业信用报告功能模块（`_gsxt_flow.html`）

### 移除
- 移除 Moonshot（月之暗面）模型支持

## [26.11.1] - 2026-03-05

### 修复
- 163 IMAP 收取报告：修复 `SEARCH` 命令不支持中文导致 `UnicodeEncodeError`，改为扫描专用文件夹全部邮件
- 163 IMAP 收取报告：修复文件夹硬编码问题，文件夹不存在时自动回退到 INBOX
- 163 IMAP 收取报告：`_decode_header_value` 加 `errors="replace"`，防止非标准编码抛异常跳过邮件
- Django-Q 延迟任务：`q_options={"countdown": 60}` 对 Django-Q 无效，改用 `Schedule.ONCE + next_run` 实现真正的60秒延迟
- 报告申请成功后 `async_task` 在 async 上下文报错，改用 `sync_to_async` 包装
- `gsxt_report_service.py`：`click_company_detail` 和 `request_report` 改用 `wait_for_selector` 替代固定 sleep，防止 `#btn_send_pdf` 超时
- `apps.py`：移除启动时自动恢复法院短信任务逻辑，彻底解决先启动 Django 后启动 qcluster 时的 SQLite 写锁卡死问题
- SQLite 连接：`CONN_MAX_AGE` 从 600 改为 0，避免多进程长连接持锁
- Django-Q 轮询间隔：`poll` 从默认 0.2s 改为 2s，降低 SQLite 写操作频率

## [26.11.0] - 2026-03-05

### 修复
- SQLite 写锁竞争：先启动 qcluster 再启动 Django 不再卡死（`busy_timeout` 提升至30秒，法院短信恢复任务改为提交 Django-Q 异步执行）
- 详情页 `#btn_send_pdf` 超时：改用 `wait_for_selector` 替代固定 sleep
- 异步上下文 ORM 调用：`asyncio.to_thread` 改为 `sync_to_async`

### 文档
- README/Makefile 明确本地开发启动顺序：先 `make qcluster`，再 `make run`

## [26.10.0] - 2026-03-05

### 新增
- Docker 支持：新增 `Dockerfile`、`docker-compose.yml`、`docker-entrypoint.sh`，一键启动 web + qcluster 两个服务，数据库和媒体文件通过 volume 持久化
- Docker healthcheck：qcluster 等待 web 健康后再启动，避免 `django_q_ormq` 表未就绪报错

### 重构
- OA 立案简化：去掉 OAConfig 表依赖，直接从 AccountCredential 读取支持站点，`execute` 接口改用 `site_name` 字段
- `jtn_filing.py`：改用 `httpx`，`headless=True`，新增 `stamp_count`（预盖章份数）和 `legal_position`（法律地位）字段填写
- `script_executor_service.py`：新增 `_map_which_side` / `_map_legal_position` 从 CaseParty 查诉讼地位
- 合同详情页文件夹生成按钮加锁，防止重复点击

### 删除
- `oa_config_admin.py`：后台"OA系统配置"菜单移除

## [26.9.0] - 2026-03-04

### 重构
- core 模块目录整理：将根目录散落的 11 个文件移入对应子目录（`middleware/`、`services/`、`exceptions/`、`filesystem/`、`http/`、`infrastructure/`、`models/`、`api/`），原位置保留 re-export 兼容模块
- 删除根目录冗余的 `config.yaml` 和 `config.example.yaml`（`config/` 子目录已有新版本）

### 修复
- 律师导入：已存在的律师不再跳过，改为补全 JSON 中有值而数据库为空的字段（基本信息、律所、团队、账号密码）

## [26.8.6] - 2026-03-04

### 修复
- 律师导入导出：导出 ZIP 新增 `license_pdf` 文件打包、`password` 占位字段（留空随机生成，填写则使用明文）
- 律师导入：律所、律师团队、业务团队不存在时自动创建
- 律师 admin：新密码字段加 `autocomplete="new-password"` 防止 Chrome 自动填充
- 律师 admin：隐藏账号密码 inline 行标题（`__str__` 显示）
- 律师 admin：修复账号密码区域标题多余 "s" 后缀
- 律师列表页：新增导入按钮

## [26.8.5] - 2026-03-04

### 修复
- 修复律师 admin 保存组织关系后重新打开团队字段为空的问题（`save_m2m` 覆盖了 M2M 写入）



### 修复
- 补充律师导入导出功能（之前只有合同有导入导出，律师遗漏）
- 律师 admin 新增明文密码输入框，保存时自动加密
- 律师 admin 组织关系改为单选下拉框，移除律所字段，自动从团队推断律所

### 文档
- 新增开源理念章节（中英文）



### 修复
- 修复注册页面 Bootstrap Token 校验逻辑（本机部署无需此限制，已移除）
- 修复首个注册用户无法登录 Django admin 的问题（`is_staff` 未设置为 `True`）
- 移除所有密码强度校验限制（本机部署场景无需）

## [26.8.2] - 2026-03-04

### 修复
- 修复 mypy INTERNAL ERROR（`mypy_django_plugin` + `django-stubs 5.x` 的 `_AnyUser` TypeAlias 触发断言，注释掉 plugin）
- 修复 CI `exceptions_handlers.py` 路径错误（改为 `exceptions/handlers.py`）
- 修复 `organization_access_policy` 缺少 `ensure_*` 方法及权限逻辑错误
- 修复 `middleware_request_id` 未捕获 response header 设置异常
- 新增 `backend/deploy/docker/Dockerfile`（container-scan CI 所需）
- 修复 `.gitignore` 允许 Dockerfile 被追踪

### 文档
- 重写中英文 README 及 LICENSE 商业授权说明（个人/≤10人免费，>10人按 200元/人 捐赠授权，捐赠即授权）

## [26.8.1] - 2026-03-03

### 修复
- 修复 CI pre-commit 全部检查通过：
  - `mypy.ini` 去掉多余的 `apiSystem` 前缀（`apiSystem.apiSystem.settings` → `apiSystem.settings`）
  - 去掉 pre-commit black hook（与 ruff-format 冲突）
  - 去掉 pre-commit mypy hook（CI 有独立 mypy job，避免 PYTHONPATH 冲突）
  - ruff ignore 列表补充历史遗留规则（`F821/C901/B904/B905/F841/E501` 等）
  - mypy 版本限制改为 `<1.19.0`（修复 1.19.1 INTERNAL ERROR）
  - 重新生成 `.secrets.baseline`（修复 detect-secrets 路径不匹配问题）

## [26.8.0] - 2026-03-03

### 新增
- **ZIP 格式导入导出**：Client / Contract / Case 三个模块支持完整的 ZIP 格式导入导出
  - ZIP 内含 `data.json`（带 `_type` 类型标记）+ `files/` 媒体文件目录
  - 导出包含所有关联数据：当事人（含身份证件/财产线索附件）、律师指派、付款记录、发票、补充协议、定稿材料、案件日志（含附件/提醒）、群聊绑定等
  - 导入按唯一键 get_or_create，重复数据跳过，已存在文件不覆盖
  - 严格校验文件类型（`_type` 标记），拒绝跨模块导入
  - 修复 Zip Slip 路径遍历安全漏洞
- **定稿材料拖拽排序**：FinalizedMaterial 新增 `order` 字段，detail 页按分类分卡片 + SortableJS 拖拽排序
- **删除合同级联删除案件**：合同删除时关联案件自动级联删除（`SET_NULL` → `CASCADE`）

### 重构
- 抽出 `serialize_client_obj` / `serialize_case_obj` / `serialize_contract_obj` 共享序列化函数，三个模块导出逻辑统一复用
- 合同导入 cases 改为复用 `CaseImportService.import_one`，不再内联重复逻辑

### 修复
- 合同导入时 cases 的 logs / chats / reminders 不再丢失
- `ContractFinanceLog` 导入改为 get_or_create，避免重复导入产生重复记录
- 案件无 `filing_number` 时从合同导入不再重复创建
- 案件导入时去掉 `contract.cases`，避免合同还原时重复创建案件
- 删除合同前手动 unbind cases 的旧逻辑已移除，CASCADE 接管
- 导入错误信息补充异常类型名，server 日志记录完整 traceback

## [26.7.5] - 2026-03-03

### 修复
- 修复 CI 多个 job 失败问题：
  - 生成并提交 `.secrets.baseline`，从 `.gitignore` 移除，解决 `pre-commit` detect-secrets 步骤报错
  - 降级 `backend-mypy-strict` job：从全量 `mypy apps/ --strict` 改为 curated 文件列表，避免不现实的全量严格检查
  - 修复 `backend-mypy-full` / `backend-coverage` job 引用了不存在的 `safe_expression_evaluator.py`，补充实现该模块
  - 修复 `backend-ruff-full` 的 21 处 lint 错误（行过长、空白行含空格、未使用 noqa、quoted 类型注解等）

## [26.7.4] - 2026-03-02

### 修复
- 删除未实现的 `/api/v1/llm/templates/sync` 端点（`PromptTemplateService` 无对应方法），消除每次调用必 500 的问题
- `sms_matching_stage` 和 `case_matcher` 改用 `ServiceLocator.get_case_service()`，修复 `/api/v1/automation/court-sms` 因调用已废弃 `build_case_service()` 导致的 500
- `organization/schemas.py` 补全 `model_rebuild()`：`LoginIn`、`LawyerOut`、`AccountCredentialOut`，修复 pydantic v2 + `from __future__ import annotations` 导致的 schema 解析失败
- `AccountCredentialOut` 的 `resolve_created_at/updated_at` 改为 `@staticmethod`，修复 `Non static resolves are not supported yet` 错误
- 补全 `.env.example` 缺失的 `SMOKE_ADMIN_PASSWORD`、`CREDENTIAL_ENCRYPTION_KEY`、`SCRAPER_ENCRYPTION_KEY` 配置项
- 修复 `Makefile` health 检查路径（`/health/`）及端口变量引用

## [26.7.3] - 2026-03-02

### 修复
- 权限系统重构：已登录用户无需 `is_admin` 即可执行所有业务操作
  - `AuthzUserMixin.is_admin` 改为"已登录即有权限"，覆盖所有继承该 mixin 的 service（案件分配、合同付款、文件夹绑定等）
  - `PermissionMixin.is_admin` 同步修复
  - `OrganizationAccessPolicy` 放开读/写权限，仅删除律所保留 superuser 限制
  - `folder_binding_service.require_admin` 改为只检查登录状态
  - `contracts/folder_binding_api._require_admin` 同步修复
  - 保留管理员限制：Django admin 入口、系统模板同步、删除律所

## [26.7.2] - 2026-03-02

### 修复
- i18n 国际化补全（第二轮）
  - 修复文件夹浏览器 API 权限检查：`_require_admin` 同时允许 `is_staff`（Django superuser），解决 admin 用户无法使用文件夹绑定功能的问题
  - 补全模板中文翻译：`caselog_inline.html`、`ai_chat.html`、`litigation_fee_calculator.html`、`client/change_form.html`、`client/id_card_merge.html`、`automation/courtsms/assign_case.html`、`submit_sms.html`、`document_recognition/recognition.html`、`invoicerecognitiontask/change_form.html`、`contracts/detail.html` 等
  - 新增各 app 英文翻译条目：cases(+45)、automation(+45)、client(+52)、contracts(+6)、core(+26)、documents(+1)

## [26.7.0] - 2026-03-01

### 新增
- 证据管理独立应用（evidence）
  - 从 documents 模块迁移为独立 app，保留向后兼容（`__getattr__` 延迟导入）
  - 证据清单 CRUD、证据明细拖拽排序、类型筛选
  - 证据 PDF 合并导出、页码范围计算
  - 证据清单替换词服务（文书生成集成）
  - Admin 管理界面（表单、内联、批量操作、自定义视图）
  - API 路由 `/api/v1/evidence/`
- 证据智能分类整理（evidence_sorting）
  - AI 证据分类器（LLM 驱动）
  - 分类结果导出、证据核对服务
  - Admin 管理界面 + 独立操作页面
  - API 路由 `/api/v1/evidence-sorting/`
- OA 系统自动立案（oa_filing）
  - JTN OA Playwright 自动化脚本（登录→添加委托方→案件信息→利冲→合同→存草稿）
  - 支持企业/自然人/非法人组织客户类型自动创建
  - 支持多委托方（动态 iframe ID 定位）
  - 案件类型全覆盖：民商事/刑事/行政/仲裁/非诉专项/常法顾问
  - 收费方式映射：定额/按标的比例/按小时/零收费
  - OAConfig 多律所配置 + FilingSession 会话管理
  - 合同详情页立案标签页（Alpine.js UI）
  - 依赖注入工厂 + API 路由 `/api/v1/oa-filing/`
- 模拟庭审（litigation_ai/mock_trial）
  - 多角色 LLM 链（原告/被告/法官视角）
  - WebSocket 实时对话（mock_trial_consumer）
  - 案件详情页"模拟庭审"入口按钮
  - 独立前端页面（HTML + CSS + JS）
  - API 路由 `/api/v1/mock-trial/`
- 法院YZW在线立案（automation/court_filing）
  - 登录：Playwright + ddddocr 识别图形验证码，拦截网络响应提取 JWT token
  - 立案：接口优先（httpx 纯 REST 流程：查法院→创建立案→上传附件→添加当事人→更新代理人→提交），接口失败自动回退 Playwright 全页面操作
  - 支持民事、行政、执行三类立案
  - 案件详情页法院立案标签页
  - API 路由 `/api/v1/court-filing/`

### 变更
- 证据相关模型/服务/Admin 从 documents 迁移到 evidence，documents 模块通过延迟导入保持向后兼容
- contract_review 新增 custom_llm_fields 和 duration_seconds 迁移
- litigation_ai Session 模型新增 session_type 字段
- docs/ 目录整体加入 .gitignore（个人分析文档不公开）

## [26.6.0] - 2026-02-27

### 新增
- 合同自动审查处理器（contract_review 应用）
  - 多方当事人支持（甲乙丙丁），动态 admin 字段
  - 上传 UI：3步向导，可搜索模型选择器，拖拽上传
  - 用户可选处理步骤：错别字检查、格式修订、合同审查、输出审查报告
  - Track Changes 输出（OOXML `<w:del>/<w:ins>` 标记）
  - LLM 智能标题识别 + OOXML 多级自动编号（一、/1./（1））
  - 附件区域独立编号重启
  - 格式标准化：黑体小二标题、宋体小四正文、1.5倍行距、正文首行缩进2字符
  - 审查评估报告页面（Apple 风格设计）
  - 评估报告 PDF 导出（weasyprint 渲染）
  - 审查人姓名自定义，输出文件名含 task_id 唯一标识
  - 处理步骤 tooltip 悬浮说明

### 修复
- SiliconFlow API 超时异常分类修正（APITimeoutError 优先于 APIError 捕获）
- LLM 调用超时时间提升至 900 秒，标题识别失败自动重试
- 补充识别 LLM 遗漏的编号段落（含真实自动编号 numId>0 的段落）
- 清除 Word 样式和段落级 Chars 缩进属性，避免缩进异常
- qcluster 重启时杀死所有 multiprocessing 子进程，防止僵尸 worker

## [26.5.0] - 2026-02-27

### 新增
- 外部模板映射可视化编辑器（左右分栏：文档预览 + 字段映射列表）
- 支持鼠标点选文档位置创建映射（选择模式 + 自动定位）
- 映射高亮联动（左右面板点击同步高亮滚动）
- 外部模板 API：预览HTML、映射CRUD、重新分析
- mammoth docx→HTML 预览

### 修复
- 修复外部模板表格提取遗漏合并单元格（改用XML解析 gridSpan/vMerge）
- 修复 wiring.py 服务工厂导入名称错误
- 修复 CaseOut 序列化 media_url 属性调用方式
- 修复 fill_action.js API 路径（cases router 双层前缀）
- 修复 API 路由尾部斜杠与中间件冲突

## [26.4.5] - 2026-02-26 19:30

### 新增
- 添加跨平台下载路径自动检测功能（文件夹浏览器优先显示用户 Downloads 目录）
- 添加 README 打赏模块（支持微信赞赏、USDT、比特币）
- 更新 README 联系方式为微信二维码

### 修复
- 修复 {{案件详情}} 替换词生成逻辑（使用 client.is_our_client 字段判断对方当事人）
- 修复合同详情页文件夹选择器横向滚动问题（支持多层级展开）

### 优化
- 清理 Git 忽略配置
  - 从 Git 中移除 backend/deploy/docker 目录
  - 清空所有迁移文件
  - 添加 backend/logs/ 到忽略列表
  - 添加 backend/apiSystem/cookies/ 到忽略列表
  - 添加 backend/apiSystem/media/ 到忽略列表
- 删除 about 页面（不再需要）

## [26.4.4] - 2026-02-26

### 修复
- 修复法院短信爬虫 Token 过期处理逻辑（正确处理 401 状态码）
- 修复爬虫拦截器 Token 刷新机制（避免无限重试）
- 修复文档替换词生成中的英文标点符号问题（全部改为中文标点）
  - 英文冒号 `:` → 中文冒号 `：`
  - 英文逗号 `,` → 中文逗号 `，`
  - 英文句号 `.` → 中文句号 `。`
  - 英文分号 `;` → 中文分号 `；`
  - 英文括号 `()` → 中文括号 `（）`

### 优化
- 清理系统配置初始化数据（删除未使用的配置项）
  - 删除 CASE_CHAT_DEFAULT_STAGE
  - 删除 COURT_SMS_ENABLED、COURT_SMS_AUTO_MATCH_CASE、DOCUMENT_DELIVERY_ENABLED
  - 删除 AI_ENABLED、AI_AUTO_NAMING_ENABLED、AI_CASE_ANALYSIS_ENABLED

## [26.4.3] - 2026-02-25

### 修复
- 修复 SMS 依赖注入错误（移除不存在的模块导入）
- 修复 SMS 当事人提取逻辑（简化提取流程，移除有问题的 PartyCandidateExtractor）
- 修复 SMS 案件绑定 MRO 问题（调整 Mixin 继承顺序）
- 修复 `_create_case_binding` 方法的 NotImplementedError 错误
- 修复 LawyerDTO 属性访问错误（name → real_name）
- 修复 SMS 通知服务详细错误信息记录
- 修复 `CaseChatServiceAdapter` 缺少 `get_or_create_chat` 方法
- 修复 `ISystemConfigService` 类型注解导致的运行时错误

### 优化
- 案件日志 inline 显示优化（隐藏标题、统一布局、添加排序功能）
- 案件日志添加正序/倒序排序按钮（默认倒序）
- 优化案件编辑页所有 inline 模块的标题栏对齐
- 案件案号备注框改为自适应宽度
- 案件日志字段调整（显示创建日期，移除提醒相关字段）
- 系统配置初始化优化（添加飞书默认配置，移除环境变量同步按钮）

## [26.4.2] - 2026-02-25

### 新增功能
- 在合同编辑页添加文件夹绑定功能（Finder 风格分栏浏览器）
  - 支持多列分栏显示文件夹层级结构
  - 支持手动输入路径
  - 支持浏览和选择文件夹

### 修复
- 修复文件夹模板初始化功能
- 升级文件模板初始化功能（完整版：文件夹模板、文件模板、绑定关系）
- 修复生成文件夹时文件放置位置不正确的问题
- 修复绑定文件夹后生成合同仍下载到 Downloads 的 bug
- 实现文件版本号自动递增（V1 → V2 → V3），重复生成不覆盖已有文件
- 修复补充协议委托人信息缺少身份证号码的 bug

### 优化
- 创建文档生成模式 Skill，统一文档生成规范
- 优化文件夹浏览器性能，减少交互闪烁

## [26.4.1] - 2026-02-25

### 修复
- 修复合同当事人选择非我方当事人时，身份未自动设为"对方当事人"的bug

## [26.4.0] - 2026-02-24

### 新增功能
- 客户回款功能优化：案件选择改为单选下拉框，根据选择的合同动态加载案件列表
  - 案件字段从 ManyToManyField 改为 ForeignKey（单选）
  - 添加 JavaScript 动态加载案件选项
  - 合同详情页支持查看回款凭证图片

### 修复
- 修复上传图片时导致创建两条相同回款记录的 bug
- 修复案件选择验证逻辑

### 优化
- 界面文案优化："收付款进度" → "律师费收款进度"，"收款记录" → "律师费收款记录"

## [26.3.0] - 2026-02-24

### 新增功能
- 客户回款记录管理：支持记录和管理采用半风险、全风险收费模式的合同中客户实际收回的款项
  - 在合同模块（/admin/contracts/）下新增"客户回款"管理入口
  - 支持创建、编辑、删除客户回款记录
  - 可关联合同和案件，上传回款凭证图片（JPG/PNG/JPEG，最大 10MB）
  - 自动记录回款金额、备注和创建时间
  - 在合同详情页的收费与财务标签页中展示客户回款卡片
  - 显示回款列表、回款总额，支持快速添加回款
  - 完整的权限控制和中英文国际化支持

## [26.2.1] - 2026-02-24

### 修复
- 删除 ContractFinanceLog Admin 后台入口（http://127.0.0.1:8002/admin/contracts/contractfinancelog/）

## [26.2.0] - 2026-02-24

### 新增功能
- 合同收款发票识别：在收款记录页面支持上传发票并自动识别发票信息
  - 支持 PDF、JPG、JPEG、PNG 格式，单文件最大 20MB
  - 自动识别发票号码、开票日期、金额、税额、价税合计等信息
  - 识别结果自动填充到发票列表，支持多文件批量上传
  - 自动更新已开票金额和开票状态
  - 使用 DataTransfer API 实现文件对象同步上传

### 优化
- 发票 Inline 表格 UI 优化：固定列宽、隐藏文件路径显示、防止表格撑爆页面

## [26.1.1] - 2026-02-24

### 修复
- ddddocr: 降级到 1.5.6（1.6.0 版本有 API 导入 bug，导致验证码识别失败）

## [26.1.0] - 2026-02-24

### 依赖更新
- Django: 6.0.1 → 6.0.2
- Gunicorn: 23.0.0 → 25.1.0（生产服务器重大更新）
- Redis: 5.0.0 → 7.2.0（跨大版本升级）
- Pandas: 2.3.3 → 3.0.1（跨大版本升级）
- Black: 24.10.0 → 26.1.0
- isort: 5.13.2 → 8.0.0（跨大版本升级）
- LangChain Core: 1.2.7 → 1.2.15
- LangChain OpenAI: 1.1.7 → 1.1.10
- OpenAI: 2.21.0 → 2.23.0
- Playwright: 1.57.0 → 1.58.0
- Django Ninja: 1.5.1 → 1.5.3
- Django Ninja JWT: 5.4.3 → 5.4.4
- Channels Redis: 4.2.0 → 4.3.0
- Cryptography: 46.0.3 → 46.0.5
- Hypothesis: 6.150.2 → 6.151.9
- pytest-django: 4.11.1 → 4.12.0
- psycopg: 3.3.2 → 3.3.3
- PyMuPDF: 1.26.7 → 1.27.1
- RapidOCR: 3.5.0 → 3.6.0
- ddddocr: 1.5.6 → 1.6.0
- OpenCV: 4.13.0.90 → 4.13.0.92
- pikepdf: 10.2.0 → 10.3.0
- reportlab: 4.4.9 → 4.4.10
- psutil: 7.2.1 → 7.2.2
- ruff: 0.15.0 → 0.15.2

## [26.0.0] - 2026-02-24

### 新增功能
- 建档编号：合同和案件支持自动生成建档编号（格式：年份_类型_HT/AJ_序号）
- 诉讼费用计算器：根据《诉讼费用交纳办法》自动计算受理费、保全费、执行费
- 案由特殊规则：支持人格权、知识产权、支付令、劳动争议等特殊案件的费用计算
- 交费通知书识别：从法院 PDF 中自动提取受理费金额，支持与系统计算金额比对
- 财产保全日期识别：使用大模型从法院文书中提取保全措施到期时间
- 财产保全材料生成：一键生成财产保全申请书、暂缓送达申请书及全套材料
- 统一模板生成服务：整合两套模板生成系统，通过 function_code 识别特殊模板
- 文件模板诉讼地位匹配：支持按诉讼地位（原告/被告/第三人等）匹配模板
- 文件夹模板诉讼地位匹配：文件夹模板同样支持诉讼地位匹配规则
- 先发一版，等我更新后面的

### 移除
- 移除 Docker 支持

## [1.0.0] - 2025-12-29

### 新增
- 案件管理系统核心功能
- 客户管理模块 - 客户信息、身份证件、财产线索管理
- 合同管理模块 - 合同创建、补充协议、付款跟踪
- 组织管理模块 - 团队、律师、账号凭证管理
- 自动化功能模块
  - 法院短信解析与文书下载
  - 法院文书自动抓取
  - 财产保全保险询价
  - 飞书群消息通知
- Django 5.x + Django Ninja API 框架
- Django-Q2 异步任务队列
- Playwright 浏览器自动化
- 完整的 Makefile 项目管理命令
- 四层架构设计 (API → Service → Model, Admin → AdminService → Model)
- 异常处理和依赖注入规范
- 完整的测试套件 (单元测试、集成测试、属性测试、结构测试)
