import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { ArchiveTab } from '../ArchiveTab'
import type { Contract } from '../../types'

vi.mock('../../api', () => ({
  contractApi: {
    getArchiveChecklist: vi.fn(),
    uploadArchiveItem: vi.fn().mockResolvedValue({}),
    deleteArchiveMaterial: vi.fn().mockResolvedValue({}),
    syncCaseMaterials: vi.fn().mockResolvedValue({ synced_count: 2 }),
    confirmArchive: vi.fn().mockResolvedValue({}),
    toggleCompactArchive: vi.fn().mockResolvedValue({}),
    scaleToA4: vi.fn().mockResolvedValue({}),
    moveArchiveMaterial: vi.fn().mockResolvedValue({}),
    reorderArchiveMaterials: vi.fn().mockResolvedValue({}),
    clearAllArchiveMaterials: vi.fn().mockResolvedValue({ deleted_count: 5 }),
    generateArchiveFolder: vi.fn().mockResolvedValue({ success: true, generated_docs: ['doc1'], errors: [] }),
    learnArchiveRules: vi.fn().mockResolvedValue({ success: true, message: 'learned' }),
    previewArchiveItem: vi.fn(),
    downloadArchiveItem: vi.fn(),
    previewSingleMaterial: vi.fn(),
    previewArchivePlaceholders: vi.fn().mockResolvedValue({ success: true, data: [{ key: 'k1', label: 'K1', value: 'V1' }] }),
  },
}))
vi.mock('../FolderScanPanel', () => ({
  FolderScanPanel: () => <div data-testid="folder-scan-panel" />,
}))

import { contractApi } from '../../api'

const baseContract = { id: 1, name: 'Test Contract', status: 'active' } as Contract

const baseChecklist = {
  items: [
    { code: 'item1', name: '起诉状', required: true, completed: true, template: null, auto_detect: null, has_case_material: false, materials: [{ id: 1, original_filename: 'file1.pdf', source: 'upload', source_label: '上传' }] },
    { code: 'item2', name: '证据目录', required: false, completed: false, template: null, auto_detect: null, has_case_material: true, materials: [] },
    { code: 'item3', name: '授权委托书', required: true, completed: false, template: 'auth_template', auto_detect: null, has_case_material: false, materials: [] },
  ],
  completed_count: 1,
  required_completed_count: 1,
  required_total_count: 2,
  completion_percentage: 33,
  compact_archive: false,
}

