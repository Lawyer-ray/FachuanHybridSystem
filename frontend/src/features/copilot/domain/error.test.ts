import { describe, expect, it } from 'vitest'

import { classifyError, diagnosticsOf, splitLanePrefix } from './error'

describe('splitLanePrefix', () => {
  it('剥掉多答的 agent 前缀', () => {
    expect(splitLanePrefix('pi：连接中断，请重试')).toEqual({ lane: 'pi', body: '连接中断，请重试' })
    expect(splitLanePrefix('openai-agents：超时')).toEqual({ lane: 'openai-agents', body: '超时' })
  })

  it('没有前缀时原样返回', () => {
    expect(splitLanePrefix('连接中断，请重试')).toEqual({ lane: '', body: '连接中断，请重试' })
  })

  it('正文里带中文冒号不会误判为前缀', () => {
    expect(splitLanePrefix('注意：这条不是前缀')).toEqual({ lane: '', body: '注意：这条不是前缀' })
  })
})

describe('classifyError', () => {
  it('空值不产出错误对象', () => {
    expect(classifyError(null)).toBeNull()
    expect(classifyError('')).toBeNull()
  })

  it('断流：可重发 + 提示已生成内容仍在', () => {
    const e = classifyError('连接中断，请重试')!
    expect(e.code).toBe('network')
    expect(e.resendable).toBe(true)
    expect(e.hint).toContain('再发一次')
  })

  it('EOF 未见 done 单独成一类（warn，不是 error）', () => {
    const e = classifyError('与本轮的连接提前结束，回答可能不完整')!
    expect(e.code).toBe('stream_broken')
    expect(e.severity).toBe('warn')
  })

  it('限流是 warn 且明说不是用户的问题', () => {
    const e = classifyError('当前使用人数较多，请稍后再试')!
    expect(e.code).toBe('rate_limited')
    expect(e.severity).toBe('warn')
    expect(e.hint).toContain('不是你的问题')
  })

  it('降级（只跑主后端）是 info 且不可重发', () => {
    const e = classifyError('并发席位已满，本轮只跑了主后端')!
    expect(e.code).toBe('capability')
    expect(e.severity).toBe('info')
    expect(e.resendable).toBe(false)
  })

  it('多答前缀不影响归类（并保留正文）', () => {
    const e = classifyError('dsh：连接中断，请重试')!
    expect(e.code).toBe('network')
    expect(e.message).toBe('连接中断，请重试')
  })

  it('未知文案落 unknown，并建议复制诊断', () => {
    const e = classifyError('某个我们从没见过的新错误')!
    expect(e.code).toBe('unknown')
    expect(e.message).toBe('某个我们从没见过的新错误')
    expect(e.hint).toContain('复制诊断')
  })
})

describe('diagnosticsOf', () => {
  it('带时间、错误码与原文（可直接发给人排查）', () => {
    const e = classifyError('连接中断，请重试')!
    const text = diagnosticsOf(e, Date.parse('2026-11-20T01:02:03Z'))
    expect(text).toContain('2026-11-20T01:02:03.000Z')
    expect(text).toContain('错误码：network')
    expect(text).toContain('原文：连接中断，请重试')
  })
})
