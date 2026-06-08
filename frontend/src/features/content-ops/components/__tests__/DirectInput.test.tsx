vi.mock('../../hooks/use-content-ops', () => ({
  useCreateTask: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { DirectInput } from '../DirectInput'

describe('DirectInput', () => {
  it('renders content textarea', () => {
    render(<DirectInput />)
    expect(screen.getByPlaceholderText('粘贴判决书摘要、案例事实或任何法律文本...')).toBeInTheDocument()
  })

  it('renders case summary input', () => {
    render(<DirectInput />)
    expect(screen.getByPlaceholderText('简要描述案例背景')).toBeInTheDocument()
  })

  it('renders submit button', () => {
    render(<DirectInput />)
    expect(screen.getByText('生成')).toBeInTheDocument()
  })

  it('renders word count', () => {
    render(<DirectInput />)
    expect(screen.getByText('0 字')).toBeInTheDocument()
  })
})
