import { describe, expect, it, vi } from 'vitest'

import {
  candidateAnchorLine,
  candidateSourceLine,
  fileRejectReason,
  flagLabel,
  formatContacts,
  formatDueLocal,
  patchRow,
  pickAutoRecommendation,
  resolveMediaUrl,
  resolveMediaUrlWithAuth,
  rowsFromParsed,
  rowsFromTask,
  selectedPendingRows,
  selectedTextRows,
  type CandidateRow,
} from './domain'
import { toLocalInputValue } from '@/lib/date'
import type { CaseRecommendation, TaskOut } from './types'

function makeRow(over: Partial<CandidateRow> = {}): CandidateRow {
  return {
    key: 'c-1',
    candidateId: 1,
    checked: true,
    dueLocal: '2026-10-15T09:30',
    reminderType: 'hearing',
    label: '开庭',
    contextText: '',
    content: '',
    source: 'llm',
    confidence: null,
    status: 'pending',
    reminderId: null,
    reviewFlags: [],
    anchorNote: '',
    derivationLabel: '',
    defaultChecked: true,
    ...over,
  }
}

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
        default_checked: true,
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
      makeRow({ key: 'c-1', candidateId: 1, checked: true, reminderType: 'hearing', label: '开庭', source: 'llm', confidence: 0.9 }),
      makeRow({ key: 'c-2', candidateId: 2, checked: false, reminderType: 'other', label: '其他', source: 'regex' }),
      makeRow({ key: 't-0', candidateId: null, checked: true, content: 'x', source: 'text' }),
    ]
    const picked = selectedPendingRows(mixed)
    expect(picked).toHaveLength(1)
    expect(picked[0]!.key).toBe('c-1')
  })
})

