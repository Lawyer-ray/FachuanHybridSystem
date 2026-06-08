vi.mock('../../api', () => ({
  documentRecognitionApi: {
    searchCases: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }),
  }
})

import { renderHook } from '@testing-library/react'
import { useCaseSearch } from '../use-case-search'

describe('automation/document-recognition/hooks/use-case-search', () => {
  it('exports useCaseSearch function', () => {
    expect(typeof useCaseSearch).toBe('function')
  })

  it('returns data and isLoading when called with query', () => {
    const { result } = renderHook(() => useCaseSearch('test query'))
    expect(result.current).toHaveProperty('data')
    expect(result.current).toHaveProperty('isLoading')
  })

  it('handles empty query', () => {
    const { result } = renderHook(() => useCaseSearch(''))
    expect(result.current).toBeDefined()
  })
})
