import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LawyerFilters } from '../LawyerFilters'

describe('LawyerFilters', () => {
  it('renders search input with placeholder', () => {
    render(<LawyerFilters search="" onSearchChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('搜索用户名、姓名、手机号...')).toBeInTheDocument()
  })

  it('displays current search value', () => {
    render(<LawyerFilters search="zhang" onSearchChange={vi.fn()} />)
    expect(screen.getByDisplayValue('zhang')).toBeInTheDocument()
  })

  it('calls onSearchChange when typing', async () => {
    const onChange = vi.fn()
    render(<LawyerFilters search="" onSearchChange={onChange} />)
    await userEvent.type(screen.getByPlaceholderText('搜索用户名、姓名、手机号...'), 'test')
    expect(onChange).toHaveBeenCalled()
  })

  it('shows clear button when search is not empty', () => {
    const { container } = render(<LawyerFilters search="keyword" onSearchChange={vi.fn()} />)
    const clearBtn = container.querySelector('button:not([type="submit"])')
    expect(clearBtn).toBeInTheDocument()
  })

  it('hides clear button when search is empty', () => {
    const { container } = render(<LawyerFilters search="" onSearchChange={vi.fn()} />)
    // When search is empty, the X/clear button should not be rendered
    const spans = container.querySelectorAll('.sr-only')
    const clearSpans = Array.from(spans).filter(s => s.textContent === '清除搜索')
    expect(clearSpans.length).toBe(0)
  })

  it('calls onSearchChange with empty string when clear is clicked', () => {
    const onChange = vi.fn()
    const { container } = render(<LawyerFilters search="keyword" onSearchChange={onChange} />)
    // Find the clear button by its sr-only child text
    const buttons = container.querySelectorAll('button')
    const clearBtn = Array.from(buttons).find(btn => btn.querySelector('.sr-only')?.textContent === '清除搜索')
    expect(clearBtn).toBeTruthy()
    fireEvent.click(clearBtn!)
    expect(onChange).toHaveBeenCalledWith('')
  })
})
