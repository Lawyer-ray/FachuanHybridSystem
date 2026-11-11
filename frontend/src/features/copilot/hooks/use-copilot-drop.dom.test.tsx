// @vitest-environment jsdom
/**
 * useCopilotDrop 双通道投放测试（jsdom）。
 *
 * 两条通道的语义完全不同，混了就会静默坏掉：
 * - 内部拖拽（目录树 → 输入区）走自定义 MIME，携带引用（不复制字节）；
 * - 系统外文件走原生 Files，进上传流。
 *
 * 钉住的几处易错点：
 * - dragover 对两条通道都必须 preventDefault（否则 drop 根本不派发）；
 * - 高亮层只在 Files 通道出现；
 * - 子元素间 enter/leave 抖动靠计数器吸收，离到外层才熄灭；
 * - 流式/上传在途不收件；
 * - 非法 JSON / 不合规 payload 静默丢弃，不打断 drop。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilotDrop } from './use-copilot-drop'
import { useCopilot } from '../store'
import { FOLDER_REF_MIME } from '../types'

/** 造一个只带被测代码用到的成员的 DragEvent 替身 */
function dragEvent(opts: {
  types?: string[]
  getData?: (type: string) => string
  files?: File[]
}): { native: React.DragEvent; preventDefault: ReturnType<typeof vi.fn> } {
  const preventDefault = vi.fn()
  const native = {
    preventDefault,
    dataTransfer: {
      types: opts.types ?? [],
      getData: opts.getData ?? (() => ''),
      files: opts.files ?? [],
    },
  } as unknown as React.DragEvent
  return { native, preventDefault }
}

const file = (name: string) => new File(['x'], name, { type: 'application/pdf' })

beforeEach(() => {
  useCopilot.getState().reset()
  vi.clearAllMocks()
})

