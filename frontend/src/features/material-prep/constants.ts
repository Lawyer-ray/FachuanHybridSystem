import type { InfoField } from './types'

/** 10 种材料类型（人工归类的候选集） */
export const SEGMENT_TYPES = [
  '起诉状',
  '借条',
  '银行流水',
  '转账凭证',
  '聊天记录',
  '主体身份证明',
  '授权委托书',
  '送达回证',
  '证据材料',
  '其他',
]

/** 段头色点取色盘 */
export const SEG_COLORS = ['#2563eb', '#22c55e', '#eab308', '#7c3aed', '#ef4444', '#0891b2']

/** 字段库：右栏便签可选的字段 */
export const FIELD_LIB: InfoField[] = [
  { k: '委托人', v: '', src: '', srcRef: null, ph: '姓名或单位' },
  { k: '对方当事人', v: '', src: '', srcRef: null, ph: '姓名或单位', hint: '多个用、分隔' },
  { k: '标的额', v: '', src: '', srcRef: null, ph: '如 120000' },
  { k: '关键日期', v: '', src: '', srcRef: null, ph: '如 2024-03-12' },
  { k: '事项 / 案由', v: '', src: '', srcRef: null, ph: '民间借贷 · 专项法律顾问' },
  { k: '业务类型', v: '', src: '', srcRef: null, opts: ['诉讼', '非诉', '常年顾问', '其他'] },
  { k: '管辖法院', v: '', src: '', srcRef: null, ph: '如 广州市天河区人民法院' },
  { k: '案号', v: '', src: '', srcRef: null, ph: '如 (2024)粤0101民初1001号' },
  { k: '备注', v: '', src: '', srcRef: null, ph: '随便写', ta: true },
]

export const MANUAL_SOURCE_TYPE = 'manual_upload'
