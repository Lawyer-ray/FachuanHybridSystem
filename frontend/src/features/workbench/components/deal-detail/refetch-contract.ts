/**
 * 详情页「合同层面的写操作」完成后的一次性刷新：合同自身（收款 / 开票金额 /
 * 当事人…）+ 案件（案件卡里也会显示钱）+ 工作的列表缓存（列表页的开票列）。
 *
 * 为什么抽出来：发票关联/解除是**局部**变更，只影响合同与列表两处数据；
 * 每次都手写一串 refetch/invalidate 一定有人漏掉某一处——漏掉时的症状是
 * 「已开票金额没变，要手动刷新页面」（律师已经踩过一次）。
 *
 * `cancelRefetch: false`：关联后立刻重挂（解除→再关联）会连发多次刷新，默认的
 * `cancelRefetch: true` 会让前一次请求被取消、只留最后一次；被取消的那次如果
 * 恰好是先发出去的（响应更旧），就有机会用旧数据覆盖新数据。这里一律不取消，
 * 让在途请求自己跑完，react-query 按发起顺序保留最后一次结果。
 */

import type { QueryClient } from '@tanstack/react-query'

import { workbenchKeys } from '../../hooks/use-workbench-data'

/** 只刷新这一份合同（最快的局部刷新） */
export function refetchContract(queryClient: QueryClient, contractId: number): void {
  void queryClient.refetchQueries({ queryKey: workbenchKeys.contract(contractId) }, { cancelRefetch: false })
  // 列表页也展示已收/已开票，不改就会「点进详情对、退回列表还是旧数」
  // 列表键首段是 'workbench'，用前缀 'workbench' 会连带详情一起失效；这里精确打
  // 分页键的片段 "contracts-page"（见 use-workbench-data 的 contractPage）。
  void queryClient.invalidateQueries({ queryKey: ['workbench', 'contracts-page'] })
}

/** 合同 + 该合同的案件（案件卡的钱跟着变时用） */
export function refetchContractAndCases(queryClient: QueryClient, contractId: number): void {
  refetchContract(queryClient, contractId)
  void queryClient.refetchQueries({ queryKey: workbenchKeys.contractCases(contractId) }, { cancelRefetch: false })
}
