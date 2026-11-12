// @vitest-environment jsdom
/**
 * ReaderDialogs 接线测试（jsdom）。
 *
 * 本组件只做「开关 → 弹窗」的接线，因此断言的是受控语义：
 * - OCR 面板、归案框只在对应值/布尔为真时出现；
 * - 归案的段数取 draft.segs.length（不是父级另算的数）；
 * - 删除确认的标题带实际页数，避免「删 3 页」写成「删 0 页」这类误导。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./OcrPanel', () => ({
  OcrPanel: ({ fromLabel, toLabel, onOk }: { fromLabel: string; toLabel: string; onOk: () => void }) => (
    <div data-testid="ocr-panel">
      OCR {fromLabel}→{toLabel}
      <button type="button" onClick={onOk}>
        OCR 填入
      </button>
    </div>
  ),
}))
vi.mock('./AssignModal', () => ({
  // 真实 AssignModal 会把填好的归属对象回传，替身只关心「有没有转发」
  AssignModal: ({ count, onConfirm }: { count: number; onConfirm: (assign: unknown) => void }) => (
    <div data-testid="assign-modal">
      归案 {count} 段
      <button type="button" onClick={() => onConfirm({})}>
        归案确认
      </button>
    </div>
  ),
}))
vi.mock('./RenameMatDialog', () => ({
  RenameMatDialog: ({ target }: { target: { mi: number; initial: string } | null }) =>
    target ? <div data-testid="rename-mat">重命名源文件 {target.initial}</div> : null,
}))
vi.mock('../RenamePackDialog', () => ({
  RenamePackDialog: ({ open }: { open: boolean }) => (open ? <div data-testid="rename-pack">重命名材料包</div> : null),
}))

import { ReaderDialogs } from './ReaderDialogs'
import type { DraftState, InboxMessageDetail, OcrPending, PageKey } from '../../types'

const draft = { segs: [{}, {}, {}], infos: [] } as unknown as DraftState
const detail = { id: 1, subject: '材料包 A' } as unknown as InboxMessageDetail
const ocrPending: OcrPending = {
  mi: 0,
  p: 3,
  rect: { x: 0, y: 0, w: 100, h: 40 },
  text: '识别文字',
  loading: false,
}

function props(over: Partial<Parameters<typeof ReaderDialogs>[0]> = {}) {
  return {
    draft,
    detail,
    ocrPending: null,
    ocrFrom: '第 3 页',
    ocrTo: '第 4 页',
    onOcrText: vi.fn(),
    onOcrRedo: vi.fn(),
    onOcrCancel: vi.fn(),
    onOcrOk: vi.fn(),
    showAssign: false,
    onAssignCancel: vi.fn(),
    onAssignConfirm: vi.fn(),
    deleteTarget: null,
    onDeleteCancel: vi.fn(),
    onDeleteConfirm: vi.fn(),
    renaming: false,
    onRenamingChange: vi.fn(),
    renameMat: null,
    onRenameMatClose: vi.fn(),
    ...over,
  }
}

describe('ReaderDialogs', () => {
  it('全部关闭时四个弹窗都不出现', () => {
    render(<ReaderDialogs {...props()} />)
    expect(screen.queryByTestId('ocr-panel')).toBeNull()
    expect(screen.queryByTestId('assign-modal')).toBeNull()
    expect(screen.queryByTestId('rename-pack')).toBeNull()
    expect(screen.queryByTestId('rename-mat')).toBeNull()
  })

  it('ocrPending 存在：OCR 面板带上起止页，确认回传 onOcrOk', () => {
    const onOcrOk = vi.fn()
    render(<ReaderDialogs {...props({ ocrPending, onOcrOk })} />)

    expect(screen.getByText('OCR 第 3 页→第 4 页')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'OCR 填入' }))
    expect(onOcrOk).toHaveBeenCalledTimes(1)
  })

  it('归案段的段数取 draft.segs.length，确认回传归属', () => {
    const onAssignConfirm = vi.fn()
    render(<ReaderDialogs {...props({ showAssign: true, onAssignConfirm })} />)

    expect(screen.getByText('归案 3 段')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '归案确认' }))
    expect(onAssignConfirm).toHaveBeenCalledTimes(1)
  })

  it('删除确认的标题带实际页数', () => {
    render(<ReaderDialogs {...props({ deleteTarget: [0, 1] as unknown as PageKey[] })} />)
    expect(screen.getByText('确认删除所选 2 页？')).toBeTruthy()
  })

  it('deleteTarget 为 null 时标题按 0 页（且框不渲染）', () => {
    render(<ReaderDialogs {...props()} />)
    expect(screen.queryByText(/确认删除所选/)).toBeNull()
  })

  it('renaming 与 renameMat 分别控制两个重命名弹窗', () => {
    render(<ReaderDialogs {...props({ renaming: true, renameMat: { mi: 1, initial: '证据.pdf' } })} />)
    expect(screen.getByTestId('rename-pack')).toBeTruthy()
    expect(screen.getByText(/证据\.pdf/)).toBeTruthy()
  })
})
