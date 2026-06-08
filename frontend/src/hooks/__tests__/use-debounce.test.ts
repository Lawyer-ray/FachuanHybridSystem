import { renderHook, act } from '@testing-library/react'

import { useDebounce } from '../use-debounce'

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('hello', 500))
    expect(result.current).toBe('hello')
  })

  it('debounces value changes', () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 'initial', delay: 500 } },
    )
    expect(result.current).toBe('initial')

    rerender({ value: 'updated', delay: 500 })
    // Before timeout, value is still initial
    expect(result.current).toBe('initial')

    // After timeout, value updates
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current).toBe('updated')
  })

  it('resets timer on rapid changes', () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 'a', delay: 300 } },
    )

    rerender({ value: 'b', delay: 300 })
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(result.current).toBe('a')

    rerender({ value: 'c', delay: 300 })
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(result.current).toBe('a')

    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current).toBe('c')
  })

  it('works with different types', () => {
    const { result, rerender } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 0, delay: 100 } },
    )

    rerender({ value: 42, delay: 100 })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current).toBe(42)
  })
})