describe('useCopilotDrop', () => {
  it('Files 通道：enter 点亮高亮层，dragover 阻止默认', () => {
    const { result } = renderHook(() => useCopilotDrop())

    const enter = dragEvent({ types: ['Files'] })
    act(() => result.current.onDragEnter(enter.native))
    expect(enter.preventDefault).toHaveBeenCalled()
    expect(useCopilot.getState().draggingFiles).toBe(true)

    const over = dragEvent({ types: ['Files'] })
    act(() => result.current.onDragOver(over.native))
    expect(over.preventDefault).toHaveBeenCalled()
  })

  it('自定义 MIME 通道：dragover 也必须 preventDefault，但不点亮文件高亮层', () => {
    const { result } = renderHook(() => useCopilotDrop())

    const enter = dragEvent({ types: [FOLDER_REF_MIME] })
    act(() => result.current.onDragEnter(enter.native))
    expect(enter.preventDefault).toHaveBeenCalled()
    expect(useCopilot.getState().draggingFiles).toBe(false)

    const over = dragEvent({ types: [FOLDER_REF_MIME] })
    act(() => result.current.onDragOver(over.native))
    expect(over.preventDefault).toHaveBeenCalled()
  })

  it('无关 MIME：完全不干预（不 preventDefault，不点亮高亮）', () => {
    const { result } = renderHook(() => useCopilotDrop())

    const enter = dragEvent({ types: ['text/plain'] })
    act(() => result.current.onDragEnter(enter.native))
    expect(enter.preventDefault).not.toHaveBeenCalled()
    expect(useCopilot.getState().draggingFiles).toBe(false)

    const over = dragEvent({ types: ['text/plain'] })
    act(() => result.current.onDragOver(over.native))
    expect(over.preventDefault).not.toHaveBeenCalled()
  })

  it('计数器吸收子元素 enter/leave 抖动：离到最外层才熄灭高亮', () => {
    const { result } = renderHook(() => useCopilotDrop())

    act(() => result.current.onDragEnter(dragEvent({ types: ['Files'] }).native))
    act(() => result.current.onDragEnter(dragEvent({ types: ['Files'] }).native))
    expect(useCopilot.getState().draggingFiles).toBe(true)

    act(() => result.current.onDragLeave(dragEvent({ types: ['Files'] }).native))
    expect(useCopilot.getState().draggingFiles).toBe(true)

    act(() => result.current.onDragLeave(dragEvent({ types: ['Files'] }).native))
    expect(useCopilot.getState().draggingFiles).toBe(false)
  })

  it('自定义 MIME 拖离不影响文件高亮计数', () => {
    const { result } = renderHook(() => useCopilotDrop())
    act(() => result.current.onDragLeave(dragEvent({ types: [FOLDER_REF_MIME] }).native))
    expect(useCopilot.getState().draggingFiles).toBe(false)
  })

  it('drop 系统文件：无条件复位高亮并交给上传流', () => {
    const { result } = renderHook(() => useCopilotDrop())
    act(() => result.current.onDragEnter(dragEvent({ types: ['Files'] }).native))
    expect(useCopilot.getState().draggingFiles).toBe(true)

    const drop = dragEvent({ types: ['Files'], files: [file('合同.pdf')] })
    act(() => result.current.onDrop(drop.native))

    expect(drop.preventDefault).toHaveBeenCalled()
    expect(useCopilot.getState().draggingFiles).toBe(false)
    expect(useCopilot.getState().pendingFiles.map((f) => f.name)).toEqual(['合同.pdf'])
  })

  it('drop 新形态引用 payload：落成引用草稿', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const payload = JSON.stringify({ kind: 'contract', ownerId: 7, subpath: '往来/合同', name: '施工合同', isFolder: true })
    const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })

    act(() => result.current.onDrop(drop.native))

    expect(useCopilot.getState().pendingRefs).toEqual([
      { kind: 'contract', ownerId: 7, subpath: '往来/合同', name: '施工合同', isFolder: true },
    ])
    // 引用通道不产生附件
    expect(useCopilot.getState().pendingFiles).toEqual([])
  })

  it('带 kind 但用 contractId 命名（旧字段名）：两个字段都兜住', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const payload = JSON.stringify({ kind: 'contract', contractId: 11, subpath: '证据', name: 'listing.pdf' })
    const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })

    act(() => result.current.onDrop(drop.native))
    expect(useCopilot.getState().pendingRefs).toEqual([{ kind: 'contract', ownerId: 11, subpath: '证据', name: 'listing.pdf' }])
  })

  it('旧 payload 只带 contractId 时按合同归属接收（注释声称兼容旧形态）', () => {
    // 旧形态 {contractId} 本身没有 kind 字段，由「是哪个 id 字段」反推 kind。
    // 此前只认 d.kind，旧 payload 被静默丢弃，与本 hook 注释写的
    // 「兼容三种 payload 形态：旧 {contractId} / 新 {kind, ownerId}」相矛盾。
    const { result } = renderHook(() => useCopilotDrop())
    const payload = JSON.stringify({ contractId: 11, subpath: '证据', name: 'listing.pdf' })
    const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })

    act(() => result.current.onDrop(drop.native))
    expect(useCopilot.getState().pendingRefs).toEqual([
      { kind: 'contract', ownerId: 11, subpath: '证据', name: 'listing.pdf' },
    ])
  })

  it('旧 payload 只带 caseId 时按案件归属接收', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const payload = JSON.stringify({ caseId: 7, subpath: '卷宗', name: '证据目录' })
    const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })

    act(() => result.current.onDrop(drop.native))
    expect(useCopilot.getState().pendingRefs).toEqual([
      { kind: 'case', ownerId: 7, subpath: '卷宗', name: '证据目录' },
    ])
  })

  it('两个 id 字段都没有、kind 也缺失时丢弃：无法判定归属', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const payload = JSON.stringify({ subpath: '证据', name: 'listing.pdf' })
    const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })

    act(() => result.current.onDrop(drop.native))
    expect(useCopilot.getState().pendingRefs).toEqual([])
  })

  it('drop 案件引用：ownerId 取 caseId', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const payload = JSON.stringify({ kind: 'case', caseId: 5, subpath: '卷宗', name: '起诉状' })
    const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })

    act(() => result.current.onDrop(drop.native))
    expect(useCopilot.getState().pendingRefs).toEqual([{ kind: 'case', ownerId: 5, subpath: '卷宗', name: '起诉状' }])
  })

  it('不合规引用 payload 静默丢弃（kind 未知 / ownerId 非数字 / subpath 空）', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const bad = [
      JSON.stringify({ kind: 'other', ownerId: 1, subpath: 'x' }),
      JSON.stringify({ kind: 'contract', ownerId: '1', subpath: 'x' }),
      JSON.stringify({ kind: 'contract', ownerId: 1, subpath: '' }),
    ]
    for (const payload of bad) {
      const drop = dragEvent({ types: [FOLDER_REF_MIME], getData: (t) => (t === FOLDER_REF_MIME ? payload : '') })
      act(() => result.current.onDrop(drop.native))
    }
    expect(useCopilot.getState().pendingRefs).toEqual([])
  })

  it('非法 JSON 静默丢弃：不当作文件处理', () => {
    const { result } = renderHook(() => useCopilotDrop())
    const drop = dragEvent({
      types: [FOLDER_REF_MIME, 'Files'],
      getData: (t) => (t === FOLDER_REF_MIME ? '{not json' : ''),
      files: [file('a.pdf')],
    })
    act(() => result.current.onDrop(drop.native))

    expect(useCopilot.getState().pendingRefs).toEqual([])
    expect(useCopilot.getState().pendingFiles).toEqual([])
  })

  it('流式在途不收件：引用与文件都不落地，但高亮仍复位', () => {
    useCopilot.setState({ streaming: true })
    const { result } = renderHook(() => useCopilotDrop())

    const refDrop = dragEvent({
      types: [FOLDER_REF_MIME],
      getData: (t) => (t === FOLDER_REF_MIME ? JSON.stringify({ kind: 'contract', ownerId: 1, subpath: 'x' }) : ''),
    })
    act(() => result.current.onDrop(refDrop.native))

    const fileDrop = dragEvent({ types: ['Files'], files: [file('a.pdf')] })
    act(() => result.current.onDrop(fileDrop.native))

    expect(useCopilot.getState().pendingRefs).toEqual([])
    expect(useCopilot.getState().pendingFiles).toEqual([])
    expect(useCopilot.getState().draggingFiles).toBe(false)
  })

  it('上传在途不收件', () => {
    useCopilot.setState({ uploadingAttachments: true })
    const { result } = renderHook(() => useCopilotDrop())

    const drop = dragEvent({ types: ['Files'], files: [file('a.pdf')] })
    act(() => result.current.onDrop(drop.native))
    expect(useCopilot.getState().pendingFiles).toEqual([])
  })

  it('在途中 enter 不点亮高亮（避免用户以为能投放）', () => {
    useCopilot.setState({ streaming: true })
    const { result } = renderHook(() => useCopilotDrop())

    const enter = dragEvent({ types: ['Files'] })
    act(() => result.current.onDragEnter(enter.native))
    expect(enter.preventDefault).toHaveBeenCalled()
    expect(useCopilot.getState().draggingFiles).toBe(false)
  })

  it('拖入文件夹（files 为空列表）也复位高亮，不让遮罩残留', () => {
    const { result } = renderHook(() => useCopilotDrop())
    act(() => result.current.onDragEnter(dragEvent({ types: ['Files'] }).native))

    const drop = dragEvent({ types: ['Files'], files: [] })
    act(() => result.current.onDrop(drop.native))

    expect(useCopilot.getState().draggingFiles).toBe(false)
    expect(useCopilot.getState().pendingFiles).toEqual([])
  })
})
