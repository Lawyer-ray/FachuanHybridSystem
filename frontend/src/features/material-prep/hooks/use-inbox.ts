import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deletePack, listMaterialPacks, renamePack, setPackStatusRemote, uploadPack } from '../api'
import type { AssignInfo, PackStatus } from '../types'

export const PACKS_KEY = ['inbox', 'material-packs']

export function useMaterialPacks() {
  return useQuery({
    queryKey: PACKS_KEY,
    queryFn: listMaterialPacks,
    staleTime: 30_000,
    // 收件箱是低频变化的慢数据（材料只在上传/判卷时才变），切回窗口不必重拉——
    // 有意偏离全站默认值（use-inbox.dom.test.tsx 对此行为有断言），勿随手删
    refetchOnWindowFocus: false,
  })
}

export function useCreatePack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => uploadPack(files),
    onSuccess: () => qc.invalidateQueries({ queryKey: PACKS_KEY }),
    // 错误统一由调用方 mutateAsync 的 catch 处理（toast 在那里弹）；置本地 onError
    // 是给全局 MutationCache 兜底的抑制标记——否则同一次失败会弹两个错误 toast
    onError: () => {
      /* 已由调用方处理，刻意留空 */
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
    // 同 useCreatePack：错误在调用方 catch 里弹过，抑制全局兜底的重复 toast
    onError: () => {
      /* 已由调用方处理，刻意留空 */
    },
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
    // 同 useCreatePack：错误在调用方 catch 里弹过，抑制全局兜底的重复 toast
    onError: () => {
      /* 已由调用方处理，刻意留空 */
    },
  })
}

export function useRenamePack() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: PACKS_KEY })
  const mut = useMutation({
    mutationFn: (v: { id: number; subject: string }) => renamePack(v.id, v.subject),
    onSuccess: invalidate,
    // 同 useCreatePack：错误在调用方 catch 里弹过，抑制全局兜底的重复 toast
    onError: () => {
      /* 已由调用方处理，刻意留空 */
    },
  })
  return { ...mut, invalidate }
}
