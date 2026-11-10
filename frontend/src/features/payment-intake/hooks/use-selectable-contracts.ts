import { useQuery } from '@tanstack/react-query'

import { INTAKE_SELECTABLE_KEY, listSelectableContracts } from '../api'

/**
 * 「换个项目」下拉的数据源。
 *
 * 后端已过滤掉已收满 / 已归档 / 案件全结案的项目——与自动匹配共用同一套
 * 资格规则，所以这里不做任何本地过滤（否则会出现"下拉能选但系统不推荐"
 * 的口径漂移）。新建的合同只要合格就会自动出现在这里。
 *
 * search 由后端做（合同名/建档号模糊匹配），本地不再筛。
 */
export function useSelectableContracts(search = '', enabled = true) {
  return useQuery({
    queryKey: [...INTAKE_SELECTABLE_KEY, search],
    queryFn: () => listSelectableContracts(search, 50),
    enabled,
    staleTime: 10_000,
  })
}
