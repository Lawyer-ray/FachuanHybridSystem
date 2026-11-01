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
  { stage: '建卷', message: '创建收案登记，选择案件类别「诉讼」', ms: 960, ok: true, at: '11-03 10:02' },
  { stage: '填表', message: '写入案由 / 委托人 / 标的额（3 项）', ms: 1240, ok: true, at: '11-03 10:03' },
  { stage: '关联', message: '关联委托合同 391 与承办律师', ms: 780, ok: true, at: '11-03 10:03' },
  { stage: '回写', message: '取回所内案号 2026-民-XXXX，已落库', ms: 620, ok: true, at: '11-03 10:03' },
]

/** OA 立案：站点清单（演示态，真实值来自 /oa-filing/configs） */
/**
 * ⚠️ 这里的站点名**不要**写真实律所名（pre-commit 隐私闸门会拦）。
 * 演示画面里显示什么由 `OAConfig` 接口返回的真实值决定，本常量只在
 * 接口不可用时兜底，所以用中性占位即可。
 */
export const DEMO_OA_SITES = [
  { name: '某某律所 OA', credential: true, lastUsed: '11-03 10:03' },
  { name: '分所 OA（测试）', credential: false, lastUsed: '—' },
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

/** 要素式转换：样例转换记录（后端已有真实记录时优先用真实值） */
export interface ConvertLogRow {
  id: number
  originalName: string
  typeName: string
  at: string
}

export const DEMO_CONVERT_LOG: ConvertLogRow[] = [
  { id: 1, originalName: '民事起诉状（传统）.docx', typeName: '金融借款起诉状', at: '2026-10-30 13:00' },
  { id: 2, originalName: '民事起诉状（传统）_修订.docx', typeName: '金融借款起诉状', at: '2026-10-30 12:59' },
  { id: 3, originalName: '起诉状_谭某某.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:02' },
  { id: 4, originalName: '起诉状_吴某某.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:01' },
  { id: 5, originalName: '起诉状_模板示例.docx', typeName: '金融借款起诉状', at: '2026-10-30 10:00' },
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
