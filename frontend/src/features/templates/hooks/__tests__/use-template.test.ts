vi.mock('../api', () => ({
  templateApi: { get: vi.fn().mockResolvedValue({ id: 1, name: 'Test' }) },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: { id: 1 }, isLoading: false }),
  }
})

import { useTemplate } from '../use-template'

describe('use-template', () => {
  it('exports useTemplate function', () => {
    expect(typeof useTemplate).toBe('function')
  })

  it('returns data from useQuery', () => {
    const result = useTemplate(1)
    expect(result).toEqual({ data: { id: 1 }, isLoading: false })
  })
})
