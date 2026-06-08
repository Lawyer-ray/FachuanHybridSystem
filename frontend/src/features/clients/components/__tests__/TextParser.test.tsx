vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    FileText: Icon, Loader2: Icon, CheckCircle2: Icon, Wand2: Icon,
    Image: Icon, X: Icon, ChevronDown: Icon,
  }
})

vi.mock('framer-motion', () => ({
  motion: {
    div: (p: Record<string, unknown>) => <div {...p}>{(p as Record<string, unknown>).children}</div>,
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../api', () => ({
  clientApi: {
    parseText: vi.fn(),
    recognizeIdentityDoc: vi.fn(),
  },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TextParser } from '../TextParser'
import { clientApi } from '../../api'

describe('TextParser', () => {
  const defaultProps = {
    onParsed: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the title button', () => {
    render(<TextParser {...defaultProps} />)
    expect(screen.getByText('智能解析')).toBeInTheDocument()
  })

  it('shows the hint text', () => {
    render(<TextParser {...defaultProps} />)
    expect(screen.getByText('粘贴文本或上传证件图片，AI 自动提取')).toBeInTheDocument()
  })

  it('expands when title is clicked', () => {
    render(<TextParser {...defaultProps} />)
    const titleButton = screen.getByText('智能解析').closest('button')!
    fireEvent.click(titleButton)
    expect(screen.getByPlaceholderText(/粘贴当事人信息文本/)).toBeInTheDocument()
  })

  it('shows parse button when expanded', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    expect(screen.getByText('解析文本')).toBeInTheDocument()
  })

  it('shows upload image button when expanded', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    expect(screen.getByText('上传图片')).toBeInTheDocument()
  })

  it('calls parseText API when parse button is clicked with text', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Wang', id_number: '110101190001010000' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'some text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(clientApi.parseText).toHaveBeenCalledWith('some text')
    })
  })

  it('displays parse result and calls onParsed when confirmed', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Wang' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'some text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('确认填充'))
    expect(defaultProps.onParsed).toHaveBeenCalledWith({ name: 'Wang' })
  })
})
