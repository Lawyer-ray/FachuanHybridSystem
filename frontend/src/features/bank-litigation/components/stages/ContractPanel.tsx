/**
 * ④ 文书 —— 自动生成委托合同 → 派机器人去 OA 做利冲检索并立案
 *
 * 这一段是两个动作串在一起：
 *   1. 系统拿案件数据把委托代理合同等文书套出来（律师核对后定稿）
 *   2. 派机器人登录律所 OA，**先查利益冲突**，没冲突才建卷
 *
 * 利冲放在立案之前是硬性的：先建了卷再发现冲突，撤销要走审批，
 * 而冲突本身可能意味着这案子根本不能接。
 */

import { FileText, Video } from 'lucide-react'

import {
  DEMO_CONFLICT_HITS,
  DEMO_CONTRACT_GEN,
  DEMO_X3_BROWSER_FRAMES,
  DEMO_X3_CONFLICT_REPORT,
  DEMO_X3_CONFLICT_REPORT_FILE,
} from '../demo-data'
import { useState } from 'react'
import { StageActionCard } from './StageActionCard'
import { BotReplayDrawer } from './BotReplayDrawer'
import { ConflictCard } from './ContractConflictCard'
import { ContractGenCard, ContractTermsCard, TermEditDrawer } from './ContractTermsCard'
import { initTermDrafts, pendingTermCount } from './contract-terms'
import { ContractRail } from './ContractRail'
import { DocDrawer } from './ContractDocDrawer'
import { DetailDrawer } from './DetailDrawer'
import { useStageAction } from './use-stage-action'
import { ActionButton, InsetBlock, KeyValueRow, Pill, SectionTitle, StepItem, WorkCard } from '../ui'
import { cn } from '@/lib/utils'

