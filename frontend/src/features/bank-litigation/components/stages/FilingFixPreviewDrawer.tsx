/**
 * ⑥ 校验 —— 一键修正的 diff 预览
 *
 * 「一键修正」是个危险按钮：它直接改的是要送法院的立案表单。
 * 所以点下去先给一张 before/after 表（红删绿增），律师看完点「确认执行」才动数据。
 *
 * 这是本页唯一一处「先预览再执行」的地方，因为其余动作错了可以重跑，
 * 这个错了会进法院系统。
 */

import { ArrowRight } from 'lucide-react'

import { DEMO_X3_FIX_DIFF } from '../demo-data'
import { ActionButton, InsetBlock, Pill } from '../ui'
import { DetailDrawer } from './DetailDrawer'

export function FilingFixPreviewDrawer({
  open,
  running,
  onConfirm,
  onClose,
}: {
  open: boolean
  running: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const items = [...new Set(DEMO_X3_FIX_DIFF.map((d) => d.item))]

  return (
    <DetailDrawer
      open={open}
      onClose={onClose}
      width={620}
      title="确认要改这些字段？"
      subtitle={`${DEMO_X3_FIX_DIFF.length} 项变更 · 只改立案表单与要素式，不动起诉状定稿`}
      badge={<Pill tone="yellow">待确认</Pill>}
      footer={
        <>
          <ActionButton dark disabled={running} onClick={onConfirm}>
            {running ? '修正中…' : '确认执行'}
          </ActionButton>
          <ActionButton onClick={onClose}>取消</ActionButton>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <div key={item}>
            <div className="mb-1.5 flex items-center gap-2">
              <span className="text-[12px] font-medium">{item}</span>
              <span className="text-[10px] text-muted-foreground">系统自动可修</span>
            </div>
            <div className="flex flex-col divide-y divide-border-light rounded-[9px] border border-border-light">
              {DEMO_X3_FIX_DIFF.filter((d) => d.item === item).map((d) => (
                <div key={d.field} className="px-3 py-2">
                  <div className="text-[10.5px] text-muted-foreground">{d.field}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="rounded-[4px] bg-status-red-bg px-1.5 py-[1px] text-[11.5px] tabular-nums text-status-red line-through">
                      {d.before}
                    </span>
                    <ArrowRight className="size-3 text-muted-foreground" />
                    <span className="rounded-[4px] bg-status-green-bg px-1.5 py-[1px] text-[11.5px] font-medium tabular-nums text-status-green">
                      {d.after}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <InsetBlock className="border-status-yellow/40 bg-status-yellow-bg/50">
          <div className="text-[10.5px] font-medium text-status-yellow">不会动的东西</div>
          <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">
            起诉状定稿、已签章的扫描件、当事人信息都不在本次变更范围。
            签章相关的 2 项仍需人工补签补盖，不在「可自动」里。
          </p>
        </InsetBlock>
      </div>
    </DetailDrawer>
  )
}
