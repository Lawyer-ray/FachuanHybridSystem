vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({
    data: undefined,
    isLoading: true,
  })),
  keepPreviousData: 'keep',
}))

import { renderHook, act } from '@testing-library/react'

import { usePaginatedList } from '../use-paginated-list'

describe('usePaginatedList', () => {
  it('returns default data when query has no data', () => {
    const { result } = renderHook(() =>
      usePaginatedList({
        queryKey: 'items',
        fetchAll: vi.fn().mockResolvedValue([]),
        filters: {},
      }),
    )
    expect(result.current.data.items).toEqual([])
    expect(result.current.data.total).toBe(0)
    expect(result.current.data.page).toBe(1)
    expect(result.current.data.totalPages).toBe(0)
    expect(result.current.isLoading).toBe(true)
  })

  it('starts at page 1', () => {
    const { result } = renderHook(() =>
      usePaginatedList({
        queryKey: 'items',
        fetchAll: vi.fn().mockResolvedValue([]),
        filters: {},
      }),
    )
    expect(result.current.page).toBe(1)
  })

  it('setPage updates page', () => {
    const { result } = renderHook(() =>
      usePaginatedList({
        queryKey: 'items',
        fetchAll: vi.fn().mockResolvedValue([]),
        filters: {},
      }),
    )
    act(() => {
      result.current.setPage(3)
    })
    expect(result.current.page).toBe(3)
  })

  it('withPageReset resets page to 1 and calls setter', () => {
    const { result } = renderHook(() =>
      usePaginatedList({
        queryKey: 'items',
        fetchAll: vi.fn().mockResolvedValue([]),
        filters: {},
      }),
    )

    // Change page first
    act(() => {
      result.current.setPage(5)
    })
    expect(result.current.page).toBe(5)

    // Use withPageReset
    const setter = vi.fn()
    act(() => {
      const resetSetter = result.current.withPageReset(setter)
      resetSetter('new-value')
    })
    expect(setter).toHaveBeenCalledWith('new-value')
    expect(result.current.page).toBe(1)
  })

  it('accepts custom pageSize', () => {
    const { result } = renderHook(() =>
      usePaginatedList({
        queryKey: 'items',
        fetchAll: vi.fn().mockResolvedValue([]),
        filters: {},
        pageSize: 10,
      }),
    )
    expect(result.current.data.pageSize).toBe(10)
  })
})
