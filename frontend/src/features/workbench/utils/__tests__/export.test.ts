/**
 * Workbench Export Utils Tests
 * 测试对话导出 Markdown 和文件下载工具
 */

import { exportToMarkdown, downloadFile } from '../export'

describe('exportToMarkdown', () => {
  const createMessage = (overrides: Record<string, unknown> = {}) => ({
    id: 1,
    role: 'user' as const,
    content: 'Hello',
    llm_model: '',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: {},
    created_at: '2026-06-15T10:00:00Z',
    ...overrides,
  })

  it('includes title as H1 heading', () => {
    const result = exportToMarkdown([createMessage()], 'Test Title')
    expect(result).toContain('# Test Title')
  })

  it('includes export timestamp', () => {
    const result = exportToMarkdown([createMessage()], 'Title')
    expect(result).toContain('导出时间:')
  })

  it('formats user messages with user heading', () => {
    const result = exportToMarkdown([createMessage({ role: 'user', content: 'Test content' })], 'Title')
    expect(result).toContain('## 用户')
    expect(result).toContain('Test content')
  })

  it('formats assistant messages with assistant heading', () => {
    const result = exportToMarkdown([createMessage({ role: 'assistant', content: 'Reply' })], 'Title')
    expect(result).toContain('## 助手')
    expect(result).toContain('Reply')
  })

  it('includes model name for assistant messages', () => {
    const result = exportToMarkdown(
      [createMessage({ role: 'assistant', content: 'Reply', llm_model: 'gpt-4o' })],
      'Title',
    )
    expect(result).toContain('模型: gpt-4o')
  })

  it('formats tool messages with tool name', () => {
    const result = exportToMarkdown(
      [createMessage({ role: 'tool', tool_name: 'search_cases' })],
      'Title',
    )
    expect(result).toContain('### 工具: search_cases')
  })

  it('uses fallback text for tool messages without tool_name', () => {
    const result = exportToMarkdown(
      [createMessage({ role: 'tool', tool_name: '' })],
      'Title',
    )
    expect(result).toContain('### 工具: 未知')
  })

  it('includes tool output as JSON code block', () => {
    const result = exportToMarkdown(
      [createMessage({ role: 'tool', tool_output: { results: [1, 2] } })],
      'Title',
    )
    expect(result).toContain('```json')
    expect(result).toContain('"results"')
  })

  it('formats system messages as blockquotes', () => {
    const result = exportToMarkdown(
      [createMessage({ role: 'system', content: 'System msg' })],
      'Title',
    )
    expect(result).toContain('> System msg')
  })

  it('separates messages with horizontal rules', () => {
    const messages = [
      createMessage({ id: 1, role: 'user', content: 'msg1' }),
      createMessage({ id: 2, role: 'assistant', content: 'msg2' }),
    ]
    const result = exportToMarkdown(messages, 'Title')
    const hrCount = (result.match(/---/g) || []).length
    expect(hrCount).toBe(2)
  })

  it('handles empty messages array', () => {
    const result = exportToMarkdown([], 'Title')
    expect(result).toContain('# Title')
    expect(result).toContain('导出时间:')
  })
})

describe('downloadFile', () => {
  it('creates a blob and triggers download', () => {
    const clickSpy = vi.fn()
    const appendSpy = vi.spyOn(document.body, 'appendChild').mockImplementation(() => document.body)
    const removeSpy = vi.spyOn(document.body, 'removeChild').mockImplementation(() => document.body)
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return { href: '', download: '', click: clickSpy } as unknown as HTMLAnchorElement
      }
      return document.createElement(tag)
    })

    downloadFile('test content', 'test.md', 'text/markdown')

    expect(createObjectURLSpy).toHaveBeenCalled()
    expect(clickSpy).toHaveBeenCalled()
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock')
    expect(appendSpy).toHaveBeenCalled()
    expect(removeSpy).toHaveBeenCalled()

    createObjectURLSpy.mockRestore()
    revokeObjectURLSpy.mockRestore()
    appendSpy.mockRestore()
    removeSpy.mockRestore()
  })
})
