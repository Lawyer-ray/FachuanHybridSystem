import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { ClientListPage } from '../ClientListPage'
import { ClientNewPage } from '../ClientNewPage'
import { ClientDetailPage } from '../ClientDetailPage'
import { ClientEditPage } from '../ClientEditPage'

// Mock client feature components
vi.mock('@/features/clients/components/ClientList', () => ({
  ClientList: () => <div data-testid="client-list">ClientList</div>,
}))

vi.mock('@/features/clients/components/ClientForm', () => ({
  ClientForm: ({ mode, clientId }: { mode: string; clientId?: string }) => (
    <div data-testid="client-form">ClientForm-{mode}{clientId ? `-${clientId}` : ''}</div>
  ),
}))

vi.mock('@/features/clients/components/ClientDetail', () => ({
  ClientDetail: ({ clientId }: { clientId: string }) => (
    <div data-testid="client-detail">ClientDetail-{clientId}</div>
  ),
}))

vi.mock('@/features/clients/hooks/use-client', () => ({
  useClient: vi.fn().mockReturnValue({
    data: { id: '1', name: '张三' },
    isLoading: false,
  }),
}))

vi.mock('@/contexts/BreadcrumbContext', () => ({
  useBreadcrumb: vi.fn(),
}))

describe('ClientListPage', () => {
  it('renders ClientList component', () => {
    render(
      <MemoryRouter>
        <ClientListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('client-list')).toBeInTheDocument()
  })
})

describe('ClientNewPage', () => {
  it('renders ClientForm in create mode', () => {
    render(
      <MemoryRouter>
        <ClientNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('client-form')).toBeInTheDocument()
    expect(screen.getByText('ClientForm-create')).toBeInTheDocument()
  })
})

describe('ClientDetailPage', () => {
  it('renders ClientDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/clients/abc-123']}>
        <Routes>
          <Route path="/admin/clients/:id" element={<ClientDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('client-detail')).toBeInTheDocument()
    expect(screen.getByText('ClientDetail-abc-123')).toBeInTheDocument()
  })
})

describe('ClientEditPage', () => {
  it('renders ClientForm in edit mode with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/clients/abc-123/edit']}>
        <Routes>
          <Route path="/admin/clients/:id/edit" element={<ClientEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('client-form')).toBeInTheDocument()
    expect(screen.getByText('ClientForm-edit-abc-123')).toBeInTheDocument()
  })
})
