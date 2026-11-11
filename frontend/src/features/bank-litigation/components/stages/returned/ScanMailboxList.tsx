/**
 * 回扫 —— 正在扫的邮箱列表。
 *
 * 每行展示一个邮箱的地址、轮询节奏、已扫邮件数，并给出「设置」入口；
 * 改过配置的邮箱打「已改配置」标。配置值由面板持有（保存后要回写到本列表），
 * 所以这里只收 `configs` + `onConfigure`，自己不存状态。
 */
import { Mail, Settings2 } from 'lucide-react'

import { DEMO_X2_SCAN_MAILBOXES, type ScanMailboxConfig } from '../../demo-data'
import { ActionButton, InsetBlock, Pill, SectionTitle, WorkCard } from '../../ui'

/** 正在扫的邮箱列表 + 每行设置入口 */
export function ScanMailboxList({
  configs,
  onConfigure,
}: {
  /** 已保存的邮箱配置（按地址覆盖演示默认值） */
  configs: Record<string, ScanMailboxConfig>
  onConfigure: (addr: string) => void
}) {
  return (
    <WorkCard>
      <SectionTitle title="系统正在扫这些邮箱" hint="每 5 分钟一轮" />
      <div className="mt-2.5 flex flex-col gap-1.5">
        {DEMO_X2_SCAN_MAILBOXES.map((base) => {
          const m = configs[base.addr] ?? base
          const changed = configs[base.addr] != null
          return (
            <InsetBlock key={base.addr}>
              <div className="flex items-center gap-2.5">
                <Mail className="size-3.5 flex-none text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px]">{m.addr}</div>
                  <div className="mt-0.5 truncate text-[10.5px] text-muted-foreground">
                    {m.note} · 每 {m.interval} · {m.folder}
                  </div>
                </div>
                {changed ? <Pill tone="blue">已改配置</Pill> : null}
                <Pill tone="green">监听中</Pill>
                <span className="flex-none text-[10.5px] tabular-nums text-muted-foreground">
                  本月 {m.count} 封
                </span>
                <ActionButton sm title="改轮询间隔 / 文件夹 / 发件人白名单" onClick={() => onConfigure(base.addr)}>
                  <Settings2 className="size-3" />
                  设置
                </ActionButton>
              </div>
            </InsetBlock>
          )
        })}
      </div>
    </WorkCard>
  )
}
