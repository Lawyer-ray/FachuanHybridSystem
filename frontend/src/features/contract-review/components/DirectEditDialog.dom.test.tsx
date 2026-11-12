// @vitest-environment jsdom
/**
 * DirectEditDialog 交互测试（jsdom）。
 *
 * 划词直改只有两件事：按指令出候选、挑一条落痕。契约：
 * - 指令为空不请求；请求带 contract_id + subpath + 选区；
 * - 落盘成功后 onApplied + onClose 都要调（否则画布不刷新/对话框不关）；
 * - applied=false 只回显原因，不关闭对话框；
 * - 点遮罩关闭，点对话框内部不关闭。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { suggestDirectEdit, applyDirectEdit, toast } = vi.hoisted(() => ({
  suggestDirectEdit: vi.fn(),
  applyDirectEdit: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

vi.mock('../api', () => ({ suggestDirectEdit, applyDirectEdit }))
vi.mock('sonner', () => ({ toast }))

import { DirectEditDialog } from './DirectEditDialog'

const props = {
  selection: '甲方应于每季度首月十日内支付。',
  contractId: 42,
  subpath: '合同/主合同.docx',
  onClose: vi.fn(),
  onApplied: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DirectEditDialog', () => {
  it('展示已选条款原文', () => {
    render(<DirectEditDialog {...props} />)
    expect(screen.getByText(props.selection)).toBeTruthy()
  })

  it('指令为空：只提示，不发请求', () => {
    render(<DirectEditDialog {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))
    expect(toast.error).toHaveBeenCalledWith('请说明要怎么改这一段')
    expect(suggestDirectEdit).not.toHaveBeenCalled()
  })

  it('生成改法：带上归属（contract_id + subpath）与选区', async () => {
    suggestDirectEdit.mockResolvedValue({
      candidates: [{ suggested: '新写法', reason: '依据' }],
      context_before: '',
      context_after: '',
    })
    render(<DirectEditDialog {...props} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '违约金降到 10%' } })
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))

    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())
    expect(suggestDirectEdit).toHaveBeenCalledWith({
      contract_id: 42,
      subpath: '合同/主合同.docx',
      selection: props.selection,
      instruction: '违约金降到 10%',
    })
  })

  it('候选为空：提示换说法', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [], context_before: '', context_after: '' })
    render(<DirectEditDialog {...props} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '改' } })
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('AI 没有给出可用的改法，换个说法再试'))
  })

  it('生成失败：错误文案回显', async () => {
    suggestDirectEdit.mockRejectedValue(new Error('模型不可用'))
    render(<DirectEditDialog {...props} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '改' } })
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('模型不可用'))
  })

  it('⌘↵ 等价于点生成', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [], context_before: '', context_after: '' })
    render(<DirectEditDialog {...props} />)

    const ta = screen.getByRole('textbox')
    fireEvent.change(ta, { target: { value: '改' } })
    fireEvent.keyDown(ta, { key: 'Enter', metaKey: true })

    await waitFor(() => expect(suggestDirectEdit).toHaveBeenCalledTimes(1))
  })

  it('采纳成功：applyDirectEdit 带归属写入，随后 onApplied + onClose', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    applyDirectEdit.mockResolvedValue({ applied: true, subpath: props.subpath, name: '主合同.docx', reason: '' })
    render(<DirectEditDialog {...props} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '改' } })
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /采纳这条/ }))

    await waitFor(() => expect(props.onApplied).toHaveBeenCalledTimes(1))
    expect(applyDirectEdit).toHaveBeenCalledWith({
      contract_id: 42,
      subpath: props.subpath,
      selection: props.selection,
      suggested: '新写法',
    })
    expect(props.onClose).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith('已写入修订痕迹', expect.anything())
  })

  it('applied=false：回显原因，不关闭对话框也不刷新画布', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    applyDirectEdit.mockResolvedValue({ applied: false, subpath: '', name: '', reason: '选区原文已找不到' })
    render(<DirectEditDialog {...props} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '改' } })
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /采纳这条/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('选区原文已找不到'))
    expect(props.onClose).not.toHaveBeenCalled()
    expect(props.onApplied).not.toHaveBeenCalled()
  })

  it('落盘抛错：提示写入失败，不关闭', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    applyDirectEdit.mockRejectedValue(new Error('磁盘只读'))
    render(<DirectEditDialog {...props} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '改' } })
    fireEvent.click(screen.getByRole('button', { name: /生成改法/ }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /采纳这条/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('磁盘只读'))
    expect(props.onClose).not.toHaveBeenCalled()
  })

  it('点遮罩关闭，点对话框内部不关闭', () => {
    const { container } = render(<DirectEditDialog {...props} />)
    const overlay = container.firstElementChild as HTMLElement

    fireEvent.click(screen.getByText('AI 改写这一段'))
    expect(props.onClose).not.toHaveBeenCalled()

    fireEvent.click(overlay)
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })

  it('标题栏关闭按钮触发 onClose', () => {
    render(<DirectEditDialog {...props} />)
    fireEvent.click(screen.getByLabelText('关闭'))
    expect(props.onClose).toHaveBeenCalledTimes(1)
  })
})
