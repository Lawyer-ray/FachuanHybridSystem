vi.mock('../api', () => ({
  lawFirmApi: { list: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  }
})

import { useLawFirms, lawFirmsQueryKey } from '../use-lawfirms'

describe('organization/hooks/use-lawfirms', () => {
  it('exports useLawFirms function', () => {
    expect(typeof useLawFirms).toBe('function')
  })

  it('exports lawFirmsQueryKey', () => {
    expect(lawFirmsQueryKey).toEqual(['lawfirms'])
  })
})
