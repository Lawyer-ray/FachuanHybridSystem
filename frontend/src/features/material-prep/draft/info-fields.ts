import type { DraftState, InfoField } from '../types'

/**
 * 右栏信息便签（委托人 / 对方当事人 / 标的额…）的不可变运算。
 */

export function addInfoField(d: DraftState, field: InfoField): DraftState {
  if (d.infos.some((f) => f.k === field.k)) return d
  return { ...d, infos: [...d.infos, { ...field }] }
}

export function removeInfoField(d: DraftState, di: number): DraftState {
  if (di < 0 || di >= d.infos.length) return d
  return { ...d, infos: d.infos.filter((_, i) => i !== di) }
}

export function setInfoValue(d: DraftState, di: number, v: string): DraftState {
  if (di < 0 || di >= d.infos.length) return d
  const infos = d.infos.map((f, i) => (i === di ? { ...f, v } : f))
  return { ...d, infos }
}

export function setInfoSource(d: DraftState, di: number, src: string, srcRef: InfoField['srcRef']): DraftState {
  if (di < 0 || di >= d.infos.length) return d
  const infos = d.infos.map((f, i) => (i === di ? { ...f, src, srcRef } : f))
  return { ...d, infos }
}
