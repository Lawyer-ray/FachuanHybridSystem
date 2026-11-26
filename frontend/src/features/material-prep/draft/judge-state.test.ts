/**
 * 分歧裁定的**门禁可见性**：把 `summary.engine_disagreements_judge` 翻成一句人能行动的话。
 *
 * 这组用例锁的是「开关勾着却什么也没发生」那条链的每一环：
 *
 * 1. 收窄：旧任务缺键 → `null`（整条提示不渲染，与引入前逐位一致）；空对象也算缺键。
 * 2. 判定条件：只有 `requested && !enabled` 才出提示——用户自己关的不许提示（那是他的选择），
 *    生效了的也不许提示（分歧清单自己会说裁了几条）。
 * 3. 文案精确到**可执行的配置项**：`gate_off` 与 `missing_key` 是两个不同的配置项，
 *    合成一句「未启用」等于让律师去猜该找管理员改哪一项。
 * 4. 落草稿：`null` 不写入且清旧值（留上一次的「未生效」是假信息）。
 */
import { describe, expect, it } from 'vitest'

import type { DraftState, JudgeState } from '../types'
import { judgeGateNotice, judgeGateReasonText, judgeOutcomeNote, mergeJudgeStates, readJudgeState } from './judge-state'
import { withJudgeState } from './state'

function state(overrides: Partial<JudgeState> = {}): JudgeState {
  return {
    requested: true,
    enabled: false,
    reason: 'missing_key',
    annotated: 0,
    accepted: 0,
    human: 0,
    ...overrides,
  }
}

describe('readJudgeState：不可信输入的收窄', () => {
  it('缺键 / 非对象 → null（旧任务的形状）', () => {
    expect(readJudgeState(undefined)).toBeNull()
    expect(readJudgeState(null)).toBeNull()
    expect(readJudgeState('x')).toBeNull()
    expect(readJudgeState(0)).toBeNull()
  })

  it('空对象也当缺键：不编造 enabled:false', () => {
    // 后端归一化前的残留形状；按「没有这件事」处理比编一个状态更诚实
    expect(readJudgeState({})).toBeNull()
  })

  it('后端固定形状零值原样收窄', () => {
    const out = readJudgeState({ enabled: false, requested: false, reason: 'not_requested' })
    expect(out).toEqual({
      requested: false,
      enabled: false,
      reason: 'not_requested',
      annotated: 0,
      accepted: 0,
      human: 0,
    })
  })

  it('原因码缺失时按 enabled 反推，不误报成 unknown', () => {
    expect(readJudgeState({ enabled: true, requested: true })?.reason).toBe('enabled')
    expect(readJudgeState({ enabled: false, requested: true })?.reason).toBe('unknown')
  })

  it('不认识的原因码保留成 unknown（后端加码时不丢信息、也不冒充某个已知原因）', () => {
    expect(readJudgeState({ enabled: false, requested: true, reason: 'quota_exhausted' })?.reason).toBe('unknown')
  })

  it('计数字段是脏值时兜底成 0', () => {
    const out = readJudgeState({ enabled: true, requested: true, annotated: 'x', accepted: -3, human: NaN })
    expect(out?.annotated).toBe(0)
    expect(out?.accepted).toBe(0)
    expect(out?.human).toBe(0)
  })
})

describe('judgeGateNotice：只有「要求了但没生效」才说话', () => {
  it('缺 key → 指出具体配置项', () => {
    expect(judgeGateNotice(state())).toContain('OCR_JUDGE_API_KEY')
  })

  it('总闸没开 → 指出另一个配置项（与缺 key 不是一句话）', () => {
    const text = judgeGateNotice(state({ reason: 'gate_off' }))
    expect(text).toContain('OCR_JUDGE_ENABLED')
    expect(text).not.toContain('OCR_JUDGE_API_KEY')
  })

  it('生效了不出提示（分歧清单自己会说裁了几条）', () => {
    expect(judgeGateNotice(state({ enabled: true, reason: 'enabled' }))).toBeNull()
  })

  it('用户自己关的不出提示（那是他的选择）', () => {
    expect(judgeGateNotice(state({ requested: false, reason: 'not_requested' }))).toBeNull()
  })

  it('旧任务（null）不出提示', () => {
    expect(judgeGateNotice(null)).toBeNull()
    expect(judgeGateNotice(undefined)).toBeNull()
  })

  it('文案必须说明「分歧去哪了」——否则律师会以为分歧也没了', () => {
    expect(judgeGateNotice(state())).toContain('全部进人工清单')
  })
})

