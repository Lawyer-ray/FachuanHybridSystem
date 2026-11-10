import { useQuery } from '@tanstack/react-query'

import { INVOICE_SELECTABLE_KEY, listSelectableContracts } from '../api'

/**
 * 「换个项目」下拉的数据源。
 *
 * 后端已按**发票专用口径**过滤（`exclude_fully_paid=False`）——与发票自动匹配
 * 共用同一套规则，所以这里不做任何本地过滤，否则会出现"下拉能选但系统不推荐"
 * 的口径漂移。新建的合同只要合格就会自动出现。
 *
 * 与款项侧的关键差异：**已收满的项目也要能选**。钱收齐了才开发票是正常顺序，
 * 拿款项的「收满即排除」口径会让这类项目彻底无法开票（实测踩过）。
 *
 * search 由后端做（合同名/建档号模糊匹配），本地不再筛。
 */
export function useSelectableContracts(search = '', enabled = true) {
  return useQuery({
    queryKey: [...INVOICE_SELECTABLE_KEY, search],
    queryFn: () => listSelectableContracts(search, 50),
    enabled,
    staleTime: 10_000,
  })
}
