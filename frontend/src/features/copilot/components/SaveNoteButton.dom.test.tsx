// @vitest-environment jsdom
/**
 * 「存进项目笔记」按钮测试（jsdom）。
 *
 * 锁死三条语义（都是会真出事的地方）：
 * 1. **会话还没落库时不可用**，且原因是人话（`aria-disabled` + title），
 *    而不是「点了没反应」；
 * 2. 打开弹窗时**预填一句话草稿**（去 Markdown、压单行、截到 300 字），
 *    律师改一句比从零写快；
 * 3. 保存只下发 `sessionId`（锚点由服务端按会话反查——前端猜锚点会写错项目）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const createNoteSpy = vi.hoisted(() => vi.fn(async () => ({ id: 'n1' })))
vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return { ...actual, createProjectNote: createNoteSpy }
})

import { SaveNoteButton } from './SaveNoteButton'
import { useCopilot } from '../store'

const MARKDOWN = '**对方**已同意 **六个月内分期**，底线 80 万不再让。'
const originalSessionId = useCopilot.getState().sessionId

beforeEach(() => {
  createNoteSpy.mockClear()
})

afterEach(() => {
  useCopilot.setState({ sessionId: originalSessionId })
})

describe('SaveNoteButton', () => {
  it('没有 sessionId 时不可用，且说明原因', () => {
    useCopilot.setState({ sessionId: null })
    render(<SaveNoteButton content={MARKDOWN} />)
    const button = screen.getByRole('button', { name: '存进项目笔记' })
    expect(button.getAttribute('aria-disabled')).toBe('true')
    expect(button.getAttribute('title')).toContain('还没落库')
  })

  it('打开弹窗时预填去掉 Markdown 的单行草稿', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    render(<SaveNoteButton content={MARKDOWN} />)
    fireEvent.click(screen.getByRole('button', { name: '存进项目笔记' }))
    const textarea = (await screen.findByLabelText('笔记内容')) as HTMLTextAreaElement
    expect(textarea.value).toBe('对方已同意 六个月内分期，底线 80 万不再让。')
  })

  it('保存只下发 sessionId 与内容（锚点由服务端反查）', async () => {
    useCopilot.setState({ sessionId: 's-1' })
    render(<SaveNoteButton content={MARKDOWN} />)
    fireEvent.click(screen.getByRole('button', { name: '存进项目笔记' }))
    await screen.findByLabelText('笔记内容')
    fireEvent.click(screen.getByRole('button', { name: '存进笔记' }))
    await waitFor(() => expect(createNoteSpy).toHaveBeenCalledTimes(1))
    expect(createNoteSpy).toHaveBeenCalledWith({ content: '对方已同意 六个月内分期，底线 80 万不再让。', sessionId: 's-1' })
  })
})
