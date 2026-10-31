import { useState } from 'react'
import { AlertTriangle, ExternalLink, Loader2, Play } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useCaseFilingInfo, useOAConfigs } from '../hooks/use-cases'
import { useCourtFiling, useOAFiling } from '../hooks/use-auto-run'
import type { AutoPhase } from '../hooks/use-auto-run'
import type { FilingEngine, FilingType } from '../types'

/**
 * 立案执行面板 —— 律所 OA 与一张网两个外部系统的入口。
 *
 * ═══ 这两条链路的共同形状 ═══
 * 提交 → 后台线程跑浏览器自动化（Playwright）→ 前端轮询会话状态 → 终态停。
 * 所以界面上必须诚实呈现三件事：
 *   1. **不能假装秒完成**：真实跑一次要开页面、填表单、传附件，几十秒到几分钟。
 *      面板上显示轮询次数与原始 status，让律师知道「确实在跑」而不是卡住。
 *   2. **凭证缺失要前置说**：OA 没配凭证、一张网没法院账号，点下去也是必失败，
 *      不如点之前就说清。这就是 `has_credential` / `has_court_credential` 的用途。
 *   3. **失败要把后端原话给人看**：自动化失败的原因（页面改版、验证码、法院退回）
 *      只有后端的 error_message 说得清，前端不做二次翻译。
 */

/** 轮询阶段 → 语气与文案 */
const PHASE_META: Record<AutoPhase, { tone: Tone; text: string }> = {
  idle: { tone: 'neutral', text: '待启动' },
  submitting: { tone: 'blue', text: '正在提交' },
  running: { tone: 'blue', text: '执行中' },
  done: { tone: 'neutral', text: '已结束' },
  timeout: { tone: 'yellow', text: '等待超时' },
}

/** 会话状态 → 语气。后端 status 字符串大小写/取值不完全统一，按语义归类。 */
function sessionTone(status: string): Tone {
  const s = (status || '').toLowerCase()
  if (s === 'success' || s === 'finished' || s === 'completed') return 'green'
  if (s === 'failed' || s === 'error') return 'red'
  if (s === 'running' || s === 'pending' || s === 'processing') return 'blue'
  return 'neutral'
}

// ───────────────────────── 律所 OA ─────────────────────────

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

  const list = configs.data ?? []
  if (!list.length) {
    return (
      <EmptyBlock icon={<AlertTriangle className="size-5" />}>
        系统未配置任何 OA 站点。
      </EmptyBlock>
    )
  }

  /* 显式剔除 undefined：`list[0]` 在 `noUncheckedIndexedAccess` 下是 `T | undefined`，
     而上面已保证 `list.length > 0`，这里只是把事实告诉类型系统，不改变运行时行为。 */
  const current = list.find((c) => c.oa_system_name === site) ?? list[0]!
  const canRun =
    Boolean(current.has_credential) &&
    Boolean(contractId) &&
    state.phase !== 'running'
  const running = state.phase === 'submitting' || state.phase === 'running'

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <select
          value={current.oa_system_name}
          onChange={(e) => {
            setSite(e.target.value)
            reset()
          }}
          className="h-[28px] rounded-[6px] border border-input bg-background px-2 text-[12px] outline-none"
        >
          {list.map((c) => (
            <option key={c.id} value={c.oa_system_name}>
              {c.oa_system_name}
            </option>
          ))}
        </select>
        <StatusBadge tone={current.has_credential ? 'green' : 'red'} size="xs">
          {current.has_credential ? '已配凭证' : '未配凭证'}
        </StatusBadge>
        {!contractId ? (
          <StatusBadge tone="red" size="xs">
            案件未关联合同
          </StatusBadge>
        ) : null}
      </div>

      <p className="text-[11px] leading-[1.65] text-muted-foreground">
        OA 立案会在服务端启动浏览器，用你配置的 OA 账号登录并填报。跑完会回写 OA
        案号与状态；中途关掉页面不影响后台执行。
      </p>

      <div className="flex items-center gap-2">
        <Button size="xs" disabled={!canRun} onClick={() => void run({ site_name: current.oa_system_name, contract_id: contractId, case_id: caseId })}>
          {running ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
          {running ? 'OA 立案进行中…' : '在 OA 立案'}
        </Button>
        <StatusBadge tone={PHASE_META[state.phase].tone} size="xs">
          {PHASE_META[state.phase].text}
        </StatusBadge>
        {state.ticks > 0 && running ? (
          <span className="text-[10.5px] tabular-nums text-muted-foreground">
            已轮询 {state.ticks} 次
          </span>
        ) : null}
      </div>

      <SessionResult
        error={state.error}
        status={state.status}
        phase={state.phase}
        hint="OA 立案"
      />
    </div>
  )
}

