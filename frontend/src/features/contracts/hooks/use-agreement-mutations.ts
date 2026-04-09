import { useMutation, useQueryClient } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { SupplementaryAgreementInput, SupplementaryAgreementUpdate } from '../types'

export function useAgreementMutations(contractId: number) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['contract', String(contractId)] })
    qc.invalidateQueries({ queryKey: ['contracts'] })
  }

  const createAgreement = useMutation({
    mutationFn: (data: SupplementaryAgreementInput) => contractApi.createAgreement(data),
    onSuccess: invalidate,
  })

  const updateAgreement = useMutation({
    mutationFn: ({ id, data }: { id: number; data: SupplementaryAgreementUpdate }) => contractApi.updateAgreement(id, data),
    onSuccess: invalidate,
  })

  const deleteAgreement = useMutation({
    mutationFn: (id: number) => contractApi.deleteAgreement(id),
    onSuccess: invalidate,
  })

  return { createAgreement, updateAgreement, deleteAgreement }
}
