import { prefetchRoute } from '../prefetch'

describe('prefetchRoute', () => {
  it('calls importFn on first call', () => {
    const importFn = vi.fn()
    prefetchRoute('test-key-1', importFn)
    expect(importFn).toHaveBeenCalledOnce()
  })

  it('does not call importFn on duplicate key', () => {
    const importFn = vi.fn()
    prefetchRoute('test-key-2', importFn)
    prefetchRoute('test-key-2', importFn)
    expect(importFn).toHaveBeenCalledOnce()
  })

  it('calls importFn for different keys', () => {
    const fn1 = vi.fn()
    const fn2 = vi.fn()
    prefetchRoute('test-key-3a', fn1)
    prefetchRoute('test-key-3b', fn2)
    expect(fn1).toHaveBeenCalledOnce()
    expect(fn2).toHaveBeenCalledOnce()
  })
})
