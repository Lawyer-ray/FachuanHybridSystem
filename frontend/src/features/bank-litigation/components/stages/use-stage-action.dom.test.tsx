// @vitest-environment jsdom
/**
 * 阶段动作引擎单测（jsdom）。
 *
 * 这套状态机是「机器在干活」的可信度来源：进度百分比、重试、中断等人、
 * 并行子任务、最终失败都写在界面上。演示用的 setTimeout 剧本是假的，
 * **但状态机的语义是真的** —— 所以这里只钉语义，不钉耗时：
 * - 跑完所有步骤 → done / percent 100 / summary 由 toSummary 投影
 * - run 抛错 → failed + error（不吞异常）
 * - 某步 fail → 立刻 failed，后面步骤不再跑
 * - 某步 confirm → 停在 awaiting，点 confirm 才继续
 * - 某步 retry → 先记 warn 日志、retries 累加，重试完继续
 * - 某步 parallel → 每子任务一条 kind='sub' 日志
 * - reset 中途打断：旧异步不再写状态
 *
 * 时间：把全局 setTimeout 换成立刻触发，只保留事件循环让出。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useStageAction, type ActionStep } from './use-stage-action'

const realSetTimeout = globalThis.setTimeout

/** 让出若干轮宏任务（等价于 await 几次 setImmediate），直到条件成立 */
async function drainUntil(cond: () => boolean, maxTicks = 100) {
  for (let i = 0; i < maxTicks; i++) {
    if (cond()) return
    await new Promise((r) => setImmediate(r))
  }
}

/** 每步 1ms、fixed 关掉波动，让断言只看语义 */
function step(text: string, extra: Partial<ActionStep> = {}): ActionStep {
  return { text, ms: 1, fixed: true, ...extra }
}

beforeEach(() => {
  // 剧本里的 sleep 全部立刻返回；jitter 在 fixed 步上也是恒等
  vi.stubGlobal('setTimeout', ((fn: () => void) => setImmediate(fn)) as unknown as typeof setTimeout)
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  globalThis.setTimeout = realSetTimeout
})

describe('useStageAction · 正常跑完', () => {
  it('初值是 idle / 0% / 空日志', () => {
    const { result } = renderHook(() => useStageAction({ steps: [step('一步')] }))
    expect(result.current.phase).toBe('idle')
    expect(result.current.percent).toBe(0)
    expect(result.current.log).toEqual([])
    expect(result.current.stepIndex).toBe(0)
  })

  it('走完所有步骤：done / 100% / 每步一条 info 日志 / 「完成」收尾', async () => {
    const steps = [step('读取案卷'), step('识别材料'), step('生成清单')]
    const { result } = renderHook(() => useStageAction({ steps }))

    await act(async () => {
      await result.current.execute()
    })

    expect(result.current.phase).toBe('done')
    expect(result.current.percent).toBe(100)
    expect(result.current.error).toBe('')
    expect(result.current.progress).toBe('')
    // 三步各一条 info + 末尾一条「完成」
    expect(result.current.log.filter((l) => l.kind === 'info').map((l) => l.text)).toEqual([
      '读取案卷',
      '识别材料',
      '生成清单',
    ])
    expect(result.current.log.at(-1)).toMatchObject({ text: '完成', kind: 'ok' })
    // 日志行都带 HH:mm:ss 时刻
    for (const line of result.current.log) expect(line.at).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })

  it('没给 run 时 summary 用「已完成」兜底', async () => {
    const { result } = renderHook(() => useStageAction({ steps: [step('一步')] }))
    await act(async () => {
      await result.current.execute()
    })
    expect(result.current.summary).toBe('已完成')
  })

  it('给了 run + toSummary 时，用真实回包投影 summary（不假装成功）', async () => {
    const run = vi.fn().mockResolvedValue({ saved: 12 })
    const toSummary = vi.fn((r: { saved: number }) => `已保存 ${r.saved} 份`)
    const { result } = renderHook(() => useStageAction({ steps: [step('一步')], run, toSummary }))

    await act(async () => {
      await result.current.execute()
    })

    expect(run).toHaveBeenCalledTimes(1)
    expect(result.current.summary).toBe('已保存 12 份')
    expect(result.current.phase).toBe('done')
  })

  it('run 抛错：phase=failed、error 带原话，日志留一条 error', async () => {
    const run = vi.fn().mockRejectedValue(new Error('材料服务 502'))
    const { result } = renderHook(() => useStageAction({ steps: [step('一步')], run }))

    await act(async () => {
      await result.current.execute()
    })

    expect(result.current.phase).toBe('failed')
    expect(result.current.error).toBe('材料服务 502')
    expect(result.current.log.at(-1)).toMatchObject({ text: '失败：材料服务 502', kind: 'error' })
  })

  it('run 抛非 Error（字符串）也能拿到文案', async () => {
    const run = vi.fn().mockRejectedValue('裸字符串错误')
    const { result } = renderHook(() => useStageAction({ steps: [step('一步')], run }))
    await act(async () => {
      await result.current.execute()
    })
    expect(result.current.error).toBe('裸字符串错误')
  })
})

