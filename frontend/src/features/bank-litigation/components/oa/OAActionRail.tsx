/**
 * 盖章 / 归档面板的右栏：一卡多段（照 deal-detail 的 DetailRail 与 ContractRail 的做法）。
 *
 * 右栏只讲三件事：这一步该怎么走、目标文件认成了哪份、以及「为什么必须先反查」。
 */

import { KeyValueRow, RailSection, StepItem, WorkCard } from '../ui'

export function OAActionRail({
  verb,
  found,
  fileCount,
}: {
  /** 提交动作的按钮文案（申请盖章 / 提交归档） */
  verb: string
  found: { contract_name?: string | null; oa_case_number?: string | null } | null
  fileCount: number
}) {
  return (
    <WorkCard padded={false} className="xl:sticky xl:top-3">
      <RailSection title="怎么用">
        <StepItem index={1} title="填文件绝对路径" desc="在已绑定的文件夹里" state="current" />
        <StepItem index={2} title="反查合同" desc="按路径找到归属合同" state="todo" />
        <StepItem index={3} title={verb} desc="服务端在 OA 里执行" state="todo" />
      </RailSection>

      <RailSection title="目标文件">
        <dl>
          <KeyValueRow label="所属合同">
            <span className="block truncate text-[12px]" title={found?.contract_name ?? ''}>
              {found?.contract_name || '未反查'}
            </span>
          </KeyValueRow>
          <KeyValueRow label="OA 案号">
            <span className="block truncate text-[12px] text-muted-foreground">
              {found?.oa_case_number || '—'}
            </span>
          </KeyValueRow>
          <KeyValueRow label="文件数">
            <span className="text-[12px] tabular-nums">{fileCount || 0}</span>
          </KeyValueRow>
        </dl>
      </RailSection>

      <RailSection title="注意">
        <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
          <div className="text-[11px] font-medium">必须先反查</div>
          <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
            反查确认文件属于哪份合同后，{verb}才会启用 —— 避免把 A 案的文件盖到 B 案上。
          </p>
        </div>
      </RailSection>
    </WorkCard>
  )
}
