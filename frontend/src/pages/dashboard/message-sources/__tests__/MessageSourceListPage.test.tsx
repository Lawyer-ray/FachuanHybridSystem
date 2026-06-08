import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import MessageSourceListPage from '../MessageSourceListPage'

vi.mock('@/features/message-sources', () => ({
  MessageSourceList: () => <div data-testid="message-source-list">MessageSourceList</div>,
}))

describe('MessageSourceListPage', () => {
  it('renders MessageSourceList component', () => {
    render(
      <MemoryRouter>
        <MessageSourceListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('message-source-list')).toBeInTheDocument()
  })
})
