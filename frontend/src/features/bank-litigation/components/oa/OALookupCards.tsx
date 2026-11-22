/**
 * OA 反查结果的两张卡：失败、成功。
 *
 * 反查（lookup）是「先验证再执行」的那一步 —— 后端按文件路径反查文件夹绑定、
 * 再由绑定找到合同。盖章与归档共用同一套结果形状，所以两张卡也共用。
 */

import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { KeyValueRow, WorkCard } from '../ui'

/** 反查失败：把后端原话原样给出，不替它猜原因 */
export function LookupErrorCard({ error }: { error: string }) {
  return (
    <div className="rounded-[10px] border border-status-red/40 bg-status-red-bg px-3.5 py-3">
      <div className="flex items-center gap-1.5 text-[12px] font-medium text-status-red">
        <AlertTriangle className="size-3.5 flex-none" /> 反查失败
      </div>
      <p className="mt-1 text-[11.5px] leading-[1.6] text-status-red/90">{error}</p>
      <p className="mt-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
        常见原因：文件不在已绑定的案件/合同文件夹里；路径写错；或这份文件不属于你的案件。
      </p>
    </div>
  )
}

/** 反查成功：认出了哪份合同、OA 案号是多少 */
export function FoundContractCard({
  found,
}: {
  found: { contract_name?: string | null; oa_case_number?: string | null }
}) {
  return (
    <WorkCard className="border-status-green/40 bg-status-green-bg/50">
      <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-status-green">
        <CheckCircle2 className="size-3.5" /> 已识别到合同
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-x-6 md:grid-cols-2">
        <div className="divide-y divide-border/60">
          <KeyValueRow label="合同">
            <span className="block truncate" title={found.contract_name ?? ''}>
              {found.contract_name || '—'}
            </span>
          </KeyValueRow>
          <KeyValueRow label="OA 案号">
            <span className="block truncate" title={found.oa_case_number ?? ''}>
              {found.oa_case_number || '（OA 尚未生成案号）'}
            </span>
          </KeyValueRow>
        </div>
      </dl>
    </WorkCard>
  )
}
