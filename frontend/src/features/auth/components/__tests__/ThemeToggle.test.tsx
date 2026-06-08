import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeToggle } from '../ThemeToggle'

const mockSetTheme = vi.fn()
let mockTheme = 'light'

vi.mock('next-themes', () => ({
  useTheme: () => ({
    theme: mockTheme,
    setTheme: mockSetTheme,
  }),
}))

describe('ThemeToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTheme = 'light'
  })

  it('renders without crashing', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: '切换主题' })).toBeInTheDocument()
  })

  it('calls setTheme("dark") when clicked in light mode', async () => {
    const user = userEvent.setup()
    render(<ThemeToggle />)
    await user.click(screen.getByRole('button', { name: '切换主题' }))
    expect(mockSetTheme).toHaveBeenCalledWith('dark')
  })

  it('calls setTheme("light") when clicked in dark mode', async () => {
    mockTheme = 'dark'
    const user = userEvent.setup()
    render(<ThemeToggle />)
    await user.click(screen.getByRole('button', { name: '切换主题' }))
    expect(mockSetTheme).toHaveBeenCalledWith('light')
  })

  it('renders screen reader text', () => {
    render(<ThemeToggle />)
    expect(screen.getByText('切换主题', { selector: '.sr-only' })).toBeInTheDocument()
  })
})
