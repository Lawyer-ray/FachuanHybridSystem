import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import AutomationIndexPage from '../AutomationIndexPage'
import QuoteListPage from '../preservation-quotes/QuoteListPage'
import QuoteDetailPage from '../preservation-quotes/QuoteDetailPage'
import RecognitionListPage from '../document-recognition/RecognitionListPage'
import RecognitionDetailPage from '../document-recognition/RecognitionDetailPage'

// Mock feature components
vi.mock('@/features/automation/preservation-quotes', () => ({
  QuoteList: () => <div data-testid="quote-list">QuoteList</div>,
  QuoteDetail: ({ quoteId }: { quoteId: number }) => (
    <div data-testid="quote-detail">QuoteDetail-{quoteId}</div>
  ),
}))

vi.mock('@/features/automation/document-recognition', () => ({
  RecognitionList: () => <div data-testid="recognition-list">RecognitionList</div>,
  RecognitionDetail: ({ taskId }: { taskId: number }) => (
    <div data-testid="recognition-detail">RecognitionDetail-{taskId}</div>
  ),
}))

vi.mock('lucide-react', () => ({
  FileSearch: (props: Record<string, unknown>) => <svg data-testid="file-search" {...props} />,
  Calculator: (props: Record<string, unknown>) => <svg data-testid="calculator" {...props} />,
  ArrowRight: (props: Record<string, unknown>) => <svg data-testid="arrow-right" {...props} />,
}))

describe('AutomationIndexPage', () => {
  it('renders the page title', () => {
    render(
      <MemoryRouter>
        <AutomationIndexPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('自动化工具')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <AutomationIndexPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('使用自动化工具提高工作效率')).toBeInTheDocument()
  })

  it('renders tool cards', () => {
    render(
      <MemoryRouter>
        <AutomationIndexPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('财产保全询价')).toBeInTheDocument()
    expect(screen.getByText('文书智能识别')).toBeInTheDocument()
  })

  it('renders tool descriptions', () => {
    render(
      <MemoryRouter>
        <AutomationIndexPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/向多家保险公司询价/)).toBeInTheDocument()
    expect(screen.getByText(/上传法律文书/)).toBeInTheDocument()
  })

  it('renders enter buttons for each tool', () => {
    render(
      <MemoryRouter>
        <AutomationIndexPage />
      </MemoryRouter>,
    )

    const enterButtons = screen.getAllByText('进入')
    expect(enterButtons).toHaveLength(2)
  })

  it('renders tool icons', () => {
    render(
      <MemoryRouter>
        <AutomationIndexPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('calculator')).toBeInTheDocument()
    expect(screen.getByTestId('file-search')).toBeInTheDocument()
  })
})

describe('QuoteListPage', () => {
  it('renders QuoteList component', () => {
    render(
      <MemoryRouter>
        <QuoteListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('quote-list')).toBeInTheDocument()
  })
})

describe('QuoteDetailPage', () => {
  it('renders QuoteDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/automation/preservation-quotes/10']}>
        <Routes>
          <Route path="/admin/automation/preservation-quotes/:id" element={<QuoteDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('quote-detail')).toBeInTheDocument()
    expect(screen.getByText('QuoteDetail-10')).toBeInTheDocument()
  })
})

describe('RecognitionListPage', () => {
  it('renders RecognitionList component', () => {
    render(
      <MemoryRouter>
        <RecognitionListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('recognition-list')).toBeInTheDocument()
  })
})

describe('RecognitionDetailPage', () => {
  it('renders RecognitionDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/automation/document-recognition/5']}>
        <Routes>
          <Route path="/admin/automation/document-recognition/:id" element={<RecognitionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('recognition-detail')).toBeInTheDocument()
    expect(screen.getByText('RecognitionDetail-5')).toBeInTheDocument()
  })
})
