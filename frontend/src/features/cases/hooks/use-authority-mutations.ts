import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseQueryKey } from './use-case'
import type { SupervisingAuthority } from '../types'

interface CreateAuthorityParams {
  name?: string
  authority_type?: string
}

interface UpdateAuthorityParams {
  id: number | string
  data: { name?: string; authority_type?: string }
}

/**
 * 主管机关 mutations（占位）
 * 后端无独立 authority CRUD router，实际通过 createFull 批量创建。
 * 这些 mutation 目前作为占位，成功后 invalidate case 缓存。
 */
export function useAuthorityMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const createAuthority = useMutation<SupervisingAuthority, Error, CreateAuthorityParams>({
    mutationFn: async (_data) => {
      // TODO: 后端无独立 authority CRUD，待后端补充后对接
      throw new Error('Authority creation is handled through case full create')
    },
    onSuccess: invalidateCase,
  })

  const updateAuthority = useMutation<SupervisingAuthority, Error, UpdateAuthorityParams>({
    mutationFn: async (_data) => {
      throw new Error('Authority update is not yet supported by backend')
    },
    onSuccess: invalidateCase,
  })

  const deleteAuthority = useMutation<void, Error, number | string>({
    mutationFn: async (_id) => {
      throw new Error('Authority deletion is not yet supported by backend')
    },
    onSuccess: invalidateCase,
  })

  return { createAuthority, updateAuthority, deleteAuthority }
}

export default useAuthorityMutations
