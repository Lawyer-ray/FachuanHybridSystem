/**
 * 演示数据 · G6. ⑥ 校验
 *
 * 送法院前的签章核对、立案条件核对与修正建议。
 */

// ───────────────────────── ⑥ 校验 · 签章核对 ─────────────────────────

export interface SignCheckRow {
  docName: string
  needSeal: string
  needSign: string
  sealOk: boolean
  signOk: boolean
  note: string
}

export const DEMO_SIGN_CHECKS: SignCheckRow[] = [
  { docName: '民事起诉状', needSeal: '公章 + 法定代表人章', needSign: '具状人签名', sealOk: true, signOk: true, note: '骑缝章覆盖全部 4 页' },
  { docName: '证据清单', needSeal: '公章', needSign: '—', sealOk: true, signOk: true, note: '与证据材料一并骑缝' },
  { docName: '授权委托书', needSeal: '公章', needSign: '委托人签名 + 指印', sealOk: true, signOk: false, note: '委托人签名处空白，需重新签署' },
  { docName: '送达地址确认书', needSeal: '公章', needSign: '确认人签名', sealOk: true, signOk: true, note: '地址与立案信息一致' },
  { docName: '退费账户确认书', needSeal: '公章', needSign: '—', sealOk: false, signOk: true, note: '未盖章，需补盖财务章' },
  { docName: '授权委托证明材料', needSeal: '公章', needSign: '—', sealOk: true, signOk: true, note: '律所函 + 执业证复印件齐全' },
]

// ───────────────────────── ⑥ 校验 · 立案条件核对 ─────────────────────────

export interface FilingCheckRow {
  check: string
  result: 'pass' | 'warn' | 'fail'
  value: string
  detail: string
}

export const DEMO_FILING_CHECKS: FilingCheckRow[] = [
  { check: '当事人主体适格', result: 'pass', value: '原告 1 · 被告 2', detail: '借贷双方均具备诉讼主体资格' },
  { check: '管辖', result: 'pass', value: '广州市天河区人民法院', detail: '合同约定签订地法院，与立案法院一致' },
  { check: '诉讼时效', result: 'pass', value: '未届满', detail: '最后还款日 2026-04-18，起算未满三年' },
  { check: '金额三处一致', result: 'fail', value: '差 31.85 元', detail: '起诉状 998,670.21 / 立案表单 998,702.06' },
  { check: '签字盖章', result: 'fail', value: '2 份未通过', detail: '授权委托书缺签名、退费确认书缺盖章' },
  { check: '要素式起诉状', result: 'warn', value: '待转换', detail: '法院要求要素式，当前为传统格式' },
]

// ───────────────────────── ⑥ 校验 · 修正建议 ─────────────────────────

export interface FilingFixRow {
  item: string
  fix: string
  owner: string
  eta: string
  auto: boolean
}

export const DEMO_FILING_FIXES: FilingFixRow[] = [
  { item: '金额三处不一致', fix: '按起诉状定稿基准重写立案表单标的额（差 31.85 元）', owner: '系统自动', eta: '即时', auto: true },
  { item: '授权委托书缺签名', fix: '通知当事人补签，签署后重新扫描上传', owner: '经办律师', eta: '1 个工作日', auto: false },
  { item: '退费确认书缺盖章', fix: '推送 OA 盖章流程，盖财务章后回传', owner: '行政', eta: '当日', auto: false },
  { item: '要素式起诉状待转换', fix: '用「要素式转换」把传统起诉状转成法院要素式', owner: '系统自动', eta: '1 分钟', auto: true },
]
