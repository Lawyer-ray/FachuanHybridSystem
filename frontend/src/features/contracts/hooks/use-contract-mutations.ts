import { useMutation, useQueryClient } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { ContractInput, ContractUpdate } from '../types'

export function useContractMutations() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ['contracts'] })

  const createContract = useMutation({
    mutationFn: (data: ContractInput) => contractApi.create(data),
    onSuccess: invalidate,
  })

  const updateContract = useMutation({
    mutationFn: ({ id, data }: { id: number | string; data: ContractUpdate }) => contractApi.update(id, data),
    onSuccess: (_, vars) => {
      invalidate()
      qc.invalidateQueries({ queryKey: ['contract', vars.id] })
    },
  })

  const deleteContract = useMutation({
    mutationFn: (id: number | string) => contractApi.delete(id),
    onSuccess: invalidate,
  })

  return { createContract, updateContract, deleteContract }
}
