import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { systemConfigApi, type SystemConfigGroup } from '../api'

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

export type { SystemConfigGroup }
