// @vitest-environment jsdom
/**
 * DiffBlock 测试（jsdom）。
 *
 * 关键不变量：
 * - 改动行按增/删分色并带符号，上下文行无符号
 * - 两个行号列：删除行只有旧侧、新增行只有新侧、上下文两侧都有
 * - 超过 16 行时折叠但**保留头尾**，并如实告知还有多少行没显示
 * - 全文一致时不画空块
 * - 超大改动按整篇替换显示并**明说**被截断（宁可不画，不能画错还不说）
 * - 复制载荷是标准 unified diff 前缀
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clipboardMock = vi.hoisted(() => ({ copyText: vi.fn(async (_text: string) => true) }))
vi.mock('@/lib/clipboard', () => clipboardMock)

import { DiffBlock } from './DiffBlock'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DiffBlock', () => {
  it('渲染增删行与行号，标题带文件名', () => {
    const { container } = render(
      <DiffBlock original={'第一条\n逾期付款的，按日万分之五计息。'} replacement={'第一条\n逾期付款的，按日万分之三计息。'} filename="借款合同.docx" />,
    )
    expect(screen.getByText('修订 · 借款合同.docx')).toBeTruthy()
    expect(container.textContent).toContain('逾期付款的，按日万分之五计息。')
    expect(container.textContent).toContain('逾期付款的，按日万分之三计息。')
    expect(screen.getByText('−')).toBeTruthy()
    expect(screen.getByText('+')).toBeTruthy()
  })

  it('全文一致时不画空块', () => {
    render(<DiffBlock original="第一条" replacement="第一条" />)
    expect(screen.getByText('改写内容与原文一致，未检测到改动。')).toBeTruthy()
  })

  it('超长改动折叠并告知未显示行数（保留头尾）', () => {
    const original = Array.from({ length: 40 }, (_, i) => `原文第${i}行`).join('\n')
    const replacement = Array.from({ length: 40 }, (_, i) => `改写第${i}行`).join('\n')
    const { container } = render(<DiffBlock original={original} replacement={replacement} />)
    // 头尾各 8 行可见，其余折叠
    expect(container.textContent).toContain('另有')
    expect(container.textContent).toContain('行未显示')
    // 首行与末行都在（关键信息常在被替换段两端）
    expect(container.textContent).toContain('原文第0行')
    expect(container.textContent).toContain('改写第39行')
  })

  it('超大改动整篇替换并明说被截断', () => {
    const original = Array.from({ length: 900 }, (_, i) => `a${i}`).join('\n')
    const replacement = Array.from({ length: 900 }, (_, i) => `b${i}`).join('\n')
    const { container } = render(<DiffBlock original={original} replacement={replacement} />)
    expect(container.textContent).toContain('改动过大，按整篇替换显示')
  })

  it('复制载荷是带 +/- 前缀的 unified diff', async () => {
    const { container } = render(<DiffBlock original={'甲'} replacement={'乙'} />)
    const button = container.querySelector('button')
    expect(button).toBeTruthy()
    fireEvent.click(button!)
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    const payload = clipboardMock.copyText.mock.calls[0]?.[0] ?? ''
    expect(payload).toContain('-甲')
    expect(payload).toContain('+乙')
  })
})
