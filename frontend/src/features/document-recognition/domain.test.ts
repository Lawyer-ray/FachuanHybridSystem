import { describe, expect, it } from 'vitest'

import {
  fileRejectReason,
  formatDueLocal,
  patchRow,
  rowsFromParsed,
  rowsFromTask,
  selectedPendingRows,
  selectedTextRows,
  toLocalInputValue,
  type CandidateRow,
} from './domain'
import type { TaskOut } from './types'

describe('toLocalInputValue', () => {
  it('带时区偏移的 ISO 转成本地 datetime-local 值', () => {
    // UTC 01:30 = 北京 09:30（测试机时区无关：用显式偏移表达「这一刻」）
    const local = toLocalInputValue('2026-10-15T01:30:00+00:00')
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(local).toHaveLength(16)
  })

  it('naive ISO 原样保留日期时间（Date 构造按本地解析）', () => {
    expect(toLocalInputValue('2026-10-15T09:30')).toBe('2026-10-15T09:30')
  })

  it('空值与非法输入返回空串', () => {
    expect(toLocalInputValue(null)).toBe('')
    expect(toLocalInputValue('')).toBe('')
    expect(toLocalInputValue('not-a-date')).toBe('')
  })
})

describe('formatDueLocal', () => {
  it('YYYY-MM-DDTHH:mm → 「MM月DD日 HH:mm」', () => {
    expect(formatDueLocal('2026-10-15T09:30')).toBe('10月15日 09:30')
  })

  it('只有日期时原样返回日期', () => {
    expect(formatDueLocal('2026-10-15')).toBe('2026-10-15')
    expect(formatDueLocal('')).toBe('')
  })
})

describe('rowsFromTask', () => {
  const task = {
    task_id: 1,
    status: 'success',
    file_path: null,
    recognition: null,
    binding: null,
    recommendations: [],
    binding_mode: 'standalone',
    date_confirmation_status: 'pending',
    error_message: null,
    created_at: '2026-09-28T10:00:00+08:00',
    finished_at: null,
    date_candidates: [
      {
        id: 11,
        due_at: '2026-10-15T01:30:00+00:00',
        reminder_type: 'hearing',
        reminder_type_label: '开庭',
        context_text: '定于…公开开庭',
        source: 'llm',
        confidence: 0.9,
        status: 'pending',
        reminder_id: null,
        confirmed_at: null,
      },
      {
        id: 12,
        due_at: '2026-10-20T00:00:00+00:00',
        reminder_type: 'evidence_deadline',
        reminder_type_label: '举证到期日',
        context_text: '',
        source: 'regex',
        confidence: null,
        status: 'confirmed',
        reminder_id: 55,
        confirmed_at: null,
      },
    ],
  } as unknown as TaskOut

  it('pending 行默认勾选可编辑，confirmed 行不勾选', () => {
    const rows = rowsFromTask(task)
    expect(rows).toHaveLength(2)
    expect(rows[0]!).toMatchObject({ candidateId: 11, checked: true, status: 'pending' })
    expect(rows[1]!).toMatchObject({ candidateId: 12, checked: false, status: 'confirmed', reminderId: 55 })
  })
})

describe('rowsFromParsed / 选择过滤', () => {
  const parsed = [
    { content: '开庭 张某诉李某', reminder_type: 'hearing', reminder_type_label: '开庭', due_at: '2026-09-30T09:00', source_text: '原文' },
    { content: '举证截止', reminder_type: 'evidence_deadline', reminder_type_label: '举证到期日', due_at: '2026-10-10T17:00', source_text: '' },
  ]

  it('全部候选成行（多日期不再丢弃）', () => {
    const rows = rowsFromParsed(parsed)
    expect(rows).toHaveLength(2)
    expect(rows[0]!).toMatchObject({ candidateId: null, checked: true, source: 'text', content: '开庭 张某诉李某' })
  })

  it('selectedTextRows 只取勾选的无 candidateId 行', () => {
    const rows = patchRow(rowsFromParsed(parsed), 't-0', { checked: false })
    expect(selectedTextRows(rows)).toHaveLength(1)
    expect(selectedTextRows(rows)[0]!.key).toBe('t-1')
  })

  it('selectedPendingRows 只取勾选的识别候选（文字行不混入）', () => {
    const mixed: CandidateRow[] = [
      { key: 'c-1', candidateId: 1, checked: true, dueLocal: '2026-10-15T09:30', reminderType: 'hearing', label: '开庭', contextText: '', content: '', source: 'llm', confidence: 0.9, status: 'pending', reminderId: null },
      { key: 'c-2', candidateId: 2, checked: false, dueLocal: '2026-10-16T09:30', reminderType: 'other', label: '其他', contextText: '', content: '', source: 'regex', confidence: null, status: 'pending', reminderId: null },
      { key: 't-0', candidateId: null, checked: true, dueLocal: '2026-10-17T09:30', reminderType: 'other', label: '其他', contextText: '', content: 'x', source: 'text', confidence: null, status: 'pending', reminderId: null },
    ]
    const picked = selectedPendingRows(mixed)
    expect(picked).toHaveLength(1)
    expect(picked[0]!.key).toBe('c-1')
  })
})

describe('patchRow', () => {
  const rows: CandidateRow[] = [
    { key: 'a', candidateId: 1, checked: true, dueLocal: '2026-10-15T09:30', reminderType: 'hearing', label: '开庭', contextText: '', content: '', source: 'llm', confidence: null, status: 'pending', reminderId: null },
  ]

  it('不可变更新目标行，其他行引用不变', () => {
    const next = patchRow(rows, 'a', { checked: false, reminderType: 'other' })
    expect(next[0]!).toMatchObject({ checked: false, reminderType: 'other' })
    expect(rows[0]!.checked).toBe(true) // 原数组未被改动
  })
})

describe('fileRejectReason', () => {
  it('接受 PDF 与图片', () => {
    expect(fileRejectReason(new File([], '传票.pdf'))).toBeNull()
    expect(fileRejectReason(new File([], 'a.jpg'))).toBeNull()
    expect(fileRejectReason(new File([], 'a.PNG'))).toBeNull()
  })

  it('拒绝不支持的格式与超大文件', () => {
    expect(fileRejectReason(new File([], 'a.docx'))).toContain('不支持的格式')
    const big = new File([new ArrayBuffer(21 * 1024 * 1024)], 'a.pdf')
    expect(fileRejectReason(big)).toContain('超过')
  })
})
