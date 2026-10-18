import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { useToday } from '@/hooks/use-today'
import { errMessage } from '@/lib/errors'
import { getContract, listLawyers, listRemindersByCase } from '../../api'
import { buildDeals } from '../../domain'
import type { ContractReminder, ReminderOut, WorkbenchDeal } from '../../types'
import { useContractCases } from '../../hooks/use-contract-cases'
import { workbenchKeys } from '../../hooks/use-workbench-data'

/**
 * 详情页数据：单合同 + 律师（补证号/律所）+ 该合同案件（与抽屉共用缓存）+ 逐案直挂提醒。
 * 四路并行、各自 60s 缓存；案件提醒要等案件 id 到齐才发。
 */
export function useDealDetail(contractId: number | null): {
  deal: WorkbenchDeal | null
  /** 合同直挂提醒（ContractOut.reminders；期限栏三源之一） */
  contractReminders: ContractReminder[]
  cases: ReturnType<typeof useContractCases>['cases']
  /** 案件直挂提醒（开庭多挂这里） */
  caseReminders: ReminderOut[]
  today: Date
  isLoading: boolean
  error: string | null
  casesError: string | null
  refetch: () => void
} {
  const today = useToday()
  const contractQ = useQuery({
    queryKey: workbenchKeys.contract(contractId ?? 0),
    queryFn: () => getContract(contractId as number),
    enabled: contractId != null,
    staleTime: 60_000,
  })
  const lawyersQ = useQuery({
    queryKey: workbenchKeys.lawyers,
    queryFn: listLawyers,
    staleTime: 60_000,
  })
  const casesQ = useContractCases(contractId)

  const caseIds = useMemo(() => casesQ.cases.map((c) => c.id).sort((a, b) => a - b), [casesQ.cases])
  const caseRemQ = useQuery({
    queryKey: workbenchKeys.caseReminders(contractId ?? 0, caseIds),
    queryFn: () => Promise.all(caseIds.map((id) => listRemindersByCase(id))).then((rs) => rs.flat()),
    enabled: contractId != null && caseIds.length > 0,
    staleTime: 60_000,
  })

  const deal = useMemo(() => {
    const contract = contractQ.data
    const lawyers = lawyersQ.data
    if (!contract) return null
    return buildDeals([contract], lawyers ?? [], today)[0] ?? null
  }, [contractQ.data, lawyersQ.data, today])

  return {
    deal,
    contractReminders: contractQ.data?.reminders ?? [],
    cases: casesQ.cases,
    caseReminders: caseRemQ.data ?? [],
    today,
    // 律师表拉不到不阻塞详情（只是缺证号/律所），合同本身失败才是页面级错误
    isLoading: contractId != null && (contractQ.isPending || casesQ.isLoading),
    error: contractQ.error ? errMessage(contractQ.error, '委托加载失败') : null,
    casesError: casesQ.error,
    refetch: () => {
      void contractQ.refetch()
      void casesQ.refetch()
    },
  }
}