export function ContractPanel() {
  /** 预览的文书名 */
  const [docOpen, setDocOpen] = useState<string | null>(null)
  /** 查看的利冲主体 */
  const [hitOpen, setHitOpen] = useState<string | null>(null)
  /** 正在编辑的条款 */
  const [termEdit, setTermEdit] = useState<string | null>(null)
  /** 条款草稿：改过的值只存在这里，不动共享常量 */
  const [drafts, setDrafts] = useState(initTermDrafts)
  /** 每份文书选用的模板 */
  const [templates, setTemplates] = useState<Record<string, string>>({})
  /** 执行录像 */
  const [replayOpen, setReplayOpen] = useState(false)
  /** 利冲报告导出结果（拿到文件名即视为已生成） */
  const [report, setReport] = useState<string | null>(null)

  /* ① 生成委托材料 */
  const genDocs = useStageAction({
    steps: [
      { text: '读取案件数据', ms: 500, parallel: ['当事人', '案由与标的', '管辖法院', '收费约定'] },
      { text: '套用《民事委托代理合同 v3.2》', ms: 900 },
      { text: '填充 24 个字段', ms: 700 },
      {
        text: '生成授权委托书',
        ms: 600,
        retry: { times: 1, delay: 800, reason: '共同借款人信息不完整，补齐后重试' },
      },
      { text: '生成风险告知书 / 收费协议', ms: 600 },
      { text: '检查必填项', ms: 500 },
    ],
    toSummary: () => '4 份文书已生成，1 份待补（送达地址确认书需选管辖法院模板）',
  })
  /* ② 派机器人去 OA 做利冲检索 —— 这是本页的核心动作 */
  const conflictRun = useStageAction({
    steps: [
      { text: '启动服务端浏览器', ms: 700, parallel: ['分配容器', '加载自动化脚本'] },
      { text: '打开律所 OA 登录页', ms: 800 },
      {
        text: '登录 OA',
        ms: 900,
        retry: { times: 2, delay: 1500, reason: '登录会话超时，重新认证' },
      },
      { text: '进入当事人库检索', ms: 600 },
      { text: '检索：委托人 某某银行某某支行 → 无冲突', ms: 500 },
      { text: '检索：被告 谭某某 → 无同名记录', ms: 450 },
      { text: '检索：共同借款人 李某某 → 命中！', ms: 900 },
      {
        text: '命中红色冲突',
        ms: 600,
        confirm: '共同借款人李某某与本所在办「离婚案」当事人为同一人（证件号一致）。这属于禁止性冲突，是否终止本次委托？',
      },
      { text: '停止建卷，保留利冲结果页快照', ms: 500 },
    ],
    toSummary: () => '命中 1 处红色冲突（李某某），OA 立案已自动阻断',
  })
  /* ③ 导出利冲报告：短进度，落一个 PDF */
  const exportReport = useStageAction({
    steps: [
      { text: '汇总 6 方检索记录', ms: 350 },
      { text: '附上命中快照与证件号比对', ms: 450 },
      { text: '渲染 PDF 并加律所抬头', ms: 550 },
    ],
    toSummary: () => 'LCA-20261101-0007 利冲审查报告.pdf 已生成，可在文书库下载',
  })

  const red = DEMO_CONFLICT_HITS.filter((h) => h.level === 'red')
  const yellow = DEMO_CONFLICT_HITS.filter((h) => h.level === 'yellow')
  const generated = DEMO_CONTRACT_GEN.filter((d) => d.status === 'generated')
  const pendingTerms = pendingTermCount(drafts)
  const customTemplates = Object.entries(templates).filter(([, v]) => v !== 'v3.2')

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="生成委托材料并做利益冲突检索"
        desc="先按案件数据把委托合同等文书套出来，再派机器人登录律所 OA 逐方比对当事人库。命中红色冲突就停在利冲页，不继续建卷。"
        actionLabel="生成文书 + 利冲检索"
        hint="5 份文书 · 6 方检索 · 约 4 秒"
        state={conflictRun}
        execute={() => void conflictRun.execute()}
        reset={conflictRun.reset}
        confirm={conflictRun.confirm}
      />

      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <MiniStat label="已生成文书" value={`${generated.length}/${DEMO_CONTRACT_GEN.length}`} tone="green" />
        <MiniStat label="待定条款" value={`${pendingTerms}`} tone={pendingTerms ? 'yellow' : 'green'} />
        <MiniStat label="红色冲突" value={`${red.length}`} tone={red.length ? 'red' : 'green'} />
        <MiniStat label="需复核" value={`${yellow.length}`} tone={yellow.length ? 'yellow' : 'green'} />
      </div>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          <ContractGenCard
            generating={genDocs.phase === 'running'}
            onGenerate={() => void genDocs.execute()}
            templates={templates}
            onTemplateChange={(name, tpl) => setTemplates((v) => ({ ...v, [name]: tpl }))}
            onOpenDoc={setDocOpen}
          />

          <ContractTermsCard drafts={drafts} onEdit={setTermEdit} />

          {/* 利冲检索 */}
          <ConflictCard
            exportState={{
              phase: exportReport.phase,
              percent: exportReport.percent,
              progress: exportReport.progress,
              report,
              onExport: () => {
                setReport(null)
                void exportReport.execute().then(() => setReport(DEMO_X3_CONFLICT_REPORT_FILE))
              },
            }}
            onOpenHit={setHitOpen}
          />

          {/* 机器人执行日志 */}
          <WorkCard>
            <SectionTitle
              title="机器人执行过程"
              hint="服务端浏览器自动化"
              action={
                <ActionButton sm onClick={() => setReplayOpen(true)}>
                  <Video className="size-3" />
                  查看执行录像
                </ActionButton>
              }
            />
            <div className="mt-3">
              <StepItem index={1} title="登录律所 OA" desc="用配置账号登录 · 1,840 ms" state="done" />
              <StepItem index={2} title="检索当事人库" desc="6 方逐方比对 · 2,260 ms" state="done" />
              <StepItem index={3} title="命中红色冲突" desc="李某某 与「离婚案」当事人同人" state="blocked" />
              <StepItem index={4} title="停止建卷" desc="等律师决定是否终止委托" state="todo" />
            </div>
            <div className="mt-2 text-[10px] text-muted-foreground">
              录像 {DEMO_X3_BROWSER_FRAMES.length} 帧 · 11-01 10:22 — 10:24
            </div>
          </WorkCard>
        </div>

        <ContractRail
          termCount={Object.keys(drafts).length}
          pendingTerms={pendingTerms}
          customTemplates={customTemplates}
        />
      </div>

      <DocDrawer name={docOpen} onClose={() => setDocOpen(null)} />
      <ConflictDrawer keyName={hitOpen} onClose={() => setHitOpen(null)} />
      <TermEditDrawer
        clause={termEdit}
        drafts={drafts}
        onSave={(clause, value) => setDrafts((v) => ({ ...v, [clause]: { value, edited: true } }))}
        onClose={() => setTermEdit(null)}
      />
      <BotReplayDrawer open={replayOpen} onClose={() => setReplayOpen(false)} />
    </div>
  )
}