describe('judgeOutcomeNote：收尾提示的尾句', () => {
  it('没生效 → 带原因（toast 里那句更短，完整因果留给横幅）', () => {
    expect(judgeOutcomeNote(state())).toBe('分歧自动裁定未生效（本环境未配置 OCR_JUDGE_API_KEY）')
  })

  it('生效且裁过 → 报裁定条数与待人工条数', () => {
    const note = judgeOutcomeNote(state({ enabled: true, reason: 'enabled', annotated: 5, accepted: 2, human: 3 }))
    expect(note).toBe('已自动裁定 2 条分歧，3 条待人工')
  })

  it('生效但一条没裁成 → 说清「转了人工」，不装作成功', () => {
    const note = judgeOutcomeNote(state({ enabled: true, reason: 'enabled', annotated: 4, accepted: 0, human: 4 }))
    expect(note).toContain('4 条')
    expect(note).toContain('人工清单')
  })

  it('生效且没有分歧送判 → 不说任何话', () => {
    expect(judgeOutcomeNote(state({ enabled: true, reason: 'enabled', annotated: 0 }))).toBeNull()
  })

  it('没要求判 → 不说任何话', () => {
    expect(judgeOutcomeNote(state({ requested: false, reason: 'not_requested' }))).toBeNull()
  })
})

describe('judgeGateReasonText：未知原因不能冒充已知原因', () => {
  it('unknown 给中性说法', () => {
    expect(judgeGateReasonText('unknown')).toBe('本环境未启用打分器')
  })
})

describe('mergeJudgeStates：多个 PDF 的卷级合并', () => {
  it('全空 → null', () => {
    expect(mergeJudgeStates([null, undefined])).toBeNull()
  })

  it('优先保留「要求了但没生效」——那是唯一需要律师知道且能上报的事实', () => {
    const ok = state({ enabled: true, reason: 'enabled', annotated: 3, accepted: 1 })
    const blocked = state()
    expect(mergeJudgeStates([ok, blocked, null])).toBe(blocked)
  })

  it('都生效时优先取「真判过东西」的那条', () => {
    const idle = state({ enabled: true, reason: 'enabled', annotated: 0 })
    const judged = state({ enabled: true, reason: 'enabled', annotated: 7, accepted: 2 })
    expect(mergeJudgeStates([idle, judged])).toBe(judged)
  })

  it('都只是「没要求」时取第一条（避免 undefined 漏到界面）', () => {
    const a = state({ requested: false, reason: 'not_requested' })
    expect(mergeJudgeStates([null, a])).toBe(a)
  })
})

describe('withJudgeState：落草稿', () => {
  const empty = { segs: [], mats: [], infos: [] } as unknown as DraftState

  it('有值就写进去（刷新后仍能解释「为什么全是人工」）', () => {
    expect(withJudgeState(empty, state()).judgeState).toEqual(state())
  })

  it('null 不写入，且清掉旧值（留着上一次的「未生效」是假信息）', () => {
    const withOld = withJudgeState(empty, state())
    const cleared = withJudgeState(withOld, null)
    expect(cleared.judgeState).toBeUndefined()
    expect('judgeState' in cleared).toBe(false)
  })

  it('本来就是空的时候返回同一个对象（不制造无意义的引用变化）', () => {
    expect(withJudgeState(empty, null)).toBe(empty)
  })
})