describe('useStageAction · 必然失败的一步', () => {
  it('fail 步当场判失败，后续步骤不再执行', async () => {
    const steps = [step('一月'), step('会炸的一步', { fail: 'OA 返回 500' }), step('永远不到')]
    const { result } = renderHook(() => useStageAction({ steps }))

    await act(async () => {
      await result.current.execute()
    })

    expect(result.current.phase).toBe('failed')
    expect(result.current.error).toBe('OA 返回 500')
    expect(result.current.log.map((l) => l.text)).toEqual(['一月', 'OA 返回 500'])
    expect(result.current.stepIndex).toBe(2)
  })
})

describe('useStageAction · 重试', () => {
  it('retry 步按 times 记 warn 并累加 retries，最后一条 ok 说重试成功', async () => {
    const steps = [step('登录 OA', { retry: { times: 2, delay: 1, reason: '验证码超时' } })]
    const { result } = renderHook(() => useStageAction({ steps }))

    await act(async () => {
      await result.current.execute()
    })

    const warns = result.current.log.filter((l) => l.kind === 'warn')
    expect(warns.map((l) => l.text)).toEqual(['验证码超时（第 1 次重试）', '验证码超时（第 2 次重试）'])
    expect(result.current.log.some((l) => l.kind === 'ok' && l.text === '重试成功 · 登录 OA')).toBe(true)
    expect(result.current.retries).toBe(2)
    expect(result.current.phase).toBe('done')
  })
})

describe('useStageAction · 中断等人', () => {
  it('confirm 步停在 awaiting，点 confirm 才继续到 done', async () => {
    const steps = [step('填表', { confirm: '请核对被告身份后继续' }), step('提交')]
    const { result } = renderHook(() => useStageAction({ steps }))

    let done!: Promise<void>
    act(() => {
      done = result.current.execute()
    })

    // 停在等人：phase=awaiting、confirmText 是剧本里那句
    await drainUntil(() => result.current.phase === 'awaiting')
    expect(result.current.phase).toBe('awaiting')
    expect(result.current.confirmText).toBe('请核对被告身份后继续')
    expect(result.current.stepIndex).toBe(1)

    act(() => result.current.confirm())
    await act(async () => {
      await done
    })

    expect(result.current.phase).toBe('done')
    expect(result.current.confirmText).toBe('')
    expect(result.current.log.some((l) => l.text === '已确认，继续' && l.kind === 'ok')).toBe(true)
    expect(result.current.log.some((l) => l.text === '提交')).toBe(true)
  })

  it('没人点 confirm 时一直挂着（不会自己往下跑）', async () => {
    const steps = [step('填表', { confirm: '等律师确认' })]
    const { result } = renderHook(() => useStageAction({ steps }))

    act(() => {
      void result.current.execute()
    })

    await drainUntil(() => result.current.phase === 'awaiting')
    expect(result.current.phase).toBe('awaiting')
    // 再让出几轮宏任务后仍在 awaiting —— 没有人点确认就不该自己往下跑
    for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r))
    expect(result.current.phase).toBe('awaiting')
    expect(result.current.log.some((l) => l.text === '提交')).toBe(false)
  })
})

