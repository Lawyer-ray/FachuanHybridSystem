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

import { AlertTriangle, CheckCircle2, Gavel, XCircle } from 'lucide-react'

import { DEMO_FILING_CHECKS, DEMO_FILING_FIXES, DEMO_SIGN_CHECKS, DEMO_X3_FIX_DIFF } from '../demo-data'
import { useState } from 'react'
import { StageActionCard } from './StageActionCard'
import { FilingAmountCard } from './FilingAmountCard'
import { FilingFixPreviewDrawer } from './FilingFixPreviewDrawer'
import { FilingNotifyCard, type NotifyStage } from './FilingNotifyCard'
import { SignDrawer } from './FilingSignDrawer'
import { useStageAction } from './use-stage-action'
import { ActionButton } from '../ui'
import { Pill, RailSection, SectionTitle, StatCell, StatStrip, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

const NOTIFY_STEPS = [
  { text: '检查硬阻塞：签章是否全部通过', ms: 300 },
  { text: '生成待办：去一张网核对立案表单', ms: 420 },
  { text: '推送站内待办 + AI 助手卡片', ms: 380 },
  { text: '发送短信', ms: 300 },
]

export function FilingPanel() {
  const [signOpen, setSignOpen] = useState<string | null>(null)
  /** 一键修正的 diff 预览是否打开 */
  const [diffOpen, setDiffOpen] = useState(false)

  /* 跑一遍完整校验 */
  const verify = useStageAction({
    steps: [
      { text: '加载校验规则', ms: 400 },
      { text: '核对当事人主体适格 · 通过', ms: 400 },
      { text: '核对管辖法院 · 通过', ms: 380 },
      { text: '核对诉讼时效 · 未届满', ms: 400 },
      {
        text: '比对三处金额',
        ms: 900,
        retry: { times: 1, delay: 800, reason: '立案表单回读超时，重新拉取' },
      },
      { text: '识别印章（6 份文书）', ms: 1200, parallel: ['起诉状', '证据清单', '授权委托书', '送达确认书', '退费确认书', '委托证明'] },
      { text: '识别签名区域', ms: 900 },
      { text: '检查要素式起诉状', ms: 450 },
      { text: '汇总校验结果', ms: 350 },
    ],
    toSummary: () => '校验完成：4 项通过 / 1 项提示 / 2 项不通过，暂不能送法院',
  })
  /* 一键修系统能自动修的那两项（只在 diff 预览确认后才跑） */
  const autoFix = useStageAction({
    steps: [
      { text: '按起诉状定稿基准重写立案表单标的额', ms: 420 },
      { text: '重写后回读校验：998,670.21 = 998,670.21', ms: 380 },
      { text: '调用要素式转换服务', ms: 640 },
      { text: '生成要素式起诉状 docx', ms: 520 },
    ],
    toSummary: () => '已自动修正 2 项：金额对齐、要素式转换完成；剩 2 份签章待人工',
  })

  /* 通知律师去一张网 */
  const notify = useStageAction({ steps: NOTIFY_STEPS, toSummary: () => '已送达' })
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

          {/* 签字盖章核对表 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle
                title="签字盖章核对"
                hint="机器比对扫描件的印章与签名区域 · 可逐份复核"
                className="w-full"
                action={<Pill tone={blocked.length ? 'red' : 'green'}>未通过 {blocked.length}</Pill>}
              />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_SIGN_CHECKS.map((d) => {
                const ok = d.sealOk && d.signOk
                return (
                  <li
                    key={d.docName}
                    onClick={() => setSignOpen(d.docName)}
                    className="flex cursor-pointer items-start gap-3 px-5 py-3 transition-colors hover:bg-secondary/40"
                  >
                    <span
                      className={cn(
                        'mt-[3px] grid size-4 flex-none place-items-center rounded-full',
                        ok ? 'bg-status-green' : 'bg-status-red',
                      )}
                    >
                      {ok ? (
                        <CheckCircle2 className="size-2.5 text-white" strokeWidth={3} />
                      ) : (
                        <XCircle className="size-2.5 text-white" strokeWidth={3} />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[12.5px] font-medium">{d.docName}</div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-muted-foreground">
                        <span>需盖：{d.needSeal}</span>
                        {d.needSign !== '—' ? (
                          <>
                            <span className="text-border">·</span>
                            <span>需签：{d.needSign}</span>
                          </>
                        ) : null}
                      </div>
                      <div
                        className={cn(
                          'mt-0.5 text-[10.5px]',
                          ok ? 'text-muted-foreground' : 'text-status-red',
                        )}
                      >
                        {d.note}
                      </div>
                    </div>
                    <div className="flex flex-none items-center gap-1.5">
                      <Pill tone={d.sealOk ? 'green' : 'red'}>章{d.sealOk ? '✓' : '✗'}</Pill>
                      <Pill tone={d.signOk ? 'green' : 'red'}>签{d.signOk ? '✓' : '✗'}</Pill>
                    </div>
                  </li>
                )
              })}
            </ul>
          </WorkCard>

          {/* 起诉条件机器判定 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle title="起诉条件机器判定" hint="法律要件 + 卷宗要件" className="w-full" />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_FILING_CHECKS.map((c) => (
                <li key={c.check} className="flex items-start gap-3 px-5 py-2.5">
                  <span
                    className={
                      c.result === 'pass'
                        ? 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-green'
                        : c.result === 'warn'
                          ? 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-yellow'
                          : 'mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-red'
                    }
                  >
                    <span className="text-[9px] font-bold text-white">
                      {c.result === 'pass' ? '✓' : c.result === 'warn' ? '!' : '✕'}
                    </span>
                  </span>
                  <span className="w-[110px] flex-none text-[12px] font-medium">{c.check}</span>
                  <span className="w-[160px] flex-none truncate text-[11px] text-muted-foreground" title={c.value}>{c.value}</span>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground" title={c.detail}>{c.detail}</span>
                  <Pill tone={c.result === 'pass' ? 'green' : c.result === 'warn' ? 'yellow' : 'red'}>
                    {c.result === 'pass' ? '通过' : c.result === 'warn' ? '提示' : '不通过'}
                  </Pill>
                </li>
              ))}
            </ul>
          </WorkCard>

          {/* 不通过的怎么修 */}
          <WorkCard padded={false}>
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <SectionTitle
                title="不通过项怎么修"
                hint="系统能自动修的会先给你看 diff"
                className="w-full"
                action={
                  <ActionButton sm dark disabled={autoFix.phase === 'running'} onClick={() => setDiffOpen(true)}>
                    {autoFix.phase === 'running' ? '修正中…' : autoFix.phase === 'done' ? '已修正 · 再看 diff' : '一键修正可自动项'}
                  </ActionButton>
                }
              />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_FILING_FIXES.map((f) => (
                <li key={f.item} className="px-5 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium">{f.item}</span>
                    <Pill tone={f.auto ? 'green' : 'yellow'}>{f.auto ? '系统自动' : '需人工'}</Pill>
                    {f.auto && autoFix.phase === 'done' ? <Pill tone="blue">已修正</Pill> : null}
                    <span className="ml-auto text-[10px] text-muted-foreground">{f.owner} · {f.eta}</span>
                  </div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">{f.fix}</div>
                </li>
              ))}
            </ul>
            {autoFix.phase === 'done' ? (
              <div className="border-t border-border-light bg-status-green-bg/30 px-5 py-2 text-[10.5px] text-status-green">
                {autoFix.summary}
              </div>
            ) : null}
          </WorkCard>

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

        <WorkCard padded={false}>
          <RailSection title="为什么最后才查签章">
            <p className="text-[10.5px] leading-[1.7] text-muted-foreground">
              签章是**不可逆**的一步。前面材料不齐可以补、金额错了可以改，
              但盖了章签了字再发现不对，就要重新走一遍签署流程。
              所以放在送法院之前的最后一关。
            </p>
          </RailSection>

          <RailSection title="这台机器查什么">
            <div className="flex flex-col gap-2 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">印章</span>
                <div className="mt-0.5">识别印章图像，比对类型（公章/法代章/财务章）与位置</div>
              </div>
              <div>
                <span className="font-medium text-foreground">签名</span>
                <div className="mt-0.5">检测签名区域是否有笔迹，空白页会直接标红</div>
              </div>
              <div>
                <span className="font-medium text-foreground">骑缝</span>
                <div className="mt-0.5">核对骑缝章是否覆盖全部附件页</div>
              </div>
            </div>
          </RailSection>

          <RailSection title="三处金额怎么算一致">
            <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>→ 起诉状定稿 = 基准，不改</div>
              <div>→ 立案表单按基准重算，回读比对</div>
              <div>→ 要素式由起诉状转换，天然同源</div>
              <div className="text-status-yellow">→ 口径不同（360/365 天）会差几毛几分</div>
            </div>
          </RailSection>

          <RailSection title="一键修正会改什么">
            <div className="rounded-[8px] border border-border-light bg-background px-2.5 py-2">
              <div className="text-[10.5px] font-medium text-secondary-foreground">
                {diffCount} 项字段变更，先看 diff 才执行
              </div>
              <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                改的是立案表单与要素式，起诉状定稿一张不改。
                签章那 2 项不在自动范围里。
              </p>
            </div>
          </RailSection>

          <RailSection title="通知是两阶段的">
            <div className="flex flex-col gap-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              <div>→ 发出 ≠ 送达，送达 ≠ 已读</div>
              <div>→ 站内待办回「已读」才算律师看到了</div>
              <div>→ 短信只到「已发送」，没有回执</div>
            </div>
          </RailSection>

          <RailSection title="一张网那一步">
            <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-[1px] size-3 flex-none text-status-yellow" />
                <p className="text-[10.5px] leading-[1.6] text-muted-foreground">
                  本页只负责「能不能去」。真正提交在「一张网立案」页，
                  由律师本人点击 —— 提交即对法院作出意思表示。
                </p>
              </div>
            </div>
          </RailSection>
        </WorkCard>
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
