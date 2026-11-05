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

/**
 * 日历卡片的主标题：**庭期沿用案名，其余行动项优先**。
 *
 * 后端 title 的口径是「关联对象名优先，取不到才退回 content」
 * （calendar_view_service: title=target_name or content）。这对庭期是对的——
 * 案名比「开庭」两个字有信息量。但对自定义事项 / 期限就错了：content 才是
 * 「要做什么」（如「债权人会议」「提交证据目录」），关联对象只是它挂在哪。
 * 绑了长合同名之后卡片上只剩合同名，用户看格子和详情都不知道该干什么。
 *
 * 因此按 kind 分流：
 *   - 庭期（court）：维持 title（案名优先）
 *   - 其余：content 与 target_name 不同就用 content，让行动项露出
 * 后端 title 语义保持不变（admin 日历等其它消费方仍在用）。
 */
export function cardTitle(e: CalendarEvent): string {
  if (e.kind === 'court') return e.title || e.content || ''
  const content = (e.content || '').trim()
  if (content && content !== e.target_name) return content
  return e.title || content
}

/**
 * 卡片的「关联对象」副标题：主标题让给了 content 之后，
 * 关联对象（合同 / 案件 / 日志名）作为归属信息补一行。
 * 与主标题相同则不重复展示。
 */
export function cardTargetLine(e: CalendarEvent): string {
  const name = (e.target_name || '').trim()
  if (!name || name === cardTitle(e)) return ''
  return name
}
