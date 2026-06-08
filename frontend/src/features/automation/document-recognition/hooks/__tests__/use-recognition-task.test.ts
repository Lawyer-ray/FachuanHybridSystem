vi.mock('../api', () => ({
  documentRecognitionApi: {
    getTask: vi.fn().mockResolvedValue({ id: 1, status: 'success' }),
  },
}))

vi.mock('../../constants', () => ({
  POLLING_INTERVALS: {
    RECOGNITION_PROCESSING: 2000,
    POLLING_TIMEOUT: 300000,
  },
}))

vi.mock('./use-recognition-tasks', () => ({
  recognitionTaskQueryKey: (id: number) => ['recognition-task', id],
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }),
  }
})

import { useRecognitionTask, shouldPoll, isCompleted } from '../use-recognition-task'

describe('automation/document-recognition/hooks/use-recognition-task', () => {
  it('exports useRecognitionTask function', () => {
    expect(typeof useRecognitionTask).toBe('function')
  })

  describe('shouldPoll', () => {
    it('returns true for pending', () => {
      expect(shouldPoll('pending')).toBe(true)
    })

    it('returns true for processing', () => {
      expect(shouldPoll('processing')).toBe(true)
    })

    it('returns false for success', () => {
      expect(shouldPoll('success')).toBe(false)
    })

    it('returns false for failed', () => {
      expect(shouldPoll('failed')).toBe(false)
    })
  })

  describe('isCompleted', () => {
    it('returns true for success', () => {
      expect(isCompleted('success')).toBe(true)
    })

    it('returns true for failed', () => {
      expect(isCompleted('failed')).toBe(true)
    })

    it('returns false for pending', () => {
      expect(isCompleted('pending')).toBe(false)
    })

    it('returns false for processing', () => {
      expect(isCompleted('processing')).toBe(false)
    })
  })
})
