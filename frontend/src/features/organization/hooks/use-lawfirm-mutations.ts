import { createCrudMutations } from '@/lib/create-crud-mutations'
import { lawFirmApi } from '../api'
import type { LawFirm, LawFirmInput, LawFirmUpdateInput } from '../types'
import { lawFirmQueryKey } from './use-lawfirm'
import { lawFirmsQueryKey } from './use-lawfirms'

export interface UpdateLawFirmParams {
  id: number
  data: LawFirmUpdateInput
}

const useBaseMutations = createCrudMutations<LawFirm, LawFirmInput, LawFirmUpdateInput>({
  api: {
    create: (data) => lawFirmApi.create(data),
    update: (id, data) => lawFirmApi.update(id, data),
    delete: (id) => lawFirmApi.delete(id),
  },
  listKey: lawFirmsQueryKey as unknown[],
  detailKey: (id) => lawFirmQueryKey(id),
})

export function useLawFirmMutations() {
  const { create, update, delete: del } = useBaseMutations()
  return {
    createLawFirm: create,
    updateLawFirm: update,
    deleteLawFirm: del,
  }
}

export default useLawFirmMutations
