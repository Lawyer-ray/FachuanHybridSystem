import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import TaskQueuePageWrapper from '../TaskQueuePage'

vi.mock('@/features/settings/components/TaskQueuePage', () => ({
  TaskQueuePage: () => <div data-testid="task-queue-page">TaskQueuePage</div>,
}))

describe('TaskQueuePageWrapper', () => {
  it('renders TaskQueuePage component', () => {
    render(
      <MemoryRouter>
        <TaskQueuePageWrapper />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('task-queue-page')).toBeInTheDocument()
  })
})
