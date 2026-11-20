// @vitest-environment jsdom
/**
 * 分栏用量徽标（jsdom）。
 *
 * 必须成立的事实：
 * 1. **一行能比**：栏头要能直接读出「谁快、谁贵（token）、缓存命中多少」，
 *    否则多答只剩「并排几份意见」，比较那一半卖点是空的；
 * 2. **缺数不编数**：某个桶没上报就整段不渲染。显示 `0 tok` / `—` 会让律师
 *    以为这一栏真的只花了 0——比不显示糟糕得多；
 * 3. **估算值可辨识**：字符启发式估算必须带 `≈`（与 provider 上报值区分）；
 * 4. **明细不出现金额**：后端没有 cost 字段，前端也不拿单价乘。
 */

import { act, cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { laneUsageFromMetadata, type LaneUsage } from '../domain'
import { useCopilot } from '../store'
import type { ChatMessage, TurnStats } from '../types'
import { LaneUsageChip } from './LaneUsageChip'

function stats(over: Partial<TurnStats> = {}): TurnStats {
  return {
    firstDeltaAt: null,
    lastDeltaAt: null,
    doneAt: null,
    estTokens: 0,
    exactTokens: null,
    samples: [],
    ...over,
  }
}

function assistant(over: Partial<ChatMessage> = {}): ChatMessage {
  return { id: 'a-1', role: 'assistant', content: '答', ...over }
}

afterEach(() => {
  // 先卸载再复位：否则下一次 setState 会通知已删掉 DOM 的残留订阅（act 警告）
  cleanup()
  act(() => {
    useCopilot.setState({ messages: [], turnStatsByLane: {}, streaming: false })
  })
})

describe('LaneUsageChip（实时账）', () => {
  it('全字段：一行给出速度 / 总量 / 缓存命中，title 给出四桶 + 耗时', () => {
    useCopilot.setState({
      turnStatsByLane: {
        pi: stats({
          firstDeltaAt: 0,
          doneAt: 5000,
          exactTokens: 240,
          inputTokens: 100,
          cacheReadTokens: 900,
          cacheWriteTokens: 10,
        }),
      },
      messages: [assistant({ agentKind: 'pi', model: 'claude-sonnet' })],
    })

    const { container, getByTestId } = render(<LaneUsageChip kind="pi" />)
    const chip = getByTestId('lane-usage-pi')

    // 240 tok / 5s = 48 tok/s；总量 1250 → 1.3k；命中 900/(100+900+10) = 89%
    expect(container.textContent).toBe('48.0 tok/s · 1.3k tok · 缓存 89%')

    const title = chip.getAttribute('title') ?? ''
    expect(title).toContain('模型 claude-sonnet')
    // 四桶齐全（缺一个就分不清「贵在输出还是贵在输入的缓存重写」）
    expect(title).toContain('输入 100 tok')
    expect(title).toContain('输出 240 tok')
    expect(title).toContain('缓存读 900 tok')
    expect(title).toContain('缓存写 10 tok')
    expect(title).toContain('总耗时 5.0s')
    // 实时路径没有首字时刻：不显示该段，也不显示 0ms
    expect(title).not.toContain('首字')
    // 不显示金额
    expect(title).not.toMatch(/元|¥|cost|\$/)
    container.remove()
  })

  it('缺字段：整段不渲染（不出现 0 tok / — / 缓存 0%）', () => {
    useCopilot.setState({ turnStatsByLane: { pi: stats({ exactTokens: 7 }) } })

    const { container, getByTestId } = render(<LaneUsageChip kind="pi" />)

    expect(container.textContent).toBe('7 tok')
    expect(container.textContent).not.toContain('缓存')
    expect(container.textContent).not.toContain('tok/s')
    expect(container.textContent).not.toContain('—')
    expect(getByTestId('lane-usage-pi').getAttribute('title')).toBe('输出 7 tok')
    container.remove()
  })

  it('估算值带 ≈（与 provider 上报值可区分）', () => {
    useCopilot.setState({
      turnStatsByLane: { pi: stats({ estTokens: 1200, firstDeltaAt: 0, doneAt: 4000 }) },
    })

    const { container } = render(<LaneUsageChip kind="pi" />)

    expect(container.textContent).toBe('≈300 tok/s · 1.2k tok')
    container.remove()
  })

  it('一个数都没有时不渲染整块（栏头不多一个看不懂的小方块）', () => {
    useCopilot.setState({ turnStatsByLane: { pi: stats() } })

    const { container } = render(<LaneUsageChip kind="pi" />)

    expect(container.textContent).toBe('')
    container.remove()
  })

  it('只订阅自己那一栏：别栏的账不会串到本栏', () => {
    useCopilot.setState({
      turnStatsByLane: {
        pi: stats({ exactTokens: 10 }),
        dsh: stats({ exactTokens: 999, firstDeltaAt: 0, doneAt: 1000 }),
      },
    })

    const { container } = render(<LaneUsageChip kind="pi" />)

    expect(container.textContent).toBe('10 tok')
    container.remove()
  })
})

describe('LaneUsageChip（历史用量：刷新后还在）', () => {
  /** 模拟 transcript 回放：后端落库的 metadata → LaneUsage */
  function historical(): LaneUsage {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: { pi: { output: 320, input: 1200, cache_read: 4800, cache_write: 0 } },
      ttft_ms: 640,
      duration_ms: 8000,
    })
    return lanes!.pi!
  }

  it('传了 usage 就优先用它（本轮账清空/切会话后仍能显示）', () => {
    // 内存账为空——刷新后的真实状态
    useCopilot.setState({ turnStatsByLane: {} })
    const usage = historical()

    const { container, getByTestId } = render(<LaneUsageChip kind="pi" usage={usage} />)

    // 320 tok / 8s = 40 tok/s；总量 6320 → 6.3k；命中 4800/6000 = 80%
    expect(container.textContent).toBe('40.0 tok/s · 6.3k tok · 缓存 80%')
    const title = getByTestId('lane-usage-pi').getAttribute('title') ?? ''
    // 缓存写 = 0（provider 上报的真 0）→ 省略该段，不写「缓存写 0 tok」
    expect(title).not.toContain('缓存写')
    expect(title).toContain('首字 640ms')
    expect(title).toContain('总耗时 8.0s')
    container.remove()
  })

  it('历史值一律无 ≈（落库的都是 provider 上报数）', () => {
    const { container } = render(<LaneUsageChip kind="pi" usage={historical()} />)
    expect(container.textContent).not.toContain('≈')
    container.remove()
  })

  it('模型名取自这一栏最近一条回答（历史来自 metadata.model）', () => {
    useCopilot.setState({
      messages: [
        assistant({ id: 'a-1', agentKind: 'pi', model: '旧模型' }),
        assistant({ id: 'a-2', agentKind: 'dsh', model: '别栏模型' }),
        assistant({ id: 'a-3', agentKind: 'pi', model: 'gpt-5' }),
      ],
    })

    const { container } = render(<LaneUsageChip kind="pi" usage={historical()} />)

    expect(container.textContent).toBe('40.0 tok/s · 6.3k tok · 缓存 80%')
    // title 里必须有最近一条 pi 的模型，而不是第一条，也不是别栏
    const title = container.firstElementChild?.getAttribute('title') ?? ''
    expect(title).toContain('模型 gpt-5')
    expect(title).not.toContain('旧模型')
    expect(title).not.toContain('别栏模型')
    container.remove()
  })

  it('usage 为 null 时回落到本轮内存账（两条路径互不干扰）', () => {
    useCopilot.setState({ turnStatsByLane: { pi: stats({ exactTokens: 5 }) } })
    const { container } = render(<LaneUsageChip kind="pi" usage={null} />)
    expect(container.textContent).toBe('5 tok')
    container.remove()
  })

  it('历史用量与内存账同时存在时，历史优先（同一个数不两处打架）', () => {
    useCopilot.setState({ turnStatsByLane: { pi: stats({ exactTokens: 5 }) } })
    const { container } = render(<LaneUsageChip kind="pi" usage={historical()} />)
    expect(container.textContent).toContain('40.0 tok/s')
    expect(container.textContent).not.toContain('5 tok')
    container.remove()
  })
})
