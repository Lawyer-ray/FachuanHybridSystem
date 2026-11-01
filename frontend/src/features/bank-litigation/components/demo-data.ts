/**
 * 立案工作台 · 演示数据（**仅用于录屏/演示，不参与真实业务**）
 *
 * ═══ 为什么单独放一个文件 ═══
 * 这些数据是为「路演录屏」凑的画面填充物：整包分段的历史记录、OA 立案的
 * 执行日志、要素式转换的样例等。它们**不来自任何后端接口**，纯前端常量。
 *
 * 集中放一处的原因：真实功能上线时，只要删掉本文件 + 各面板里的引用即可，
 * 不需要在 7 个组件里到处找散落的假数据。
 *
 * ═══ 使用约定（硬性） ═══
 * 1. 只允许出现在**展示性**位置（表格行、时间线、统计数字），
 *    绝不能参与任何判断逻辑（`if (DEMO_xxx)` 这种用法禁止）。
 * 2. 所有名称/案号已脱敏：案号用「（20XX）粤0606民初XXXX号」，人名用「某某」。
 *    这是 pre-commit 的隐私闸门要求，也是演示材料该有的样子。
 * 3. 数值要与真实业务口径一致（金额千分位、页码区间连续、时间倒序），
 *    否则律师一眼看出是假的，演示反而减分。
 */

/** 整包分段：历史拆分记录（演示态） */
export interface SplitHistoryRow {
  id: string
  fileName: string
  pages: number
  materials: number
  /** 复核结果：全部确认 / 有需复核项 / 有未识别项 */
  result: 'confirmed' | 'review' | 'unrecognized'
  /** 归案数量（0 表示未归案） */
  imported: number
  at: string
  by: string
}

export const DEMO_SPLIT_HISTORY: SplitHistoryRow[] = [
  {
    id: 'sp_1',
    fileName: '某某银行个贷不良_首批扫描件.pdf',
    pages: 278,
    materials: 84,
    result: 'confirmed',
    imported: 84,
    at: '11-03 09:12',
    by: '黄某某',
  },
  {
    id: 'sp_2',
    fileName: '诉讼盖章_全套扫描_补寄.pdf',
    pages: 46,
    materials: 12,
    result: 'review',
    imported: 12,
    at: '11-01 16:40',
    by: '黄某某',
  },
  {
    id: 'sp_3',
    fileName: '借款合同及借据_扫描.pdf',
    pages: 120,
    materials: 36,
    result: 'confirmed',
    imported: 36,
    at: '10-29 11:25',
    by: '房某某',
  },
  {
    id: 'sp_4',
    fileName: '催收档案_2026Q3.pdf',
    pages: 30,
    materials: 10,
    result: 'unrecognized',
    imported: 0,
    at: '10-28 09:05',
    by: '黄某某',
  },
  {
    id: 'sp_5',
    fileName: '当事人身份材料_扫描.pdf',
    pages: 18,
    materials: 6,
    result: 'confirmed',
    imported: 6,
    at: '10-26 14:30',
    by: '房某某',
  },
]

/** 整包分段：拆分引擎的识别能力（当前模板支持的材料类型） */
export const DEMO_SPLIT_TEMPLATE_TYPES = [
  '起诉状',
  '证据清单及明细',
  '当事人身份证明',
  '授权委托材料',
  '送达地址确认书',
  '借款合同',
  '放款凭证',
  '还款明细',
  '催收记录',
  '判决书',
  '裁定书',
  '上诉状',
  '答辩状',
]

/** OA 立案：执行日志（演示态） */
export interface OAFilingLogRow {
  stage: string
  message: string
  ms: number
  ok: boolean
  at: string
}

export const DEMO_OA_FILING_LOG: OAFilingLogRow[] = [
  { stage: '登录', message: '使用配置账号登录 OA 成功', ms: 1840, ok: true, at: '11-03 10:02' },
  { stage: '建卷', message: '打开「收案登记」页面，选择案件类别「诉讼」', ms: 960, ok: true, at: '11-03 10:02' },
  { stage: '校验', message: '会话失效，前往登录页重新认证', ms: 4100, ok: false, at: '11-03 10:02' },
  { stage: '重试', message: '第 1 次重试：清理 Cookie 后重新登录成功', ms: 2260, ok: true, at: '11-03 10:02' },
  { stage: '填表', message: '写入案由 / 委托人 / 主办律师（3 项）', ms: 1240, ok: true, at: '11-03 10:03' },
  { stage: '填表', message: '写入标的额 / 收费方式 / 委托人类型（3 项）', ms: 890, ok: true, at: '11-03 10:03' },
  { stage: '关联', message: '关联委托合同 391 与承案团队', ms: 780, ok: true, at: '11-03 10:03' },
  { stage: '上传', message: '上传委托代理合同（扫描件）1 份，2.4 MB', ms: 3120, ok: true, at: '11-03 10:03' },
  { stage: '提交', message: '提交收案登记单，等待 OA 审批流', ms: 1140, ok: true, at: '11-03 10:03' },
  { stage: '轮询', message: '审批流第 1 节点（立案登记）已通过', ms: 4200, ok: true, at: '11-03 10:03' },
  { stage: '回写', message: '取回所内案号 2026-民-XXXX，已落库', ms: 620, ok: true, at: '11-03 10:03' },
  { stage: '收尾', message: '关闭浏览器上下文，会话结束', ms: 180, ok: true, at: '11-03 10:03' },
]

/** OA 立案：站点清单（演示态，真实值来自 /oa-filing/configs） */
/**
 * ⚠️ 这里的站点名**不要**写真实律所名（pre-commit 隐私闸门会拦）。
 * 演示画面里显示什么由 `OAConfig` 接口返回的真实值决定，本常量只在
 * 接口不可用时兜底，所以用中性占位即可。
 */
export const DEMO_OA_SITES: OASiteRow[] = [
  { name: '某某律所 OA', credential: true, lastUsed: '11-03 10:03', filedThisMonth: 42, avgMs: '48 s', loginAt: '11-03 10:02', status: 'ok' },
  { name: '某某律所 OA（备用线路）', credential: true, lastUsed: '11-02 16:41', filedThisMonth: 6, avgMs: '1 m 12 s', loginAt: '11-02 16:40', status: 'ok' },
  { name: '分所 OA（诉讼）', credential: true, lastUsed: '11-01 09:18', filedThisMonth: 11, avgMs: '55 s', loginAt: '11-01 09:17', status: 'ok' },
  { name: '分所 OA（测试）', credential: false, lastUsed: '10-28 15:02', filedThisMonth: 0, avgMs: '—', loginAt: '10-28 15:01', status: 'expired' },
  { name: '某某律所 OA（归档专用）', credential: true, lastUsed: '10-26 11:33', filedThisMonth: 3, avgMs: '37 s', loginAt: '10-26 11:32', status: 'ok' },
]

/** OA 盖章：历史盖章记录（演示态） */
export interface StampLogRow {
  fileName: string
  contract: string
  page: string
  ok: boolean
  at: string
}

export const DEMO_STAMP_LOG: StampLogRow[] = [
  { fileName: '民事起诉状（定稿）.pdf', contract: '某某银行个贷不良批量诉讼', page: '第 3 页', ok: true, at: '11-03 09:40' },
  { fileName: '证据清单及明细.pdf', contract: '某某银行个贷不良批量诉讼', page: '第 12 页', ok: true, at: '11-03 09:42' },
  { fileName: '授权委托书（扫描件）.pdf', contract: '某某银行个贷不良批量诉讼', page: '第 1 页', ok: true, at: '11-03 09:44' },
  { fileName: '送达地址确认书.pdf', contract: '某某银行个贷不良批量诉讼', page: '骑缝', ok: false, at: '11-02 17:20' },
]

/**
 * 要素式转换：样例转换记录（时间倒序，最新在上）。
 *
 * 后端有真实记录时优先用真实值；本列表是接口不可用（或记录为空）时的兜底画面。
 */
export interface ConvertLogRow {
  id: number
  originalName: string
  typeName: string
  at: string
  /** 原文件页数 */
  pages: number
  /** 转换耗时（毫秒） */
  ms: number
  /** 结果：成功 / 失败（原文件格式不支持或后端开关未开） */
  ok: boolean
}

