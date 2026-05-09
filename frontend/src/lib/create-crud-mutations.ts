/**
 * CRUD Mutations 工厂函数
 *
 * 生成标准的 create/update/delete mutations hook，减少重复模板代码。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

/** CRUD API 接口 */
export interface CrudApi<TData, TInput, TUpdateInput, TId = number> {
  create: (data: TInput) => Promise<TData>
  update: (id: TId, data: TUpdateInput) => Promise<TData>
  delete: (id: TId) => Promise<void>
}

/** CRUD Mutations 配置 */
export interface CrudMutationsConfig<TData, TInput, TUpdateInput, TId = number> {
  /** CRUD API 对象 */
  api: CrudApi<TData, TInput, TUpdateInput, TId>
  /** 列表查询 key（用于 invalidateQueries） */
  listKey: unknown[] | ((query: { queryKey: readonly unknown[] }) => boolean)
  /** 生成详情查询 key（可选，用于更新/删除时 invalidate 详情缓存） */
  detailKey?: (id: TId) => readonly unknown[]
  /** 是否在更新时直接 setQueryData 更新详情缓存（默认 true） */
  optimisticDetail?: boolean
  /** 是否在删除时 removeQueries 移除详情缓存（默认 true） */
  removeDetailOnDelete?: boolean
}

/** Update 参数 */
export interface UpdateParams<TData, TId = number> {
  id: TId
  data: TData
}

/**
 * 创建标准 CRUD mutations hook
 *
 * @example
 * ```ts
 * const useTeamMutations = createCrudMutations({
 *   api: teamApi,
 *   listKey: ['teams'],
 *   detailKey: (id) => ['team', id],
 * })
 * ```
 */
export function createCrudMutations<TData, TInput, TUpdateInput, TId = number>(
  config: CrudMutationsConfig<TData, TInput, TUpdateInput, TId>,
) {
  const { api, listKey, detailKey, optimisticDetail = true, removeDetailOnDelete = true } = config

  return function useCrudMutations() {
    const queryClient = useQueryClient()

    const create = useMutation<TData, Error, TInput>({
      mutationFn: (data) => api.create(data),
      onSuccess: () => {
        if (typeof listKey === 'function') {
          queryClient.invalidateQueries({ predicate: listKey })
        } else {
          queryClient.invalidateQueries({ queryKey: listKey })
        }
      },
    })

    const update = useMutation<TData, Error, { id: TId; data: TUpdateInput }>({
      mutationFn: ({ id, data }) => api.update(id, data),
      onSuccess: (updated, { id }) => {
        if (typeof listKey === 'function') {
          queryClient.invalidateQueries({ predicate: listKey })
        } else {
          queryClient.invalidateQueries({ queryKey: listKey })
        }
        if (detailKey) {
          const key = detailKey(id)
          queryClient.invalidateQueries({ queryKey: key })
          if (optimisticDetail) {
            queryClient.setQueryData(key, updated)
          }
        }
      },
    })

    const deleteMutation = useMutation<void, Error, TId>({
      mutationFn: (id) => api.delete(id),
      onSuccess: (_, id) => {
        if (typeof listKey === 'function') {
          queryClient.invalidateQueries({ predicate: listKey })
        } else {
          queryClient.invalidateQueries({ queryKey: listKey })
        }
        if (detailKey && removeDetailOnDelete) {
          queryClient.removeQueries({ queryKey: detailKey(id) })
        }
      },
    })

    return { create, update, delete: deleteMutation }
  }
}
