import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { ErrorBoundary } from '../ErrorBoundary'

function ThrowingComponent({ shouldThrow = true }: { shouldThrow?: boolean }) {
  if (shouldThrow) {
    throw new Error('Test error')
  }
  return <div>No error</div>
}

describe('ErrorBoundary', () => {
  // Suppress console.error for expected errors
  let consoleSpy: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    consoleSpy.mockRestore()
  })

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>child content</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('child content')).toBeInTheDocument()
  })

  it('renders error UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('页面加载失败')).toBeInTheDocument()
    expect(screen.getByText('Test error')).toBeInTheDocument()
  })

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Custom fallback')).toBeInTheDocument()
    expect(screen.queryByText('页面加载失败')).not.toBeInTheDocument()
  })

  it('shows retry and reload buttons', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('重试')).toBeInTheDocument()
    expect(screen.getByText('刷新页面')).toBeInTheDocument()
  })

  it('resets error state on retry', async () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )

    expect(screen.getByText('页面加载失败')).toBeInTheDocument()
    // Click retry - this calls handleReset which sets hasError to false
    // but since the child still throws, it will re-catch
    await userEvent.click(screen.getByText('重试'))
    // After retry, the boundary re-renders children, which throw again
    expect(screen.getByText('页面加载失败')).toBeInTheDocument()
  })

  it('shows default error message when error has no message', () => {
    function ThrowEmptyError() {
      throw new Error('')
    }

    render(
      <ErrorBoundary>
        <ThrowEmptyError />
      </ErrorBoundary>
    )
    expect(screen.getByText('发生了未知错误')).toBeInTheDocument()
  })
})
