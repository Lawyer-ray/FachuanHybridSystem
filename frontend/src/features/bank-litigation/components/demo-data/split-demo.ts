/**
 * 演示数据 · A. 整包分段（基础版）
 *
 * 整包分段首页的历史拆分记录与识别能力清单。
 * 真实功能上线时整个文件删除即可。
 */

import type { SplitHistoryRow } from './types'

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
