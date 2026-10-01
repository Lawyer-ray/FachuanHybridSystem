import { describe, expect, it } from 'vitest'

import type { CalendarEvent } from './api'
import { briefLine, cellMetaLines, isKeyKind, rangeLabel, summaryLine } from './api-meta'

function ev(p: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 1,
    kind: 'court',
    kind_label: '开庭',
    title: '开庭提醒',
    content: '原文',
    day: '2026-10-01',
    time: '09:00',
    time_range: '09:00-12:00',
    place: '',
    person: '',
    case_no: '',
    hearing_type: '',
    target_type: '',
    target_name: '',
    case_id: null,
    is_today: false,
    is_overdue: false,
    is_completed: false,
    members: 1,
    member_ids: [1],
    ...p,
  }
}

describe('isKeyKind（与后端 calendar_view_service 口径对应）', () => {
  it('只有庭期 / 期限算紧要', () => {
    expect(isKeyKind('court')).toBe(true)
    expect(isKeyKind('deadline')).toBe(true)
    expect(isKeyKind('custom')).toBe(false)
    expect(isKeyKind('')).toBe(false)
  })
})

describe('summaryLine 副标题回落链', () => {
  it('有人名/地点 → 「人名 · 地点」（缺谁跳谁）', () => {
    expect(summaryLine(ev({ person: '赵律师', place: '第三法庭' }))).toBe('赵律师 · 第三法庭')
    expect(summaryLine(ev({ person: '赵律师' }))).toBe('赵律师')
    expect(summaryLine(ev({ place: '第三法庭' }))).toBe('第三法庭')
  })
  it('无人名地点 → 案号 / 关联对象名', () => {
    expect(summaryLine(ev({ case_no: '（2026）粤01民初1号', target_name: '张三案' }))).toBe('（2026）粤01民初1号 · 张三案')
    expect(summaryLine(ev({ target_name: '张三案' }))).toBe('张三案')
    expect(summaryLine(ev())).toBe('')
  })
})

describe('briefLine / cellMetaLines / rangeLabel', () => {
  it('地点优先于人名的紧凑一行', () => {
    expect(briefLine(ev({ place: '第三法庭', person: '赵律师' }))).toBe('第三法庭')
    expect(briefLine(ev({ person: '赵律师', case_no: 'X号' }))).toBe('赵律师')
    expect(briefLine(ev())).toBe('')
  })
  it('日历格两行元信息：律师在前、地点在后', () => {
    expect(cellMetaLines(ev({ person: '赵律师', place: '第三法庭' }))).toEqual({
      primary: '赵律师',
      secondary: '第三法庭',
    })
  })
  it('时段区间原文透传', () => {
    expect(rangeLabel(ev({ time_range: '10:00-12:00' }))).toBe('10:00-12:00')
    expect(rangeLabel(ev({ time_range: '' }))).toBe('')
  })
})
