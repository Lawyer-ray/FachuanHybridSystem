vi.mock('../api', () => ({
  contractApi: {
    listLawyers: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  }
})

import { useLawyers } from '../use-lawyers'

describe('contracts/hooks/use-lawyers', () => {
  it('exports useLawyers function', () => {
    expect(typeof useLawyers).toBe('function')
  })

  it('returns data and isLoading', () => {
    const result = useLawyers()
    expect(result).toHaveProperty('data')
    expect(result).toHaveProperty('isLoading')
  })
})
