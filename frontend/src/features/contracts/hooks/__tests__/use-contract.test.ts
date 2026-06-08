vi.mock('../api', () => ({
  contractApi: {
    get: vi.fn().mockResolvedValue({ id: 1 }),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }),
  }
})

import { useContract, contractQueryKey } from '../use-contract'

describe('contracts/hooks/use-contract', () => {
  it('exports useContract function', () => {
    expect(typeof useContract).toBe('function')
  })

  it('contractQueryKey returns correct key', () => {
    expect(contractQueryKey(5)).toEqual(['contract', 5])
    expect(contractQueryKey('abc')).toEqual(['contract', 'abc'])
  })
})
