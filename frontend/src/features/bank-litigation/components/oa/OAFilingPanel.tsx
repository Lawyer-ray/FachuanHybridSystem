/**
 * 律所 OA 立案面板（`OAFilingPanel`）。
 *
 * ═══ 为什么这个面板单独一个文件 ═══
 * 一张网（`CourtFilingPanel`）和 OA 立案挤在同一个 `FilingPanels.tsx` 里时，
 * 文件轻松越过 450 行红线。两个面板除了共用 `SessionResult` 之外没有任何交集，
 * 拆开后各自的展示组件（`oa/*`、`court/*`）也有了明确归属。
 *
 * ═══ 会话形状（与一张网相同）═══
 * 提交 → 后台 Playwright 跑 → 前端轮询 → 终态停。面板必须诚实呈现：
 *   1. 不能假装秒完成 —— 显示轮询次数与后端原始 status；
 *   2. 凭证缺失要前置说 —— 没配凭证点下去必失败，不如点之前就说清；
 *   3. 失败给后端原话 —— 页面改版/验证码这类原因前端不做二次翻译。
 */

import { useState } from 'react'
import { Loader2, Play } from 'lucide-react'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge } from '@/components/shared/status-badge'

import { useOAConfigs } from '../../hooks/use-cases'
import { useOAFiling } from '../../hooks/use-auto-run'
import {
  ActionButton,
  InsetBlock,
  KeyValueRow,
  Pill,
  RailSection,
  SectionTitle,
  StatCell,
  StatStrip,
  StepItem,
  WorkCard,
} from '../ui'
import { DEMO_OA_FILING_LOG, DEMO_OA_HISTORY, DEMO_OA_SITES } from '../demo-data'
import { PHASE_META, SessionResult, pillTone } from '../filing-session'
import { OAFailureCauses } from './OAFailureCauses'
import { OAFieldMapping } from './OAFieldMapping'
import { OAHistoryTable } from './OAHistoryTable'
import { OASiteList, type OASiteListItem } from './OASiteList'

