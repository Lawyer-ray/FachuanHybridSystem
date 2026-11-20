import { describe, expect, it } from 'vitest'

import {
  classifyError,
  diagnosticsOf,
  encodeError,
  errorActions,
  mergeError,
  splitErrorEnvelope,
  splitLanePrefix,
} from './error'

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

describe('classifyError：code 优先', () => {
  it('命中 code 就走 code 表，连 detail 一起带出来', () => {
    const e = classifyError({
      code: 'rate_limited',
      message: '当前使用人数较多，请稍后再试',
      scope: 'agent',
      detail: { backend: 'pi', model: 'gpt-5', retry_after: 12 },
    })!
    expect(e.code).toBe('rate_limited')
    expect(e.kind).toBe('rate_limited')
    expect(e.severity).toBe('warn')
    expect(e.scope).toBe('agent')
    expect(e.detail).toEqual({ backend: 'pi', model: 'gpt-5', retry_after: 12 })
    expect(e.resendable).toBe(true)
  })

  it('code 与文案冲突时 code 赢（文案只是展示原文）', () => {
    // 文案说「连接中断」，但后端明确说是能力不支持：不能按网络错误引导用户重发
    const e = classifyError({ code: 'capability_unsupported', message: '连接中断，请重试' })!
    expect(e.code).toBe('capability_unsupported')
    expect(e.kind).toBe('capability')
    expect(e.resendable).toBe(false)
  })

  it('未知 code 落 unknown 且不抛（前端比后端旧时不能白屏）', () => {
    expect(() =>
      classifyError({ code: 'brand_new_code', message: '某个我们从没见过的新错误' }),
    ).not.toThrow()
    const e = classifyError({ code: 'brand_new_code', message: '某个我们从没见过的新错误' })!
    expect(e.code).toBe('unknown')
    // 原始 code 留着：支持人员要能看到后端到底发了什么
    expect(e.rawCode).toBe('brand_new_code')
    expect(e.hint).toContain('复制诊断')
  })

  it('未知 code 但文案能对上：退回文案分类（不是一律 unknown）', () => {
    const e = classifyError({ code: 'brand_new_code', message: 'dsh：连接中断，请重试' })!
    expect(e.code).toBe('backend_unavailable')
    expect(e.kind).toBe('network')
    expect(e.lane).toBe('dsh')
    expect(e.rawCode).toBe('brand_new_code')
  })

  it('后端历史拼写 context_overflow 归到 context_exceeded（同一个意思两个名字）', () => {
    const e = classifyError({ code: 'context_overflow', message: '上下文超出窗口' })!
    expect(e.code).toBe('context_exceeded')
    expect(errorActions(e).map((a) => a.id)).toEqual(['compact_context'])
  })

  it('没有对应 code 的旧拼写（busy/auth）老实落 unknown，不硬套动作', () => {
    expect(classifyError({ code: 'auth', message: '凭据失效' })!.code).toBe('unknown')
    expect(classifyError({ code: 'busy', message: '执行位满' })!.code).toBe('unknown')
  })

  it('空值不产出错误对象', () => {
    expect(classifyError(null)).toBeNull()
    expect(classifyError('')).toBeNull()
    expect(classifyError(undefined)).toBeNull()
    // 只有 code、没有正文：没东西可展示
    expect(classifyError({ code: 'rate_limited', message: '  ' })).toBeNull()
  })
})

