import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deletePack, listMaterialPacks, renamePack, setPackStatusRemote, uploadPack } from '../api'
import type { AssignInfo, PackStatus } from '../types'

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
  const invalidate = useMemo(
    () => () => qc.invalidateQueries({ queryKey: PACKS_KEY }),
    [qc],
  )
  const mut = useMutation({
    mutationFn: (v: { id: number; status: PackStatus; assign?: AssignInfo }) =>
      setPackStatusRemote(v.id, v.status, v.assign),
    onSuccess: invalidate,
    onError: (e) => {
      throw e
    },
  })
  // 稳定返回对象：否则消费方（DeskPage 的 judge / 键盘监听）每次渲染都拿到新引用
  return useMemo(() => ({ ...mut, invalidate }), [mut, invalidate])
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
  const invalidate = useMemo(
    () => () => qc.invalidateQueries({ queryKey: PACKS_KEY }),
    [qc],
  )
  const mut = useMutation({
    mutationFn: (v: { id: number; subject: string }) => renamePack(v.id, v.subject),
    onSuccess: invalidate,
    onError: (e) => {
      throw e
    },
  })
  // 稳定返回对象：避免消费方每次渲染拿到新引用
  return useMemo(() => ({ ...mut, invalidate }), [mut, invalidate])
}
