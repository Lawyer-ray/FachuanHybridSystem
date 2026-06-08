vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: Function) => {
    const state = {
      models: [
        { id: 'gpt-4', name: 'GPT-4', backend: 'openai', max_model_len: 8192 },
        { id: 'claude-3', name: 'Claude 3', backend: 'anthropic', max_model_len: 100000 },
      ],
      modelsLoading: false,
      selectedModel: 'gpt-4',
      favoriteModel: '',
      setSelectedModel: vi.fn(),
      setFavoriteModel: vi.fn(),
    }
    return selector(state)
  }),
}))

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelSelector } from '../ModelSelector'
import { useWorkbenchStore } from '../../stores/workbench-store'

describe('ModelSelector', () => {
  beforeEach(() => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: Function) => {
      const state = {
        models: [
          { id: 'gpt-4', name: 'GPT-4', backend: 'openai', max_model_len: 8192 },
          { id: 'claude-3', name: 'Claude 3', backend: 'anthropic', max_model_len: 100000 },
        ],
        modelsLoading: false,
        selectedModel: 'gpt-4',
        favoriteModel: '',
        setSelectedModel: vi.fn(),
        setFavoriteModel: vi.fn(),
      }
      return selector(state)
    })
  })

  it('shows selected model name', () => {
    render(<ModelSelector />)
    expect(screen.getByText('GPT-4')).toBeInTheDocument()
  })

  it('shows loading skeleton when models are loading', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: Function) => {
      const state = { models: [], modelsLoading: true, selectedModel: '', favoriteModel: '', setSelectedModel: vi.fn(), setFavoriteModel: vi.fn() }
      return selector(state)
    })
    const { container } = render(<ModelSelector />)
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument()
  })

  it('shows empty message when no models', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: Function) => {
      const state = { models: [], modelsLoading: false, selectedModel: '', favoriteModel: '', setSelectedModel: vi.fn(), setFavoriteModel: vi.fn() }
      return selector(state)
    })
    render(<ModelSelector />)
    expect(screen.getByText('暂无模型')).toBeInTheDocument()
  })

  it('opens popover on click', async () => {
    render(<ModelSelector />)
    await userEvent.click(screen.getByText('GPT-4'))
    expect(screen.getByText('Claude 3')).toBeInTheDocument()
  })

  it('is disabled when disabled prop is true', () => {
    render(<ModelSelector disabled />)
    const button = screen.getByText('GPT-4').closest('button')
    expect(button).toBeDisabled()
  })
})
