// @vitest-environment jsdom
/**
 * 工具行与 chip 的「五态 + 耗时」（jsdom）。
 *
 * 锁的是三条会被律师直接读错的口径：
 * 1. **状态不能由 `content` 有无推断**：删除类工具的合法结果就是空串，旧写法会把它
 *    永远显示成「调用中」；
 * 2. **没有 `toolStartedAt` 就不显示耗时**：编一个 `0.0s` 比不显示更有害（律师拿它
 *    判断是不是卡死）；
 * 3. **历史数据（无 `toolState`）要按有无结果回落**，不能因为缺字段就显示成「准备中」。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '../types'
import { ToolChip } from './ToolChips'
import { ToolRow } from './ToolRow'

const tool = (over: Partial<ChatMessage> = {}): ChatMessage => ({
  id: 't1',
  role: 'tool',
  content: '',
  toolName: 'get_current_user',
  toolCallId: 'c1',
  ...over,
})

describe('ToolRow：五态与耗时', () => {
  it('running：显示「调用中」与耗时，且不折叠出返回值', () => {
    render(<ToolRow message={tool({ toolState: 'running', toolStartedAt: 1_000 })} />)

    expect(screen.getByText(/调用中/)).toBeTruthy()
    // 1.0s 起，只要格式对就算过（时间在跑，不锁具体数字）
    expect(document.body.textContent).toMatch(/\d+\.\d+s|\d+s/)
    expect(screen.queryByText('工具返回原文')).toBeNull()
  })

  it('ok + 空结果：仍显示「已完成」（空结果是合法结果，不是「还在跑」）', () => {
    render(<ToolRow message={tool({ toolState: 'ok', toolStartedAt: 0, toolEndedAt: 900 })} />)

    expect(screen.getByText(/已完成/)).toBeTruthy()
    expect(document.body.textContent).toContain('0.9s')
    // 没有返回值就不给空的「返回原文」折叠块（展开是空的，比收起更让人困惑）
    expect(screen.queryByText('工具返回原文')).toBeNull()
  })

  it('ok + 有结果：给出「返回原文」折叠块', () => {
    render(<ToolRow message={tool({ toolState: 'ok', content: '{"ok":true}' })} />)

    expect(screen.getByText('工具返回原文')).toBeTruthy()
    expect(document.body.textContent).toContain('{"ok":true}')
  })

  it('error：显示「失败」而不是「已完成」', () => {
    render(<ToolRow message={tool({ toolState: 'error', content: 'HTTP 500' })} />)

    expect(screen.getByText(/失败/)).toBeTruthy()
    expect(document.body.textContent).not.toContain('已完成')
  })

  it('stopped：显示「已中止」', () => {
    render(<ToolRow message={tool({ toolState: 'stopped' })} />)
    expect(screen.getByText(/已中止/)).toBeTruthy()
  })

  it('历史数据（无 toolState）：有 content 按已完成回落，无 content 按调用中回落', () => {
    const { unmount } = render(<ToolRow message={tool({ content: '{"ok":true}' })} />)
    expect(screen.getByText(/已完成/)).toBeTruthy()
    unmount()

    render(<ToolRow message={tool()} />)
    expect(screen.getByText(/调用中/)).toBeTruthy()
  })

  it('没有 toolStartedAt 时**不显示耗时**（不许编 0.0s）', () => {
    render(<ToolRow message={tool({ toolState: 'running' })} />)

    expect(document.body.textContent).not.toMatch(/\d+(\.\d+)?s/)
    expect(document.body.textContent).not.toContain('0.0s')
  })

  it('改写类工具结算后画 diff，运行中不画（参数还在渐进完整）', () => {
    const rewrite = { original: '甲', replacement: '乙', filename: '合同.docx' }
    const { unmount } = render(<ToolRow message={tool({ toolState: 'running', rewrite })} />)
    expect(screen.queryByText('甲')).toBeNull()
    unmount()

    render(<ToolRow message={tool({ toolState: 'ok', rewrite, content: 'ok' })} />)
    // 结算后标题用文件名，diff 块里能看到原文
    expect(document.body.textContent).toContain('合同.docx')
    expect(document.body.textContent).toContain('甲')
  })
})

describe('ToolChip：状态与耗时和整行同一口径', () => {
  it('保留工具短名（不把 chip 撑宽），状态进 title', () => {
    render(<ToolChip tool={tool({ toolState: 'error', toolStartedAt: 0, toolEndedAt: 2_000 })} />)

    expect(document.body.textContent).toContain('get_current_user')
    expect(document.body.textContent).toContain('2s')
    expect(screen.getByTitle(/失败 · /)).toBeTruthy()
  })

  it('没有开始时刻时不显示耗时，运行中给一个省略号', () => {
    render(<ToolChip tool={tool({ toolState: 'running' })} />)

    expect(document.body.textContent).toContain('…')
    expect(document.body.textContent).not.toContain('0.0s')
  })
})
