import { useMutation, useQueryClient } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { PaymentInput, PaymentUpdate } from '../types'

export function usePaymentMutations(contractId: number) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['payments', contractId] })
    qc.invalidateQueries({ queryKey: ['contract', String(contractId)] })
    qc.invalidateQueries({ queryKey: ['contracts'] })
  }

  const createPayment = useMutation({
    mutationFn: (data: PaymentInput) => contractApi.createPayment(data),
    onSuccess: invalidate,
  })

  const updatePayment = useMutation({
    mutationFn: ({ id, data }: { id: number; data: PaymentUpdate }) => contractApi.updatePayment(id, data),
    onSuccess: invalidate,
  })

  const deletePayment = useMutation({
    mutationFn: (id: number) => contractApi.deletePayment(id, true),
    onSuccess: invalidate,
  })

  return { createPayment, updatePayment, deletePayment }
}
