import { describe, expect, it } from 'vitest'

import type { CalendarEvent } from './api'
import { briefLine, cardTargetLine, cardTitle, cellMetaLines, isKeyKind, rangeLabel, summaryLine } from './api-meta'

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
    reminder_type: 'hearing',
    members: 1,
    member_ids: [1],
    can_delete: false,
    can_edit: false,
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
    expect(summaryLine(ev({ case_no: '（20XX）粤01民初1号', target_name: '张三案' }))).toBe('（20XX）粤01民初1号 · 张三案')
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

describe('cardTitle / cardTargetLine：卡片主标题的行动项优先', () => {
  // 后端口径 title = target_name or content（关联对象名优先）。这对庭期是对的，
  // 但对自定义事项 / 期限会让长合同名把真正的行动项挤掉。
  // 只关心「名字够长」这一件事，不含任何真实主体信息
  const longContract = '测试用超长合同名称'.repeat(5)

  it('庭期：维持案名优先，不被 content（如「开庭」）覆盖', () => {
    const e = ev({ kind: 'court', title: longContract, content: '开庭', target_name: longContract })
    expect(cardTitle(e)).toBe(longContract)
    // 主标题已是案名，不再重复一行
    expect(cardTargetLine(e)).toBe('')
  })

  it('自定义事项：content 优先，让行动项露出来', () => {
    const e = ev({ kind: 'meeting', title: longContract, content: '债权人会议', target_name: longContract })
    expect(cardTitle(e)).toBe('债权人会议')
    // 关联对象降为副标题，避免用户丢失归属信息
    expect(cardTargetLine(e)).toBe(longContract)
  })

  it('自定义事项：没有关联对象时直接用 content', () => {
    const e = ev({ kind: 'meeting', title: '债权人会议', content: '债权人会议', target_name: '' })
    expect(cardTitle(e)).toBe('债权人会议')
    expect(cardTargetLine(e)).toBe('')
  })

  it('content 与 target_name 相同：不重复展示', () => {
    const e = ev({ kind: 'deadline', title: longContract, content: longContract, target_name: longContract })
    expect(cardTitle(e)).toBe(longContract)
    expect(cardTargetLine(e)).toBe('')
  })

  it('content 为空：退回 title，不显示空白标题', () => {
    const e = ev({ kind: 'meeting', title: '与客户会谈', content: '', target_name: '某合同' })
    expect(cardTitle(e)).toBe('与客户会谈')
    expect(cardTargetLine(e)).toBe('某合同')
  })

  it('content 只有空白字符：同样退回 title', () => {
    const e = ev({ kind: 'deadline', title: '提交证据目录', content: '   ', target_name: '' })
    expect(cardTitle(e)).toBe('提交证据目录')
  })
})
