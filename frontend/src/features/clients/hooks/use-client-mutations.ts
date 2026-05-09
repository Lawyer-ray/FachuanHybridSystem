import { createCrudMutations } from '@/lib/create-crud-mutations'
import { clientApi } from '../api'
import type { Client, ClientInput } from '../types'
import { clientQueryKey } from './use-client'

export interface UpdateClientParams {
  id: string
  data: ClientInput
}

const useBaseMutations = createCrudMutations<Client, ClientInput, ClientInput, string>({
  api: {
    create: (data) => clientApi.create(data),
    update: (id, data) => clientApi.update(id, data),
    delete: (id) => clientApi.delete(id),
  },
  listKey: ['clients'],
  detailKey: (id) => clientQueryKey(id),
})

export function useClientMutations() {
  const { create, update, delete: del } = useBaseMutations()
  return {
    createClient: create,
    updateClient: update,
    deleteClient: del,
  }
}

export default useClientMutations
