// @vitest-environment jsdom
/**
 * 工具行与 chip 的「五态图标 + 耗时 + 原文归一化」（jsdom）。
 *
 * 锁的是会被律师直接读错的口径：
 * 1. **状态不能由 `content` 有无推断**：删除类工具的合法结果就是空串，旧写法会把它
 *    永远显示成「调用中」；
 * 2. **没有 `toolStartedAt` 就不显示耗时**：编一个 `0.0s` 比不显示更有害（律师拿它
 *    判断是不是卡死）；
 * 3. **历史数据（无 `toolState`）要按有无结果回落**，不能因为缺字段就显示成「准备中」；
 * 4. **五态一律只出图标**：可见文字里不许再出现「已完成/失败/调用中」（用户要的是
 *    「打勾或打叉，我自己点开」），但字必须留在无障碍树里（`sr-only`）；
 * 5. **原文展开就直接看到**：不再套一层「工具返回原文」的二次点击；
 * 6. 原文先过 `domain/tool-content` 的 `formatToolContent`：`<pre>` 里是真换行 +
 *    缩进两格的 JSON，不是 `{'type': 'text', 'text': '{\n  "total": 1…'}` 那层噪声。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ToolState } from '../domain'
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

/** 五态 → 那一枚图标的 lucide 类名（`ToolStateIcon` 的五条分支各一枚） */
const STATE_ICON: Array<[ToolState, string, string]> = [
  ['preparing', '准备中', 'lucide-circle'],
  ['running', '调用中', 'lucide-loader-circle'],
  ['ok', '已完成', 'lucide-check'],
  ['error', '失败', 'lucide-x'],
  ['stopped', '已中止', 'lucide-minus'],
]

/** 节点上**看得见**的文字：去掉 `sr-only` 的读屏专用文本 */
function visibleTextOf(node: Element): string {
  const clone = node.cloneNode(true) as Element
  for (const el of clone.querySelectorAll('.sr-only')) el.remove()
  return clone.textContent ?? ''
}

