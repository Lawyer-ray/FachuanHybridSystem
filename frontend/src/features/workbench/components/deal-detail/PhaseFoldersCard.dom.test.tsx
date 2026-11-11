// @vitest-environment jsdom
/**
 * PhaseFoldersCard：右栏「合同文件夹」——由阶段树派生，不另存目录清单。
 *
 * 契约：目录名恒为 `<编号>-<阶段名>`（与磁盘上交付给客户的结构逐字一致），
 * 点子项把同一个名字交回调用方（它按同口径拼 subpath）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { info: vi.fn(), success: vi.fn(), error: vi.fn() } }))

import { toast } from 'sonner'

import { PhaseFoldersCard } from './PhaseFoldersCard'

const ROWS = [
  { no: '1', name: '尽职调查', depth: 1 },
  { no: '2', name: '方案设计', depth: 1 },
  { no: '2.1', name: '职工安置', depth: 2 },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PhaseFoldersCard', () => {
  it('目录名 = <编号>-<阶段名>', () => {
    render(<PhaseFoldersCard rows={ROWS} onOpenDir={vi.fn()} />)
    expect(screen.getByText('1-尽职调查')).toBeTruthy()
    expect(screen.getByText('2-方案设计')).toBeTruthy()
    expect(screen.getByText('2.1-职工安置')).toBeTruthy()
  })

  it('点子项把同一目录名交回调用方（subpath 由调用方按同口径拼）', () => {
    const onOpenDir = vi.fn()
    render(<PhaseFoldersCard rows={ROWS} onOpenDir={onOpenDir} />)
    fireEvent.click(screen.getByText('2.1-职工安置'))
    expect(onOpenDir).toHaveBeenCalledWith('2.1-职工安置')
  })

  it('层级越深缩进越多', () => {
    render(<PhaseFoldersCard rows={ROWS} onOpenDir={vi.fn()} />)
    const first = screen.getByText('1-尽职调查').closest('button') as HTMLElement
    const nested = screen.getByText('2.1-职工安置').closest('button') as HTMLElement
    expect(first.style.paddingLeft).toBe('4px')
    expect(nested.style.paddingLeft).toBe('16px')
  })

  it('空态：提示先设计阶段', () => {
    render(<PhaseFoldersCard rows={[]} onOpenDir={vi.fn()} />)
    expect(screen.getByText('还没有阶段，设计阶段后这里自动出现对应目录')).toBeTruthy()
  })

  it('「新建文件夹」给的是开发中提示，不假装已实现', () => {
    render(<PhaseFoldersCard rows={ROWS} onOpenDir={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /新建文件夹/ }))
    expect(toast.info).toHaveBeenCalledWith('新建文件夹正在开发中')
  })
})
