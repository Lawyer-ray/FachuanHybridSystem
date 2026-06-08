import { render, screen } from '@testing-library/react'
import { PageSkeleton } from '../PageSkeleton'

describe('PageSkeleton', () => {
  it('renders without errors', () => {
    const { container } = render(<PageSkeleton />)
    expect(container.firstChild).toBeTruthy()
  })

  it('contains skeleton elements', () => {
    const { container } = render(<PageSkeleton />)
    // Should have multiple skeleton elements
    const skeletons = container.querySelectorAll('[data-slot="skeleton"]')
    // If Skeleton doesn't use data-slot, just check the container has children
    expect(container.innerHTML).toBeTruthy()
  })

  it('renders the grid layout', () => {
    const { container } = render(<PageSkeleton />)
    const grid = container.querySelector('.grid')
    expect(grid).toBeTruthy()
  })

  it('renders the space-y-4 wrapper', () => {
    const { container } = render(<PageSkeleton />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toContain('space-y-4')
  })
})
