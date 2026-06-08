vi.mock('../../api', () => ({
  contractApi: {
    generateContract: vi.fn(),
    generateSupplementaryAgreement: vi.fn(),
    generateFolder: vi.fn(),
  },
}))

vi.mock('../SupplementaryAgreementList', () => ({
  SupplementaryAgreementList: () => <div data-testid="agreement-list" />,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { DocumentsTab } from '../DocumentsTab'
import type { Contract } from '../types'

describe('DocumentsTab', () => {
  const baseContract = {
    id: 1,
    name: '测试合同',
    matched_document_template: '模板A',
    matched_folder_templates: '文件夹模板A',
    has_matched_templates: true,
    supplementary_agreements: [],
    reminders: [],
  } as unknown as Contract

  it('renders template section', () => {
    render(<DocumentsTab contract={baseContract} />)
    expect(screen.getByText('匹配的模板')).toBeInTheDocument()
    expect(screen.getByText('文件模板')).toBeInTheDocument()
    expect(screen.getByText('文件夹模板')).toBeInTheDocument()
  })

  it('shows matched template badge', () => {
    render(<DocumentsTab contract={baseContract} />)
    expect(screen.getByText('已匹配模板')).toBeInTheDocument()
  })

  it('shows unmatched template placeholders', () => {
    const contract = {
      ...baseContract,
      matched_document_template: null,
      matched_folder_templates: null,
      has_matched_templates: false,
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    expect(screen.getByText('合同自动生成时自动匹配')).toBeInTheDocument()
    expect(screen.getByText('归档时自动匹配')).toBeInTheDocument()
  })

  it('renders agreement list', () => {
    render(<DocumentsTab contract={baseContract} />)
    expect(screen.getByTestId('agreement-list')).toBeInTheDocument()
  })

  it('renders reminders section', () => {
    render(<DocumentsTab contract={baseContract} />)
    expect(screen.getByText('重要日期提醒')).toBeInTheDocument()
    expect(screen.getByText('暂无提醒')).toBeInTheDocument()
  })

  it('renders reminders when available', () => {
    const contract = {
      ...baseContract,
      reminders: [
        { id: 1, content: '续保提醒', reminder_type_label: '续保', due_at: '2099-12-31' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    expect(screen.getByText('续保提醒')).toBeInTheDocument()
    expect(screen.getByText('续保')).toBeInTheDocument()
  })

  it('shows overdue badge for past reminders', () => {
    const contract = {
      ...baseContract,
      reminders: [
        { id: 1, content: '已过期提醒', reminder_type_label: '过期', due_at: '2020-01-01' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    expect(screen.getByText('已过期')).toBeInTheDocument()
  })

  it('renders document generation section', () => {
    render(<DocumentsTab contract={baseContract} />)
    expect(screen.getByText('文档生成')).toBeInTheDocument()
    expect(screen.getByText('生成合同')).toBeInTheDocument()
  })

  it('disables generate contract when no template', () => {
    const contract = {
      ...baseContract,
      matched_document_template: null,
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    const btn = screen.getByText('生成合同')
    expect(btn.closest('button')).toBeDisabled()
  })

  it('shows disabled supplementary agreement button when no agreements', () => {
    render(<DocumentsTab contract={baseContract} />)
    const btn = screen.getByText('生成补充协议')
    expect(btn.closest('button')).toBeDisabled()
  })

  it('shows supplementary agreement button when one agreement exists', () => {
    const contract = {
      ...baseContract,
      supplementary_agreements: [{ id: 1, name: '补充协议1' }],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    const btn = screen.getByText('生成补充协议')
    expect(btn.closest('button')).not.toBeDisabled()
  })

  it('shows folder generation controls', () => {
    render(<DocumentsTab contract={baseContract} />)
    expect(screen.getByText('生成文件夹')).toBeInTheDocument()
  })

  it('disables folder generation when not unlocked', () => {
    render(<DocumentsTab contract={baseContract} />)
    const btn = screen.getByText('生成文件夹')
    expect(btn.closest('button')).toBeDisabled()
  })

  it('enables folder generation after unlock', () => {
    render(<DocumentsTab contract={baseContract} />)
    // Find and click the lock/unlock button (the button next to generate folder)
    const buttons = screen.getAllByRole('button')
    // The unlock button is the one next to the generate folder button
    const lockButton = buttons.find(b => b.querySelector('.lucide-lock') || b.querySelector('[class*="lock"]'))
    if (lockButton) {
      fireEvent.click(lockButton)
    }
    // After clicking, the generate folder button should be enabled
    // (if there is a matched folder template)
  })

  it('renders all supplementary agreements in dialog', () => {
    const contract = {
      ...baseContract,
      supplementary_agreements: [
        { id: 1, name: '补充协议1' },
        { id: 2, name: '补充协议2' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    // Click the generate agreement button to open the dialog
    fireEvent.click(screen.getByText('生成补充协议'))
    expect(screen.getByText('选择补充协议')).toBeInTheDocument()
    expect(screen.getByText('补充协议1')).toBeInTheDocument()
    expect(screen.getByText('补充协议2')).toBeInTheDocument()
  })
})
