vi.mock('../api', () => ({
  recognitionApi: {
    listTasks: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  },
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }),
  }
})

import { useRecognitionTasks } from '../use-recognition-tasks'

describe('automation/document-recognition/hooks/use-recognition-tasks', () => {
  it('exports useRecognitionTasks function', () => {
    expect(typeof useRecognitionTasks).toBe('function')
  })

  it('returns data and isLoading', () => {
    const result = useRecognitionTasks({ page: 1, page_size: 10 })
    expect(result).toHaveProperty('data')
    expect(result).toHaveProperty('isLoading')
  })

  it('accepts filter parameters', () => {
    const result = useRecognitionTasks({ page: 2, page_size: 20, status: 'success' })
    expect(result).toBeDefined()
  })
})
