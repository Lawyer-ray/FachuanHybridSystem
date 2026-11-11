/**
 * ⑤ 回扫 —— 客户寄回、行政扫描、邮箱自动扫到，材料自动归到本案
 *
 * 这一阶段解决的问题：**材料的回流是分散的**（快递、扫描仪、邮箱、微信），
 * 律师不该挨个去找「刚才那份传票放哪了」。系统扫邮箱、认案号、认当事人，
 * 认出来的自动下载并挂到对应案件。
 *
 * 认不准的不硬塞 —— 低于阈值进「待处理」，让人来定。
 *
 * 所以这一屏要能回答四件事：扫的是哪些邮箱、它们怎么配的（能改）；
 * 扫到的邮件里附件长什么样（能预览）；哪些归上了、哪些没归上（能筛）；
 * 没归上的怎么手工挂到案子上去（搜案件 → 选槽位 → 确认）。
 *
 * 本文件只做编排：跨块的页面级状态（打开哪封邮件、哪个邮箱在配、哪封在做手工归案、
 * 标记无关系集合）和两个动作引擎留在这里，各块各自的视图状态收在下层组件。
 */

import { useState } from 'react'

import { DEMO_RETURNED_MAILS, type ScanMailboxConfig } from '../demo-data'
import { StageActionCard } from './StageActionCard'
import { useStageAction } from './use-stage-action'
import { StatCell, StatStrip } from '../ui'
import { claimKindOf } from './returned/claim-kind'
import { ScanMailboxList } from './returned/ScanMailboxList'
import { ScanBatchTable } from './returned/ScanBatchTable'
import { ReturnedDiffTable } from './returned/ReturnedDiffTable'
import { ClaimedMailCard } from './returned/ClaimedMailCard'
import { ReturnedRail } from './returned/ReturnedRail'
import { MailDrawer } from './returned/MailDrawer'
import { MailboxConfigDrawer } from './returned/MailboxConfig'
import { AssignDrawer } from './returned/AssignDrawer'

export function ReturnedPanel() {
  /** 打开着详情的那封邮件 */
  const [mailOpen, setMailOpen] = useState<string | null>(null)
  /** 正在配置的邮箱地址 */
  const [configAddr, setConfigAddr] = useState<string | null>(null)
  /** 已保存的邮箱配置（按地址覆盖默认值） */
  const [mailboxConfig, setMailboxConfig] = useState<Record<string, ScanMailboxConfig>>({})
  /** 正在做手动归案的那封邮件 */
  const [assignSubject, setAssignSubject] = useState<string | null>(null)
  /** 演示：标记为无关的邮件 */
  const [ignored, setIgnored] = useState<Set<string>>(new Set())

  /* 立刻扫一轮邮箱 */
  const scanNow = useStageAction({
    steps: [
      { text: '连接 3 个邮箱', ms: 600, parallel: ['一张网收件箱', '行政扫描仪', '客户往来邮箱'] },
      {
        text: '拉取新到邮件',
        ms: 700,
        retry: { times: 1, delay: 1000, reason: 'IMAP 连接被限流，等待后重试' },
      },
      { text: '下载附件 5 份（18.2 MB）', ms: 1100 },
      { text: '「Re: 谭某某案 补充材料」→ 案号+当事人名匹配 → 归案', ms: 500 },
      { text: '「扫描件-不动产权证」→ 文件名关键词匹配 → 归案', ms: 450 },
      { text: '「（20XX）粤0106民初XXXX号 受理通知书」→ 案号精确匹配 → 回填案号', ms: 550 },
      {
        text: '「FW: 律师函签收回执」→ 匹配度 62%，低于阈值',
        ms: 500,
        confirm: '这封邮件匹配度只有 62%，低于 80% 阈值。要放进「待处理」让人来定，还是按发送人自动归到本案？',
      },
      { text: '重跑缺件检测', ms: 700 },
    ],
    toSummary: () => '3 封自动归案、1 封进待处理；缺件从 5 项降到 3 项',
  })
  /* 对低匹配度的那封手动指定归属 */
  const assignManual = useStageAction({
    steps: [
      { text: '读取待处理邮件附件 1 份', ms: 320 },
      { text: '按发送人「客户 李某某」关联到本案共同借款人', ms: 420 },
      { text: '归入「送达地址确认书」槽位', ms: 340 },
    ],
    toSummary: () => '律师函签收回执已手动归属到本案',
  })

  const rows = DEMO_RETURNED_MAILS.map((m) => (ignored.has(m.subject) ? { ...m, action: '已标记无关' } : m))
  const auto = rows.filter((m) => claimKindOf(m.action) === 'auto')
  const manual = rows.filter((m) => claimKindOf(m.action) === 'manual')
  const attachments = rows.reduce((n, m) => n + m.attachments, 0)

  return (
    <div className="flex flex-col gap-3.5">
      <StageActionCard
        title="扫描邮箱，把新到的材料认领回来"
        desc="客户寄回、行政扫描、法院短信转发都会落到邮箱。系统按案号、当事人名、文件名认案，认出来的自动下载并挂到本案；认不准的进待处理，不硬塞。"
        actionLabel="立即扫描邮箱"
        hint="3 个邮箱 · 约 3 秒"
        state={scanNow}
        execute={() => void scanNow.execute()}
        reset={scanNow.reset}
        confirm={scanNow.confirm}
      />

      <StatStrip className="grid-cols-2 sm:grid-cols-4">
        <StatCell label="扫到邮件" value={`${rows.length} 封`} />
        <StatCell label="附件" value={`${attachments} 份`} />
        <StatCell label="自动归案" value={`${auto.length} 封`} tone="green" />
        <StatCell label="待人工" value={`${manual.length} 封`} tone={manual.length ? 'yellow' : 'green'} />
      </StatStrip>

      <div className="grid grid-cols-1 items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-[18px]">
          {/* 邮箱自动扫描：每行可改配置 */}
          <ScanMailboxList configs={mailboxConfig} onConfigure={setConfigAddr} />

          {/* 行政扫描批次 */}
          <ScanBatchTable />

          {/* 归案前后 */}
          <ReturnedDiffTable />

          {/* 归案结果：可筛选 */}
          <ClaimedMailCard ignored={ignored} onOpenMail={setMailOpen} onAssign={setAssignSubject} />
        </div>

        <ReturnedRail />
      </div>

      <MailDrawer
        subject={mailOpen}
        onClose={() => setMailOpen(null)}
        ignored={ignored}
        onIgnore={(s) => {
          setIgnored((prev) => new Set(prev).add(s))
          setMailOpen(null)
        }}
        onAssign={(s) => {
          setMailOpen(null)
          setAssignSubject(s)
        }}
      />

      <MailboxConfigDrawer
        addr={configAddr}
        saved={mailboxConfig}
        onClose={() => setConfigAddr(null)}
        onSave={(cfg) => {
          setMailboxConfig((prev) => ({ ...prev, [cfg.addr]: cfg }))
          setConfigAddr(null)
        }}
      />

      <AssignDrawer
        subject={assignSubject}
        onClose={() => setAssignSubject(null)}
        assign={assignManual}
      />
    </div>
  )
}
