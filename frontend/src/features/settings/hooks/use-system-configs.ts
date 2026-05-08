import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { systemConfigApi, type SystemConfigGroup, type SystemConfigItem } from '../api'

export function useSystemConfigs() {
  return useQuery({
    queryKey: ['system-configs'],
    queryFn: () => systemConfigApi.listConfigs(),
    select: (data) => data.groups,
  })
}

export function useUpdateSystemConfigs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ category, updates }: { category: string; updates: Record<string, string> }) =>
      systemConfigApi.updateConfigs(category, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-configs'] })
    },
  })
}

export function useCreateSystemConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { key: string; value?: string; category: string; description?: string; is_secret?: boolean }) =>
      systemConfigApi.createConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-configs'] })
    },
  })
}

export function usePatchSystemConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, data }: { key: string; data: Partial<SystemConfigItem> }) =>
      systemConfigApi.patchConfig(key, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-configs'] })
    },
  })
}

export function useDeleteSystemConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => systemConfigApi.deleteConfig(key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system-configs'] })
    },
  })
}

export type { SystemConfigGroup }