export function OAFilingPanel({
  caseId,
  contractId,
}: {
  caseId: number
  contractId: number | null
}) {
  const configs = useOAConfigs()
  const { state, run, reset } = useOAFiling()
  /* 默认站点不写死站点名：站点名属机构标识，写进代码即泄露。
     从后端 /oa-filing/configs 返回的列表里取第一个（后端 SUPPORTED_SITES 才是权威）。 */
  const [site, setSite] = useState<string>('')

  if (configs.loading) return <LoadingBlock text="正在读取 OA 配置…" size="sm" />
  if (configs.error) {
    return <ErrorBlock error={configs.error} fallback="OA 配置读取失败" onRetry={configs.reload} />
  }

  /* 后端没配站点时不再直接摊一个空面板：演示态下用 DEMO_OA_SITES 撑住画面，
     真实环境里 configs 一定有条目，这条兜底只在接口返回空数组时生效。 */
  const list = configs.data ?? []
  const siteRows: OASiteListItem[] = list.length
    ? list.map((c) => ({
        id: c.id,
        name: c.oa_system_name,
        hasCredential: Boolean(c.has_credential),
      }))
    : DEMO_OA_SITES.map((d, i) => ({ id: -1 - i, name: d.name, hasCredential: d.credential }))

  /* 显式剔除 undefined：`siteRows[0]` 在 `noUncheckedIndexedAccess` 下是 `T | undefined`，
     而两个分支都已保证非空，这里只是把事实告诉类型系统，不改变运行时行为。 */
  const current = siteRows.find((c) => c.name === site) ?? siteRows[0]!
  const canRun =
    Boolean(current.hasCredential) &&
    Boolean(contractId) &&
    state.phase !== 'running'
  const running = state.phase === 'submitting' || state.phase === 'running'

  /* 执行日志里的失败步数 = 需要律师回头处理的事，统计条上直接给药。 */
  const logFailed = DEMO_OA_FILING_LOG.filter((l) => !l.ok).length
  const logMs = DEMO_OA_FILING_LOG.reduce((sum, l) => sum + l.ms, 0)

  return (
    <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
      {/* ══════ 左列 ══════ */}
      <div className="flex min-w-0 flex-col gap-3.5">
        {/* ① 顶部统计：四个数字把「这次能不能立、最近立得怎么样」一次说清 */}
        <StatStrip className="grid-cols-2 md:grid-cols-4">
          <StatCell label="本月立案" value={`${DEMO_OA_SITES.reduce((s, x) => s + x.filedThisMonth, 0)} 件`} />
          <StatCell label="凭证状态" value={current.hasCredential ? '已配置' : '未配置'} tone={current.hasCredential ? 'green' : 'red'} />
          <StatCell label="关联合同" value={contractId ? '已关联' : '未关联'} tone={contractId ? 'green' : 'red'} />
          <StatCell label="日志失败步" value={`${logFailed} 步`} tone={logFailed ? 'yellow' : 'green'} />
        </StatStrip>

        {/* ② 站点清单 + 这一步做什么：并排两张卡，把原先只有一个下拉框的位置铺满 */}
        <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2">
          <OASiteList
            sites={siteRows}
            currentName={current.name}
            onPick={(name) => {
              setSite(name)
              reset()
            }}
          />

          <WorkCard>
            <SectionTitle title="这一步做什么" hint="服务端驱动，不在你的浏览器里跑" />
            <p className="mt-2 text-[11.5px] leading-[1.7] text-muted-foreground">
              在服务端启动浏览器，用你配置的 OA 账号登录并填报收案登记。
              跑完会把所内案号与状态回写到本案；中途关掉页面不影响后台执行。
            </p>
            <InsetBlock className="mt-2.5">
              <dl className="divide-y divide-border-light">
                <KeyValueRow label="执行方式">
                  <span className="text-[12px]">Playwright 浏览器自动化</span>
                </KeyValueRow>
                <KeyValueRow label="单件耗时">
                  <span className="text-[12px] tabular-nums">约 40 s – 2 min</span>
                </KeyValueRow>
                <KeyValueRow label="失败重试">
                  <span className="text-[12px]">凭证类自动重试 1 次</span>
                </KeyValueRow>
                <KeyValueRow label="本次日志耗时">
                  <span className="text-[12px] tabular-nums">{(logMs / 1000).toFixed(1)} s</span>
                </KeyValueRow>
              </dl>
            </InsetBlock>
          </WorkCard>
        </div>

        {/* ③ 动作区 */}
        <WorkCard>
          <div className="flex flex-wrap items-center gap-2">
            <ActionButton dark disabled={!canRun} onClick={() => void run({ site_name: current.name, contract_id: contractId, case_id: caseId })}>
              {running ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
              {running ? 'OA 立案进行中…' : '在 OA 立案'}
            </ActionButton>
            <Pill tone={pillTone(PHASE_META[state.phase].tone)}>
              {PHASE_META[state.phase].text}
            </Pill>
            {state.ticks > 0 && running ? (
              <span className="text-[10.5px] tabular-nums text-muted-foreground">
                已轮询 {state.ticks} 次
              </span>
            ) : null}
            {!contractId ? (
              <StatusBadge tone="red" size="xs">
                案件未关联合同
              </StatusBadge>
            ) : null}
            {!current.hasCredential ? (
              <StatusBadge tone="red" size="xs">
                该站点未配凭证
              </StatusBadge>
            ) : null}
            {!canRun && !running ? (
              <span className="text-[10.5px] text-muted-foreground">
                补齐上述两项后才允许发起
              </span>
            ) : null}
          </div>
          <SessionResult
            error={state.error}
            status={state.status}
            phase={state.phase}
            hint="OA 立案"
          />
        </WorkCard>

        {/* ④ 执行日志：服务端逐步做了什么（真实实现应来自会话进度事件） */}
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle
              title="执行日志"
              hint={`最近一次 · 共 ${DEMO_OA_FILING_LOG.length} 步 · ${logFailed} 次重试`}
              className="w-full"
            />
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_OA_FILING_LOG.map((l) => (
              <li key={`${l.stage}-${l.at}-${l.ms}`} className="flex items-center gap-3 px-5 py-2.5">
                {l.ok ? (
                  <span className="grid size-4 flex-none place-items-center rounded-full bg-status-green">
                    <span className="text-[9px] font-bold text-white">✓</span>
                  </span>
                ) : (
                  <span className="grid size-4 flex-none place-items-center rounded-full bg-status-red">
                    <span className="text-[9px] font-bold text-white">✕</span>
                  </span>
                )}
                <Pill tone={l.ok ? 'neutral' : 'red'}>{l.stage}</Pill>
                <span className="min-w-0 flex-1 truncate text-[11.5px]" title={l.message}>
                  {l.message}
                </span>
                <span className="w-[64px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  {l.ms} ms
                </span>
                <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  {l.at}
                </span>
              </li>
            ))}
          </ul>
        </WorkCard>

        {/* ⑤ 字段映射 / ⑥ 历史立案记录 / ⑦ 失败原因 */}
        <OAFieldMapping />
        <OAHistoryTable />
        <OAFailureCauses />
      </div>

      {/* 右栏：一卡多段（照 deal-detail 的 DetailRail） */}
      <WorkCard padded={false} className="xl:sticky xl:top-3">
        <RailSection title="OA 立案进度">
          <StepItem index={1} title="确认站点凭证" desc={current.hasCredential ? '已配置' : '未配置'}
            state={current.hasCredential ? 'done' : 'blocked'} />
          <StepItem index={2} title="服务端开浏览器" desc="用你的 OA 账号登录" state="todo" />
          <StepItem index={3} title="填写收案登记" desc="案由/委托人/标的额" state="todo" />
          <StepItem index={4} title="回写所内案号" desc="落库到本案" state="todo" />
        </RailSection>

        <RailSection title="本次立案">
          <dl>
            <KeyValueRow label="OA 站点">
              <span className="block truncate text-[12px]">{current.name}</span>
            </KeyValueRow>
            <KeyValueRow label="关联合同">
              <span className="text-[12px]">{contractId ? `#${contractId}` : '未关联'}</span>
            </KeyValueRow>
            <KeyValueRow label="发起人">
              <span className="text-[12px]">主办律师</span>
            </KeyValueRow>
            <KeyValueRow label="所内案号">
              <span className="text-[12px] text-muted-foreground">执行后回填</span>
            </KeyValueRow>
          </dl>
        </RailSection>

        <RailSection title="近期表现">
          <StatStrip className="grid-cols-2">
            <StatCell label="平均耗时" value={DEMO_OA_SITES[0]?.avgMs ?? '—'} />
            <StatCell label="已立案" value={`${DEMO_OA_HISTORY.filter((r) => r.state === 'filed').length} 件`} tone="green" />
          </StatStrip>
          <dl className="mt-2.5">
            <KeyValueRow label="最近成功">
              <span className="text-[12px] tabular-nums">{DEMO_OA_HISTORY[0]?.at ?? '—'}</span>
            </KeyValueRow>
            <KeyValueRow label="最近退回">
              <span className="text-[12px] tabular-nums">
                {DEMO_OA_HISTORY.find((r) => r.state === 'returned')?.at ?? '—'}
              </span>
            </KeyValueRow>
            <KeyValueRow label="待处理失败">
              <span className="text-[12px] tabular-nums">{logFailed} 步</span>
            </KeyValueRow>
          </dl>
        </RailSection>

        <RailSection title="注意">
          <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
            <div className="text-[11px] font-medium">中途关页面不影响执行</div>
            <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              立案在服务端后台跑，关掉页面它照常进行；回来后刷新即可看到结果。
              页面改版、字段校验失败这两类不要反复重试 —— 重试不改源数据，只会锁账号。
            </p>
          </div>
        </RailSection>
      </WorkCard>
    </div>
  )
}
