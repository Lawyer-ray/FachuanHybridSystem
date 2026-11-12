// @vitest-environment jsdom
/**
 * DeskDialogs 接线测试（jsdom）。
 *
 * 本组件不持有状态，只负责把父级的 target 接成三个弹窗，因此断言的重点是
 * 「开关由 target 是否为空决定」和「回调带对了对象」：
 * - 归案的 count 用消息的 segs，确认时把消息原样回传；
 * - 删除确认的取消走 onDeleteCancel（关框不等于点了取消也算取消）；
 * - 重命名框只在 renameTarget 存在时打开。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./reader/AssignModal', () => ({
  AssignModal: ({ count, onCancel, onConfirm }: { count: number; onCancel: () => void; onConfirm: () => void }) => (
    <div data-testid="assign-modal">
      <span>归案 {count} 段</span>
      <button type="button" onClick={onCancel}>
        归案取消
      </button>
      <button type="button" onClick={onConfirm}>
        归案确认
      </button>
    </div>
  ),
}))
vi.mock('./RenamePackDialog', () => ({
  RenamePackDialog: ({ open, pack }: { open: boolean; pack: { subject: string } | null }) =>
    open ? <div data-testid="rename-dialog">重命名 {pack?.subject}</div> : null,
}))

import { DeskDialogs } from './DeskDialogs'
import type { InboxMessage } from '../types'

const pack = { id: 1, subject: '材料包 A', segs: 3 } as unknown as InboxMessage

function baseProps() {
  return {
    assigning: null,
    onAssignCancel: vi.fn(),
    onAssignConfirm: vi.fn(),
    deleteTarget: null,
    onDeleteCancel: vi.fn(),
    onDeleteConfirm: vi.fn(),
    deleting: false,
    renameTarget: null,
    onRenameOpenChange: vi.fn(),
  }
}

describe('DeskDialogs', () => {
  it('三个 target 都为空：不出现归案框与重命名框', () => {
    render(<DeskDialogs {...baseProps()} />)
    expect(screen.queryByTestId('assign-modal')).toBeNull()
    expect(screen.queryByTestId('rename-dialog')).toBeNull()
  })

  it('assigning 存在：归案框带 segs 数，确认时把消息原样回传', () => {
    const onAssignConfirm = vi.fn()
    render(<DeskDialogs {...baseProps()} assigning={pack} onAssignConfirm={onAssignConfirm} />)

    expect(screen.getByText('归案 3 段')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '归案确认' }))
    expect(onAssignConfirm).toHaveBeenCalledWith(pack)
  })

  it('归案取消回传 onAssignCancel', () => {
    const onAssignCancel = vi.fn()
    render(<DeskDialogs {...baseProps()} assigning={pack} onAssignCancel={onAssignCancel} />)
    fireEvent.click(screen.getByRole('button', { name: '归案取消' }))
    expect(onAssignCancel).toHaveBeenCalledTimes(1)
  })

  it('deleteTarget 存在：确认框标题带材料包名，确认走 onDeleteConfirm', () => {
    const onDeleteConfirm = vi.fn()
    render(<DeskDialogs {...baseProps()} deleteTarget={pack} onDeleteConfirm={onDeleteConfirm} />)

    expect(screen.getByText('删除「材料包 A」？')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(onDeleteConfirm).toHaveBeenCalledTimes(1)
  })

  it('删除框点取消走 onDeleteCancel', () => {
    const props = baseProps()
    render(<DeskDialogs {...props} deleteTarget={pack} />)
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(props.onDeleteCancel).toHaveBeenCalledTimes(1)
  })

  it('deleting 中：确认按钮换文案拦住重复提交，且不再回传 onDeleteConfirm', () => {
    const props = baseProps()
    render(<DeskDialogs {...props} deleteTarget={pack} deleting />)

    fireEvent.click(screen.getByRole('button', { name: '处理中…' }))
    expect(props.onDeleteConfirm).not.toHaveBeenCalled()
    expect((screen.getByRole('button', { name: '取消' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('renameTarget 存在才打开重命名框，并带上该包', () => {
    render(<DeskDialogs {...baseProps()} renameTarget={pack} />)
    const dialog = screen.getByTestId('rename-dialog')
    expect(within(dialog).getByText('重命名 材料包 A')).toBeTruthy()
  })
})
