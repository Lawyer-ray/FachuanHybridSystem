// @vitest-environment jsdom
/**
 * SpecialDocDrawer：交付物抽屉（下载 / 重命名 / 删除 / 重新起草）。
 *
 * 契约要点：
 * - 预览是**占位但说实话**：>6 页时页码只抽 6 个 + 「…共 N 页」；计划项（pending）直接空态
 * - 重命名走行内输入：Enter 提交、Escape 取消、空名字不提交
 * - 封面在、版本历史逐版可下载（按「名字 + 版本」交给调用方）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SpecialDocDrawer, type DrawerDoc } from './special-doc-drawer'

function doc(over: Partial<DrawerDoc> = {}): DrawerDoc {
  return {
    name: '职工安置方案与补偿测算表',
    pages: 34,
    status: 'drafting',
    updatedAt: '11-07 09:40',
    owner: '黄某某',
    phaseId: 'p2',
    phaseName: '职工安置',
    phaseSeq: '2',
    ...over,
  }
}

function setup(over: Partial<DrawerDoc> = {}) {
  const handlers = { onDownload: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(), onRedraft: vi.fn(), onClose: vi.fn() }
  const view = render(<SpecialDocDrawer open doc={doc(over)} {...handlers} />)
  return { ...handlers, ...view }
}

describe('外壳', () => {
  it('doc=null 时整块不渲染', () => {
    const { container } = render(
      <SpecialDocDrawer
        open
        doc={null}
        onClose={vi.fn()}
        onDownload={vi.fn()}
        onRename={vi.fn()}
        onDelete={vi.fn()}
        onRedraft={vi.fn()}
      />,
    )
    expect(container.textContent).toBe('')
  })

  it('副标题带阶段编号/名称/页数/上传人', () => {
    setup()
    expect(screen.getByText('2 职工安置 · 34 页 · 11-07 09:40 由 黄某某 上传')).toBeTruthy()
  })

  it('状态徽标按 status 走文案', () => {
    setup({ status: 'done' })
    expect(screen.getAllByText('已定稿').length).toBeGreaterThan(0)
  })
})

describe('预览占位', () => {
  it('超过 6 页时只抽 6 个页码 + 「…共 34 页」，且页码点一下就走下载', () => {
    const { onDownload } = setup({ pages: 34 })
    expect(screen.getByText('…共 34 页')).toBeTruthy()
    const chips = [1, 2, 3, 4, 5, 6].map((n) => screen.getByRole('button', { name: String(n) }))
    expect(chips).toHaveLength(6)
    expect(screen.queryByRole('button', { name: '7' })).toBeNull()
    fireEvent.click(chips[0]!)
    expect(onDownload).toHaveBeenCalledWith('职工安置方案与补偿测算表')
  })

  it('不超过 6 页时不显示「…共 N 页」', () => {
    setup({ pages: 4, name: '工商登记与股权结构核实', status: 'done' })
    expect(screen.queryByText(/^…共/)).toBeNull()
  })

  it('计划项（pending）没有文件，给空态而不是骨架', () => {
    setup({ status: 'pending', name: '清算方案（计划）' })
    expect(screen.getByText('计划中的交付物还没有文件，先「重新起草」生成草稿')).toBeTruthy()
  })

  it('明确标注「占位」与真实预览去向', () => {
    setup()
    expect(screen.getByText('占位')).toBeTruthy()
    expect(screen.getByText('真实预览走云端 Office')).toBeTruthy()
  })
})

describe('动作', () => {
  it('下载当前版本', () => {
    const { onDownload } = setup()
    fireEvent.click(screen.getByRole('button', { name: /下载$/ }))
    expect(onDownload).toHaveBeenCalledWith('职工安置方案与补偿测算表')
  })

  it('删除带当前名字交给调用方', () => {
    const { onDelete } = setup()
    fireEvent.click(screen.getByRole('button', { name: /删除/ }))
    expect(onDelete).toHaveBeenCalledWith('职工安置方案与补偿测算表')
  })

  it('重新起草带当前名字', () => {
    const { onRedraft } = setup()
    fireEvent.click(screen.getByRole('button', { name: /重新起草/ }))
    expect(onRedraft).toHaveBeenCalledWith('职工安置方案与补偿测算表')
  })
})

describe('重命名', () => {
  it('进入编辑态时输入框预填当前名字', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    expect((screen.getByDisplayValue('职工安置方案与补偿测算表') as HTMLInputElement).value).toBe(
      '职工安置方案与补偿测算表',
    )
  })

  it('Enter 提交新名字（去首尾空白）', () => {
    const { onRename } = setup()
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    const input = screen.getByDisplayValue('职工安置方案与补偿测算表')
    fireEvent.change(input, { target: { value: '  职工安置方案 v2  ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith('职工安置方案与补偿测算表', '职工安置方案 v2')
  })

  it('空名字不提交（只退出编辑）', () => {
    const { onRename } = setup()
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    const input = screen.getByDisplayValue('职工安置方案与补偿测算表')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.queryByDisplayValue('')).toBeNull()
  })

  it('Escape 取消，不提交', () => {
    const { onRename } = setup()
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    const input = screen.getByDisplayValue('职工安置方案与补偿测算表')
    fireEvent.change(input, { target: { value: '改了但取消' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.queryByDisplayValue('改了但取消')).toBeNull()
  })

  it('「取消」按钮同样只退出编辑', () => {
    const { onRename } = setup()
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onRename).not.toHaveBeenCalled()
  })

  it('「保存」按钮提交', () => {
    const { onRename } = setup()
    fireEvent.click(screen.getByRole('button', { name: /重命名/ }))
    const input = screen.getByDisplayValue('职工安置方案与补偿测算表')
    fireEvent.change(input, { target: { value: '新名字' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(onRename).toHaveBeenCalledWith('职工安置方案与补偿测算表', '新名字')
  })
})

describe('版本历史', () => {
  it('逐版可下载，参数是「名字 + 版本」（避免与服务端文件名混淆）', () => {
    const { onDownload } = setup()
    const downloadButtons = screen.getAllByTitle('下载该版本')
    expect(downloadButtons.length).toBeGreaterThan(0)
    fireEvent.click(downloadButtons[0]!)
    const arg = (onDownload as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0] as string
    expect(arg.startsWith('职工安置方案与补偿测算表 v')).toBe(true)
  })
})
