/**
 * ⑥ 校验 → 通知律师去一张网
 *
 * 这一步是**最后一道人工闸门之前**的机器检查：
 * 签字盖章齐不齐、当事人信息对不对、金额三处一致不一致。
 * 齐了才通知律师去一张网提交 —— 提交那一下仍然由律师本人点（见一张网页）。
 *
 * 与「③ 缺件」的区别：那里查「材料有没有」，这里查「材料对不对」。
 * 有了一份材料但没签字盖章，等于没有。
 */

import { Gavel } from 'lucide-react'

import { DEMO_SIGN_CHECKS, DEMO_X3_FIX_DIFF } from '../demo-data'
import { useState } from 'react'
import { StageActionCard } from './StageActionCard'
import { FilingAmountCard } from './FilingAmountCard'
import { FilingFixPreviewDrawer } from './FilingFixPreviewDrawer'
import { FilingNotifyCard, type NotifyStage } from './FilingNotifyCard'
import { SignDrawer } from './FilingSignDrawer'
import { StatCell, StatStrip } from '../ui'
import { FilingRail } from './filing/FilingRail'
import { CheckResultTable, FixSuggestionTable, SignCheckTable } from './filing/FilingTables'
import { useFilingAutoFix, useFilingNotify, useFilingVerify } from './use-filing-actions'

export function FilingPanel() {
  const [signOpen, setSignOpen] = useState<string | null>(null)
  /** 一键修正的 diff 预览是否打开 */
  const [diffOpen, setDiffOpen] = useState(false)

  const verify = useFilingVerify()
  const autoFix = useFilingAutoFix()
  const notify = useFilingNotify()
  const [notifyStage, setNotifyStage] = useState<NotifyStage>('idle')

  const sealOk = DEMO_SIGN_CHECKS.filter((d) => d.sealOk).length
  const signOk = DEMO_SIGN_CHECKS.filter((d) => d.signOk).length
  const blocked = DEMO_SIGN_CHECKS.filter((d) => !d.sealOk || !d.signOk)
  const total = DEMO_SIGN_CHECKS.length
  const diffCount = DEMO_X3_FIX_DIFF.length

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="核对签字盖章，看能不能送法院"
        desc="这是送法院前的最后一关：签章不齐、金额对不上都过不去。机器只做检查，通过后通知律师去一张网，提交那一下仍由律师本人点。"
        actionLabel="开始校验"
        hint="6 份文书 · 约 3 秒"
        state={verify}
        execute={() => void verify.execute()}
        reset={verify.reset}
        confirm={verify.confirm}
      />

      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="待核对文书" value={`${total} 份`} />
        <StatCell label="盖章齐" value={`${sealOk}/${total}`} tone={sealOk === total ? 'green' : 'yellow'} />
        <StatCell label="签字齐" value={`${signOk}/${total}`} tone={signOk === total ? 'green' : 'yellow'} />
        <StatCell
          label="阻塞项"
          value={`${blocked.length} 份`}
          tone={blocked.length ? 'red' : 'green'}
        />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 三处金额对比 */}
          <FilingAmountCard />

          {/* 三张核对表：签字盖章 / 起诉条件 / 不通过项怎么修 */}
          <SignCheckTable blockedCount={blocked.length} onOpen={setSignOpen} />
          <CheckResultTable />
          <FixSuggestionTable
            autoFixPhase={autoFix.phase}
            autoFixSummary={autoFix.summary}
            onOpenDiff={() => setDiffOpen(true)}
          />

          {/* 报送与通知 */}
          <FilingNotifyCard
            blockedCount={blocked.length}
            blockedNotes={blocked.map((d) => d.note)}
            stage={notifyStage}
            onSend={() => {
              setNotifyStage('sending')
              void notify.execute().then(() => setNotifyStage('sent'))
            }}
          />
        </div>

        <FilingRail diffCount={diffCount} />
      </div>

      <SignDrawer name={signOpen} onClose={() => setSignOpen(null)} />
      <FilingFixPreviewDrawer
        open={diffOpen}
        running={autoFix.phase === 'running'}
        onConfirm={() => {
          setDiffOpen(false)
          void autoFix.execute()
        }}
        onClose={() => setDiffOpen(false)}
      />

      {/* diff 预览是这一页唯一的「先看再改」 */}
      <div className="flex items-center gap-2 px-1">
        <Gavel className="size-3.5 flex-none text-muted-foreground" />
        <span className="text-[10.5px] text-muted-foreground">
          机器只做检查与修正建议；{diffCount} 项自动修正必须经律师确认 diff 后才执行。
        </span>
      </div>
    </div>
  )
}
