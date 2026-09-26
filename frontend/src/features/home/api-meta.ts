/**
 * 日历事件的展示辅助。
 *
 * 合并 / 归一化 / 统计都已移到后端（GET /reminders/calendar，与 Django admin
 * 日历共用同一个 service），这里只保留纯展示层面的加工：副标题摘要、时段显示。
 */

import type { CalendarEvent } from './api'

/** 是否紧要（庭期 / 期限）——与后端 calendar_view_service 的 is_key_kind 对应 */
export function isKeyKind(kind: string): boolean {
  return kind === 'court' || kind === 'deadline'
}

/**
 * 副标题摘要。优先级与 admin 的 reminder-event-meta 一致：
 * 有人名/地点时给「人名 · 地点」，否则退到案号 / 关联对象名。
 */
export function summaryLine(e: CalendarEvent): string {
  const parts = [e.person, e.place].filter(Boolean)
  if (parts.length) return parts.join(' · ')
  return [e.case_no, e.target_name].filter(Boolean).join(' · ')
}

/** 更紧凑的一行：只留最关键的一段（地点优先，其次人名） */
export function briefLine(e: CalendarEvent): string {
  return e.place || e.person || e.case_no || e.target_name
}

/**
 * 日历格事件行的两行元信息：第一行律师（承办人），第二行地点。
 * 律师在前——「谁去开庭」比「在哪个法庭」更常被需要。
 */
export function cellMetaLines(e: CalendarEvent): { primary: string; secondary: string } {
  return { primary: e.person, secondary: e.place }
}

/** 时段区间原文（如 10:00-12:00）；没有则空串 */
export function rangeLabel(e: CalendarEvent): string {
  return e.time_range
}
