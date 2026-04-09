import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseLog, CaseLogAttachment } from '../types'
import { caseQueryKey } from './use-case'

interface CreateLogParams {
  case_id: number
  content: string
}

interface UpdateLogParams {
  id: number | string
  data: { case_id?: number; content?: string }
}

interface UploadAttachmentsParams {
  logId: number | string
  files: File[]
}

export function useLogMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const createLog = useMutation<CaseLog, Error, CreateLogParams>({
    mutationFn: (data) => caseApi.createLog(data),
    onSuccess: invalidateCase,
  })

  const updateLog = useMutation<CaseLog, Error, UpdateLogParams>({
    mutationFn: ({ id, data }) => caseApi.updateLog(id, data),
    onSuccess: invalidateCase,
  })

  const deleteLog = useMutation<void, Error, number | string>({
    mutationFn: (id) => caseApi.deleteLog(id),
    onSuccess: invalidateCase,
  })

  const uploadAttachments = useMutation<CaseLogAttachment[], Error, UploadAttachmentsParams>({
    mutationFn: ({ logId, files }) => caseApi.uploadLogAttachments(logId, files),
    onSuccess: invalidateCase,
  })

  return { createLog, updateLog, deleteLog, uploadAttachments }
}

export default useLogMutations