describe('ToolRow：五态与耗时', () => {
  it('running：显示耗时，且没有返回值时不给空的内容区', () => {
    render(<ToolRow message={tool({ toolState: 'running', toolStartedAt: 1_000 })} />)

    // 1.0s 起，只要格式对就算过（时间在跑，不锁具体数字）
    expect(document.body.textContent).toMatch(/\d+\.\d+s|\d+s/)
    expect(document.querySelector('pre')).toBeNull()
  })

  it('ok + 空结果：仍认成功（空结果是合法结果，不是「还在跑」），且不渲染空内容区', () => {
    render(<ToolRow message={tool({ toolState: 'ok', toolStartedAt: 0, toolEndedAt: 900 })} />)

    expect(screen.getByText(/已完成/)).toBeTruthy()
    expect(document.body.textContent).toContain('0.9s')
    // 空结果是合法结果：不渲染空壳 `<pre>`（展开是空的比收起更让人困惑）
    expect(document.querySelector('pre')).toBeNull()
  })

  it('ok + 有结果：展开就直接看到原文，**没有**「工具返回原文」的二次点击', () => {
    render(<ToolRow message={tool({ toolState: 'ok', content: '{"ok":true}' })} />)

    expect(screen.queryByText('工具返回原文')).toBeNull()
    // 外层只有一枚 details（原来那枚内层 details 已删）
    expect(document.querySelectorAll('details')).toHaveLength(1)
    const pre = document.querySelector('pre')!
    // 归一化：单行 JSON → 缩进两格的真换行（工具原文不再是一整行转义噪声）
    expect(pre.textContent).toBe(`{
  "ok": true
}`)
    expect(pre.className).toContain('max-h-56')
    expect(pre.className).toContain('overflow-y-auto')
  })

  it('MCP 信封的真实形状：`<pre>` 里不再有 `{\'type\': \'text\'` 与字面 \\n', () => {
    const content =
      "{'type': 'text', 'text': '{\\n  \"total\": 1,\\n  \"items\": []\\n}'}"
    render(<ToolRow message={tool({ toolState: 'ok', content })} />)

    const pre = document.querySelector('pre')!
    expect(pre.textContent).not.toContain("'type'")
    expect(pre.textContent).not.toContain('\\n')
    expect(pre.textContent).toBe(`{
  "total": 1,
  "items": []
}`)
  })

  it('error：认失败而不是已完成', () => {
    render(<ToolRow message={tool({ toolState: 'error', content: 'HTTP 500' })} />)

    expect(screen.getByText(/失败/)).toBeTruthy()
    expect(document.body.textContent).not.toContain('已完成')
    expect(document.querySelector('pre')!.textContent).toBe('HTTP 500')
  })

  it('stopped：认已中止', () => {
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

describe('五态一律只出图标（可见文字为零，读屏保留）', () => {
  it.each(STATE_ICON)('ToolRow %s：可见文字里没有「%s」，图标是 %s', (state, word, icon) => {
    render(<ToolRow message={tool({ toolState: state })} />)
    const summary = document.querySelector('summary')!

    expect(visibleTextOf(summary)).not.toContain(word)
    // 字只是移到读屏：不许为了省像素把无障碍信息删掉
    expect(summary.textContent).toContain(word)
    expect(summary.querySelector(`svg.${icon}`)).toBeTruthy()
  })

  it.each(STATE_ICON)('ToolChip %s：可见文字里没有「%s」，图标是 %s', (state, word, icon) => {
    render(<ToolChip tool={tool({ toolState: state, toolStartedAt: 0, toolEndedAt: 2_000 })} />)
    const summary = document.querySelector('summary')!

    expect(visibleTextOf(summary)).not.toContain(word)
    expect(summary.textContent).toContain(word)
    expect(summary.querySelector(`svg.${icon}`)).toBeTruthy()
    // 鼠标停在 chip 上仍能看到是哪一态（读屏走 sr-only，键盘/触屏不走 title）
    expect(summary.getAttribute('title')).toContain(word)
  })

  it('五枚状态图标都对读屏隐藏（状态词已经念过一遍，图标不再重复念）', () => {
    for (const [state] of STATE_ICON) {
      const { unmount } = render(<ToolRow message={tool({ toolState: state })} />)
      expect(document.querySelector('summary svg')!.getAttribute('aria-hidden')).toBe('true')
      unmount()
    }
  })
})

describe('ToolChip：折叠态只出必要信息，展开态独占整行', () => {
  it('ok：可见文字只有工具名与耗时', () => {
    render(<ToolChip tool={tool({ toolState: 'ok', toolStartedAt: 0, toolEndedAt: 200 })} />)
    const summary = document.querySelector('summary')!

    const visible = visibleTextOf(summary)
    expect(visible).toContain('get_current_user')
    expect(visible).toContain('0.2s')
    expect(visible).not.toContain('已完成')
  })

  it('summary 里有可见的展开指示，且不嵌交互元素（否则出两个焦点）', () => {
    render(<ToolChip tool={tool({ toolState: 'ok' })} />)
    const summary = document.querySelector('summary')!

    expect(summary.querySelector('svg[aria-hidden="true"]')).toBeTruthy()
    expect(summary.querySelector('button, a')).toBeNull()
  })

  it('展开态：details 拿 open:basis-full 独占整行，返回值读的是归一化后的文本', () => {
    render(<ToolChip tool={tool({ toolState: 'ok', content: '{"ok":true}' })} />)
    const details = document.querySelector('details')!

    // 收起时是一枚 chip，展开时在换行容器里占一整行（这是当年用整行 ToolRow 的理由）
    expect(details.className).toContain('open:basis-full')
    const pre = document.querySelector('pre')!
    expect(pre.textContent).toBe(`{
  "ok": true
}`)
    expect(pre.className).not.toContain('max-w-[')
    expect(pre.className).toContain('whitespace-pre-wrap')
  })

  it('空结果是合法结果：不渲染空的内容区', () => {
    render(<ToolChip tool={tool({ toolState: 'ok', content: '  ' })} />)
    expect(document.querySelector('pre')).toBeNull()
  })

  it('没有开始时刻时不显示耗时，运行中给一个省略号', () => {
    render(<ToolChip tool={tool({ toolState: 'running' })} />)

    expect(document.body.textContent).toContain('…')
    expect(document.body.textContent).not.toContain('0.0s')
  })
})
