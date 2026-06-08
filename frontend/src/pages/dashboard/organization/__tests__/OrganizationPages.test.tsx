import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { OrganizationPage } from '../OrganizationPage'
import { LawFirmNewPage } from '../lawfirms/LawFirmNewPage'
import { LawFirmDetailPage } from '../lawfirms/LawFirmDetailPage'
import { LawFirmEditPage } from '../lawfirms/LawFirmEditPage'
import { LawyerNewPage } from '../lawyers/LawyerNewPage'
import { LawyerDetailPage } from '../lawyers/LawyerDetailPage'
import { LawyerEditPage } from '../lawyers/LawyerEditPage'

// Mock feature components
vi.mock('@/features/organization/components/OrganizationTabs', () => ({
  OrganizationTabs: () => <div data-testid="organization-tabs">OrganizationTabs</div>,
}))

vi.mock('@/features/organization/components/LawFirmForm', () => ({
  LawFirmForm: ({ mode, lawFirmId }: { mode: string; lawFirmId?: string }) => (
    <div data-testid="lawfirm-form">LawFirmForm-{mode}{lawFirmId ? `-${lawFirmId}` : ''}</div>
  ),
}))

vi.mock('@/features/organization/components/LawFirmDetail', () => ({
  LawFirmDetail: ({ lawFirmId }: { lawFirmId: string }) => (
    <div data-testid="lawfirm-detail">LawFirmDetail-{lawFirmId}</div>
  ),
}))

vi.mock('@/features/organization/components/LawyerForm', () => ({
  LawyerForm: ({ mode, lawyerId }: { mode: string; lawyerId?: string }) => (
    <div data-testid="lawyer-form">LawyerForm-{mode}{lawyerId ? `-${lawyerId}` : ''}</div>
  ),
}))

vi.mock('@/features/organization/components/LawyerDetail', () => ({
  LawyerDetail: ({ lawyerId }: { lawyerId: string }) => (
    <div data-testid="lawyer-detail">LawyerDetail-{lawyerId}</div>
  ),
}))

vi.mock('@/features/organization/hooks/use-lawfirm', () => ({
  useLawFirm: vi.fn().mockReturnValue({
    data: { id: '1', name: '测试律所' },
    isLoading: false,
  }),
}))

vi.mock('@/features/organization/hooks/use-lawyer', () => ({
  useLawyer: vi.fn().mockReturnValue({
    data: { id: '1', real_name: '张律师', username: 'zhang' },
    isLoading: false,
  }),
}))

vi.mock('@/contexts/BreadcrumbContext', () => ({
  useBreadcrumb: vi.fn(),
}))

describe('OrganizationPage', () => {
  it('renders the page title', () => {
    render(
      <MemoryRouter>
        <OrganizationPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('组织管理')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <OrganizationPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('管理律所、律师、团队和账号凭证信息')).toBeInTheDocument()
  })

  it('renders OrganizationTabs component', () => {
    render(
      <MemoryRouter>
        <OrganizationPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('organization-tabs')).toBeInTheDocument()
  })
})

describe('LawFirmNewPage', () => {
  it('renders LawFirmForm in create mode', () => {
    render(
      <MemoryRouter>
        <LawFirmNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawfirm-form')).toBeInTheDocument()
    expect(screen.getByText('LawFirmForm-create')).toBeInTheDocument()
  })
})

describe('LawFirmDetailPage', () => {
  it('renders LawFirmDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/organization/lawfirms/42']}>
        <Routes>
          <Route path="/admin/organization/lawfirms/:id" element={<LawFirmDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawfirm-detail')).toBeInTheDocument()
    expect(screen.getByText('LawFirmDetail-42')).toBeInTheDocument()
  })
})

describe('LawFirmEditPage', () => {
  it('renders LawFirmForm in edit mode', () => {
    render(
      <MemoryRouter initialEntries={['/admin/organization/lawfirms/42/edit']}>
        <Routes>
          <Route path="/admin/organization/lawfirms/:id/edit" element={<LawFirmEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawfirm-form')).toBeInTheDocument()
    expect(screen.getByText('LawFirmForm-edit-42')).toBeInTheDocument()
  })
})

describe('LawyerNewPage', () => {
  it('renders LawyerForm in create mode', () => {
    render(
      <MemoryRouter>
        <LawyerNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawyer-form')).toBeInTheDocument()
    expect(screen.getByText('LawyerForm-create')).toBeInTheDocument()
  })
})

describe('LawyerDetailPage', () => {
  it('renders LawyerDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/organization/lawyers/7']}>
        <Routes>
          <Route path="/admin/organization/lawyers/:id" element={<LawyerDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawyer-detail')).toBeInTheDocument()
    expect(screen.getByText('LawyerDetail-7')).toBeInTheDocument()
  })
})

describe('LawyerEditPage', () => {
  it('renders LawyerForm in edit mode', () => {
    render(
      <MemoryRouter initialEntries={['/admin/organization/lawyers/7/edit']}>
        <Routes>
          <Route path="/admin/organization/lawyers/:id/edit" element={<LawyerEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawyer-form')).toBeInTheDocument()
    expect(screen.getByText('LawyerForm-edit-7')).toBeInTheDocument()
  })
})