// ───────────────────────── 一张网 ─────────────────────────

export function CourtFilingPanel({ caseId }: { caseId: number }) {
  const info = useCaseFilingInfo(caseId)
  const { state, run, reset } = useCourtFiling()

  /* 立案类型与引擎：后端会给一个建议值（suggested_filing_type / default_filing_engine），
     但那只是建议 —— 同一件案子可能先起诉后执行，也可能法院插件没装只能走浏览器。
     所以两个都给用户可改，默认用后端建议。
     ⚠️ 必须用「用户改过没有」来兜：直接 `useState(info.data?.xxx)` 时，
     首次渲染 data 还是 null，值会被永久钉在 fallback 上（后端建议形同虚设）。 */
  const [typeOverride, setTypeOverride] = useState<FilingType | null>(null)
  const [engineOverride, setEngineOverride] = useState<FilingEngine | null>(null)

  if (info.loading) return <LoadingBlock text="正在读取立案信息…" size="sm" />
  if (info.error) {
    return <ErrorBlock error={info.error} fallback="立案信息读取失败" onRetry={info.reload} />
  }

  const i = info.data
  if (!i) return <EmptyBlock>没有可用的立案信息。</EmptyBlock>

  const filingType: FilingType = typeOverride ?? ((i.suggested_filing_type as FilingType) || 'civil')
  const filingEngine: FilingEngine = engineOverride ?? ((i.default_filing_engine as FilingEngine) || 'api')

  const running = state.phase === 'submitting' || state.phase === 'running'
  const blockers: string[] = []
  if (!i.has_court_credential) blockers.push('未配置一张网（法院）账号')
  if (!i.plugin_available) blockers.push('法院立案插件未安装')
  if (!i.our_party_is_plaintiff_side) blockers.push('我方不是原告方，本页只处理起诉立案')
  if (!i.court_name) blockers.push('未登记管辖法院')
  // 执行立案的前提是有生效裁判文书。后端会在执行时才校验，
  // 但那时会话已建、浏览器已开，失败得很晚。这里前置提示。
  //
  // 判定口径：本案当前阶段已经是执行（说明已经走到这一步），或者
  // 案件已有登记案号（有一审判决才会立案号）。两者都没有才提示。
  if (filingType === 'execution') {
    const alreadyExecution = /执行|enforcement/i.test(i.case_name) || i.court_name != null
    if (!alreadyExecution) {
      blockers.push('执行立案需先有生效裁判文书（本案尚未登记案号）')
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-1 text-[12px] leading-[1.65]">
        <dt className="text-muted-foreground">案由</dt>
        <dd className="min-w-0 truncate">{i.cause_of_action || '—'}</dd>
        <dt className="text-muted-foreground">管辖法院</dt>
        <dd className="min-w-0 truncate">{i.court_name || '（未登记）'}</dd>
        <dt className="text-muted-foreground">原告</dt>
        <dd className="min-w-0 truncate">{i.plaintiff_name || '—'}</dd>
        <dt className="text-muted-foreground">被告</dt>
        <dd className="min-w-0 truncate">{i.defendant_name || '—'}</dd>
        <dt className="text-muted-foreground">标的额</dt>
        <dd className="tabular-nums">{i.target_amount ? `¥${i.target_amount}` : '—'}</dd>
        <dt className="text-muted-foreground">立案类型</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <select
            value={filingType}
            onChange={(e) => setTypeOverride(e.target.value as FilingType)}
            disabled={running}
            className="h-[24px] rounded-[5px] border border-input bg-background px-1.5 text-[11.5px] outline-none disabled:opacity-60"
          >
            <option value="civil">民事一审</option>
            <option value="execution">执行立案</option>
          </select>
          <select
            value={filingEngine}
            onChange={(e) => setEngineOverride(e.target.value as FilingEngine)}
            disabled={running}
            className="h-[24px] rounded-[5px] border border-input bg-background px-1.5 text-[11.5px] outline-none disabled:opacity-60"
          >
            <option value="api">接口引擎</option>
            <option value="playwright">浏览器自动化</option>
          </select>
          {i.suggested_filing_type !== filingType ? (
            <span className="text-[10.5px] text-status-yellow">
              已改为「{filingType === 'execution' ? '执行立案' : '民事一审'}」，后端建议是「
              {i.suggested_filing_type === 'execution' ? '执行立案' : '民事一审'}」
            </span>
          ) : null}
        </dd>
      </dl>

      {blockers.length ? (
        <ul className="flex flex-col gap-1 rounded-[7px] border border-status-red/40 bg-status-red-bg px-2.5 py-1.5">
          {blockers.map((b) => (
            <li key={b} className="flex items-start gap-1.5 text-[11.5px] text-status-red">
              <AlertTriangle className="mt-[2px] size-3 flex-none" />
              {b}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="text-[11px] leading-[1.65] text-muted-foreground">
        填报与推送由服务端驱动一张网。**提交前请律师自己核对表单** ——
        机器填到头，送出去那一下必须人点。
      </p>

      <div className="flex items-center gap-2">
        <Button
          size="xs"
          disabled={blockers.length > 0 || running}
          onClick={() => {
            reset()
            void run({ case_id: caseId, filing_type: filingType, filing_engine: filingEngine })
          }}
        >
          {running ? <Loader2 className="size-3 animate-spin" /> : <ExternalLink className="size-3" />}
          {running ? '一张网立案进行中…' : '推送到一张网'}
        </Button>
        <StatusBadge tone={PHASE_META[state.phase].tone} size="xs">
          {PHASE_META[state.phase].text}
        </StatusBadge>
        {state.ticks > 0 && running ? (
          <span className="text-[10.5px] tabular-nums text-muted-foreground">
            已轮询 {state.ticks} 次
          </span>
        ) : null}
      </div>

      <SessionResult error={state.error} status={state.status} phase={state.phase} hint="一张网立案" />
    </div>
  )
}

// ───────────────────────── 会话结果 ─────────────────────────

/**
 * 会话结果块。三个面板共用：
 * 失败原因（error）、后端原始 status、超时提醒，是同一套呈现。
 */
function SessionResult({
  error,
  status,
  phase,
  hint,
}: {
  error: string | null
  status: string
  phase: AutoPhase
  hint: string
}) {
  if (phase === 'idle') return null

  return (
    <div className="rounded-[7px] border border-border bg-secondary/30 px-2.5 py-1.5">
      <div className="flex items-center gap-2 text-[11.5px]">
        <span className="text-muted-foreground">会话状态</span>
        <StatusBadge tone={sessionTone(status)} size="xs">
          {status || '（未返回）'}
        </StatusBadge>
      </div>
      {error ? (
        <p className="mt-1 text-[11.5px] leading-[1.6] text-status-red">
          {hint}失败：{error}
        </p>
      ) : null}
      {phase === 'timeout' ? (
        <p className={cn('mt-1 text-[11.5px] leading-[1.6] text-status-yellow')}>
          等待超过 15 分钟仍未结束。任务可能仍在后台运行 —— 稍后回本页刷新查看，
          或到 OA / 一张网里确认实际结果，不要重复提交。
        </p>
      ) : null}
    </div>
  )
}