/** 统计格：这一版用独立小块，不再依赖 StatStrip 的固定四列 */
function MiniStat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'neutral' | 'green' | 'red' | 'yellow'
}) {
  const map = {
    neutral: 'text-foreground',
    green: 'text-status-green',
    red: 'text-status-red',
    yellow: 'text-status-yellow',
  } as const
  return (
    <div className="rounded-[10px] border border-border-light bg-secondary/30 px-3 py-2 text-center">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-[14px] font-[620] tabular-nums', map[tone])}>{value}</div>
    </div>
  )
}

/** 利冲详情：能看到匹配到了什么、怎么办 */
function ConflictDrawer({ keyName, onClose }: { keyName: string | null; onClose: () => void }) {
  const h = keyName ? DEMO_CONFLICT_HITS.find((x, i) => `${x.subject}-${i}` === keyName) : null
  const [exported, setExported] = useState<string | null>(null)

  return (
    <DetailDrawer
      open={h != null}
      onClose={onClose}
      title={h?.subject ?? ''}
      subtitle={h?.role}
      badge={h ? <Pill tone={h.level === 'red' ? 'red' : h.level === 'yellow' ? 'yellow' : 'green'}>
        {h.level === 'red' ? '红色冲突' : h.level === 'yellow' ? '需复核' : '无冲突'}
      </Pill> : null}
      footer={
        h ? (
          <>
            <ActionButton dark onClick={() => setExported('冲突审查结论-LCA-20261101-0007.pdf')}>
              导出利冲报告
            </ActionButton>
            <ActionButton onClick={onClose}>标记为已核实</ActionButton>
          </>
        ) : null
      }
    >
      {h ? (
        <div className="flex flex-col gap-3">
          <dl>
            <KeyValueRow label="检索对象">{h.subject}</KeyValueRow>
            <KeyValueRow label="本案身份">{h.role}</KeyValueRow>
            <KeyValueRow label="检索结果">
              <span className={h.level === 'red' ? 'text-status-red' : h.level === 'yellow' ? 'text-status-yellow' : 'text-status-green'}>
                {h.level === 'red' ? '存在冲突' : h.level === 'yellow' ? '疑似，需人工判断' : '无冲突'}
              </span>
            </KeyValueRow>
          </dl>

          <InsetBlock className={h.level === 'red' ? 'border-status-red/40 bg-status-red-bg/60' : 'bg-secondary/25'}>
            <div className="text-[10px] text-muted-foreground">判定依据</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">{h.detail}</p>
          </InsetBlock>

          {h.level === 'red' ? (
            <InsetBlock className="border-status-red/40 bg-status-red-bg/40">
              <div className="text-[10.5px] font-medium text-status-red">按执业规范必须停止</div>
              <p className="mt-1 text-[10.5px] leading-[1.65] text-muted-foreground">
                同一自然人在对方阵营，属于禁止性冲突。需由主任律师判定是否终止本次委托，
                或取得双方书面同意后继续。
              </p>
            </InsetBlock>
          ) : null}

          <div>
            <div className="mb-1.5 text-[10.5px] text-muted-foreground">审查报告会带上这些</div>
            <dl className="divide-y divide-border-light">
              {DEMO_X3_CONFLICT_REPORT.map((r) => (
                <KeyValueRow key={r.title} label={r.title}>
                  {r.value}
                </KeyValueRow>
              ))}
            </dl>
          </div>

          {exported ? (
            <InsetBlock className="border-status-green/40 bg-status-green-bg/40">
              <div className="flex items-center gap-1.5 text-[10.5px] font-medium text-status-green">
                <FileText className="size-3" />
                已生成 PDF
              </div>
              <p className="mt-1 text-[10.5px] text-muted-foreground">{exported} · 3 页 · 含命中快照</p>
            </InsetBlock>
          ) : null}
        </div>
      ) : null}
    </DetailDrawer>
  )
}
