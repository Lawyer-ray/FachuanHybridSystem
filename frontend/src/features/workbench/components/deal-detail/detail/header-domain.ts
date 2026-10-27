import type { WorkbenchDeal } from '../../../types'
import type { MetaPart } from './case-section-domain'

/**
 * 页头 meta：类型 · 状态 · 建档编号（空值不渲染）。
 * 我方 → 对方与主办不再出现在页头——右栏「当事人」「办案团队」卡已完整展示，页头重复一遍只会把标题推得更长。
 */
export function headerMetaParts(deal: WorkbenchDeal): MetaPart[] {
  const parts: MetaPart[] = []
  if (deal.ctype) parts.push({ v: deal.ctype, strong: true })
  if (deal.statusLabel) parts.push({ v: deal.statusLabel, strong: true })
  if (deal.filingNo) parts.push({ k: '建档', v: deal.filingNo })
  return parts
}

/** 面包屑短名：全称动辄五六十字会顶满一整行，18 字足够定位；完整名在主标题和 hover title 里 */
export function crumbName(name: string, cap = 18): string {
  return name.length > cap ? name.slice(0, cap) + '…' : name
}
