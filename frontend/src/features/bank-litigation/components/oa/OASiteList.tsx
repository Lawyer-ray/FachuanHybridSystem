/**
 * OA 立案 · 站点清单。
 *
 * ═══ 为什么站点要摊成一张表，而不是一个下拉框 ═══
 * 下拉框只回答「选哪个」，回答不了「这条路通不通、最近跑得怎么样」。
 * 立案失败最常见的原因是凭证过期 —— 而凭证状态、最近登录时间、本月立了几件
 * 恰好是判断「现在点下去会不会挂」的全部依据，所以并排列出来。
 *
 * ═══ 两种数据不要混 ═══
 * 列表本身来自后端 `/oa-filing/configs`（站点名可能是真实律所名，本组件照实显示）；
 * 「本月件数 / 平均耗时 / 登录时间」是演示态的补充统计。这部分**按下标对齐**
 * 而不是按站点名匹配：站点名是机构标识，演示常量里不该出现真实名字，
 * 按名字匹配必然全部对不上、整列变「—」。真实接口补齐这些字段后删掉本映射即可。
 * 后端没有任何站点时整表回落到 `DEMO_OA_SITES`。
 */

import { StatusBadge } from '@/components/shared/status-badge'
import { cn } from '@/lib/utils'

import { SectionTitle, WorkCard } from '../ui'
import { DEMO_OA_SITES } from '../demo-data'

export interface OASiteListItem {
  /* 后端 OAConfig.id 是字符串，演示兜底行用负数序号 */
  id: string | number
  name: string
  hasCredential: boolean
}

export function OASiteList({
  sites,
  currentName,
  onPick,
}: {
  sites: OASiteListItem[]
  currentName: string
  onPick: (name: string) => void
}) {
  /* 后端无配置时用演示清单撑住画面；此时演示行自己带凭证状态与统计。 */
  const usingDemo = sites.length === 0
  const rows: (OASiteListItem & { filedThisMonth?: number; avgMs?: string; loginAt?: string; lastUsed?: string })[] =
    usingDemo
      ? DEMO_OA_SITES.map((d, i) => ({
          id: i,
          name: d.name,
          hasCredential: d.credential,
          filedThisMonth: d.filedThisMonth,
          avgMs: d.avgMs,
          loginAt: d.loginAt,
          lastUsed: d.lastUsed,
        }))
      : sites.map((s, i) => {
          const d = DEMO_OA_SITES[i % DEMO_OA_SITES.length]
          return {
            ...s,
            filedThisMonth: d?.filedThisMonth,
            avgMs: d?.avgMs,
            loginAt: d?.loginAt,
            lastUsed: d?.lastUsed,
          }
        })

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="OA 站点"
          hint={`共 ${rows.length} 条 · 凭证状态决定能不能发起`}
          className="w-full"
        />
      </div>
      <ul className="divide-y divide-border-light">
        {rows.map((s) => {
          const active = s.name === currentName
          return (
            <li key={`${s.id}-${s.name}`}>
              <button
                type="button"
                onClick={() => onPick(s.name)}
                className={cn(
                  'flex w-full items-center gap-3 px-5 py-2.5 text-left transition-colors hover:bg-secondary/50',
                  active && 'bg-secondary/40',
                )}
              >
                <span className={cn('size-1.5 flex-none rounded-full', active ? 'bg-foreground' : 'bg-border')} />
                <span className="min-w-0 flex-1 truncate text-[12px]" title={s.name}>
                  {s.name}
                </span>
                <span className="w-[64px] flex-none">
                  <StatusBadge tone={s.hasCredential ? 'green' : 'red'} size="xs">
                    {s.hasCredential ? '已配凭证' : '未配凭证'}
                  </StatusBadge>
                </span>
                <span className="w-[74px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
                  本月 {s.filedThisMonth ?? '—'} 件
                </span>
                <span className="w-[62px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
                  均 {s.avgMs ?? '—'}
                </span>
                <span className="w-[88px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  登录 {s.loginAt ?? '—'}
                </span>
                <span className="w-[88px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  最近 {s.lastUsed ?? '—'}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </WorkCard>
  )
}
