import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import SettingsOverviewPage from '../SettingsOverviewPage'
import LawFirmSettingsPage from '../LawFirmSettingsPage'
import TeamSettingsPage from '../TeamSettingsPage'
import LawyerSettingsPage from '../LawyerSettingsPage'
import ServiceConfigPage from '../ServiceConfigPage'

// Mock settings feature components
vi.mock('@/features/settings/components/SettingsOverview', () => ({
  SettingsOverview: () => <div data-testid="settings-overview">SettingsOverview</div>,
}))

vi.mock('@/features/settings/components/LawFirmSettings', () => ({
  LawFirmSettings: () => <div data-testid="lawfirm-settings">LawFirmSettings</div>,
}))

vi.mock('@/features/settings/components/TeamSettings', () => ({
  TeamSettings: () => <div data-testid="team-settings">TeamSettings</div>,
}))

vi.mock('@/features/settings/components/LawyerSettings', () => ({
  LawyerSettings: () => <div data-testid="lawyer-settings">LawyerSettings</div>,
}))

vi.mock('@/features/settings/components/ServiceConfig', () => ({
  ServiceConfig: () => <div data-testid="service-config">ServiceConfig</div>,
}))

describe('SettingsOverviewPage', () => {
  it('renders SettingsOverview component', () => {
    render(
      <MemoryRouter>
        <SettingsOverviewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('settings-overview')).toBeInTheDocument()
  })
})

describe('LawFirmSettingsPage', () => {
  it('renders LawFirmSettings component', () => {
    render(
      <MemoryRouter>
        <LawFirmSettingsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawfirm-settings')).toBeInTheDocument()
  })
})

describe('TeamSettingsPage', () => {
  it('renders TeamSettings component', () => {
    render(
      <MemoryRouter>
        <TeamSettingsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('team-settings')).toBeInTheDocument()
  })
})

describe('LawyerSettingsPage', () => {
  it('renders LawyerSettings component', () => {
    render(
      <MemoryRouter>
        <LawyerSettingsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lawyer-settings')).toBeInTheDocument()
  })
})

describe('ServiceConfigPage', () => {
  it('renders ServiceConfig component', () => {
    render(
      <MemoryRouter>
        <ServiceConfigPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('service-config')).toBeInTheDocument()
  })
})