describe('useStageAction · 并行子任务', () => {
  it('parallel 里每个子任务各一条 kind=sub 日志，文字带 ↳ 前缀', async () => {
    const steps = [step('抓取材料', { parallel: ['读起诉状', '读证据清单'] })]
    const { result } = renderHook(() => useStageAction({ steps }))

    await act(async () => {
      await result.current.execute()
    })

    const subs = result.current.log.filter((l) => l.kind === 'sub')
    expect(subs.map((l) => l.text)).toEqual(['  ↳ 读起诉状', '  ↳ 读证据清单'])
    // 子任务日志在本步 info 之前
    const infoIdx = result.current.log.findIndex((l) => l.text === '抓取材料')
    expect(result.current.log.findIndex((l) => l.kind === 'sub')).toBeLessThan(infoIdx)
  })
})

describe('useStageAction · reset 打断', () => {
  it('reset 把状态清回初值，且旧的异步不再往下写', async () => {
    const steps = [step('填表', { confirm: '等确认' }), step('提交')]
    const { result } = renderHook(() => useStageAction({ steps }))

    act(() => {
      void result.current.execute()
    })
    await drainUntil(() => result.current.phase === 'awaiting')
    expect(result.current.phase).toBe('awaiting')

    act(() => result.current.reset())
    expect(result.current.phase).toBe('idle')
    expect(result.current.log).toEqual([])
    expect(result.current.stepIndex).toBe(0)

    // reset 释放了挂起的 confirm 回调，但 aborted 标记会让循环直接 return
    for (let i = 0; i < 10; i++) await new Promise((r) => setImmediate(r))
    expect(result.current.phase).toBe('idle')
    expect(result.current.log).toEqual([])
  })

  it('reset 后可以重新 execute（aborted 标记在下一轮事件循环被清掉）', async () => {
    const steps = [step('一步')]
    const { result } = renderHook(() => useStageAction({ steps }))

    act(() => result.current.reset())
    // reset 用 setTimeout(0) 清标记；等它跑完
    await new Promise((r) => setImmediate(r))

    await act(async () => {
      await result.current.execute()
    })
    expect(result.current.phase).toBe('done')
  })
})

describe('useStageAction · 进度权重', () => {
  it('进度分 6 段平滑推进（按权重），等长两段在中点正好 50%，收尾 100%', async () => {
    const seen: number[] = []
    const steps = [step('第一步', { ms: 100 }), step('第二步', { ms: 100 })]

    const { result } = renderHook(() => useStageAction({ steps }))

    let done!: Promise<void>
    act(() => {
      done = result.current.execute()
    })
    // 逐拍采样：React 的批量更新让「渲染即记录」拿不到中间值，
    // 所以手动让出宏任务并在每拍读一次 result.current.percent。
    for (let i = 0; i < 100; i++) {
      seen.push(result.current.percent)
      if (result.current.phase === 'done') break
      await new Promise((r) => setImmediate(r))
    }
    await act(async () => {
      await done
    })

    // 单调不减
    for (let i = 1; i < seen.length; i++) expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1]!)
    // 平滑推进：出现过 0 与 100 之间、且非 0/100 的中间值（不是一步跳到 100）
    expect(seen.some((p) => p > 0 && p < 100)).toBe(true)
    expect(seen).toContain(50)
    expect(seen.at(-1)).toBe(100)
  })

  it('权重按 ms 分配：短步骤在总进度中占的比例更小', async () => {
    // 第一步 20ms、第二步 80ms（总 100）→ 第一步走完时约 20%
    const steps = [step('短', { ms: 20 }), step('长', { ms: 80 })]
    const { result } = renderHook(() => useStageAction({ steps }))

    let done!: Promise<void>
    act(() => {
      done = result.current.execute()
    })
    let firstStepEndPercent = -1
    for (let i = 0; i < 100; i++) {
      // 日志里出现第二步的 info 行时，说明第一步已经走完
      if (result.current.log.some((l) => l.text === '长')) {
        firstStepEndPercent = result.current.percent
        break
      }
      await new Promise((r) => setImmediate(r))
    }
    await act(async () => {
      await done
    })

    // 第一步只占 20/100 —— 走完时进度远不到一半
    expect(firstStepEndPercent).toBeGreaterThanOrEqual(0)
    expect(firstStepEndPercent).toBeLessThan(50)
  })
})
