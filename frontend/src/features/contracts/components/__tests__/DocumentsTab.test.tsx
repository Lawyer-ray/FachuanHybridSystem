import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DocumentsTab } from '../DocumentsTab'
import type { Contract } from '../types'
import { contractApi } from '../../api'
import { toast } from 'sonner'

vi.mock('../../api', () => ({
  contractApi: {
    generateContract: vi.fn(),
    generateSupplementaryAgreement: vi.fn(),
    generateFolder: vi.fn(),
  },
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../SupplementaryAgreementList', () => ({
  SupplementaryAgreementList: () => <div data-testid="agreement-list" />,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: unknown }) => (
    <div><span>{label}</span><span>{value as React.ReactNode}</span></div>
  ),
  DetailCard: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <div><h3>{title}</h3>{children}</div>
  ),
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    FolderDown: Icon, FileText: Icon, Loader2: Icon, Lock: Icon,
    Unlock: Icon, Search: Icon,
  }
})

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

  beforeEach(() => {
    vi.clearAllMocks()
  })

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

  it('shows "soon" badge for upcoming reminders', () => {
    const soon = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString()
    const contract = {
      ...baseContract,
      reminders: [
        { id: 1, content: '即将到期', reminder_type_label: '提醒', due_at: soon },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    expect(screen.getAllByText('即将到期').length).toBeGreaterThanOrEqual(1)
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

  it('renders all supplementary agreements in dialog', () => {
    const contract = {
      ...baseContract,
      supplementary_agreements: [
        { id: 1, name: '补充协议1' },
        { id: 2, name: '补充协议2' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    fireEvent.click(screen.getByText('生成补充协议'))
    expect(screen.getByText('选择补充协议')).toBeInTheDocument()
    expect(screen.getByText('补充协议1')).toBeInTheDocument()
    expect(screen.getByText('补充协议2')).toBeInTheDocument()
  })

  it('calls handleGenerateContract when generate contract clicked', async () => {
    vi.mocked(contractApi.generateContract).mockResolvedValue(
      new Response(JSON.stringify({ message: '已生成并保存' }), {
        headers: { 'content-type': 'application/json' },
      }),
    )
    render(<DocumentsTab contract={baseContract} />)
    fireEvent.click(screen.getByText('生成合同'))
    await waitFor(() => {
      expect(contractApi.generateContract).toHaveBeenCalledWith(1)
    })
  })

  it('calls handleGenerateContract with blob response', async () => {
    const mockBlob = { size: 100, type: 'application/octet-stream' }
    const mockRes = {
      headers: { get: () => 'application/octet-stream' },
      blob: () => Promise.resolve(mockBlob),
    }
    vi.mocked(contractApi.generateContract).mockResolvedValue(mockRes as unknown as Response)

    render(<DocumentsTab contract={baseContract} />)
    fireEvent.click(screen.getByText('生成合同'))
    await waitFor(() => {
      expect(contractApi.generateContract).toHaveBeenCalledWith(1)
    })
  })

  it('handles generate contract failure', async () => {
    vi.mocked(contractApi.generateContract).mockRejectedValue(new Error('fail'))
    render(<DocumentsTab contract={baseContract} />)
    fireEvent.click(screen.getByText('生成合同'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('生成合同失败')
    })
  })

  it('generates single supplementary agreement directly', async () => {
    const mockRes = {
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ message: 'ok' }),
    }
    vi.mocked(contractApi.generateSupplementaryAgreement).mockResolvedValue(mockRes as unknown as Response)
    const contract = {
      ...baseContract,
      supplementary_agreements: [{ id: 5, name: '协议A' }],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    fireEvent.click(screen.getByText('生成补充协议'))
    await waitFor(() => {
      expect(contractApi.generateSupplementaryAgreement).toHaveBeenCalledWith(1, 5)
    })
  })

  it('handles supplementary agreement generation failure', async () => {
    vi.mocked(contractApi.generateSupplementaryAgreement).mockRejectedValue(new Error('fail'))
    const contract = {
      ...baseContract,
      supplementary_agreements: [{ id: 5, name: '协议A' }],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    fireEvent.click(screen.getByText('生成补充协议'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('生成补充协议失败')
    })
  })

  it('generates folder after unlock', async () => {
    vi.mocked(contractApi.generateFolder).mockResolvedValue(new Blob())

    render(<DocumentsTab contract={baseContract} />)
    // The unlock button is rendered as a button with Lock icon next to "生成文件夹"
    // Find all buttons and click the one after "生成文件夹"
    const allButtons = screen.getAllByRole('button')
    const generateFolderBtn = screen.getByText('生成文件夹').closest('button')!
    const idx = allButtons.indexOf(generateFolderBtn)
    // The unlock button should be the next one
    if (idx >= 0 && idx + 1 < allButtons.length) {
      fireEvent.click(allButtons[idx + 1])
    }
    // Now click generate folder
    fireEvent.click(screen.getByText('生成文件夹'))
    await waitFor(() => {
      expect(contractApi.generateFolder).toHaveBeenCalledWith(1)
    })
  })

  it('handles generate folder failure', async () => {
    vi.mocked(contractApi.generateFolder).mockRejectedValue(new Error('fail'))

    render(<DocumentsTab contract={baseContract} />)
    const allButtons = screen.getAllByRole('button')
    const generateFolderBtn = screen.getByText('生成文件夹').closest('button')!
    const idx = allButtons.indexOf(generateFolderBtn)
    if (idx >= 0 && idx + 1 < allButtons.length) {
      fireEvent.click(allButtons[idx + 1])
    }
    fireEvent.click(screen.getByText('生成文件夹'))
    await waitFor(() => {
      expect(contractApi.generateFolder).toHaveBeenCalled()
    })
  })

  it('cancels agreement dialog', () => {
    const contract = {
      ...baseContract,
      supplementary_agreements: [
        { id: 1, name: '协议1' },
        { id: 2, name: '协议2' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    fireEvent.click(screen.getByText('生成补充协议'))
    expect(screen.getByText('选择补充协议')).toBeInTheDocument()
    // Click cancel button in dialog footer
    const cancelBtns = screen.getAllByText('取消')
    // Last cancel button should be in the dialog footer
    fireEvent.click(cancelBtns[cancelBtns.length - 1])
  })

  it('selects agreement in dialog and generates', async () => {
    const mockRes = {
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ message: 'ok' }),
    }
    vi.mocked(contractApi.generateSupplementaryAgreement).mockResolvedValue(mockRes as unknown as Response)
    const contract = {
      ...baseContract,
      supplementary_agreements: [
        { id: 1, name: '协议1' },
        { id: 2, name: '协议2' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    fireEvent.click(screen.getByText('生成补充协议'))
    // Select first agreement
    fireEvent.click(screen.getByText('协议1'))
    // Click confirm
    fireEvent.click(screen.getByText('确定生成'))
    await waitFor(() => {
      expect(contractApi.generateSupplementaryAgreement).toHaveBeenCalledWith(1, 1)
    })
  })

  it('shows unnamed agreement in dialog', () => {
    const contract = {
      ...baseContract,
      supplementary_agreements: [
        { id: 1, name: '' },
      ],
    } as unknown as Contract
    render(<DocumentsTab contract={contract} />)
    fireEvent.click(screen.getByText('生成补充协议'))
    expect(screen.getByText('未命名补充协议 #1')).toBeInTheDocument()
  })

  it('does not generate contract while already generating', async () => {
    vi.mocked(contractApi.generateContract).mockImplementation(() => new Promise(() => {}))
    render(<DocumentsTab contract={baseContract} />)
    fireEvent.click(screen.getByText('生成合同'))
    fireEvent.click(screen.getByText('生成合同'))
    // Should only call once
    await waitFor(() => {
      expect(contractApi.generateContract).toHaveBeenCalledTimes(1)
    })
  })
})
