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
    // 错误统一由调用方 mutateAsync 的 catch 处理（toast 在那里弹），这里不再重复兜底
  })
}

export function useJudgePack() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: PACKS_KEY })
  const mut = useMutation({
    mutationFn: (v: { id: number; status: PackStatus; assign?: AssignInfo }) =>
      setPackStatusRemote(v.id, v.status, v.assign),
    onSuccess: invalidate,
  })
  // 注意：react-query v5 每次渲染返回新的 mut 对象，这里没有（也无法）做引用稳定化；
  // 消费方不要把返回值直接放进依赖数组做「稳定引用」假设
  return { ...mut, invalidate }
}

export function useDeletePack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deletePack(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: PACKS_KEY }),
  })
}

export function useRenamePack() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: PACKS_KEY })
  const mut = useMutation({
    mutationFn: (v: { id: number; subject: string }) => renamePack(v.id, v.subject),
    onSuccess: invalidate,
  })
  return { ...mut, invalidate }
}
