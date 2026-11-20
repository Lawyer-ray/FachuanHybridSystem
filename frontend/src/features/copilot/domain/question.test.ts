import { describe, expect, it } from 'vitest'

import type { QuestionDraft, QuestionItem } from './question'
import {
  answeredCount,
  buildAnswerBatch,
  emptyDraft,
  formatCountdown,
  isAnswered,
  normalizeQuestions,
  setFreeform,
  toggleSelection,
} from './question'

function q(over: Partial<QuestionItem> = {}): QuestionItem {
  return {
    id: 'q1',
    question: '哪一份合同？',
    context: '',
    options: [
      { label: '甲合同', description: '' },
      { label: '乙合同', description: '' },
    ],
    allowFreeform: true,
    allowMultiple: false,
    allowComment: false,
    ...over,
  }
}

function draft(over: Partial<QuestionDraft> = {}): QuestionDraft {
  return { ...emptyDraft(), ...over }
}

describe('normalizeQuestions', () => {
  it('收下后端标准形状', () => {
    const out = normalizeQuestions([
      {
        id: 'q1',
        question: '选哪个',
        context: '第三条原文',
        options: [{ label: 'A', description: '甲方案' }],
        allow_freeform: false,
        allow_multiple: true,
        allow_comment: true,
      },
    ])
    expect(out).toHaveLength(1)
    expect(out[0]).toEqual({
      id: 'q1',
      question: '选哪个',
      context: '第三条原文',
      options: [{ label: 'A', description: '甲方案' }],
      allowFreeform: false,
      allowMultiple: true,
      allowComment: true,
    })
  })

  it('options 写成字符串数组也收', () => {
    const out = normalizeQuestions([{ question: '随便', options: ['A', ' B ', ''] }])
    expect(out[0]!.options.map((o) => o.label)).toEqual(['A', 'B'])
  })

  it('缺 question 文本的题整条丢弃，不抛错', () => {
    expect(normalizeQuestions([{ id: 'x' }, 'not-an-object', null, { question: '有题面' }])).toHaveLength(1)
  })

  it('非数组输入返回空数组', () => {
    expect(normalizeQuestions(undefined)).toEqual([])
    expect(normalizeQuestions({ questions: [] })).toEqual([])
  })

  it('id 缺失按序补位（保证 React key 稳定）', () => {
    const out = normalizeQuestions([{ question: '一' }, { question: '二' }])
    expect(out.map((i) => i.id)).toEqual(['q1', 'q2'])
  })

  it('布尔缺省与后端同口径：允许自由文本、不允许单选多选与备注', () => {
    const out = normalizeQuestions([{ question: '一' }])
    expect(out[0]!.allowFreeform).toBe(true)
    expect(out[0]!.allowMultiple).toBe(false)
    expect(out[0]!.allowComment).toBe(false)
  })
})

describe('toggleSelection', () => {
  it('单选：点击替换，再点取消', () => {
    const item = q()
    const once = toggleSelection(item, draft(), '甲合同')
    expect(once.selections).toEqual(['甲合同'])
    expect(toggleSelection(item, once, '甲合同').selections).toEqual([])
  })

  it('单选：勾选项会清空已输入的自由文本（两者互斥）', () => {
    const next = toggleSelection(q(), draft({ text: '我要自己写' }), '乙合同')
    expect(next.selections).toEqual(['乙合同'])
    expect(next.text).toBe('')
  })

  it('多选：可累加，也可单独取消', () => {
    const item = q({ allowMultiple: true })
    const two = toggleSelection(item, toggleSelection(item, draft(), '甲合同'), '乙合同')
    expect(two.selections).toEqual(['甲合同', '乙合同'])
    expect(toggleSelection(item, two, '甲合同').selections).toEqual(['乙合同'])
  })
})

describe('setFreeform', () => {
  it('单选：输入文本会清空已选（答案编码互斥）', () => {
    const next = setFreeform(q(), draft({ selections: ['甲合同'] }), '两类都不是')
    expect(next.selections).toEqual([])
    expect(next.text).toBe('两类都不是')
  })

  it('单选：清空文本时不清 selections（用户可能只是想改字）', () => {
    const next = setFreeform(q(), draft({ selections: ['甲合同'], text: 'x' }), '  ')
    expect(next.selections).toEqual(['甲合同'])
    expect(next.text).toBe('  ')
  })

  it('多选：文本与选择共存', () => {
    const next = setFreeform(q({ allowMultiple: true }), draft({ selections: ['甲合同'] }), '还要 B')
    expect(next.selections).toEqual(['甲合同'])
    expect(next.text).toBe('还要 B')
  })
})

describe('buildAnswerBatch', () => {
  it('只回传已作答的题，未答的不出现在 batch 里', () => {
    const items = [q({ id: 'q1' }), q({ id: 'q2', question: '第二题' })]
    const batch = buildAnswerBatch(items, { q1: draft({ selections: ['甲合同'] }) })
    expect(batch).toEqual([{ id: 'q1', selections: ['甲合同'], text: '', comment: '' }])
  })

  it('不允许自由文本的题不回传 text（后端按 allow_freeform 决定是否采用）', () => {
    const items = [q({ allowFreeform: false })]
    const batch = buildAnswerBatch(items, { q1: draft({ text: '偷偷写的' }) })
    expect(batch).toHaveLength(1)
    expect(batch[0]!.text).toBe('')
  })

  it('不允许备注的题不回传 comment', () => {
    const items = [q()]
    const batch = buildAnswerBatch(items, { q1: draft({ selections: ['甲合同'], comment: '备注' }) })
    expect(batch[0]!.comment).toBe('')
  })

  it('全空草稿视为未答', () => {
    expect(buildAnswerBatch([q()], { q1: draft() })).toEqual([])
    expect(isAnswered(draft({ text: '   ' }))).toBe(false)
  })
})

describe('answeredCount / formatCountdown', () => {
  it('统计已答题数', () => {
    const items = [q({ id: 'q1' }), q({ id: 'q2' }), q({ id: 'q3' })]
    expect(answeredCount(items, { q1: draft({ selections: ['甲合同'] }), q3: draft({ text: 'x' }) })).toBe(2)
  })

  it('倒计时到点返回空串（UI 改用「已继续」文案）', () => {
    expect(formatCountdown(0)).toBe('')
    expect(formatCountdown(-5)).toBe('')
    expect(formatCountdown(9)).toBe('0:09')
    expect(formatCountdown(125)).toBe('2:05')
  })
})
