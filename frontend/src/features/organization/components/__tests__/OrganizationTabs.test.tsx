vi.mock('../LawFirmList', () => ({ LawFirmList: () => <div data-testid="lawfirm-list">LawFirmList</div> }))
vi.mock('../LawyerList', () => ({ LawyerList: () => <div data-testid="lawyer-list">LawyerList</div> }))
vi.mock('../TeamList', () => ({ TeamList: () => <div data-testid="team-list">TeamList</div> }))
vi.mock('../CredentialList', () => ({ CredentialList: () => <div data-testid="credential-list">CredentialList</div> }))

import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OrganizationTabs } from '../OrganizationTabs'

// Use MemoryRouter wrapper to provide useSearchParams
import { MemoryRouter } from 'react-router'

describe('OrganizationTabs', () => {
  const renderWithRouter = () => {
    return render(
      <MemoryRouter>
        <OrganizationTabs />
      </MemoryRouter>
    )
  }

  it('renders all four tab triggers', () => {
    renderWithRouter()
    expect(screen.getByText('律所')).toBeInTheDocument()
    expect(screen.getByText('律师')).toBeInTheDocument()
    expect(screen.getByText('团队')).toBeInTheDocument()
    expect(screen.getByText('凭证')).toBeInTheDocument()
  })

  it('shows LawFirmList by default', () => {
    renderWithRouter()
    expect(screen.getByTestId('lawfirm-list')).toBeInTheDocument()
  })

  it('switches to lawyers tab on click', async () => {
    renderWithRouter()
    await userEvent.click(screen.getByText('律师'))
    expect(screen.getByTestId('lawyer-list')).toBeInTheDocument()
  })

  it('switches to teams tab on click', async () => {
    renderWithRouter()
    await userEvent.click(screen.getByText('团队'))
    expect(screen.getByTestId('team-list')).toBeInTheDocument()
  })

  it('switches to credentials tab on click', async () => {
    renderWithRouter()
    await userEvent.click(screen.getByText('凭证'))
    expect(screen.getByTestId('credential-list')).toBeInTheDocument()
  })
})
