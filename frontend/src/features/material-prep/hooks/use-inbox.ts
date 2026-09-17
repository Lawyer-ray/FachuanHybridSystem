import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deletePack, listMaterialPacks, renamePack, setPackStatusRemote, uploadPack } from '../api'
import type { AssignInfo, InboxMessage, PackStatus } from '../types'

export const PACKS_KEY = ['inbox', 'material-packs']

export function useMaterialPacks() {
  return useQuery({
    queryKey: PACKS_KEY,
    queryFn: listMaterialPacks,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
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

export function useJudgePack() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: PACKS_KEY })
  const mut = useMutation({
    mutationFn: (v: { id: number; status: PackStatus; assign?: AssignInfo }) =>
      setPackStatusRemote(v.id, v.status, v.assign),
    onSuccess: invalidate,
    onError: (e) => {
      throw e
    },
  })
  return { ...mut, invalidate }
}

export function useDeletePack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deletePack(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: PACKS_KEY }),
    onError: (e) => {
      throw e
    },
  })
}

export function useRenamePack() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: PACKS_KEY })
  const mut = useMutation({
    mutationFn: (v: { id: number; subject: string }) => renamePack(v.id, v.subject),
    onSuccess: invalidate,
    onError: (e) => {
      throw e
    },
  })
  return { ...mut, invalidate }
}

export function upsertPackLocal(list: InboxMessage[] | undefined, id: number): InboxMessage[] {
  return list?.filter((m) => m.id !== id) ?? []
}
