/**
 * 立案会话的阶段映射单测（node）。
 *
 * 这一份被 OA 立案与一张网立案两侧共用：
 * - PHASE_META：轮询阶段 → 语气 / 文案（idle..timeout 五种全覆盖）
 * - pillTone：把 StatusBadge 的 Tone 窄化成 Pill 接受的五种
 * - sessionTone：后端会话 status → 语气（一张网立案结果块 + OA 盖章面板共用）
 */
import { describe, expect, it } from 'vitest'

import { PHASE_META, pillTone, sessionTone } from './constants'

describe('PHASE_META', () => {
  it('五个阶段各有语气与文案，一句都不重复', () => {
    const phases = ['idle', 'submitting', 'running', 'done', 'timeout'] as const
    expect(Object.keys(PHASE_META).sort()).toEqual([...phases].sort())

    expect(PHASE_META.idle).toEqual({ tone: 'neutral', text: '待启动' })
    expect(PHASE_META.submitting).toEqual({ tone: 'blue', text: '正在提交' })
    expect(PHASE_META.running).toEqual({ tone: 'blue', text: '执行中' })
    // done 是中性色：终态不预设成功或失败，成败看后端 status
    expect(PHASE_META.done).toEqual({ tone: 'neutral', text: '已结束' })
    expect(PHASE_META.timeout).toEqual({ tone: 'yellow', text: '等待超时' })

    const texts = phases.map((p) => PHASE_META[p].text)
    expect(new Set(texts).size).toBe(phases.length)
  })
})

describe('pillTone', () => {
  it('purple 窄化成 neutral（Pill 不收 purple），其余原样透传', () => {
    expect(pillTone('purple')).toBe('neutral')
    expect(pillTone('green')).toBe('green')
    expect(pillTone('red')).toBe('red')
    expect(pillTone('yellow')).toBe('yellow')
    expect(pillTone('blue')).toBe('blue')
    expect(pillTone('neutral')).toBe('neutral')
  })
})

describe('sessionTone', () => {
  // OA 盖章 / 归档面板的「会话状态」胶囊复用这条映射，它认得哪些 status 值必须钉住：
  // 尤其 in_progress —— 后端 OA 会话会返回这个值，漏了就会灰成「中性」但实际在跑。
  it.each([
    ['success', 'green'],
    ['finished', 'green'],
    ['completed', 'green'],
    ['failed', 'red'],
    ['error', 'red'],
    ['running', 'blue'],
    ['pending', 'blue'],
    ['processing', 'blue'],
    ['in_progress', 'blue'],
    ['', 'neutral'],
    ['unknown_status', 'neutral'],
  ])('%s → %s', (status, tone) => {
    expect(sessionTone(status)).toBe(tone)
  })
})