describe('classifyError：旧后端（无 code）走文案兜底', () => {
  it('断流：可重发 + 提示已生成内容仍在', () => {
    const e = classifyError('连接中断，请重试')!
    expect(e.code).toBe('backend_unavailable')
    expect(e.kind).toBe('network')
    expect(e.rawCode).toBe('')
    expect(e.resendable).toBe(true)
    expect(e.hint).toContain('再发一次')
  })

  it('EOF 未见 done 单独成一类（warn，不是 error）', () => {
    const e = classifyError('与本轮的连接提前结束，回答可能不完整')!
    expect(e.kind).toBe('stream_broken')
    expect(e.code).toBe('upstream_timeout')
    expect(e.severity).toBe('warn')
  })

  it('限流是 warn 且明说不是用户的问题', () => {
    const e = classifyError('当前使用人数较多，请稍后再试')!
    expect(e.code).toBe('rate_limited')
    expect(e.severity).toBe('warn')
    expect(e.hint).toContain('不是你的问题')
  })

  it('降级（只跑主后端）是 info 且不可重发、不给「换个后端」按钮', () => {
    const e = classifyError('并发席位已满，本轮只跑了主后端')!
    expect(e.kind).toBe('capability')
    expect(e.severity).toBe('info')
    expect(e.resendable).toBe(false)
    // 席位满换哪个后端都是满的，按钮点了没用 → 不给动作
    expect(e.code).toBe('unknown')
    expect(errorActions(e)).toEqual([])
  })

  it('压缩失败不冒充「上下文超限」（否则会推出一个只会再失败一次的按钮）', () => {
    const e = classifyError('压缩失败，请稍后再试')!
    expect(e.kind).toBe('compact')
    expect(e.code).toBe('unknown')
    expect(errorActions(e)).toEqual([])
  })

  it('多答前缀不影响归类（并保留正文与来源）', () => {
    const e = classifyError('dsh：连接中断，请重试')!
    expect(e.code).toBe('backend_unavailable')
    expect(e.message).toBe('连接中断，请重试')
    expect(e.lane).toBe('dsh')
  })

  it('未知文案落 unknown，并建议复制诊断', () => {
    const e = classifyError('某个我们从没见过的新错误')!
    expect(e.code).toBe('unknown')
    expect(e.message).toBe('某个我们从没见过的新错误')
    expect(e.hint).toContain('复制诊断')
  })
})

describe('envelope：结构化字段随 lastError 一个字符串走', () => {
  it('编码后能被原样拆回来（store 只存字符串，不必改状态形状）', () => {
    const raw = encodeError({
      code: 'rate_limited',
      message: '当前使用人数较多',
      scope: 'agent',
      detail: { retry_after: 8, backend: 'pi' },
    })
    expect(splitErrorEnvelope(raw)).toEqual({
      message: '当前使用人数较多',
      code: 'rate_limited',
      scope: 'agent',
      detail: { retry_after: 8, backend: 'pi' },
    })
    const e = classifyError(raw)!
    expect(e.code).toBe('rate_limited')
    expect(e.message).toBe('当前使用人数较多')
  })

  it('没有结构化字段时退化成纯文案（旧写法一字不改）', () => {
    const raw = encodeError({ message: '连接中断，请重试' })
    expect(raw).toBe('连接中断，请重试')
    expect(splitErrorEnvelope(raw)).toEqual({ message: '连接中断，请重试' })
  })

  it('坏 JSON 只丢结构化字段，不吞掉整条错误', () => {
    const raw = '连接中断，请重试\u0001copilot-error:{不是json'
    expect(splitErrorEnvelope(raw)).toEqual({ message: '连接中断，请重试' })
    expect(classifyError(raw)!.message).toBe('连接中断，请重试')
  })

  it('多答前缀在 envelope 里照样能剥', () => {
    const raw = encodeError({ code: 'upstream_timeout', message: 'dsh：连接提前结束' })
    const e = classifyError(raw)!
    expect(e.lane).toBe('dsh')
    expect(e.message).toBe('连接提前结束')
  })
})