export const DEMO_CONVERT_LOG: ConvertLogRow[] = [
  { id: 15, originalName: '起诉状_谭某某_定稿.docx', typeName: '金融借款起诉状', at: '2026-11-03 10:12', pages: 4, ms: 1840, ok: true },
  { id: 14, originalName: '起诉状_吴某某_定稿.docx', typeName: '金融借款起诉状', at: '2026-11-03 10:08', pages: 4, ms: 2106, ok: true },
  { id: 13, originalName: '起诉状_陈某某.docx', typeName: '信用卡纠纷起诉状', at: '2026-11-03 09:51', pages: 3, ms: 1622, ok: true },
  { id: 12, originalName: '起诉状_某某公司（扫描件）.pdf', typeName: '借款合同纠纷起诉状', at: '2026-11-02 17:26', pages: 6, ms: 0, ok: false },
  { id: 11, originalName: '起诉状_林某某.docx', typeName: '借款合同纠纷起诉状', at: '2026-11-02 16:47', pages: 5, ms: 2380, ok: true },
  { id: 10, originalName: '上诉状_某某贸易公司.docx', typeName: '民事上诉状', at: '2026-11-02 15:03', pages: 7, ms: 2740, ok: true },
  { id: 9, originalName: '起诉状_保证合同_汇总.docx', typeName: '保证合同纠纷起诉状', at: '2026-11-01 16:20', pages: 9, ms: 3215, ok: true },
  { id: 8, originalName: '起诉状_抵押合同_汇总.docx', typeName: '抵押合同纠纷起诉状', at: '2026-11-01 15:08', pages: 8, ms: 2960, ok: true },
  { id: 7, originalName: '起诉状_融资租赁_首期.docx', typeName: '融资租赁合同纠纷起诉状', at: '2026-11-01 11:34', pages: 6, ms: 2210, ok: true },
  { id: 6, originalName: '起诉状_买卖合同_某某公司.docx', typeName: '买卖合同纠纷起诉状', at: '2026-10-31 15:52', pages: 5, ms: 1975, ok: true },
  { id: 5, originalName: '起诉状_模板示例.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:00', pages: 4, ms: 1490, ok: true },
  { id: 4, originalName: '起诉状_吴某某.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:01', pages: 4, ms: 1705, ok: true },
  { id: 3, originalName: '起诉状_谭某某.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:02', pages: 4, ms: 1812, ok: true },
  { id: 2, originalName: '民事起诉状（传统）_修订.docx', typeName: '金融借款起诉状', at: '2026-10-30 12:59', pages: 5, ms: 2050, ok: true },
  { id: 1, originalName: '民事起诉状（传统）.docx', typeName: '金融借款起诉状', at: '2026-10-30 13:00', pages: 5, ms: 1888, ok: true },
]

/** 要素式转换：传统 → 要素式的字段映射（用于展示「转换了什么」） */
export const DEMO_CONVERT_MAPPING = [
  { from: '原告', to: '原告基本信息（要素 1）' },
  { from: '被告', to: '被告基本信息（要素 2）' },
  { from: '诉讼请求', to: '诉讼请求（要素 3）' },
  { from: '事实与理由', to: '事实与理由（要素 4）' },
  { from: '证据清单', to: '证据（要素 5）' },
  { from: '管辖法院', to: '受诉法院（要素 6）' },
]

/* ══════════════════════════════════════════════════════════════════
 * OA 立案（`OAFilingPanel`）专用演示数据
 * —— 新组件在 `components/oa/` 下，只读这里的常量，不做任何业务判断。
 * ══════════════════════════════════════════════════════════════════ */

/** OA 站点清单行（DEMO_OA_SITES 的类型） */
export interface OASiteRow {
  name: string
  credential: boolean
  /** 最近一次立案时间 */
  lastUsed: string
  /** 本月立案件数 */
  filedThisMonth: number
  /** 平均单件耗时（人读量级） */
  avgMs: string
  /** 最近一次登录成功时间 */
  loginAt: string
  /** 凭证体检结果：正常 / 凭证过期 */
  status: 'ok' | 'expired'
}

/** OA 立案：历史立案记录（演示态，时间倒序） */
export interface OAFilingHistoryRow {
  caseNo: string
  client: string
  amount: string
  oaCaseNo: string
  state: 'filed' | 'pending' | 'returned'
  cost: string
  at: string
}

