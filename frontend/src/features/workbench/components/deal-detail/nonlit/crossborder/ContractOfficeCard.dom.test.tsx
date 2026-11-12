// @vitest-environment jsdom
/**
 * ContractOfficeCard：合同原文卡（OnlyOffice 渲染 docx，锁定修订模式）。
 *
 * 契约要点：
 * - 交给 OnlyOffice 的必须是**站内下载路径 + review 模式**（DS 带不了
 *   Authorization 头，鉴权由后端 editor-config 换成签名代理地址）；写成外部
 *   URL 或 edit 模式都会让律师改到原件。
 * - 「全屏」只抬预览区高度，不接管整屏（演示时要同时看到下面的双语对照），
 *   按钮文案随之切换。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const office = vi.hoisted(() => ({ view: vi.fn() }))

vi.mock('@/components/shared/onlyoffice/OfficeView', () => ({
  OfficeView: (props: { fileUrl: string; fileName: string; mode: string }) => {
    office.view(props)
    return <div>OFFICE_VIEW</div>
  },
}))

import { ContractOfficeCard } from './ContractOfficeCard'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ContractOfficeCard', () => {
  it('把站内下载路径与 review 模式交给 OnlyOffice', () => {
    render(<ContractOfficeCard />)
    expect(screen.getByText('OFFICE_VIEW')).toBeTruthy()
    const props = office.view.mock.calls[0]![0]
    expect(props.fileUrl).toBe('/api/v1/contract-review/88a5cc96-58eb-48f5-aaf5-84e698c796d6/download')
    expect(props.fileUrl.startsWith('/api/')).toBe(true)
    expect(props.mode).toBe('review')
    expect(props.fileName).toBe('Factory_Lease_Agreement_TH-CN_v3.docx')
  })

  it('页头写明只读与修订处数', () => {
    render(<ContractOfficeCard />)
    expect(screen.getByText('合同原文 · 锁定修订')).toBeTruthy()
    expect(screen.getByText('docx 原件 · 修订共 5 处 · 只读')).toBeTruthy()
  })

  it('全屏按钮切换文案，预览区高度随之变化（不接管整屏）', () => {
    const { container } = render(<ContractOfficeCard />)
    const shell = () => container.querySelector('.overflow-hidden.rounded-\\[10px\\]') as HTMLElement

    expect(shell().className).toContain('h-[620px]')
    fireEvent.click(screen.getByRole('button', { name: /全屏/ }))
    expect(screen.getByRole('button', { name: /退出全屏/ })).toBeTruthy()
    expect(shell().className).toContain('h-[calc(100vh-200px)]')

    fireEvent.click(screen.getByRole('button', { name: /退出全屏/ }))
    expect(shell().className).toContain('h-[620px]')
  })
})