describe('ArchiveTab', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.mocked(contractApi.getArchiveChecklist).mockResolvedValue(baseChecklist)
  })

  it('renders checklist title', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    expect(screen.getByText('归档检查清单')).toBeInTheDocument()
  })

  it('renders checklist items', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('起诉状')
    expect(screen.getByText('证据目录')).toBeInTheDocument()
    expect(screen.getByText('授权委托书')).toBeInTheDocument()
  })

  it('renders progress bar', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    expect(screen.getAllByText(/1\/2/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders toolbar buttons', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('从合同文件夹同步')
    expect(screen.getByText('生成归档文件夹')).toBeInTheDocument()
    expect(screen.getByText('学习分类规则')).toBeInTheDocument()
    expect(screen.getByText('从案件材料同步')).toBeInTheDocument()
    expect(screen.getByText('缩放至A4')).toBeInTheDocument()
  })

  it('renders template item with preview and download buttons', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('授权委托书')
    // Template items have eye and download icons
    const previewButtons = screen.getAllByTitle('预览替换词')
    expect(previewButtons.length).toBeGreaterThan(0)
  })

  it('shows confirm archive button when canArchive', async () => {
    vi.mocked(contractApi.getArchiveChecklist).mockResolvedValue({
      ...baseChecklist,
      required_completed_count: 2,
      required_total_count: 2,
    })
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('确认归档')
    expect(screen.getByText('确认归档')).toBeInTheDocument()
  })

  it('does not show confirm archive when not all required done', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    expect(screen.queryByText('确认归档')).not.toBeInTheDocument()
  })

  it('handles checklist fetch error', async () => {
    vi.mocked(contractApi.getArchiveChecklist).mockRejectedValue(new Error('fail'))
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    // Should still render
    expect(screen.getByText('归档检查清单')).toBeInTheDocument()
  })

  it('opens folder scan dialog', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('从合同文件夹同步')
    fireEvent.click(screen.getByText('从合同文件夹同步'))
    expect(screen.getByTestId('folder-scan-panel')).toBeInTheDocument()
  })

  it('handles generate folder success', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('生成归档文件夹')
    fireEvent.click(screen.getByText('生成归档文件夹'))
    await screen.findByText('生成归档文件夹')
  })

  it('handles generate folder with docs', async () => {
    vi.mocked(contractApi.generateArchiveFolder).mockResolvedValue({
      success: true, generated_docs: ['doc1', 'doc2'], errors: [],
    })
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('生成归档文件夹')
    fireEvent.click(screen.getByText('生成归档文件夹'))
  })

  it('handles generate folder failure', async () => {
    vi.mocked(contractApi.generateArchiveFolder).mockResolvedValue({
      success: false, generated_docs: [], errors: ['Error occurred'],
    })
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('生成归档文件夹')
    fireEvent.click(screen.getByText('生成归档文件夹'))
  })

  it('handles learn rules', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('学习分类规则')
    fireEvent.click(screen.getByText('学习分类规则'))
  })

  it('handles learn rules failure', async () => {
    vi.mocked(contractApi.learnArchiveRules).mockResolvedValue({ success: false, message: 'Failed' })
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('学习分类规则')
    fireEvent.click(screen.getByText('学习分类规则'))
  })

  it('handles sync case materials', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('从案件材料同步')
    fireEvent.click(screen.getByText('从案件材料同步'))
  })

  it('handles scale to A4', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('缩放至A4')
    fireEvent.click(screen.getByText('缩放至A4'))
  })

  it('opens clear all dialog', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    const trashButtons = screen.getAllByTitle('清空全部材料')
    fireEvent.click(trashButtons[0])
    expect(screen.getByText('确认清空全部材料')).toBeInTheDocument()
  })

  it('shows required items count warning', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText(/必需项/)
    expect(screen.getByText(/必需项.*1\/2/)).toBeInTheDocument()
  })

  it('renders item badges for different types', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('起诉状')
    // completed item has ✓, required has !, template has ⚡, case_material has 📋
    expect(screen.getByText('⚡')).toBeInTheDocument() // template badge
    expect(screen.getByText('✓')).toBeInTheDocument() // completed badge
  })

  it('renders material count', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('(1)')
    // item1 has 1 material
  })

  it('renders compact mode toggle', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    const compactButton = screen.getByTitle('精简视图')
    expect(compactButton).toBeInTheDocument()
    fireEvent.click(compactButton)
  })

  it('renders expand all toggle', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    const expandButton = screen.getByTitle('展开全部子项')
    expect(expandButton).toBeInTheDocument()
  })

  it('handles empty checklist', async () => {
    vi.mocked(contractApi.getArchiveChecklist).mockResolvedValue({
      items: [], completed_count: 0, required_completed_count: 0,
      required_total_count: 0, completion_percentage: 0, compact_archive: false,
    })
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('归档检查清单')
    expect(screen.getByText('归档检查清单')).toBeInTheDocument()
  })

  it('renders with archived contract status', async () => {
    render(<ArchiveTab contract={{ ...baseContract, status: 'archived' } as Contract} />)
    await screen.findByText('归档检查清单')
    // canArchive should be false for archived contracts
    expect(screen.queryByText('确认归档')).not.toBeInTheDocument()
  })

  it('handles preview placeholders', async () => {
    render(<ArchiveTab contract={baseContract} />)
    await screen.findByText('授权委托书')
    const previewButtons = screen.getAllByTitle('预览替换词')
    fireEvent.click(previewButtons[0])
    await screen.findByText(/替换词预览/)
  })
})