export const DEMO_OA_HISTORY: OAFilingHistoryRow[] = [
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥998,670.21', oaCaseNo: 'OA-2026-0418', state: 'filed', cost: '48 s', at: '11-03 10:03' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥642,300.00', oaCaseNo: 'OA-2026-0417', state: 'filed', cost: '51 s', at: '11-03 09:26' },
  { caseNo: '2026-民-XXXX', client: '某某小额贷款公司', amount: '¥331,880.40', oaCaseNo: 'OA-2026-0415', state: 'pending', cost: '—', at: '11-02 17:52' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥1,204,512.00', oaCaseNo: 'OA-2026-0412', state: 'filed', cost: '1 m 12 s', at: '11-02 16:41' },
  { caseNo: '2026-民-XXXX', client: '某某融资担保公司', amount: '¥86,400.00', oaCaseNo: '—', state: 'returned', cost: '2 m 04 s', at: '11-02 14:03' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥475,020.75', oaCaseNo: 'OA-2026-0408', state: 'filed', cost: '44 s', at: '11-01 15:10' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥738,900.00', oaCaseNo: 'OA-2026-0406', state: 'filed', cost: '55 s', at: '11-01 09:18' },
  { caseNo: '2026-民-XXXX', client: '某某资产管理公司', amount: '¥2,015,600.00', oaCaseNo: 'OA-2026-0402', state: 'filed', cost: '1 m 26 s', at: '10-31 16:44' },
  { caseNo: '2026-民-XXXX', client: '某某小额贷款公司', amount: '¥59,800.00', oaCaseNo: 'OA-2026-0399', state: 'filed', cost: '39 s', at: '10-31 11:07' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥512,340.66', oaCaseNo: '—', state: 'returned', cost: '1 m 48 s', at: '10-30 18:12' },
  { caseNo: '2026-民-XXXX', client: '某某融资担保公司', amount: '¥298,000.00', oaCaseNo: 'OA-2026-0391', state: 'filed', cost: '47 s', at: '10-30 10:35' },
  { caseNo: '2026-民-XXXX', client: '某某银行某某支行', amount: '¥1,680,000.00', oaCaseNo: 'OA-2026-0386', state: 'filed', cost: '1 m 03 s', at: '10-29 14:20' },
]

/** OA 立案：法穿字段 → OA 收案登记字段映射（演示态） */
export interface OAFieldMappingRow {
  from: string
  to: string
  /** 取值来源：案件数据 / 委托合同 / 系统推断 / 手工补录 */
  source: 'case' | 'contract' | 'infer' | 'manual'
}

export const DEMO_OA_FIELD_MAPPING: OAFieldMappingRow[] = [
  { from: '案由', to: '案件类别 / 案由', source: 'case' },
  { from: '委托人', to: '委托人名称', source: 'contract' },
  { from: '委托人类型', to: '委托人身份（法人/自然人）', source: 'infer' },
  { from: '主办律师', to: '承办律师', source: 'case' },
  { from: '承案团队', to: '承办部门', source: 'infer' },
  { from: '标的额', to: '争议标的金额', source: 'case' },
  { from: '收费方式', to: '收费方式（计时/计件/风险）', source: 'contract' },
  { from: '合同编号', to: '关联委托合同号', source: 'contract' },
  { from: '管辖法院', to: '受理机关', source: 'case' },
  { from: '对方当事人', to: '对方当事人名称', source: 'case' },
  { from: '收案日期', to: '收案日期', source: 'infer' },
  { from: '所内案号', to: 'OA 案号（执行后回填）', source: 'manual' },
]

/** OA 立案：常见失败原因与处理建议（演示态） */
export interface OAFailureCause {
  cause: string
  /** 触发位置：登录 / 填表 / 提交 / 轮询 */
  stage: string
  /** 最近 30 天出现次数 */
  hits: number
  advice: string
  /** 是否可由系统自动重试 */
  autoRetry: boolean
}

export const DEMO_OA_FAILURE_CAUSES: OAFailureCause[] = [
  {
    cause: '凭证过期',
    stage: '登录',
    hits: 3,
    advice: '到「设置 → OA 站点」重新录入密码；系统会自动重试 1 次，仍失败需人工更新。',
    autoRetry: true,
  },
  {
    cause: '页面改版',
    stage: '填表',
    hits: 2,
    advice: 'OA 表单字段顺序变了，选择器失配。联系管理员更新站点适配脚本，不要反复重试。',
    autoRetry: false,
  },
  {
    cause: '验证码拦截',
    stage: '登录',
    hits: 1,
    advice: '连续登录触发图形验证码。等待 10 分钟后重试，或改走备用线路站点。',
    autoRetry: true,
  },
  {
    cause: '字段校验不通过',
    stage: '提交',
    hits: 4,
    advice: '多为标的额与受理机关为空。到「起诉条件」补齐后重新发起，源数据缺项重试无效。',
    autoRetry: false,
  },
  {
    cause: 'OA 审批流卡住',
    stage: '轮询',
    hits: 2,
    advice: '收案登记单已提交但审批未流转。到 OA 里手动催办，法穿不再重复提交。',
    autoRetry: false,
  },
  {
    cause: '附件上传超时',
    stage: '上传',
    hits: 1,
    advice: '扫描件超过 20 MB 时容易超时。压缩后重试，或先在 OA 里手工上传再回落单号。',
    autoRetry: true,
  },
]

// ═══════════════════════════════════════════════════════════════════════
// 一张网立案（CourtFilingPanel）演示数据 —— 前缀 DEMO_COURT_*
// ═══════════════════════════════════════════════════════════════════════

/**
 * 字段映射：法穿字段 → 一张网表单字段。
 *
 * 视频原型里的核心画面。真实系统里这张表是**动态生成**的（后端按法院
 * 表单定义 + 案件数据算出来），这里用常量复刻同样的形状：
 * 每一行都能回答「这个值是从哪来的、填到法院哪个格子」。
 */
export interface CourtFieldMappingRow {
  /** 法穿侧字段名 */
  from: string
  /** 一张网表单字段名 */
  to: string
  /** 本次要填进去的值（已按法院口径格式化） */
  value: string
  /** mapped=自动填好；confirm=机器拿不准，要律师看一眼 */
  status: 'mapped' | 'confirm'
  /** confirm 状态下说明为什么要人看 */
  note?: string
}

export const DEMO_COURT_FIELD_MAPPING: CourtFieldMappingRow[] = [
  { from: '案件名称', to: '案件名称', value: '某某银行广州分行诉谭某某金融借款合同纠纷', status: 'mapped' },
  { from: '案由', to: '案由（三级）', value: '金融借款合同纠纷', status: 'mapped' },
  { from: '原告名称', to: '原告（全称）', value: '某某银行广州分行', status: 'mapped' },
  { from: '原告类型', to: '原告主体类型', value: '法人 / 其他组织', status: 'mapped' },
  { from: '统一社会信用代码', to: '原告证件号码', value: '9144XX XXXX XXXX XXXX', status: 'confirm', note: '营业执照扫描件与案件登记值末两位不一致，建议核对原件' },
  { from: '被告名称', to: '被告（姓名）', value: '谭某某', status: 'mapped' },
  { from: '被告身份证号', to: '被告证件号码', value: '4401XX XXXX XXXX XXXX', status: 'mapped' },
  { from: '被告送达地址', to: '被告送达地址', value: '广州市天河区某某街道某某路 X 号', status: 'confirm', note: '合同约定地址与户籍地址不同，需确认以哪一个送达' },
  { from: '标的额', to: '诉讼标的额（元）', value: '998,670.21', status: 'confirm', note: '与起诉状标的额差 31.85 元，见下方三处金额校验' },
  { from: '诉讼请求（本金）', to: '请求事项·本金', value: '820,000.00', status: 'mapped' },
  { from: '诉讼请求（利息）', to: '请求事项·利息', value: '178,670.21', status: 'mapped' },
  { from: '管辖法院', to: '受诉法院', value: '广州市天河区人民法院', status: 'mapped' },
  { from: '立案类型', to: '案件类别', value: '民事一审', status: 'mapped' },
  { from: '承办律师', to: '代理人姓名', value: '黄某某', status: 'mapped' },
]

/**
 * 三处金额校验：同一笔钱在三个地方各写了一次，机器对不齐就必须停下来。
 *
 * 这是视频原型反复强调的一点 —— 立案被退回最多的原因就是标的额不一致，
 * 而律师手工改一处的概率极高。三列并排，差异标红，比一句提示有用得多。
 */
export interface CourtAmountCheckRow {
  item: string
  /** 起诉状（要素式文书）上的数 */
  fromPleading: string
  /** 一张网立案表单里填的数 */
  fromCourtForm: string
  /** 要素式结构化字段里的数 */
  fromElement: string
  /** 三处是否一致 */
  ok: boolean
  /** 差异说明（ok=false 时必填） */
  diff?: string
}

export const DEMO_COURT_AMOUNT_CHECK: CourtAmountCheckRow[] = [
  { item: '本金', fromPleading: '820,000.00', fromCourtForm: '820,000.00', fromElement: '820,000.00', ok: true },
  { item: '利息', fromPleading: '178,638.36', fromCourtForm: '178,670.21', fromElement: '178,638.36', ok: false, diff: '立案表单标的额被人工改动，差 31.85 元' },
  { item: '罚息', fromPleading: '0.00', fromCourtForm: '0.00', fromElement: '0.00', ok: true },
  { item: '复利', fromPleading: '0.00', fromCourtForm: '0.00', fromElement: '0.00', ok: true },
  { item: '诉讼费（预交）', fromPleading: '13,786.00', fromCourtForm: '13,786.00', fromElement: '13,786.00', ok: true },
  { item: '合计', fromPleading: '998,638.36', fromCourtForm: '998,670.21', fromElement: '998,638.36', ok: false, diff: '合计随利息一并偏差 31.85 元，递交前须回到起诉状口径' },
]

/**
 * 历史递交记录（时间倒序）。同一案号可能递交多次
 * —— 被退回、补正、换法院重交，都会留下新的一条。
 */
export interface CourtSubmitHistoryRow {
  id: string
  at: string
  /** 批次号：一次递交一个批次，重试会新开批次 */
  batch: string
  filingNumber: string
  result: 'accepted' | 'returned' | 'failed' | 'pending'
  /** 法院受理号 / 退回单号 */
  receipt: string
}

export const DEMO_COURT_SUBMIT_HISTORY: CourtSubmitHistoryRow[] = [
  { id: 'cs_1', at: '2026-11-03 10:03', batch: 'B-20261103-0031', filingNumber: '（20XX）粤0106民初XXXX号', result: 'accepted', receipt: 'TH20261103008812' },
  { id: 'cs_2', at: '2026-11-02 17:26', batch: 'B-20261102-0047', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261102001465' },
  { id: 'cs_3', at: '2026-11-02 15:08', batch: 'B-20261102-0042', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_4', at: '2026-11-01 16:41', batch: 'B-20261101-0038', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261101000932' },
  { id: 'cs_5', at: '2026-10-30 11:19', batch: 'B-20261030-0026', filingNumber: '（20XX）粤0106民初XXXX号', result: 'accepted', receipt: 'TH20261030005117' },
  { id: 'cs_6', at: '2026-10-29 15:54', batch: 'B-20261029-0022', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_7', at: '2026-10-29 09:33', batch: 'B-20261029-0019', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261029000671' },
  { id: 'cs_8', at: '2026-10-28 14:07', batch: 'B-20261028-0015', filingNumber: '（20XX）粤0106民初XXXX号', result: 'pending', receipt: '待法院处理' },
  { id: 'cs_9', at: '2026-10-27 10:22', batch: 'B-20261027-0011', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_10', at: '2026-10-26 16:48', batch: 'B-20261026-0008', filingNumber: '（20XX）粤0106民初XXXX号', result: 'returned', receipt: 'CT20261026000418' },
  { id: 'cs_11', at: '2026-10-26 09:15', batch: 'B-20261026-0004', filingNumber: '（20XX）粤0106民初XXXX号', result: 'failed', receipt: '—' },
  { id: 'cs_12', at: '2026-10-24 11:02', batch: 'B-20261024-0003', filingNumber: '（20XX）粤0106民初XXXX号', result: 'accepted', receipt: 'TH20261024002233' },
]

/** 随案材料：递交时要一并上传的套件 */
export interface CourtMaterialRow {
  id: string
  name: string
  /** 页数 */
  pages: number
  /** 盖章状态 */
  stamp: 'stamped' | 'partial' | 'none'
  /** 上传时间（未上传为空） */
  uploadedAt: string | null
}

export const DEMO_COURT_MATERIALS: CourtMaterialRow[] = [
  { id: 'cm_1', name: '民事起诉状（要素式）.pdf', pages: 4, stamp: 'stamped', uploadedAt: '11-03 09:40' },
  { id: 'cm_2', name: '证据目录及证据材料.pdf', pages: 46, stamp: 'stamped', uploadedAt: '11-03 09:42' },
  { id: 'cm_3', name: '当事人身份证明材料.pdf', pages: 6, stamp: 'stamped', uploadedAt: '11-03 09:43' },
  { id: 'cm_4', name: '授权委托书（含代理人证）.pdf', pages: 3, stamp: 'stamped', uploadedAt: '11-03 09:44' },
  { id: 'cm_5', name: '律师事务所函.pdf', pages: 1, stamp: 'stamped', uploadedAt: '11-03 09:44' },
  { id: 'cm_6', name: '送达地址确认书.pdf', pages: 1, stamp: 'partial', uploadedAt: '11-03 09:45' },
  { id: 'cm_7', name: '借款合同及借据.pdf', pages: 12, stamp: 'stamped', uploadedAt: '11-03 09:46' },
  { id: 'cm_8', name: '放款凭证与还款明细.pdf', pages: 18, stamp: 'none', uploadedAt: '11-03 09:47' },
  { id: 'cm_9', name: '催收记录（含公告）.pdf', pages: 9, stamp: 'none', uploadedAt: null },
  { id: 'cm_10', name: '诉讼费预交凭证.pdf', pages: 1, stamp: 'none', uploadedAt: null },
]

/**
 * 法院平台信息：立案庭的联系方式与须知要点。
 *
 * 这些值真实系统里来自法院配置；演示态写成常量。
 * 电话用号段占位（不带真实坐席号码），地址到街道级即止。
 */
export const DEMO_COURT_PLATFORM = {
  courtName: '广州市天河区人民法院',
  courtCode: '440106',
  filingChamber: '立案庭（民商事立案窗口）',
  phone: '020-XXXX XXXX',
  workTime: '工作日 08:30–12:00 / 14:00–17:30',
  onlineChannel: '广东法院诉讼服务网 · 网上立案',
  address: '广州市天河区某某街道某某大道 X 号',
  notices: [
    '网上立案后 3 个工作日内答复，退回补正的需在 7 日内重新递交，逾期视为撤回。',
    '起诉状须使用要素式文本并加盖公章，落款日期与递交日期一致。',
    '证据材料按 PDF 上传，单份不超过 50 MB，扫描分辨率不低于 200 dpi。',
    '送达地址确认书须由当事人本人或法定代表人签章，代理人代签需另附授权。',
    '同一原告同批次案件的诉讼费可合并预交，但每案须单独附缴费凭证。',
  ],
} as const

/**
 * 校验规则口径：三处校验各自在比什么、不一致会怎样。
 *
 * 律师最怕的是「系统拦了但不说为什么」。把口径写在界面上，
 * 客户问起来他能直接照着解释。
 */
export interface CourtCheckRuleRow {
  id: 'amount' | 'party' | 'jurisdiction'
  title: string
  /** 比对的字段 */
  fields: string
  /** 判定口径 */
  rule: string
  /** 不一致时的处理 */
  onFail: 'block' | 'warn'
}

export const DEMO_COURT_CHECK_RULES: CourtCheckRuleRow[] = [
  {
    id: 'amount',
    title: '金额校验',
    fields: '起诉状标的额 ↔ 一张网表单标的额 ↔ 要素式字段',
    rule: '三处逐项比对（本金 / 利息 / 罚息 / 复利 / 合计），允许误差 0.00 元；任一项不一致即阻断递交。',
    onFail: 'block',
  },
  {
    id: 'party',
    title: '当事人校验',
    fields: '原告 / 被告名称与证件号 ↔ 身份证明材料',
    rule: '名称须与营业执照/身份证 OCR 结果完全一致；法人须校验统一社会信用代码，自然人须校验身份证号。',
    onFail: 'warn',
  },
  {
    id: 'jurisdiction',
    title: '管辖校验',
    fields: '被告住所地 / 合同履行地 ↔ 受诉法院',
    rule: '按合同约定管辖优先；无约定时取被告住所地或合同履行地基层法院。级别管辖按标的额定位。',
    onFail: 'warn',
  },
]

// ═══════════════════════════════════════════════════════════════════
// 要素式转换 · 演示数据（前缀 DEMO_CONVERT_*）
//
// 这一页的演示要回答律师三个问题：我该用哪个文书类型、转换到底改了哪几处、
// 转完的东西长什么样。下面的常量分别对应这三问：
//   文书类型库 → 选哪个（并给出本月用量，说明哪个是主力）
//   字段映射   → 改了哪几处（含必填与示例值，让人能对照自己的起诉状）
//   前后对比   → 长什么样（左传统、右要素式，同一段事实两种写法）
// ═══════════════════════════════════════════════════════════════════

/** 要素式转换：文书类型库（覆盖 15 条转换记录里出现的全部类型 + 常用预备类型） */
export interface ConvertTemplateRow {
  /** 法院文书类型编号（mbid），下拉框里的值就是它 */
  mbid: string
  name: string
  /** 适用的案由 */
  cause: string
  /** 模板版本：法院示范文本改版后旧版本生成的文件会被标「待重转」 */
  version: string
  /** 本月转换次数（展示用，说明哪类文书是主力） */
  monthly: number
}

/** 按本月用量倒序：主力类型排前面，律师一眼看到自己最常用的那条 */
export const DEMO_CONVERT_TEMPLATES: ConvertTemplateRow[] = [
  { mbid: 'MBID-FL-0102', name: '金融借款合同纠纷起诉状', cause: '金融借款合同纠纷', version: 'v2026.1', monthly: 38 },
  { mbid: 'MBID-LOAN-0211', name: '借款合同纠纷起诉状', cause: '民间借贷纠纷', version: 'v2026.1', monthly: 21 },
  { mbid: 'MBID-CT-0308', name: '信用卡纠纷起诉状', cause: '信用卡纠纷', version: 'v2026.1', monthly: 17 },
  { mbid: 'MBID-GUAR-0405', name: '保证合同纠纷起诉状', cause: '保证合同纠纷', version: 'v2025.2', monthly: 9 },
  { mbid: 'MBID-MORT-0412', name: '抵押合同纠纷起诉状', cause: '抵押合同纠纷', version: 'v2026.1', monthly: 7 },
  { mbid: 'MBID-LEASE-0513', name: '融资租赁合同纠纷起诉状', cause: '融资租赁合同纠纷', version: 'v2026.1', monthly: 6 },
  { mbid: 'MBID-LABOR-0620', name: '劳动争议起诉状', cause: '劳动争议', version: 'v2025.3', monthly: 4 },
  { mbid: 'MBID-CON-0715', name: '买卖合同纠纷起诉状', cause: '买卖合同纠纷', version: 'v2026.1', monthly: 3 },
  { mbid: 'MBID-TORT-0801', name: '机动车交通事故责任纠纷起诉状', cause: '机动车交通事故责任纠纷', version: 'v2026.1', monthly: 2 },
  { mbid: 'MBID-DIV-0907', name: '离婚纠纷起诉状', cause: '离婚纠纷', version: 'v2025.2', monthly: 2 },
  { mbid: 'MBID-APL-1003', name: '民事上诉状', cause: '通用（二审）', version: 'v2026.1', monthly: 2 },
  { mbid: 'MBID-ANS-1009', name: '民事答辩状', cause: '通用（应诉）', version: 'v2026.1', monthly: 1 },
]

/**
 * 要素式转换：传统 → 要素式的字段映射。
 *
 * 比早先多了「是否必填」与「示例值」两列：律师拿自己的起诉状对照时，
 * 最常问的是「我这份里没写到调解意愿，会不会被打回」。必填列回答这个。
 * 示例值一律用脱敏后的真实口径（案号 XXXX、地名某某区、金额千分位）。
 */
export interface ConvertMappingRow {
  /** 要素式文书里的栏位名 */
  from: string
  /** 该栏位在传统起诉状里对应的内容 */
  to: string
  /** 缺了会被法院退回（一张网立案的前置校验） */
  required: boolean
  /** 示例值（脱敏） */
  sample: string
}

export const DEMO_CONVERT_MAPPING_DETAIL: ConvertMappingRow[] = [
  { from: '原告', to: '原告基本信息', required: true, sample: '某某银行广州分行' },
  { from: '被告', to: '被告基本信息', required: true, sample: '谭某某，男，19XX 年生' },
  { from: '诉讼请求', to: '诉讼请求（分项列明）', required: true, sample: '本金 ¥998,670.21 及利息' },
  { from: '事实与理由', to: '事实与理由（按要素分段）', required: true, sample: '20XX 年 XX 月放款 XX 万元' },
  { from: '证据清单', to: '证据（逐份对应事实）', required: true, sample: '借款合同 P1–12、放款凭证 P13' },
  { from: '管辖法院', to: '受诉法院', required: true, sample: '广州市天河区人民法院' },
  { from: '利息计算', to: '利息计算方式与截止日', required: true, sample: '按 LPR 上浮 50%，计至清偿日' },
  { from: '担保情况', to: '担保物权与保证人', required: false, sample: '房产抵押 + 某某公司连带保证' },
  { from: '送达地址', to: '送达地址确认', required: true, sample: '佛山市顺德区某某街道 XX 号' },
  { from: '调解意愿', to: '是否同意调解', required: false, sample: '同意调解' },
  { from: '诉讼费承担', to: '诉讼费用负担请求', required: false, sample: '由被告承担' },
  { from: '附件目录', to: '随附材料清单', required: false, sample: '起诉状副本 2 份、证据 3 组' },
]

/** 要素式转换：同一段事实在传统起诉状与要素式文本里的写法对比（预览用） */
export interface ConvertPreviewField {
  label: string
  /** 传统起诉状里的写法（整段叙述） */
  legacy: string
  /** 要素式示范文本里的写法（拆成栏位） */
  elemental: string
  /** 传统写法里是否有对应表述；没有 = 要素式新增的栏位 */
  matched: boolean
}

export const DEMO_CONVERT_PREVIEW: ConvertPreviewField[] = [
  {
    label: '当事人',
    legacy: '原告某某银行广州分行，住所地佛山市顺德区某某街道。负责人黄某某，行长。被告谭某某，男，19XX 年 XX 月 XX 日出生，住佛山市顺德区某某街道。',
    elemental: '原告：某某银行广州分行（统一社会信用代码 91XXXXXXXXXXXXXXXX）\n被告：谭某某（身份证号已脱敏）',
    matched: true,
  },
  {
    label: '诉讼请求',
    legacy: '请求判令被告偿还借款本金 998,670.21 元及相应利息、罚息，并承担本案诉讼费用。',
    elemental: '1. 偿还本金 ¥998,670.21\n2. 支付利息（按 LPR 上浮 50%，自 20XX-XX-XX 计至清偿日）\n3. 诉讼费由被告承担',
    matched: true,
  },
  {
    label: '事实与理由',
    legacy: '20XX 年 XX 月 XX 日，被告与原告签订《个人借款合同》，借款 1,000,000.00 元，期限 36 个月。原告依约放款，被告自 20XX 年 XX 月起未按约还款，至起诉日尚欠本金 998,670.21 元。',
    elemental: '合同签订日：20XX-XX-XX\n放款金额：¥1,000,000.00\n违约起始：20XX-XX\n尚欠本金：¥998,670.21',
    matched: true,
  },
  {
    label: '证据',
    legacy: '证据一《个人借款合同》、证据二放款凭证、证据三还款明细，以上证据证明借款关系成立及被告违约事实。',
    elemental: '证据 1《个人借款合同》P1–12\n证据 2 放款凭证 P13\n证据 3 还款明细 P14–16',
    matched: true,
  },
  {
    label: '利息计算方式',
    legacy: '（传统起诉状通常只写「及相应利息」，具体算法在庭审中主张）',
    elemental: '按 LPR 上浮 50%，自 20XX-XX-XX 计至实际清偿日，暂计至起诉日 ¥86,412.55',
    matched: false,
  },
  {
    label: '是否同意调解',
    legacy: '（传统起诉状无此栏位）',
    elemental: '同意调解。可接受分期，首期不低于 30%。',
    matched: false,
  },
]

/** 要素式转换：本月转换量统计（展示用；真实值应来自后端转换记录聚合） */
export interface ConvertStatSummary {
  /** 累计转换次数 */
  total: number
  /** 本月转换次数 */
  monthly: number
  /** 平均单份耗时（毫秒） */
  avgMs: number
  /** 失败率（百分比，含 403 开关未开、原文件格式不支持） */
  failRate: number
  /** 本月失败次数（与 failRate 对得上，避免两个数字打架） */
  failed: number
}

export const DEMO_CONVERT_STATS: ConvertStatSummary = {
  total: 1584,
  monthly: 112,
  avgMs: 1840,
  failRate: 2.7,
  failed: 3,
}

/**
 * OA 归档：归档操作日志（演示态，时间倒序）。
 *
 * 归档这一步真正的风险不是「漏传」，而是「传了但传错目录」——
 * 所以动作列区分生成文件夹 / 上传 / 删除，结果列写明成功与否与原因。
 */
export interface ArchiveLogRow {
  at: string
  /** 动作：生成文件夹 / 上传材料 / 删除多余文件 / 同步案件材料 */
  action: string
  /** 涉及的文件或目录 */
  target: string
  by: string
  ok: boolean
  /** 失败原因（成功时为「—」） */
  note: string
}

export const DEMO_ARCHIVE_LOG: ArchiveLogRow[] = [
  { at: '11-03 10:41', action: '生成文件夹', target: '结案归档/某某银行个贷不良批量诉讼', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:42', action: '上传材料', target: '案卷封面.pdf（1 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:42', action: '上传材料', target: '结案归档登记表.pdf（2 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:44', action: '上传材料', target: '民事起诉状（定稿）.pdf（4 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:45', action: '上传材料', target: '（20XX）粤0106民初XXXX号 民事判决书.pdf（7 页）', by: '黄某某', ok: true, note: '—' },
  { at: '11-03 10:46', action: '删除多余文件', target: '办案工作日记_草稿.pdf', by: '黄某某', ok: true, note: '草稿不入卷' },
  { at: '11-02 17:12', action: '同步案件材料', target: '案件材料 → 归档目录（9 份）', by: '房某某', ok: false, note: '有 1 份为低置信度分段，需先复核' },
  { at: '11-02 16:58', action: '上传材料', target: '办案服务质量监督卡.pdf（1 页）', by: '房某某', ok: true, note: '—' },
  { at: '11-01 15:20', action: '生成文件夹', target: '结案归档/某某银行信用卡批量诉讼', by: '黄某某', ok: false, note: '必需项缺 2 项，生成被拦' },
  { at: '11-01 09:34', action: '上传材料', target: '授权委托书（扫描件）.pdf（2 页）', by: '房某某', ok: true, note: '—' },
]

/** OA 归档：归档类别对比（三类清单项数与必备项差异，说明「类别不同清单不同」） */
export interface ArchiveCategoryRow {
  /** 归档类别 */
  category: string
  /** 检查清单项数（执业规范口径） */
  items: number
  /** 其中必需项 */
  required: number
  /** 本所该类已归档卷数（近一年） */
  archived: number
  /** 该类特有材料（一句话，展示用） */
  only: string
}

export const DEMO_ARCHIVE_CATEGORIES: ArchiveCategoryRow[] = [
  { category: '诉讼', items: 20, required: 11, archived: 128, only: '判决书 / 庭审笔录 / 代理词' },
  { category: '非诉', items: 12, required: 7, archived: 64, only: '尽职调查报告 / 法律意见书' },
  { category: '刑事', items: 18, required: 10, archived: 23, only: '会见笔录 / 阅卷笔录 / 辩护词' },
]

/** OA 归档：材料明细（页数 / 上传时间 / 来源文件），按材料代码索引 */
export interface ArchiveMaterialMeta {
  /** 材料页数（多份合并时为总页数） */
  pages: number
  /** 上传或生成时间 */
  at: string
  /** 来源文件名（合同文件夹 / 案件材料里的原名） */
  source: string
}

export const DEMO_ARCHIVE_MATERIALS: Record<string, ArchiveMaterialMeta> = {
  lt_1: { pages: 1, at: '11-03 10:42', source: '案卷封面_模板_2026.docx' },
  lt_2: { pages: 2, at: '11-03 10:42', source: '结案归档登记表_模板_2026.docx' },
  lt_3: { pages: 3, at: '11-03 10:43', source: '案卷目录_生成.pdf' },
  lt_4: { pages: 12, at: '10-21 14:08', source: '委托代理合同_签署版.pdf' },
  lt_5: { pages: 2, at: '10-21 14:09', source: '律师费发票_扫描.pdf' },
  lt_6: { pages: 9, at: '11-02 17:35', source: '律师办案工作日记_汇总.pdf' },
  lt_7: { pages: 4, at: '10-30 15:12', source: '民事起诉状（定稿）.docx' },
  lt_8: { pages: 6, at: '10-28 10:22', source: '阅卷笔录_扫描.pdf' },
  lt_9: { pages: 5, at: '10-27 16:40', source: '会见笔录_谭某某.pdf' },
  lt_10: { pages: 18, at: '10-29 11:25', source: '调查材料_银行流水.pdf' },
  lt_11: { pages: 11, at: '10-25 09:18', source: '诉讼保全申请书及裁定书.pdf' },
  lt_12: { pages: 3, at: '11-02 11:05', source: '代理意见_一审.pdf' },
  lt_13: { pages: 2, at: '10-26 14:30', source: '集体讨论记录_2026Q3.pdf' },
  lt_14: { pages: 1, at: '10-22 09:44', source: '出庭通知书_扫描.pdf' },
  lt_15: { pages: 7, at: '11-01 16:40', source: '代理词_一审.pdf' },
  lt_16: { pages: 24, at: '11-01 16:42', source: '庭审笔录_扫描.pdf' },
  lt_17: { pages: 7, at: '11-03 10:45', source: '（20XX）粤0106民初XXXX号 民事判决书.pdf' },
  lt_18: { pages: 1, at: '11-02 16:58', source: '办案服务质量监督卡_模板.pdf' },
  lt_19: { pages: 2, at: '11-02 17:02', source: '办案小结_定稿.docx' },
  lt_20: { pages: 2, at: '11-01 09:34', source: '授权委托书（扫描件）.pdf' },
}

// ═══════════════════════════════════════════════════════════════════
// 整包分段（DEMO_BUNDLE_*）—— 组件：components/bundle/*
// 覆盖 idle 态的画面：历史拆分记录 / 每包明细 / 识别能力计数 /
// 拆分规则 / 常见问题。全部为演示数据，不参与任何判断逻辑。
// ═══════════════════════════════════════════════════════════════════

/** 整包分段：拆分记录（扩展版，45 天内的全部拆分，时间倒序） */
export interface BundleSplitRecord {
  id: string
  fileName: string
  causeOfAction: '金融借款合同纠纷' | '买卖合同纠纷' | '民间借贷纠纷'
  pages: number
  materials: number
  /** 按页内容识别 / 按分隔页识别 */
  mode: 'content' | 'separator'
  result: 'confirmed' | 'review' | 'unrecognized'
  imported: number
  /** 需复核 + 未识别的段数 */
  flagged: number
  /** 整包体积（MB）与识别耗时 */
  sizeMb: number
  elapsed: string
  at: string
  by: string
}

export const DEMO_BUNDLE_SPLIT_RECORDS: BundleSplitRecord[] = [
  { id: 'bsp_01', fileName: '某某银行个贷不良_首批扫描件.pdf', causeOfAction: '金融借款合同纠纷', pages: 278, materials: 84, mode: 'content', result: 'confirmed', imported: 84, flagged: 0, sizeMb: 46.2, elapsed: '6 m 12 s', at: '11-03 09:12', by: '黄某某' },
  { id: 'bsp_02', fileName: '买卖合同_送货单与对账单.pdf', causeOfAction: '买卖合同纠纷', pages: 64, materials: 19, mode: 'content', result: 'review', imported: 18, flagged: 2, sizeMb: 11.8, elapsed: '1 m 48 s', at: '11-02 17:26', by: '房某某' },
  { id: 'bsp_03', fileName: '诉讼盖章_全套扫描_补寄.pdf', causeOfAction: '金融借款合同纠纷', pages: 46, materials: 12, mode: 'content', result: 'review', imported: 12, flagged: 1, sizeMb: 8.4, elapsed: '1 m 22 s', at: '11-01 16:40', by: '黄某某' },
  { id: 'bsp_04', fileName: '民间借贷_借条与转账凭证.pdf', causeOfAction: '民间借贷纠纷', pages: 22, materials: 7, mode: 'content', result: 'confirmed', imported: 7, flagged: 0, sizeMb: 3.9, elapsed: '42 s', at: '10-31 15:08', by: '谭某某' },
  { id: 'bsp_05', fileName: '借款合同及借据_扫描.pdf', causeOfAction: '金融借款合同纠纷', pages: 120, materials: 36, mode: 'content', result: 'confirmed', imported: 36, flagged: 0, sizeMb: 21.6, elapsed: '2 m 54 s', at: '10-29 11:25', by: '房某某' },
  { id: 'bsp_06', fileName: '催收档案_2026Q3.pdf', causeOfAction: '金融借款合同纠纷', pages: 30, materials: 10, mode: 'content', result: 'unrecognized', imported: 0, flagged: 6, sizeMb: 5.1, elapsed: '58 s', at: '10-28 09:05', by: '黄某某' },
  { id: 'bsp_07', fileName: '买卖货物_出库单整包（分隔页扫描）.pdf', causeOfAction: '买卖合同纠纷', pages: 188, materials: 47, mode: 'separator', result: 'confirmed', imported: 47, flagged: 0, sizeMb: 33.7, elapsed: '3 m 06 s', at: '10-27 16:52', by: '谭某某' },
  { id: 'bsp_08', fileName: '当事人身份材料_扫描.pdf', causeOfAction: '金融借款合同纠纷', pages: 18, materials: 6, mode: 'content', result: 'confirmed', imported: 6, flagged: 0, sizeMb: 2.8, elapsed: '36 s', at: '10-26 14:30', by: '房某某' },
  { id: 'bsp_09', fileName: '民间借贷_微信聊天记录截屏.pdf', causeOfAction: '民间借贷纠纷', pages: 14, materials: 5, mode: 'content', result: 'review', imported: 4, flagged: 3, sizeMb: 6.2, elapsed: '48 s', at: '10-24 10:14', by: '黄某某' },
  { id: 'bsp_10', fileName: '担保与抵押登记材料.pdf', causeOfAction: '金融借款合同纠纷', pages: 52, materials: 15, mode: 'content', result: 'confirmed', imported: 15, flagged: 0, sizeMb: 9.6, elapsed: '1 m 34 s', at: '10-22 15:47', by: '谭某某' },
  { id: 'bsp_11', fileName: '买卖合同_发票与签收单（补寄）.pdf', causeOfAction: '买卖合同纠纷', pages: 27, materials: 9, mode: 'separator', result: 'confirmed', imported: 9, flagged: 0, sizeMb: 4.4, elapsed: '51 s', at: '10-20 11:03', by: '房某某' },
  { id: 'bsp_12', fileName: '借款人征信与流水整包.pdf', causeOfAction: '金融借款合同纠纷', pages: 96, materials: 28, mode: 'content', result: 'review', imported: 26, flagged: 4, sizeMb: 17.9, elapsed: '2 m 18 s', at: '10-17 09:38', by: '黄某某' },
  { id: 'bsp_13', fileName: '民间借贷_判决书与上诉状（二审包）.pdf', causeOfAction: '民间借贷纠纷', pages: 41, materials: 11, mode: 'content', result: 'unrecognized', imported: 0, flagged: 5, sizeMb: 7.3, elapsed: '1 m 06 s', at: '10-15 17:21', by: '谭某某' },
  { id: 'bsp_14', fileName: '某某银行对公不良_第二批扫描件.pdf', causeOfAction: '金融借款合同纠纷', pages: 312, materials: 93, mode: 'content', result: 'confirmed', imported: 93, flagged: 0, sizeMb: 52.4, elapsed: '7 m 03 s', at: '10-12 10:26', by: '房某某' },
  { id: 'bsp_15', fileName: '买卖合同_质量异议往来函件.pdf', causeOfAction: '买卖合同纠纷', pages: 33, materials: 12, mode: 'content', result: 'confirmed', imported: 12, flagged: 0, sizeMb: 5.8, elapsed: '59 s', at: '10-09 14:05', by: '黄某某' },
]

/** 整包分段：某一包的拆分明细（复核表用的演示快照，页码连续、时间倒序） */
export interface BundleSegmentDetail {
  order: number
  pageStart: number
  pageEnd: number
  label: string
  filename: string
  confidence: number
  flag: 'ok' | 'low_confidence' | 'unrecognized'
  /** 依据：页眉标题 / 正文首段 / 去分隔页 / 版式连续 */
  evidence: string
}

export const DEMO_BUNDLE_SEGMENT_DETAIL: BundleSegmentDetail[] = [
  { order: 1, pageStart: 1, pageEnd: 4, label: '民事起诉状', filename: '01_民事起诉状.pdf', confidence: 0.96, flag: 'ok', evidence: '页眉标题「民事起诉状」' },
  { order: 2, pageStart: 5, pageEnd: 6, label: '证据清单及明细', filename: '02_证据清单及明细.pdf', confidence: 0.94, flag: 'ok', evidence: '表头「证据清单」+ 编号列' },
  { order: 3, pageStart: 7, pageEnd: 7, label: '当事人身份证明', filename: '03_当事人身份证明.pdf', confidence: 0.88, flag: 'ok', evidence: '身份证版式识别' },
  { order: 4, pageStart: 8, pageEnd: 10, label: '授权委托材料', filename: '04_授权委托材料.pdf', confidence: 0.91, flag: 'ok', evidence: '正文首段「特委托」' },
  { order: 5, pageStart: 11, pageEnd: 11, label: '送达地址确认书', filename: '05_送达地址确认书.pdf', confidence: 0.72, flag: 'low_confidence', evidence: '标题模糊（扫描倾斜 3.4°）' },
  { order: 6, pageStart: 12, pageEnd: 18, label: '借款合同', filename: '06_借款合同.pdf', confidence: 0.97, flag: 'ok', evidence: '合同编号连续 P12–P18' },
  { order: 7, pageStart: 19, pageEnd: 19, label: '借款借据', filename: '07_借款借据.pdf', confidence: 0.93, flag: 'ok', evidence: '表头「借款借据」' },
  { order: 8, pageStart: 20, pageEnd: 24, label: '放款凭证', filename: '08_放款凭证.pdf', confidence: 0.89, flag: 'ok', evidence: '银行回单版式 + 金额一致' },
  { order: 9, pageStart: 25, pageEnd: 30, label: '还款明细', filename: '09_还款明细.pdf', confidence: 0.95, flag: 'ok', evidence: '表格列「期次 / 应还 / 实还」' },
  { order: 10, pageStart: 31, pageEnd: 33, label: '催收记录', filename: '10_催收记录.pdf', confidence: 0.84, flag: 'ok', evidence: '正文「催收函」+ 签收章' },
  { order: 11, pageStart: 34, pageEnd: 34, label: '其他材料', filename: '11_未识别.pdf', confidence: 0.41, flag: 'unrecognized', evidence: '整页空白（仅 2% 墨迹）' },
  { order: 12, pageStart: 35, pageEnd: 38, label: '担保合同', filename: '12_担保合同.pdf', confidence: 0.9, flag: 'ok', evidence: '合同标题「保证合同」' },
]

/** 整包分段：识别能力（每类材料 + 本月拆过几次） */
export const DEMO_BUNDLE_CAPABILITIES: { label: string; monthCount: number; avgConfidence: number }[] = [
  { label: '起诉状', monthCount: 47, avgConfidence: 0.96 },
  { label: '证据清单及明细', monthCount: 45, avgConfidence: 0.93 },
  { label: '当事人身份证明', monthCount: 68, avgConfidence: 0.9 },
  { label: '授权委托材料', monthCount: 51, avgConfidence: 0.92 },
  { label: '送达地址确认书', monthCount: 43, avgConfidence: 0.74 },
  { label: '借款合同', monthCount: 39, avgConfidence: 0.97 },
  { label: '放款凭证', monthCount: 36, avgConfidence: 0.89 },
  { label: '还款明细', monthCount: 34, avgConfidence: 0.95 },
  { label: '催收记录', monthCount: 29, avgConfidence: 0.85 },
  { label: '判决书', monthCount: 12, avgConfidence: 0.94 },
  { label: '裁定书', monthCount: 9, avgConfidence: 0.92 },
  { label: '上诉状', monthCount: 8, avgConfidence: 0.91 },
  { label: '答辩状', monthCount: 6, avgConfidence: 0.88 },
]

/** 整包分段：拆分规则（按页内容识别 vs 按分隔页识别、模板选择逻辑） */
export const DEMO_BUNDLE_RULES: { title: string; body: string; example: string }[] = [
  {
    title: '按页内容识别（默认）',
    body: '每页先做版式 + 正文识别，判断它属于哪类材料；相邻同类型的页合并为一段。适合银行直接导出的整包扫描件。',
    example: 'P12–P18 连续识别为「借款合同」→ 合并为 1 份',
  },
  {
    title: '按分隔页识别',
    body: '扫描时每份材料之间插了空白分隔页（或条码页），就按分隔页切，不做类型推断，只按分隔页上的手写/条码标题命名。',
    example: 'P188 整包 → 47 份（每份前有 1 页分隔）',
  },
  {
    title: '模板选择逻辑',
    body: '模板跟着案件阶段走，不跟文件名走。一审起诉用 filing_materials_v1；二审/再审答辩用 appeal_defense_v1。选错模板，判决书与上诉状会全落「未识别」。',
    example: '二审包误用一审模板 → 5 段只认 1 段',
  },
  {
    title: '归案后的命名',
    body: '归案时用引擎给出的类型名做材料类型，不手工改名 —— 材料齐备度按类型名做关键词匹配，改名会让槽位判空。',
    example: '「借款合同」改成「担保合同」→ 主合同槽位变缺件',
  },
]

/** 整包分段：常见问题（折叠块） */
export const DEMO_BUNDLE_FAQ: { q: string; a: string }[] = [
  {
    q: '扫描件歪斜、双面透字导致识别不准怎么办？',
    a: '低于 0.75 置信度的段会标「需复核」。复核表里核对页码区间即可，不必重新扫。倾斜超过 5° 时建议在扫描仪侧重新走一遍自动纠偏。',
  },
  {
    q: '整包里混进了重复页（同一页扫了两遍）？',
    a: '引擎会算页面指纹，完全相同的页只保留第一处，并在复核表里标出「重复页已合并」。若是二次扫描版本不同（有手写批注），不会合并，需人工删一段。',
  },
  {
    q: '空白页、骑缝章页会占一份材料吗？',
    a: '整页墨迹低于 3% 的按空白页处理，不单独成段；骑缝章页并入相邻段。整包全是空白时该段标「未识别」，需要重扫。',
  },
  {
    q: '拆分到一半任务失败了，要重新上传吗？',
    a: '不用。任务在后台保留，超过 10 分钟前端会提示超时，但后台仍可能跑完 —— 到「拆分记录」里看结果，或稍后重试轮询。',
  },
  {
    q: '一包几百页要跑多久？',
    a: '实测约 1.3 s/页：278 页约 6 分钟，312 页约 7 分钟。耗时不影响复核，可以先去处理别的案件。',
  },
]

// ═══════════════════════════════════════════════════════════════════
// 起诉条件（DEMO_READINESS_*）—— 组件：components/ReadinessPanel.tsx
// 演示态补充：槽位来源与更新时间 / 校验依据 / 历史校验 / 同类案件对比 /
// 材料清单明细。真实判定仍以接口返回为准，这里只做画面填充。
// ═══════════════════════════════════════════════════════════════════

/** 起诉条件：材料槽位补充信息（文件数 / 最后更新 / 来源） */
export interface ReadinessSlotMeta {
  fileCount: number
  lastAt: string
  /** 来源：整包分段 / OA 盖章 / 人工上传 / 要素式转换 */
  source: string
}

export const DEMO_READINESS_SLOT_META: Record<string, ReadinessSlotMeta> = {
  contract: { fileCount: 1, lastAt: '11-03 09:14', source: '整包分段 · 自动归案' },
  iou: { fileCount: 2, lastAt: '11-03 09:14', source: '整包分段 · 自动归案' },
  stmt: { fileCount: 3, lastAt: '11-03 09:15', source: '整包分段 · 自动归案' },
  coll: { fileCount: 4, lastAt: '11-01 16:41', source: '整包分段 · 自动归案' },
  id: { fileCount: 2, lastAt: '10-26 14:31', source: '人工上传' },
  guarantee: { fileCount: 0, lastAt: '—', source: '不适用' },
}

/** 起诉条件：每项校验的「判定依据」补充（接口只给 field，这里给口径说明） */
export const DEMO_READINESS_CHECK_BASIS: Record<string, { basis: string; source: string }> = {
  parties: { basis: '原告与被告均已登记，一方缺失即不通过', source: 'Case.parties[]' },
  jurisdiction: { basis: '必须登记至少一个主管机关（管辖法院）', source: 'Case.supervising_authorities[]' },
  limitation: { basis: '自收案日起推算，超过 3 年提示超期风险', source: 'Case.start_date' },
  materials: { basis: '按案由的关键材料槽位逐项比对，缺件即不通过', source: 'CaseMaterial' },
  amount: { basis: '标的额必须大于 0，否则无法计算受理费', source: 'Case.target_amount' },
}

/** 起诉条件：历史校验记录（时间倒序） */
export interface ReadinessHistoryRow {
  at: string
  result: 'pass' | 'fail'
  passed: number
  total: number
  missing: number
  by: string
  note: string
}

export const DEMO_READINESS_HISTORY: ReadinessHistoryRow[] = [
  { at: '11-03 10:06', result: 'pass', passed: 5, total: 5, missing: 0, by: '黄某某', note: '归案后自动复校' },
  { at: '11-03 09:16', result: 'fail', passed: 4, total: 5, missing: 1, by: '系统定时', note: '催收记录未归案' },
  { at: '11-02 17:52', result: 'fail', passed: 3, total: 5, missing: 2, by: '黄某某', note: '缺还款明细、催收记录' },
  { at: '11-01 16:44', result: 'fail', passed: 3, total: 5, missing: 2, by: '房某某', note: '补寄材料尚未复核' },
  { at: '10-31 15:10', result: 'fail', passed: 2, total: 5, missing: 3, by: '系统定时', note: '首次建档，材料为空' },
  { at: '10-29 11:30', result: 'fail', passed: 2, total: 5, missing: 3, by: '黄某某', note: '管辖法院未登记' },
  { at: '10-27 14:02', result: 'fail', passed: 1, total: 5, missing: 4, by: '系统定时', note: '仅登记当事人' },
]

/** 起诉条件：同一委托下其他案件的通过率（演示态） */
export interface ReadinessPeerRow {
  caseName: string
  stage: string
  passed: number
  total: number
  missing: number
  latestAt: string
}

export const DEMO_READINESS_PEERS: ReadinessPeerRow[] = [
  { caseName: '某某银行广州分行诉谭某某金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '11-03 10:06' },
  { caseName: '某某银行广州分行诉吴某某金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '11-02 15:31' },
  { caseName: '某某银行广州分行诉李某某金融借款合同纠纷', stage: '一审', passed: 4, total: 5, missing: 1, latestAt: '11-02 11:20' },
  { caseName: '某某银行广州分行诉陈某某金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '11-01 09:48' },
  { caseName: '某某银行广州分行诉黄某某金融借款合同纠纷', stage: '一审', passed: 3, total: 5, missing: 2, latestAt: '10-30 16:12' },
  { caseName: '某某银行广州分行诉某某贸易公司金融借款合同纠纷', stage: '一审', passed: 5, total: 5, missing: 0, latestAt: '10-28 10:05' },
  { caseName: '某某银行广州分行诉刘某某金融借款合同纠纷', stage: '二审', passed: 3, total: 3, missing: 0, latestAt: '10-24 14:37' },
]

/** 起诉条件：材料清单明细（文件名 / 页数 / 上传时间 / 大小） */
export interface ReadinessFileRow {
  name: string
  slot: string
  pages: number
  size: string
  at: string
  source: string
}

export const DEMO_READINESS_FILES: ReadinessFileRow[] = [
  { name: '借款合同.pdf', slot: '借款/主合同', pages: 7, size: '1.8 MB', at: '11-03 09:14', source: '整包分段' },
  { name: '借款借据.pdf', slot: '借据或放款凭证', pages: 1, size: '0.3 MB', at: '11-03 09:14', source: '整包分段' },
  { name: '放款凭证.pdf', slot: '借据或放款凭证', pages: 5, size: '1.1 MB', at: '11-03 09:14', source: '整包分段' },
  { name: '还款明细.pdf', slot: '还款明细或对账单', pages: 6, size: '1.4 MB', at: '11-03 09:15', source: '整包分段' },
  { name: '对账单_2026Q3.pdf', slot: '还款明细或对账单', pages: 3, size: '0.7 MB', at: '11-03 09:15', source: '整包分段' },
  { name: '还款流水_全量.pdf', slot: '还款明细或对账单', pages: 12, size: '2.6 MB', at: '11-01 16:41', source: '整包分段' },
  { name: '催收记录.pdf', slot: '催收记录', pages: 3, size: '0.9 MB', at: '11-01 16:41', source: '整包分段' },
  { name: '催收函及签收单.pdf', slot: '催收记录', pages: 8, size: '2.1 MB', at: '11-01 16:41', source: '整包分段' },
  { name: '当事人身份证明.pdf', slot: '当事人身份证明', pages: 1, size: '0.2 MB', at: '10-26 14:31', source: '人工上传' },
  { name: '被告身份信息核查.pdf', slot: '当事人身份证明', pages: 1, size: '0.2 MB', at: '10-26 14:31', source: '人工上传' },
]


// ═══════════════════════════════════════════════════════════════════════
// OA 盖章（主会话补：agent 未覆盖此页）
// ═══════════════════════════════════════════════════════════════════════

/** 可用印章清单（演示态） */
export interface OASealRow {
  name: string
  kind: '公章' | '合同章' | '财务章' | '法定代表人章'
  holder: string
  status: 'available' | 'in-use' | 'expired'
  usedThisMonth: number
  lastUsed: string
}

export const DEMO_OA_SEALS: OASealRow[] = [
  { name: '某某律所 公章', kind: '公章', holder: '行政部', status: 'available', usedThisMonth: 42, lastUsed: '11-03 09:44' },
  { name: '某某律所 合同专用章', kind: '合同章', holder: '行政部', status: 'available', usedThisMonth: 18, lastUsed: '11-02 16:20' },
  { name: '某某律所 财务专用章', kind: '财务章', holder: '财务部', status: 'in-use', usedThisMonth: 7, lastUsed: '11-03 10:15' },
  { name: '法定代表人 私章', kind: '法定代表人章', holder: '主任办', status: 'available', usedThisMonth: 31, lastUsed: '11-03 09:44' },
  { name: '某某律所 旧版公章', kind: '公章', holder: '行政部', status: 'expired', usedThisMonth: 0, lastUsed: '2025-12-31' },
]

/** 盖章位置规则：哪类文书该盖哪些章、盖在哪 */
export interface OASealRuleRow {
  docType: string
  seals: string
  position: string
  note: string
}

export const DEMO_OA_SEAL_RULES: OASealRuleRow[] = [
  { docType: '民事起诉状', seals: '公章 + 法定代表人章', position: '具状人处 + 骑缝', note: '骑缝章须覆盖全部附件页' },
  { docType: '证据清单及明细', seals: '公章', position: '清单末尾', note: '与证据材料一并骑缝' },
  { docType: '授权委托书', seals: '委托人签章 + 律所公章', position: '委托人签名处 + 落款', note: '缺委托人签章视为无效' },
  { docType: '送达地址确认书', seals: '公章', position: '确认人处', note: '须与立案信息一致' },
  { docType: '律师事务所函', seals: '公章', position: '落款处', note: '需注明承办律师与执业证号' },
  { docType: '办案小结', seals: '公章', position: '落款处', note: '归档前最后一环' },
]

/** 盖章历史（扩到 12 条，含失败） */
export interface StampHistoryRow {
  fileName: string
  docType: string
  seals: string
  page: string
  ok: boolean
  reason: string
  at: string
  by: string
}

export const DEMO_STAMP_HISTORY: StampHistoryRow[] = [
  { fileName: '民事起诉状（定稿）.pdf', docType: '民事起诉状', seals: '公章+法代章', page: '第3页 + 骑缝', ok: true, reason: '', at: '11-03 09:44', by: '黄某某' },
  { fileName: '证据清单及明细.pdf', docType: '证据清单', seals: '公章', page: '第12页 + 骑缝', ok: true, reason: '', at: '11-03 09:42', by: '黄某某' },
  { fileName: '授权委托书（扫描件）.pdf', docType: '授权委托书', seals: '公章', page: '第1页', ok: true, reason: '', at: '11-03 09:40', by: '黄某某' },
  { fileName: '送达地址确认书.pdf', docType: '送达地址确认书', seals: '公章', page: '骑缝', ok: false, reason: '骑缝章位置与印章库不符', at: '11-02 17:20', by: '黄某某' },
  { fileName: '律师事务所函.pdf', docType: '律所函', seals: '公章', page: '落款处', ok: true, reason: '', at: '11-02 15:05', by: '房某某' },
  { fileName: '民事起诉状（初稿）.pdf', docType: '民事起诉状', seals: '公章', page: '第2页', ok: false, reason: '文件已被新版替代，拒绝盖章', at: '11-02 11:30', by: '房某某' },
  { fileName: '保全申请书.pdf', docType: '保全申请书', seals: '公章+法代章', page: '第1页 + 骑缝', ok: true, reason: '', at: '11-01 16:48', by: '黄某某' },
  { fileName: '证据目录.pdf', docType: '证据清单', seals: '公章', page: '末尾', ok: true, reason: '', at: '11-01 16:45', by: '黄某某' },
  { fileName: '执行申请书.pdf', docType: '执行申请书', seals: '公章', page: '落款处', ok: true, reason: '', at: '10-31 14:10', by: '房某某' },
  { fileName: '办案小结.docx', docType: '办案小结', seals: '公章', page: '落款处', ok: false, reason: '非 PDF 格式，需先转档', at: '10-31 10:02', by: '房某某' },
  { fileName: '退费账户确认书.pdf', docType: '退费确认书', seals: '公章', page: '确认人处', ok: true, reason: '', at: '10-30 17:22', by: '黄某某' },
  { fileName: '法定代表人身份证明.pdf', docType: '法代证明', seals: '公章', page: '落款处', ok: true, reason: '', at: '10-30 15:38', by: '黄某某' },
]

/** 盖章常见失败原因 */
export interface StampFailureRow {
  cause: string
  stage: string
  last30: number
  autoRetry: boolean
  advice: string
}

export const DEMO_STAMP_FAILURES: StampFailureRow[] = [
  { cause: '骑缝章位置与印章库不符', stage: '盖章执行', last30: 3, autoRetry: false, advice: '检查文档页数与印章库登记的骑缝位置，必要时手工注入' },
  { cause: '文件已被新版替代', stage: '反查归属', last30: 5, autoRetry: false, advice: '确认取的是最新版文件，旧版禁止盖章' },
  { cause: '非 PDF 格式', stage: '格式校验', last30: 8, autoRetry: true, advice: '系统会自动转档为 PDF 后重试' },
  { cause: '印章使用权限不足', stage: '权限校验', last30: 2, autoRetry: false, advice: '由行政部授权对应印章，或改用其他可用章' },
  { cause: '文件不在绑定文件夹', stage: '反查归属', last30: 6, autoRetry: false, advice: '把文件放进已绑定的案件/合同文件夹后再试' },
]

/** 批量盖章预设：一次给一套材料盖齐章 */
export interface StampBatchRow {
  name: string
  docs: number
  pages: number
  seals: string
  note: string
}

export const DEMO_STAMP_BATCHES: StampBatchRow[] = [
  { name: '一审起诉全套', docs: 7, pages: 46, seals: '公章 + 法代章', note: '起诉状/证据清单/委托书/送达确认/退费账户/律所函/法代证明' },
  { name: '执行申请全套', docs: 5, pages: 28, seals: '公章', note: '执行申请书/限高申请/失信申请/账户确认/材料清单' },
  { name: '保全材料', docs: 3, pages: 15, seals: '公章 + 法代章', note: '保全申请书/担保函/财产线索' },
  { name: '归档补章', docs: 4, pages: 22, seals: '公章', note: '案卷封面/目录/办案小结/监督卡' },
]
