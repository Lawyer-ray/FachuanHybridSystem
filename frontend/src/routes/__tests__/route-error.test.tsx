import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { RouteError } from '../route-error'

// Mock react-router hooks
vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return {
    ...actual,
    useRouteError: vi.fn(),
    isRouteErrorResponse: vi.fn((error: unknown) => {
      return error != null && typeof error === 'object' && 'status' in error && 'statusText' in error
    }),
    useNavigate: () => vi.fn(),
  }
})

// Mock lucide-react
vi.mock('lucide-react', () => ({
  AlertTriangle: (props: Record<string, unknown>) => <svg data-testid="alert-icon" {...props} />,
  RefreshCw: (props: Record<string, unknown>) => <svg data-testid="refresh-icon" {...props} />,
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left-icon" {...props} />,
}))

import { useRouteError, isRouteErrorResponse } from 'react-router'

const mockUseRouteError = vi.mocked(useRouteError)
const mockIsRouteErrorResponse = vi.mocked(isRouteErrorResponse)

describe('RouteError', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset isRouteErrorResponse to default behavior
    mockIsRouteErrorResponse.mockImplementation((error: unknown) => {
      return error != null && typeof error === 'object' && 'status' in error && 'statusText' in error
    })
  })

  it('renders error page with default title', () => {
    mockUseRouteError.mockReturnValue(new Error('test error'))

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    expect(screen.getByText('页面加载失败')).toBeInTheDocument()
  })

  it('renders error message for standard Error', () => {
    mockUseRouteError.mockReturnValue(new Error('something broke'))

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    expect(screen.getByText('something broke')).toBeInTheDocument()
  })

  it('renders error message for unknown error', () => {
    mockUseRouteError.mockReturnValue('unknown')

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    expect(screen.getByText('发生了未知错误')).toBeInTheDocument()
  })

  it('renders return and refresh buttons', () => {
    mockUseRouteError.mockReturnValue(new Error('test'))

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    expect(screen.getByText('返回')).toBeInTheDocument()
    expect(screen.getByText('刷新页面')).toBeInTheDocument()
  })

  it('renders alert icon', () => {
    mockUseRouteError.mockReturnValue(new Error('test'))

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('alert-icon')).toBeInTheDocument()
  })

  it('renders error message for route error response', () => {
    const routeError = {
      status: 404,
      statusText: 'Not Found',
    }
    mockIsRouteErrorResponse.mockReturnValue(true)
    mockUseRouteError.mockReturnValue(routeError as never)

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    expect(screen.getByText('404 Not Found')).toBeInTheDocument()
  })

  it('handles back button click', () => {
    mockUseRouteError.mockReturnValue(new Error('test'))

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    const backButton = screen.getByText('返回').closest('button')!
    expect(backButton).toBeInTheDocument()
    fireEvent.click(backButton)
  })

  it('handles refresh button click', () => {
    mockUseRouteError.mockReturnValue(new Error('test'))

    render(
      <MemoryRouter>
        <RouteError />
      </MemoryRouter>,
    )

    const refreshButton = screen.getByText('刷新页面').closest('button')!
    expect(refreshButton).toBeInTheDocument()
    fireEvent.click(refreshButton)
  })
})
