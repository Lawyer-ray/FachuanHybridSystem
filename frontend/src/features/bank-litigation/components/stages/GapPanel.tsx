/**
 * ③ 缺件 —— 系统发现遗漏，自动通知客户补什么
 *
 * 这一步的价值不在「列出来」，而在**通知发出去、客户补齐了、系统认出来了**。
 * 所以版面围绕「每条缺件的通知状态」展开：发了没、走了哪个渠道、客户回了什么。
 *
 * 补件是个**来回拉扯的过程**（发通知 → 已读 → 催办 → 上传 → 认出来），
 * 所以清单之外还要能看每一条的完整沟通过程、能勾选批量催办、能改话术、
 * 能按来源分组 —— 否则律师只能一条条点开猜客户到底卡在哪一步。
 *
 * 本文件只做编排：勾选/分组/抽屉三处需要跨块共享的状态留在这里，
 * 各块自己的局部状态（批量回执、话术编辑、催办执行态）随块下沉到 gap/ 下的子组件。
 */

import { Send } from 'lucide-react'
import { useState } from 'react'

import { DEMO_GAP_NOTICES, type GapSource } from '../demo-data'
import { InsetBlock, Pill, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { useStageAction } from './use-stage-action'
import { StageActionCard } from './StageActionCard'
import { GapBatchBar } from './gap/GapBatchBar'
import { GapDrawer } from './gap/GapDrawer'
import { GapNoticeCount, GapNoticeEmpty, GapNoticeList } from './gap/GapNoticeList'
import { GapRail } from './gap/GapRail'
import { GapReceivedCard } from './gap/GapReceivedCard'
import { GapScriptCard } from './gap/GapScriptCard'
import { GapSourceTabs } from './gap/GapSourceTabs'
import { isAllChecked, openCheckedItems, visibleNotices } from './gap/gap-utils'

export function GapPanel() {
  /** 点开的缺件项 */
  const [picked, setPicked] = useState<string | null>(null)
  /** 演示：手动关闭的缺件（律师判断这条不用补） */
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  /** 批量操作勾选的缺件项 */
  const [checked, setChecked] = useState<Set<string>>(new Set())
  /** 缺件按来源分组 */
  const [sourceTab, setSourceTab] = useState<'全部' | GapSource>('全部')

  /* 重新检测缺件：演示时会话可反复触发 */
  const detect = useStageAction({
    steps: [
      { text: '加载借贷类必备清单（6 项）', ms: 400 },
      { text: '逐份材料比对槽位', ms: 900, parallel: ['合同类', '借据类', '还款类', '催收类', '身份类'] },
      { text: '催收记录：止于 2025-06，缺最近 12 个月 → 硬阻塞', ms: 500 },
      { text: '抵押物权属证明：未见不动产权证 → 硬阻塞', ms: 450 },
      { text: '共同借款人身份证明：2 人仅见 1 人 → 硬阻塞', ms: 450 },
      { text: '还款账户流水：止于 2026-04 → 建议补', ms: 400 },
      {
        text: '生成补件清单',
        ms: 600,
        confirm: '共 5 项缺件，其中 3 项硬阻塞。确认全部发给客户，还是先发硬阻塞的 3 项？',
      },
      {
        text: '推送客户（短信 + 邮件）',
        ms: 800,
        retry: { times: 1, delay: 1200, reason: '短信网关超时，重试中' },
      },
      { text: '同步通知主办律师', ms: 350 },
    ],
    toSummary: () => '发现 5 项缺件（3 项硬阻塞），已通过短信+邮件推送给客户经理',
  })

  const blockers = DEMO_GAP_NOTICES.filter((g) => g.severity === 'blocker')
  const received = DEMO_GAP_NOTICES.filter((g) => g.status === 'received')
  const waiting = DEMO_GAP_NOTICES.filter((g) => g.status !== 'received')
  const blockerOpen = blockers.filter((g) => g.status !== 'received').length

  const visible = visibleNotices(sourceTab)
  /** 勾选里还没补齐的那些 —— 批量催办只该发给它们 */
  const checkedOpen = openCheckedItems(checked)
  const allChecked = isAllChecked(visible, checked)

  const toggleOne = (item: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(item)) next.delete(item)
      else next.add(item)
      return next
    })
  const toggleAll = () =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (allChecked) visible.forEach((g) => next.delete(g.item))
      else visible.forEach((g) => next.add(g.item))
      return next
    })

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="重新检测缺件并通知客户"
        desc="系统拿已转换的正文比对必备清单，缺什么当场列出来。硬阻塞项会随通知一起发出去，客户点短信里的免登录链接就能补。"
        actionLabel="检测并通知"
        hint="5 项缺件 · 约 2.7 秒"
        state={detect}
        execute={() => void detect.execute()}
        reset={detect.reset}
        confirm={detect.confirm}
      />

      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="发现缺件" value={`${DEMO_GAP_NOTICES.length} 项`} tone="yellow" />
        <StatCell label="硬阻塞" value={`${blockers.length} 项`} tone="red" />
        <StatCell label="客户已补" value={`${received.length} 项`} tone="green" />
        <StatCell label="仍待补" value={`${waiting.length} 项`} tone={waiting.length ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 通知是自动发出去的 */}
          <WorkCard>
            <SectionTitle title="补件通知已自动发出" hint="识别到缺件后 3 分钟内" />
            <InsetBlock className="mt-2.5">
              <div className="flex items-start gap-2.5">
                <Send className="mt-[2px] size-3.5 flex-none text-status-blue" />
                <div className="min-w-0">
                  <div className="text-[12px] font-medium">
                    已向客户经理 王某某 发送补件清单（{DEMO_GAP_NOTICES.length} 项）
                  </div>
                  <div className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                    短信 + 邮件双通道 · 10-28 14:02 · 附带客户上传链接（免登录，链接即凭证）
                  </div>
                </div>
              </div>
            </InsetBlock>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Pill tone="blue">短信已送达</Pill>
              <Pill tone="blue">邮件已送达</Pill>
              <Pill tone="green">客户已读</Pill>
            </div>
          </WorkCard>

          {/* 逐项缺件：按来源分组 + 可勾选批量操作 */}
          <WorkCard padded={false}>
            <div className="flex flex-wrap items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle
                title="缺件清单"
                hint="硬阻塞项不补齐无法送法院"
                className="w-full"
                action={<GapNoticeCount tab={sourceTab} visibleCount={visible.length} />}
              />
            </div>

            <GapSourceTabs value={sourceTab} onChange={setSourceTab} />

            <GapBatchBar
              checked={checked}
              checkedOpen={checkedOpen}
              allChecked={allChecked}
              onToggleAll={toggleAll}
              onClear={() => setChecked(new Set())}
            />

            <GapNoticeList visible={visible} checked={checked} onToggle={toggleOne} onPick={setPicked} />
            {visible.length === 0 ? <GapNoticeEmpty tabLabel={sourceTab} /> : null}
          </WorkCard>

          <GapScriptCard />

          <GapReceivedCard />
        </div>

        <GapRail blockerOpen={blockerOpen} />
      </div>

      <GapDrawer
        item={picked}
        onClose={() => setPicked(null)}
        dismissed={dismissed}
        onDismiss={(k) => {
          setDismissed((prev) => new Set(prev).add(k))
          setPicked(null)
        }}
      />
    </div>
  )
}
