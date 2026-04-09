/**
 * FeeCalculator - 诉讼费计算器
 *
 * Requirements: 11.4
 */

import { Calculator, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useCalculateFee } from '../hooks/use-reference-data'
import type { FeeCalculationResponse } from '../types'

export interface FeeCalculatorProps {
  targetAmount?: number | null
  preservationAmount?: number | null
  caseType?: string
  causeOfAction?: string
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return '-'
  return `¥${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function FeeRow({ label, value }: { label: string; value: number | null | undefined }) {
  if (value == null) return null
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-muted-foreground text-sm">{label}</span>
      <span className="text-sm font-medium">{formatCurrency(value)}</span>
    </div>
  )
}

function FeeResults({ data }: { data: FeeCalculationResponse }) {
  const rows: { label: string; value: number | null }[] = []

  if (data.show_acceptance_fee) rows.push({ label: '案件受理费', value: data.acceptance_fee })
  if (data.show_half_fee) rows.push({ label: '案件受理费（减半）', value: data.acceptance_fee_half })
  if (data.preservation_fee != null) rows.push({ label: '保全费', value: data.preservation_fee })
  if (data.execution_fee != null) rows.push({ label: '执行费', value: data.execution_fee })
  if (data.show_payment_order_fee) rows.push({ label: '支付令费', value: data.payment_order_fee })
  if (data.bankruptcy_fee != null) rows.push({ label: '破产费', value: data.bankruptcy_fee })
  if (data.divorce_fee != null) rows.push({ label: '离婚案件费', value: data.divorce_fee })
  if (data.personality_rights_fee != null) rows.push({ label: '人格权案件费', value: data.personality_rights_fee })
  if (data.ip_fee != null) rows.push({ label: '知识产权案件费', value: data.ip_fee })
  if (data.fixed_fee != null) rows.push({ label: '固定费用', value: data.fixed_fee })

  if (rows.length === 0) {
    return <p className="text-muted-foreground text-sm">无计算结果</p>
  }

  return (
    <div className="divide-y">
      {rows.map((r) => (
        <FeeRow key={r.label} label={r.label} value={r.value} />
      ))}
      {data.fee_display_text && (
        <p className="text-muted-foreground pt-2 text-xs">{data.fee_display_text}</p>
      )}
    </div>
  )
}

export function FeeCalculator({ targetAmount, preservationAmount, caseType, causeOfAction }: FeeCalculatorProps) {
  const calculateFee = useCalculateFee()

  const handleCalculate = () => {
    calculateFee.mutate({
      target_amount: targetAmount ?? undefined,
      preservation_amount: preservationAmount ?? undefined,
      case_type: caseType,
      cause_of_action: causeOfAction ?? undefined,
    })
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Calculator className="size-4" />
            诉讼费计算
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={handleCalculate}
            disabled={calculateFee.isPending}
          >
            {calculateFee.isPending ? (
              <Loader2 className="mr-1 size-3 animate-spin" />
            ) : (
              <Calculator className="mr-1 size-3" />
            )}
            计算
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {calculateFee.data ? (
          <FeeResults data={calculateFee.data} />
        ) : calculateFee.isError ? (
          <p className="text-destructive text-sm">计算失败：{calculateFee.error.message}</p>
        ) : (
          <p className="text-muted-foreground text-sm">点击"计算"按钮获取诉讼费</p>
        )}
      </CardContent>
    </Card>
  )
}

export default FeeCalculator
