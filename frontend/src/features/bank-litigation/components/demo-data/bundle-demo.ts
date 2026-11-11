/**
 * 演示数据 · E. 整包拆分 UI（组件：components/bundle/*）
 *
 * 覆盖 idle 态的画面：历史拆分记录 / 每包明细 / 识别能力计数 /
 * 拆分规则 / 常见问题。全部为演示数据，不参与任何判断逻辑。
 * 真实功能上线时整个文件删除即可。
 */

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
