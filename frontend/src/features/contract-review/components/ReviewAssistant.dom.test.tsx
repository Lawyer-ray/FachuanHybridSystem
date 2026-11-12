// @vitest-environment jsdom
/**
 * ReviewAssistant 交互测试（jsdom）。
 *
 * 右栏是「选中原文 → 指令 → 预览 → 插入」四段式的唯一落地处，契约：
 * - 无选区时明确说「只答不改」，点发送只提示不调接口；
 * - 有选区但指令空 → 提示填指令，不发请求；
 * - 生成改法调 suggestDirectEdit（归属用 contract_id=0，因为只调 LLM 不碰文件）；
 * - 采纳调 applyTaskEdit（归属用 task_id），applied=false 不当异常、只提示重框；
 * - 选区变化清空旧候选（旧候选取自旧选区，绝不能插到新选区里）。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { suggestDirectEdit, applyTaskEdit, toast } = vi.hoisted(() => ({
  suggestDirectEdit: vi.fn(),
  applyTaskEdit: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

vi.mock('../api', () => ({ suggestDirectEdit, applyTaskEdit }))
vi.mock('sonner', () => ({ toast }))

import { ReviewAssistant } from './ReviewAssistant'

beforeEach(() => {
  vi.clearAllMocks()
})

const SEL = '甲方应于每季度首月十日内支付全部价款。'

describe('ReviewAssistant', () => {
  it('无选区：提示「只答不改」，点发送只弹 toast 不调接口', () => {
    render(<ReviewAssistant taskId="t1" selection="" onApplied={vi.fn()} />)
    expect(screen.getByText('还没有选中原文')).toBeTruthy()

    fireEvent.click(screen.getByLabelText('发送'))
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('当前只支持'))
    expect(suggestDirectEdit).not.toHaveBeenCalled()
  })

  it('有选区但指令为空：生成改法只提示，不发请求', () => {
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)
    expect(screen.getByText(/已选中原文 · \d+ 字/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))
    expect(toast.error).toHaveBeenCalledWith('说明一下要怎么改这一段')
    expect(suggestDirectEdit).not.toHaveBeenCalled()
  })

  it('指令就绪 → suggestDirectEdit 用 contract_id=0 生成候选并渲染红删绿增', async () => {
    suggestDirectEdit.mockResolvedValue({
      candidates: [{ suggested: '甲方应于收到发票后三十日内支付。', reason: '依据：《民法典》第509条' }],
      context_before: '',
      context_after: '',
    })
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '付款节点改到开票后 30 天' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))

    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())
    expect(suggestDirectEdit).toHaveBeenCalledWith({
      contract_id: 0,
      subpath: '',
      selection: SEL,
      instruction: '付款节点改到开票后 30 天',
    })
    expect(screen.getByText('已附依据')).toBeTruthy()
    expect(screen.getByText('甲方应于收到发票后三十日内支付。')).toBeTruthy()
    expect(screen.getByText('依据：《民法典》第509条')).toBeTruthy()
  })

  it('候选为空：提示换说法（不是静默成功）', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [], context_before: '', context_after: '' })
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('AI 没给出可用改法，换个说法再试'))
  })

  it('生成失败：错误文案回显，不抛异常', async () => {
    suggestDirectEdit.mockRejectedValue(new Error('LLM 网关超时'))
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('LLM 网关超时'))
  })

  it('采纳：applyTaskEdit 用 task_id + 当前选区，成功后计数并通知父级刷新', async () => {
    suggestDirectEdit.mockResolvedValue({
      candidates: [{ suggested: '新写法', reason: '' }],
      context_before: '',
      context_after: '',
    })
    applyTaskEdit.mockResolvedValue({ applied: true, name: 'out.docx', reason: '' })
    const onApplied = vi.fn()
    render(<ReviewAssistant taskId="task-9" selection={SEL} onApplied={onApplied} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /插入为修订/ }))

    await waitFor(() => expect(onApplied).toHaveBeenCalledTimes(1))
    expect(applyTaskEdit).toHaveBeenCalledWith({ task_id: 'task-9', selection: SEL, suggested: '新写法' })
    expect(toast.success).toHaveBeenCalledWith('已写入修订痕迹', expect.anything())
    // 落盘成功后候选清空、出现「已插入 N 处修订」回执
    await waitFor(() => expect(screen.queryByText('改法 1')).toBeNull())
    expect(screen.getByText('1')).toBeTruthy()
  })

  it('applied=false 不是异常：回显后端 reason，不通知父级刷新', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    applyTaskEdit.mockResolvedValue({ applied: false, name: '', reason: '选区原文已找不到' })
    const onApplied = vi.fn()
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={onApplied} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /插入为修订/ }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('选区原文已找不到'))
    expect(onApplied).not.toHaveBeenCalled()
    expect(screen.getByText('改法 1')).toBeTruthy()
  })

  it('写入抛错：提示写入失败，不通知父级刷新', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    applyTaskEdit.mockRejectedValue(new Error('文件被占用'))
    const onApplied = vi.fn()
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={onApplied} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /插入为修订/ }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('文件被占用'))
    expect(onApplied).not.toHaveBeenCalled()
  })

  it('选区变化清空旧候选：旧候选取自旧选区，不能插到新选区上', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    const { rerender } = render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))
    await waitFor(() => expect(screen.getByText('改法 1')).toBeTruthy())

    rerender(<ReviewAssistant taskId="t1" selection="另一段完全不同的原文。" onApplied={vi.fn()} />)
    await waitFor(() => expect(screen.queryByText('改法 1')).toBeNull())
  })

  it('autoPrompt 带入选区与指令：自动生成一次，并标注「来自建议卡」', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    render(
      <ReviewAssistant
        taskId="t1"
        selection=""
        autoPrompt={{ text: '承租人应提前三十日通知。', instruction: '按泰国法审查', seq: 1 }}
        onApplied={vi.fn()}
      />,
    )

    await waitFor(() => expect(suggestDirectEdit).toHaveBeenCalledTimes(1))
    expect(suggestDirectEdit).toHaveBeenCalledWith(
      expect.objectContaining({ selection: '承租人应提前三十日通知。', instruction: '按泰国法审查' }),
    )
    expect(screen.getByText('（来自建议卡）')).toBeTruthy()
  })

  it('同一 seq 重复渲染不重跑（自动生成一条建议只跑一次）', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [], context_before: '', context_after: '' })
    const base = { text: '原文', instruction: '按泰国法审查' }
    const { rerender } = render(
      <ReviewAssistant taskId="t1" selection="" autoPrompt={{ ...base, seq: 1 }} onApplied={vi.fn()} />,
    )
    await waitFor(() => expect(suggestDirectEdit).toHaveBeenCalledTimes(1))

    // 父级重渲染（同一条建议）不应再打一次接口
    rerender(<ReviewAssistant taskId="t1" selection="" autoPrompt={{ ...base, seq: 1 }} onApplied={vi.fn()} />)
    await new Promise((r) => setTimeout(r, 20))
    expect(suggestDirectEdit).toHaveBeenCalledTimes(1)
  })

  it('有候选时出现「换个说法」入口，点击重跑生成', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [{ suggested: '新写法', reason: '' }], context_before: '', context_after: '' })
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByRole('button', { name: '生成改法' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /换个说法/ })).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /换个说法/ }))
    await waitFor(() => expect(suggestDirectEdit).toHaveBeenCalledTimes(2))
  })

  it('⌘↵ 触发生成（键盘快捷键与按钮等价）', async () => {
    suggestDirectEdit.mockResolvedValue({ candidates: [], context_before: '', context_after: '' })
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)

    const textarea = screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方')
    fireEvent.change(textarea, { target: { value: '改一下' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    await waitFor(() => expect(suggestDirectEdit).toHaveBeenCalledTimes(1))
  })

  it('选区存在时点底部发送走 suggest；无选区时按 Enter 只提示不改文档', () => {
    render(<ReviewAssistant taskId="t1" selection={SEL} onApplied={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('例如：按泰国法审查这一条，我方是承租方'), { target: { value: '改一下' } })
    fireEvent.click(screen.getByLabelText('发送'))
    expect(suggestDirectEdit).toHaveBeenCalledTimes(1)
  })

  it('无选区时底部输入框按 Enter 只提示，不发请求', () => {
    render(<ReviewAssistant taskId="t1" selection="" onApplied={vi.fn()} />)
    const bottomInput = screen.getByPlaceholderText('无选区时只能提问，不会改文档')
    fireEvent.keyDown(bottomInput, { key: 'Enter' })
    expect(toast.info).toHaveBeenCalled()
    expect(suggestDirectEdit).not.toHaveBeenCalled()
  })
})
