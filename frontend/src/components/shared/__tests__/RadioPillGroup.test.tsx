import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RadioPillGroup } from '../RadioPillGroup'

const options = [
  { value: 'a', label: 'Option A' },
  { value: 'b', label: 'Option B' },
  { value: 'c', label: 'Option C' },
]

describe('RadioPillGroup', () => {
  it('renders all options', () => {
    render(<RadioPillGroup options={options} value="a" onChange={vi.fn()} />)
    expect(screen.getByText('Option A')).toBeInTheDocument()
    expect(screen.getByText('Option B')).toBeInTheDocument()
    expect(screen.getByText('Option C')).toBeInTheDocument()
  })

  it('shows the selected option as checked', () => {
    render(<RadioPillGroup options={options} value="b" onChange={vi.fn()} />)
    const radios = screen.getAllByRole('radio')
    expect(radios[0]).not.toBeChecked()
    expect(radios[1]).toBeChecked()
    expect(radios[2]).not.toBeChecked()
  })

  it('calls onChange when a different option is clicked', async () => {
    const onChange = vi.fn()
    render(<RadioPillGroup options={options} value="a" onChange={onChange} />)
    await userEvent.click(screen.getByText('Option B'))
    expect(onChange).toHaveBeenCalledWith('b')
  })

  it('applies custom className', () => {
    const { container } = render(
      <RadioPillGroup options={options} value="a" onChange={vi.fn()} className="custom" />
    )
    const group = container.firstChild as HTMLElement
    expect(group.className).toContain('custom')
  })

  it('renders with empty options', () => {
    const { container } = render(<RadioPillGroup options={[]} value="" onChange={vi.fn()} />)
    expect(container.querySelectorAll('label')).toHaveLength(0)
  })
})
