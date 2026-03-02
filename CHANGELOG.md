# 更新日志

本项目的所有重要更改都将记录在此文件中。

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
  - 金诚同达 OA Playwright 自动化脚本（登录→添加委托方→案件信息→利冲→合同→存草稿）
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
- 法院一张网在线立案（automation/court_filing）
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
