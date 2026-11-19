// @vitest-environment jsdom
/**
 * CodeBlock 测试（jsdom）。
 *
 * 关键不变量：
 * - 高亮后的 span 树仍能取回**原文**（递归取文本节点）
 * - 复制内容去掉末尾空行（贴进 Word/邮件不会多一行）
 * - 无语言标注时不显示 `language-*`，回落为 `code`
 * - 复制成功后才点亮「已复制」（失败不误报）
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clipboardMock = vi.hoisted(() => ({ copyText: vi.fn(async () => true) }))
vi.mock('@/lib/clipboard', () => clipboardMock)

import { CodeBlock } from './CodeBlock'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CodeBlock', () => {
  it('显示语言标签', () => {
    render(
      <CodeBlock>
        <code className="hljs language-ts">{'const a = 1'}</code>
      </CodeBlock>,
    )
    expect(screen.getByText('ts')).toBeTruthy()
  })

  it('无语言标注时回落为 code', () => {
    render(
      <CodeBlock>
        <code>{'plain'}</code>
      </CodeBlock>,
    )
    expect(screen.getByText('code')).toBeTruthy()
  })

  it('高亮后的 span 树能取回原文（递归取文本）并去掉末尾空行', async () => {
    render(
      <CodeBlock>
        <code className="hljs language-python">
          <span className="hljs-keyword">{'def'}</span>
          {' f():\n'}
          {'    return 1\n\n'}
        </code>
      </CodeBlock>,
    )
    fireEvent.click(screen.getByRole('button', { name: '复制这段代码' }))
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    expect(clipboardMock.copyText).toHaveBeenCalledWith('def f():\n    return 1')
  })

  it('复制成功后点亮「已复制」', async () => {
    render(
      <CodeBlock>
        <code>{'x'}</code>
      </CodeBlock>,
    )
    fireEvent.click(screen.getByRole('button', { name: '复制这段代码' }))
    await waitFor(() => expect(screen.getByText('已复制')).toBeTruthy())
  })

  it('复制失败不点亮「已复制」（不误导用户）', async () => {
    clipboardMock.copyText.mockResolvedValueOnce(false)
    render(
      <CodeBlock>
        <code>{'x'}</code>
      </CodeBlock>,
    )
    fireEvent.click(screen.getByRole('button', { name: '复制这段代码' }))
    await waitFor(() => expect(clipboardMock.copyText).toHaveBeenCalled())
    expect(screen.queryByText('已复制')).toBeNull()
  })
})
