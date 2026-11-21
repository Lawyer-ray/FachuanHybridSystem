// @vitest-environment jsdom
/**
 * 综合结论卡（jsdom）：正文 / 参与栏 / 丢弃原因 / 来源锚点 / 未核验 / tokens / 空正文不出卡。
 *
 * 锁的都是「不说就会误导」的口径：
 * - `dropped` 的三种原因必须翻成人话（没正文 / 本轮失败 / 超长被截），不能都写成「没参与」；
 * - `citations` 是「栏名 · 引文」的来源锚点，不是核验结果；
 * - `unverified` 只表示「本轮没核上」，不能读成「引用是错的」；
 * - 空正文整卡不渲染（挂个空标题会让律师以为综合结论就是没有结论）。
 *
 * 一律走 `toSynthesisView(wire)` 组装，确保 snake_case → camelCase 的映射与
 * 原因文案映射都在真实路径上被覆盖。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Synthesis } from '../../adjudication-types'
import { toSynthesisView } from '../../domain/fusion'
import { SynthesisCard } from './SynthesisCard'

const synthesisWire = (over: Partial<Synthesis> = {}): Synthesis => ({
  synthesis_id: 'sy-1',
  session_id: 's-1',
  turn: 2,
  text: '## 结论\n\n甲方可主张解除合同，并要求赔偿损失。',
  model: 'kimi-2.6',
  lanes_used: ['pi', 'dsh'],
  dropped: [],
  citations: [],
  unverified: [],
  tokens: { prompt: 2100, completion: 640, total: 2740 },
  ...over,
})

describe('SynthesisCard：正文与元信息', () => {
  it('Markdown 正文按 assistant 那套渲染器出卡，并展示模型与 tokens', () => {
    render(<SynthesisCard synthesis={toSynthesisView(synthesisWire())} />)
    const card = screen.getByTestId('synthesis-card')
    expect(card.textContent).toContain('甲方可主张解除合同')
    expect(screen.getByText('结论')).toBeTruthy()
    expect(screen.getByTestId('synthesis-model').textContent).toBe('kimi-2.6')
    expect(screen.getByTestId('synthesis-tokens').textContent).toContain('2740')
    expect(screen.getByTestId('synthesis-lanes').textContent).toContain('Pi、DeepSeek Harness')
  })

  it('空正文（只有空白）→ 整卡不渲染', () => {
    render(<SynthesisCard synthesis={toSynthesisView(synthesisWire({ text: '   ' }))} />)
    expect(screen.queryByTestId('synthesis-card')).toBeNull()
  })
})

describe('SynthesisCard：被丢弃的栏', () => {
  it('dropped 三种原因分别显示「本轮无正文 / 本轮失败 / 超长被截」', () => {
    render(
      <SynthesisCard
        synthesis={toSynthesisView(
          synthesisWire({
            lanes_used: ['pi'],
            dropped: [
              { lane: 'dsh', reason: 'empty' },
              { lane: 'openai-agents', reason: 'failed' },
              { lane: 'other', reason: 'too_long' },
            ],
          }),
        )}
      />,
    )
    const dropped = screen.getByTestId('synthesis-dropped').textContent ?? ''
    expect(dropped).toContain('DeepSeek Harness（本轮无正文）')
    expect(dropped).toContain('openai-agents（本轮失败）')
    expect(dropped).toContain('other（超长被截）')
    // 三种原因不许折叠成同一句话
    expect(dropped).not.toContain('没参与')
  })

  it('没有丢弃的栏时不渲染该行（不虚构「少了一栏」）', () => {
    render(<SynthesisCard synthesis={toSynthesisView(synthesisWire())} />)
    expect(screen.queryByTestId('synthesis-dropped')).toBeNull()
  })
})

describe('SynthesisCard：来源锚点与未核验', () => {
  it('citations 按「栏名 · 引文」显示，并声明不是核验结果', () => {
    render(
      <SynthesisCard
        synthesis={toSynthesisView(
          synthesisWire({
            citations: [
              { lane: 'pi', quote: '《民法典》第五百八十四条' },
              { lane: 'dsh', quote: '（2023）京 01 民终 1234 号' },
            ],
          }),
        )}
      />,
    )
    const citations = screen.getByTestId('synthesis-citations').textContent ?? ''
    expect(citations).toContain('Pi · 《民法典》第五百八十四条')
    expect(citations).toContain('DeepSeek Harness · （2023）京 01 民终 1234 号')
    expect(citations).toContain('不是核验结果')
  })

  it('unverified 显示未核验项，并说明「没核上」不是「错」', () => {
    render(
      <SynthesisCard
        synthesis={toSynthesisView(
          synthesisWire({ unverified: ['pi 引《X 办法》第 7 条，本轮无核验命中'] }),
        )}
      />,
    )
    const unverified = screen.getByTestId('synthesis-unverified').textContent ?? ''
    expect(unverified).toContain('pi 引《X 办法》第 7 条，本轮无核验命中')
    expect(unverified).toContain('不等于引用有误')
  })

  it('没有 citations / unverified 时两块都不渲染', () => {
    render(<SynthesisCard synthesis={toSynthesisView(synthesisWire())} />)
    expect(screen.queryByTestId('synthesis-citations')).toBeNull()
    expect(screen.queryByTestId('synthesis-unverified')).toBeNull()
  })
})
