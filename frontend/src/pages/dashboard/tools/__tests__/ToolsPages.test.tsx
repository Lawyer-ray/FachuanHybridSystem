import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import CourtSmsPage from '../CourtSmsPage'
import CourtSmsDetailPage from '../CourtSmsDetailPage'
import CourierTrackingPage from '../CourierTrackingPage'
import ElementConvertPage from '../ElementConvertPage'
import LprCalculatorPage from '../LprCalculatorPage'
import ContentOpsPage from '../ContentOpsPage'
import ContentOpsInspirationPage from '../ContentOpsInspirationPage'

// Mock tool feature components
vi.mock('@/features/tools', () => ({
  CourtSmsTool: () => <div data-testid="court-sms-tool">CourtSmsTool</div>,
  CourierTrackingTool: () => <div data-testid="courier-tracking-tool">CourierTrackingTool</div>,
  ElementConvertTool: () => <div data-testid="element-convert-tool">ElementConvertTool</div>,
  LprCalculatorTool: () => <div data-testid="lpr-calculator-tool">LprCalculatorTool</div>,
}))

vi.mock('@/features/tools/components/CourtSmsDetail', () => ({
  CourtSmsDetail: ({ smsId }: { smsId: number }) => (
    <div data-testid="court-sms-detail">CourtSmsDetail-{smsId}</div>
  ),
}))

vi.mock('@/features/content-ops', () => ({
  ContentWorkbench: () => <div data-testid="content-workbench">ContentWorkbench</div>,
  InspirationPage: () => <div data-testid="inspiration-page">InspirationPage</div>,
}))

describe('CourtSmsPage', () => {
  it('renders CourtSmsTool component', () => {
    render(
      <MemoryRouter>
        <CourtSmsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('court-sms-tool')).toBeInTheDocument()
  })
})

describe('CourtSmsDetailPage', () => {
  it('renders CourtSmsDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/tools/court-sms/42']}>
        <Routes>
          <Route path="/admin/tools/court-sms/:id" element={<CourtSmsDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('court-sms-detail')).toBeInTheDocument()
    expect(screen.getByText('CourtSmsDetail-42')).toBeInTheDocument()
  })
})

describe('CourierTrackingPage', () => {
  it('renders CourierTrackingTool component', () => {
    render(
      <MemoryRouter>
        <CourierTrackingPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('courier-tracking-tool')).toBeInTheDocument()
  })
})

describe('ElementConvertPage', () => {
  it('renders ElementConvertTool component', () => {
    render(
      <MemoryRouter>
        <ElementConvertPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('element-convert-tool')).toBeInTheDocument()
  })
})

describe('LprCalculatorPage', () => {
  it('renders LprCalculatorTool component', () => {
    render(
      <MemoryRouter>
        <LprCalculatorPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('lpr-calculator-tool')).toBeInTheDocument()
  })
})

describe('ContentOpsPage', () => {
  it('renders ContentWorkbench component', () => {
    render(
      <MemoryRouter>
        <ContentOpsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('content-workbench')).toBeInTheDocument()
  })
})

describe('ContentOpsInspirationPage', () => {
  it('renders InspirationPage component', () => {
    render(
      <MemoryRouter>
        <ContentOpsInspirationPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('inspiration-page')).toBeInTheDocument()
  })
})