describe('errorActions：code → 动作', () => {
  it('rate_limited 读 detail.retry_after 出倒计时按钮', () => {
    const e = classifyError({ code: 'rate_limited', message: '限流', detail: { retry_after: 12 } })!
    expect(errorActions(e)).toEqual([{ id: 'retry', label: '等 12 秒后重试', waitSeconds: 12 }])
  })

  it('后端实际字段叫 retry_after_seconds 也认（契约写的是 retry_after，两个都读）', () => {
    const e = classifyError({
      code: 'rate_limited',
      message: '当前使用人数较多，请稍后重试',
      detail: { reason: 'HTTP 429', retry_after_seconds: 9 },
    })!
    expect(errorActions(e)).toEqual([{ id: 'retry', label: '等 9 秒后重试', waitSeconds: 9 }])
  })

  it('retry_after 是数字字符串也认；不是数字就不编秒数', () => {
    const str = classifyError({ code: 'rate_limited', message: '限流', detail: { retry_after: '7' } })!
    expect(errorActions(str)[0]!.waitSeconds).toBe(7)
    const bad = classifyError({ code: 'rate_limited', message: '限流', detail: { retry_after: 'soon' } })!
    expect(errorActions(bad)).toEqual([{ id: 'retry', label: '稍后重试', waitSeconds: undefined }])
  })

  it('retry_after=0（现在已经可以了）不给「等 0 秒」这种废话', () => {
    const e = classifyError({ code: 'rate_limited', message: '限流', detail: { retry_after: 0 } })!
    expect(errorActions(e)[0]!.label).toBe('重试')
  })

  it('capability_unsupported / context_exceeded 各自的动作', () => {
    expect(
      errorActions(classifyError({ code: 'capability_unsupported', message: '不支持' })!),
    ).toEqual([{ id: 'switch_backend', label: '换个后端' }])
    expect(errorActions(classifyError({ code: 'context_exceeded', message: '超限' })!)).toEqual([
      { id: 'compact_context', label: '压缩上下文' },
    ])
  })

  it('其余 code 没有对应动作（组件据此不渲染按钮）', () => {
    for (const code of ['quota_exhausted', 'backend_unavailable', 'upstream_timeout', 'tool_args_invalid', 'unknown']) {
      const e = classifyError({ code, message: '出错了' })!
      expect(errorActions(e)).toEqual([])
    }
  })
})

describe('mergeError：同 code 合并计数', () => {
  const a = classifyError({ code: 'rate_limited', message: '限流', detail: { retry_after: 5 } })!

  it('同 code 累加次数、文案取最新', () => {
    const b = classifyError({ code: 'rate_limited', message: '又限流了' })!
    const merged = mergeError(a, b)
    expect(merged.repeat).toBe(2)
    expect(merged.message).toBe('又限流了')
  })

  it('code 变了就是另一件事，从头计数', () => {
    const c = classifyError({ code: 'backend_unavailable', message: '后端没起来' })!
    expect(mergeError(a, c).repeat).toBe(1)
  })

  it('没有上一条时首次计数为 1', () => {
    expect(mergeError(null, a).repeat).toBe(1)
  })
})

describe('diagnosticsOf：能拿去问技术支持', () => {
  it('带时间、错误码与原文（可直接发给人排查）', () => {
    const e = classifyError('连接中断，请重试')!
    const text = diagnosticsOf(e, Date.parse('2026-11-20T01:02:03Z'))
    expect(text).toContain('2026-11-20T01:02:03.000Z')
    expect(text).toContain('错误码：backend_unavailable')
    expect(text).toContain('原文：连接中断，请重试')
  })

  it('detail 进诊断：说清哪个后端、哪个模型、还能等几秒', () => {
    const e = classifyError({
      code: 'rate_limited',
      message: '当前使用人数较多',
      scope: 'agent',
      detail: { retry_after: 12, model: 'gpt-5', backend: 'pi' },
    })!
    const text = diagnosticsOf(e, Date.parse('2026-11-20T01:02:03Z'))
    expect(text).toContain('范围：agent')
    // 键排序后拼接，两台机器上的诊断可以直接 diff
    expect(text).toContain('详情：backend=pi | model=gpt-5 | retry_after=12')
  })

  it('未知 code 时把后端原始码也写进去', () => {
    const e = classifyError({ code: 'brand_new_code', message: '没见过' })!
    expect(diagnosticsOf(e)).toContain('后端原始码：brand_new_code')
  })

  it('合并计数后带上连续次数', () => {
    const one = classifyError('连接中断，请重试')!
    const merged = mergeError(one, classifyError('连接中断，请重试')!)
    expect(diagnosticsOf(merged)).toContain('连续次数：2')
  })

  it('detail 里的嵌套值也能写（且不抛）', () => {
    const e = classifyError({ code: 'tool_args_invalid', message: '参数不合法', detail: { args: { a: 1 } } })!
    expect(diagnosticsOf(e)).toContain('args={"a":1}')
  })
})
