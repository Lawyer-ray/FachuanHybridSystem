vi.mock('../api', () => ({
  lawyerApi: { list: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: [], isLoading: false }),
    keepPreviousData: Symbol('keepPreviousData'),
  }
})

import { useLawyers, lawyersQueryKey } from '../use-lawyers'

describe('organization/hooks/use-lawyers', () => {
  it('exports useLawyers function', () => {
    expect(typeof useLawyers).toBe('function')
  })

  it('lawyersQueryKey returns correct key without params', () => {
    const key = lawyersQueryKey()
    expect(key).toEqual(['lawyers', { search: '' }])
  })

  it('lawyersQueryKey returns correct key with search', () => {
    const key = lawyersQueryKey({ search: 'zhang' })
    expect(key).toEqual(['lawyers', { search: 'zhang' }])
  })
})
