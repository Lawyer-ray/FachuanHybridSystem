import { describe, expect, it } from 'vitest'

import { canContinue, canRegenerate } from './turn-actions'

/**
 * 两个判据的语义锁死（node 环境，纯函数）。
 *
 * 重点不是「能返回 true」，而是**旧数据不能退化**：`finish_reason` 是后加的
 * 字段，历史行只有 `truncated`；任何一处只看新字段，都会让老会话里所有被
 * 停止过的回答失去「可继续」。
 */
describe('canContinue：被中断/出错时可继续', () => {
  it('truncated 为 true 即可继续（旧数据只有这一路信号）', () => {
    expect(canContinue({ truncated: true })).toBe(true)
  })

  it('落库终态 cancelled / error 也可继续（生成器被关闭时没有 truncated）', () => {
    expect(canContinue({ finishReason: 'cancelled' })).toBe(true)
    expect(canContinue({ finishReason: 'error' })).toBe(true)
  })

  it('蛇形键（后端 metadata 原样传入）同样识别', () => {
    expect(canContinue({ finish_reason: 'cancelled' })).toBe(true)
    expect(canContinue({ finish_reason: 'error' })).toBe(true)
  })

  it('正常结束 / 降级 不可继续（再补写只会重复或画蛇添足）', () => {
    expect(canContinue({ finishReason: 'ok' })).toBe(false)
    expect(canContinue({ finishReason: 'degraded' })).toBe(false)
    expect(canContinue({ truncated: false, finishReason: 'ok' })).toBe(false)
  })

  it('未知终态 / 空输入一律不可用（宁可不给按钮，也不要点了没反应）', () => {
    expect(canContinue({})).toBe(false)
    expect(canContinue({ finishReason: '' })).toBe(false)
    expect(canContinue({ finishReason: null })).toBe(false)
    expect(canContinue({ finishReason: 42 as unknown as string })).toBe(false)
    expect(canContinue(null)).toBe(false)
    expect(canContinue(undefined)).toBe(false)
  })

  it('两路信号同时存在时任一成立即可（脚手架不会因字段缺失而退化）', () => {
    expect(canContinue({ truncated: true, finishReason: 'ok' })).toBe(true)
    expect(canContinue({ truncated: false, finishReason: 'error' })).toBe(true)
  })
})

describe('canRegenerate：已结束且非失败', () => {
  it('streaming=false 视为已结束 → 可重生成', () => {
    expect(canRegenerate({ streaming: false })).toBe(true)
  })

  it('显式 ended 也可（按轮记账的调用方）', () => {
    expect(canRegenerate({ ended: true })).toBe(true)
  })

  it('还在流式接收 → 不可（此时该显示「停止」）', () => {
    expect(canRegenerate({ streaming: true })).toBe(false)
    expect(canRegenerate({ streaming: true, ended: true })).toBe(false)
  })

  it('失败的栏 → 不可（本轮没跑起来，要的是整轮重跑）', () => {
    expect(canRegenerate({ streaming: false, failed: true })).toBe(false)
  })

  it('终态 error / cancelled → 不可（归 canContinue 管）', () => {
    expect(canRegenerate({ streaming: false, finishReason: 'error' })).toBe(false)
    expect(canRegenerate({ streaming: false, finish_reason: 'cancelled' })).toBe(false)
  })

  it('degraded 可重生成：别栏失败，这一栏自己是正常回答', () => {
    expect(canRegenerate({ streaming: false, finishReason: 'degraded' })).toBe(true)
  })

  it('状态未知 → 保守为不可用（半途的栏上不能出现会重复计费的动作）', () => {
    expect(canRegenerate({})).toBe(false)
    expect(canRegenerate({ ended: false, streaming: false })).toBe(false)
    expect(canRegenerate(null)).toBe(false)
    expect(canRegenerate(undefined)).toBe(false)
  })
})
