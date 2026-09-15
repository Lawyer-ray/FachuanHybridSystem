import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listMaterialPacks, uploadPack } from '../api'
import type { InboxMessage } from '../types'

export const PACKS_KEY = ['inbox', 'material-packs']

export function useMaterialPacks() {
  return useQuery({
    queryKey: PACKS_KEY,
    queryFn: listMaterialPacks,
    staleTime: 30_000,
  })
}

export function useCreatePack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => uploadPack(files),
    onSuccess: () => qc.invalidateQueries({ queryKey: PACKS_KEY }),
    onError: (e) => {
      throw e
    },
  })
}

export function upsertPackLocal(list: InboxMessage[] | undefined, id: number): InboxMessage[] {
  return list?.filter((m) => m.id !== id) ?? []
}
