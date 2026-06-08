import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PageFooter } from '../PageFooter'

describe('PageFooter', () => {
  it('renders stats', () => {
    render(
      <PageFooter stats={[{ label: 'Total', value: '100' }]} page={1} total={100} />
    )
    expect(screen.getByText('Total：')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('shows page info when total exceeds pageSize', () => {
    render(<PageFooter page={2} total={100} pageSize={20} />)
    expect(screen.getByText(/第 2\/5 页/)).toBeInTheDocument()
  })

  it('does not show pagination when total is within pageSize', () => {
    render(<PageFooter page={1} total={10} pageSize={20} />)
    expect(screen.queryByText(/上一页/)).not.toBeInTheDocument()
    expect(screen.queryByText(/下一页/)).not.toBeInTheDocument()
  })

  it('shows next page button when not on last page', () => {
    render(<PageFooter page={1} total={100} pageSize={20} />)
    expect(screen.getByText('下一页')).toBeInTheDocument()
    expect(screen.queryByText('上一页')).not.toBeInTheDocument()
  })

  it('shows prev page button when not on first page', () => {
    render(<PageFooter page={3} total={100} pageSize={20} />)
    expect(screen.getByText('上一页')).toBeInTheDocument()
    expect(screen.getByText('下一页')).toBeInTheDocument()
  })

  it('calls onPageChange on button click', async () => {
    const onPageChange = vi.fn()
    render(<PageFooter page={2} total={100} pageSize={20} onPageChange={onPageChange} />)

    await userEvent.click(screen.getByText('下一页'))
    expect(onPageChange).toHaveBeenCalledWith(3)

    await userEvent.click(screen.getByText('上一页'))
    expect(onPageChange).toHaveBeenCalledWith(1)
  })

  it('renders with empty stats', () => {
    const { container } = render(<PageFooter />)
    expect(container).toBeTruthy()
  })
})