describe('patchRow', () => {
  const rows: CandidateRow[] = [makeRow({ key: 'a', candidateId: 1 })]

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

describe('rowsFromTask 默认勾选（只认后端 default_checked）', () => {
  it('后端默认勾选才勾，缺失或 false 不勾，与 confidence 无关', () => {
    const t = {
      task_id: 2,
      status: 'success',
      recognition: null,
      binding: null,
      recommendations: [],
      binding_mode: 'standalone',
      date_confirmation_status: 'pending',
      date_candidates: [
        { id: 21, due_at: '2026-10-15T01:30:00+00:00', reminder_type: 'hearing', reminder_type_label: '开庭', context_text: '', source: 'llm', confidence: 0.3, status: 'pending', reminder_id: null, confirmed_at: null, default_checked: true },
        { id: 22, due_at: '2026-10-20T00:00:00+00:00', reminder_type: 'other', reminder_type_label: '其他', context_text: '', source: 'regex', confidence: 0.9, status: 'pending', reminder_id: null, confirmed_at: null, default_checked: false },
        { id: 23, due_at: '2026-11-01T00:00:00+00:00', reminder_type: 'other', reminder_type_label: '其他', context_text: '', source: 'llm', confidence: null, status: 'pending', reminder_id: null, confirmed_at: null },
      ],
    } as unknown as TaskOut
    const rows = rowsFromTask(t)
    expect(rows.map((r) => r.checked)).toEqual([true, false, false])
    expect(rows.map((r) => r.defaultChecked)).toEqual([true, false, false])
  })
})

describe('candidateSourceLine（候选来源行）', () => {
  it('优先后端推导标签', () => {
    expect(candidateSourceLine(makeRow({ derivationLabel: '按送达日推算', source: 'llm' }))).toBe('按送达日推算')
  })

  it('无推导标签时回落提取来源中文', () => {
    expect(candidateSourceLine(makeRow({ source: 'llm' }))).toBe('AI')
    expect(candidateSourceLine(makeRow({ source: 'merged' }))).toBe('AI+规则')
  })

  it('未知来源原样返回', () => {
    expect(candidateSourceLine(makeRow({ source: 'custom' }))).toBe('custom')
  })
})

describe('candidateAnchorLine（候选起算点行）', () => {
  it('有起算点说明时原样返回', () => {
    expect(candidateAnchorLine(makeRow({ anchorNote: '起算点：本份文书送达日 2026-11-24 + 7 天' }))).toBe(
      '起算点：本份文书送达日 2026-11-24 + 7 天',
    )
  })

  it('缺失时返回空串（调用方据此收起整行）', () => {
    expect(candidateAnchorLine(makeRow())).toBe('')
  })
})

describe('flagLabel（复核标记中文）', () => {
  it('词表内的标记翻译为中文', () => {
    expect(flagLabel('anchor_effective')).toBe('起算点待确认')
    expect(flagLabel('generic_boilerplate')).toBe('通用文书')
    expect(flagLabel('low_confidence')).toBe('低置信')
    expect(flagLabel('far_future')).toBe('远期日期')
    expect(flagLabel('duplicate')).toBe('重复项')
    expect(flagLabel('discarded_by_gate')).toBe('已过滤')
  })

  it('未知标记原样返回，不吞掉后端新增标记', () => {
    expect(flagLabel('brand_new_flag')).toBe('brand_new_flag')
  })
})

describe('pickAutoRecommendation（推荐预选）', () => {
  const reco = (score: number, id = 1): CaseRecommendation => ({
    case_id: id, case_name: `案件${id}`, score, reasons: [], case_numbers: [], parties: [], status: 'active',
  })

  it('唯一高分（≥80）预选', () => {
    expect(pickAutoRecommendation([reco(92)])?.case_id).toBe(1)
  })

  it('首位高分且明显领先次位（≥15 分）才预选', () => {
    expect(pickAutoRecommendation([reco(95, 1), reco(80, 2)])?.case_id).toBe(1)
    expect(pickAutoRecommendation([reco(90, 1), reco(85, 2)])).toBeNull()
  })

  it('首位低于 80 分不预选，空列表返回 null', () => {
    expect(pickAutoRecommendation([reco(70)])).toBeNull()
    expect(pickAutoRecommendation([])).toBeNull()
  })
})

describe('formatContacts（联系人展示串）', () => {
  it('姓名+电话组合，顿号多人、分号分组，过滤空条目', () => {
    expect(
      formatContacts([
        { role: '联系人', name: '张三', phone: '0757-1234567' },
        { role: '联系人', name: '李四', phone: null },
        { role: '联系电话', name: '', phone: '13900000000' },
      ]),
    ).toBe('张三（0757-1234567）；李四；13900000000')
  })

  it('空数组返回空串', () => {
    expect(formatContacts([])).toBe('')
  })
})

describe('resolveMediaUrl（media 链接解析）', () => {
  it('相对链接按显式 origin 拼接', () => {
    expect(resolveMediaUrl('/media/a.pdf', 'http://127.0.0.1:8002')).toBe('http://127.0.0.1:8002/media/a.pdf')
  })

  it('绝对地址原样返回，空值返回空串', () => {
    expect(resolveMediaUrl('https://x.cn/media/a.pdf')).toBe('https://x.cn/media/a.pdf')
    expect(resolveMediaUrl(null)).toBe('')
    expect(resolveMediaUrl('')).toBe('')
  })

  it('media 鉴权：resolveMediaUrl 只拼绝对地址，票据由 resolveMediaUrlWithAuth 追加（M-2）', async () => {
    // resolveMediaUrl 不再碰 token——JWT 不能进 URL（access log / Referer）。
    // 票据换取是异步的，走 resolveMediaUrlWithAuth + withDownloadTicket。
    const dt = await import('@/lib/download-ticket')
    const spy = vi.spyOn(dt, 'withDownloadTicket').mockResolvedValue('http://127.0.0.1:8002/media/a.pdf?ticket=TK')
    try {
      expect(resolveMediaUrl('/media/a.pdf', 'http://127.0.0.1:8002')).toBe('http://127.0.0.1:8002/media/a.pdf')
      await expect(resolveMediaUrlWithAuth('/media/a.pdf', 'http://127.0.0.1:8002')).resolves.toBe(
        'http://127.0.0.1:8002/media/a.pdf?ticket=TK',
      )
      expect(spy).toHaveBeenCalledWith('http://127.0.0.1:8002/media/a.pdf')
    } finally {
      spy.mockRestore()
    }
  })

  it('resolveMediaUrlWithAuth：空值/绝对地址不白跑一次换票', async () => {
    await expect(resolveMediaUrlWithAuth(null)).resolves.toBe('')
    // 绝对地址（第三方 OSS 等）也直接返回，不消耗票据
    await expect(resolveMediaUrlWithAuth('https://x.cn/a.pdf')).resolves.toBe('https://x.cn/a.pdf')
  })
})
