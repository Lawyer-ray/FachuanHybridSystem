import { useState } from 'react'
import { AlertTriangle, Archive, CheckCircle2, Loader2, Search, Stamp } from 'lucide-react'

import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'
import { KeyValueRow, Pill, RailSection, SectionTitle, StatCell, StatStrip, StepItem, WorkCard } from './ui'
import { DEMO_OA_SEAL_RULES, DEMO_OA_SEALS, DEMO_STAMP_BATCHES, DEMO_STAMP_FAILURES, DEMO_STAMP_HISTORY } from './demo-data'
import { cn } from '@/lib/utils'

import { lookupArchiveContract, lookupStampContract, type ArchiveLookupOut, type StampLookupOut } from '../api'
import { useOAArchive, useOAStamp, type AutoPhase } from '../hooks/use-auto-run'

/**
 * OA 盖章 / 归档面板。
 *
 * ═══ 为什么这两个合成一个面板 ═══
 * 它们的流程形状完全相同：
 *   填文件路径 → 反查合同（确认系统认得出这份文件属于哪件）→ 提交 → 轮询
 * 差别只在调哪个 apply。分成两个面板会让「反查」这套逻辑写两遍，
 * 而反查正是最容易出错的一步（路径不在绑定目录里就 404）。
 *
 * ═══ 为什么必须先反查，而不是直接提交 ═══
 * 这两个动作的入参是 **file_path**，后端按文件所在目录找文件夹绑定、
 * 再由绑定找合同。路径不对时 apply 会失败在一个很晚的阶段（OA 已经动了），
 * 而 lookup 是纯查询、无副作用，先用它确认「认得出来」再提交。
 * 这就是「先验证再执行」。
 */

type Kind = 'stamp' | 'archive'

const META: Record<
  Kind,
  { title: string; verb: string; icon: typeof Stamp; hint: string; lookup: (p: string) => Promise<StampLookupOut | ArchiveLookupOut> }
> = {
  stamp: {
    title: 'OA 盖章',
    verb: '申请盖章',
    icon: Stamp,
    hint: '对已绑定文件夹里的文件发起盖章。系统按文件路径反查合同，再到 OA 里走盖章流程。',
    lookup: (p) => lookupStampContract({ file_path: p, site_name: '' }),
  },
  archive: {
    title: 'OA 归档',
    verb: '提交归档',
    icon: Archive,
    hint: '把结案材料提交到 OA 归档。可以一次填多个路径（每行一个）。',
    lookup: (p) => lookupArchiveContract({ file_paths: [p], site_name: '' }),
  },
}

export function OAStampPanel({ siteName }: { siteName?: string }) {
  return <OAActionPanel kind="stamp" siteName={siteName} />
}

export function OAArchivePanel({ siteName }: { siteName?: string }) {
  return <OAActionPanel kind="archive" siteName={siteName} />
}

function OAActionPanel({ kind, siteName }: { kind: Kind; siteName?: string }) {
  const meta = META[kind]
  const Icon = meta.icon

  const [paths, setPaths] = useState('')
  const [looking, setLooking] = useState(false)
  const [lookupErr, setLookupErr] = useState<string | null>(null)
  const [found, setFound] = useState<StampLookupOut | ArchiveLookupOut | null>(null)

  // 会话形状显式收成最小交集：StampSessionOut 与 ArchiveSessionOut 都有
  // id/status/error_message，只声明用得到的字段，避免在条件分支里退化成 any。
  // hook 定义在 use-auto-run.ts 里（与 useOAFiling 放一起）：
  // 跨文件调用 useAutoRun 的泛型时，typescript-eslint 解析不出类型，
  // 整条 state.xxx 都退化成 any 并报 unsafe。所以在 hook 文件里封好再用。
  const stampRun = useOAStamp(siteName)
  const archiveRun = useOAArchive(siteName)
  const { state, run, reset } = kind === 'stamp' ? stampRun : archiveRun

  const running = state.phase === 'submitting' || state.phase === 'running'
  const list = paths
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean)

  async function onLookup() {
    if (!list.length) return
    // `list` 已 filter 掉空行，但 `list[0]` 在 noUncheckedIndexedAccess 下仍是 T | undefined；
    // 上面已 return 掉空数组，这里把非空事实告诉类型系统。
    const target = list[0]!
    setLooking(true)
    setLookupErr(null)
    setFound(null)
    reset()
    try {
      const r = await meta.lookup(target)
      setFound(r)
    } catch (e) {
      setLookupErr(errMessage(e, 'OA 凭证查询失败'))
    } finally {
      setLooking(false)
    }
  }

  return (
    <div className="flex flex-col gap-3.5">
      <StatStrip className="grid-cols-3">
        <StatCell label="文件路径" value={list.length ? `${list.length} 个` : '未填'} tone={list.length ? 'neutral' : 'yellow'} />
        <StatCell label="合同归属" value={found ? '已确认' : '未反查'} tone={found ? 'green' : 'neutral'} />
        <StatCell label="可执行" value={found ? '是' : '否'} tone={found ? 'green' : 'yellow'} />
      </StatStrip>

    <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex min-w-0 flex-col gap-3.5">
      {/* ══ ① 说明卡 ══ */}
      <WorkCard>
        <SectionTitle title={meta.title} hint={meta.hint} />
      </WorkCard>

      {/* ══ ② 输入卡 ══ */}
      <WorkCard>
        <SectionTitle
          title="文件路径"
          hint={kind === 'archive' ? '每行一个，可一次归档多份' : '填一份文件的绝对路径'}
        />
        <textarea
          value={paths}
          onChange={(e) => {
            setPaths(e.target.value)
            setFound(null)
            setLookupErr(null)
            reset()
          }}
          rows={kind === 'archive' ? 4 : 2}
          placeholder={
            kind === 'archive'
              ? '文件绝对路径，每行一个\n例：/Users/xxx/案件/某某案/判决书.pdf'
              : '文件绝对路径\n例：/Users/xxx/案件/某某案/起诉状.pdf'
          }
          className="mt-2 w-full resize-y rounded-[7px] border border-input bg-background px-2.5 py-2 font-mono text-[11.5px] leading-[1.6] outline-none focus:border-ring/60"
        />

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" disabled={!list.length || looking || running} onClick={() => void onLookup()}>
            {looking ? <Loader2 className="size-3.5 animate-spin" /> : <Search className="size-3.5" />}
            反查合同
          </Button>
          <Button
            size="sm"
            disabled={!found || running}
            onClick={() => void run(list)}
            title={found ? '' : '先反查出合同再提交'}
          >
            {running ? <Loader2 className="size-3.5 animate-spin" /> : <Icon className="size-3.5" />}
            {running ? '执行中…' : meta.verb}
          </Button>
          <PhaseBadge phase={state.phase} ticks={state.ticks} />
          {!found && list.length > 0 && !running ? (
            <span className="text-[10.5px] text-muted-foreground">先「反查合同」，确认归属后才允许{meta.verb}</span>
          ) : null}
        </div>
      </WorkCard>

      {lookupErr ? (
        <div className="rounded-[10px] border border-status-red/40 bg-status-red-bg px-3.5 py-3">
          <div className="flex items-center gap-1.5 text-[12px] font-medium text-status-red">
            <AlertTriangle className="size-3.5 flex-none" /> 反查失败
          </div>
          <p className="mt-1 text-[11.5px] leading-[1.6] text-status-red/90">{lookupErr}</p>
          <p className="mt-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
            常见原因：文件不在已绑定的案件/合同文件夹里；路径写错；或这份文件不属于你的案件。
          </p>
        </div>
      ) : null}

      {found ? (
        <WorkCard className="border-status-green/40 bg-status-green-bg/50">
          <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-status-green">
            <CheckCircle2 className="size-3.5" /> 已识别到合同
          </div>
          <dl className="mt-2 grid grid-cols-1 gap-x-6 md:grid-cols-2">
            <div className="divide-y divide-border/60">
              <KeyValueRow label="合同">
                <span className="block truncate" title={found.contract_name ?? ''}>
                  {found.contract_name || '—'}
                </span>
              </KeyValueRow>
              <KeyValueRow label="OA 案号">
                <span className="block truncate" title={found.oa_case_number ?? ''}>
                  {found.oa_case_number || '（OA 尚未生成案号）'}
                </span>
              </KeyValueRow>
            </div>
          </dl>
        </WorkCard>
      ) : null}

      {/* ══ 盖章流程（说明这张页在干什么）══ */}
      {kind === 'stamp' ? (
        <WorkCard>
          <SectionTitle title="盖章流程" hint="系统按文件路径反查合同，再到 OA 里走盖章" />
          <div className="mt-3 grid grid-cols-1 gap-x-8 gap-y-0 md:grid-cols-2">
            <StepItem index={1} title="填文件绝对路径" desc="文件须在已绑定的文件夹里" state="current" />
            <StepItem index={2} title="反查归属合同" desc="按路径匹配，确认属于哪份委托" state="todo" />
            <StepItem index={3} title="校验文件与印章" desc="格式、版本、骑缝位置三处校验" state="todo" />
            <StepItem index={4} title="OA 执行盖章" desc="服务端驱动，完成后回写状态" state="todo" />
          </div>
        </WorkCard>
      ) : null}

      {/* ══ 批量盖章预设 ══ */}
      {kind === 'stamp' ? (
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle title="批量盖章预设" hint="一次盖齐一整套材料" className="w-full" />
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_STAMP_BATCHES.map((b) => (
              <li key={b.name} className="flex items-start gap-3 px-5 py-2.5">
                <span className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-medium">{b.name}</span>
                    <Pill tone="blue">{b.seals}</Pill>
                    <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
                      {b.docs} 份 · {b.pages} 页
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10.5px] text-muted-foreground">{b.note}</div>
                </span>
              </li>
            ))}
          </ul>
        </WorkCard>
      ) : null}

      {/* ══ 印章库 ══ */}
      {kind === 'stamp' ? (
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle title="可用印章" hint={`${DEMO_OA_SEALS.filter((x) => x.status === 'available').length} 枚可用`} className="w-full" />
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_OA_SEALS.map((x) => (
              <li key={x.name} className="flex items-center gap-3 px-5 py-2.5">
                <span className="min-w-0 flex-1 truncate text-[12px]" title={x.name}>{x.name}</span>
                <Pill>{x.kind}</Pill>
                <span className="w-[60px] flex-none text-[11px] text-muted-foreground">{x.holder}</span>
                <Pill tone={x.status === 'available' ? 'green' : x.status === 'in-use' ? 'yellow' : 'red'}>
                  {x.status === 'available' ? '可用' : x.status === 'in-use' ? '使用中' : '已停用'}
                </Pill>
                <span className="w-[52px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
                  {x.usedThisMonth} 次
                </span>
                <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  {x.lastUsed}
                </span>
              </li>
            ))}
          </ul>
        </WorkCard>
      ) : null}

      {/* ══ 盖章位置规则 ══ */}
      {kind === 'stamp' ? (
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle title="盖章位置规则" hint="哪类文书盖哪些章、盖在哪" className="w-full" />
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_OA_SEAL_RULES.map((r) => (
              <li key={r.docType} className="px-5 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-medium">{r.docType}</span>
                  <Pill tone="blue">{r.seals}</Pill>
                  <span className="ml-auto text-[11px] text-muted-foreground">{r.position}</span>
                </div>
                <div className="mt-0.5 text-[10.5px] text-muted-foreground">{r.note}</div>
              </li>
            ))}
          </ul>
        </WorkCard>
      ) : null}

      {/* ══ 盖章历史 ══ */}
      {kind === 'stamp' ? (
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle title="盖章记录" hint={`最近 ${DEMO_STAMP_HISTORY.length} 次`} className="w-full" />
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_STAMP_HISTORY.map((r) => (
              <li key={r.fileName + r.at} className="flex items-center gap-3 px-5 py-2.5">
                <span
                  className={
                    r.ok
                      ? 'grid size-4 flex-none place-items-center rounded-full bg-status-green'
                      : 'grid size-4 flex-none place-items-center rounded-full bg-status-red'
                  }
                >
                  <span className="text-[9px] font-bold text-white">{r.ok ? '✓' : '✕'}</span>
                </span>
                <span className="min-w-0 flex-1 truncate text-[12px]" title={r.fileName}>{r.fileName}</span>
                <Pill>{r.page}</Pill>
                {r.ok ? (
                  <Pill tone="green">已盖章</Pill>
                ) : (
                  <span className="max-w-[180px] truncate text-[10.5px] text-status-red" title={r.reason}>
                    {r.reason}
                  </span>
                )}
                <span className="w-[64px] flex-none text-right text-[10.5px] text-muted-foreground">{r.by}</span>
                <span className="w-[82px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">{r.at}</span>
              </li>
            ))}
          </ul>
        </WorkCard>
      ) : null}

      {/* ══ 常见失败原因 ══ */}
      {kind === 'stamp' ? (
        <WorkCard padded={false}>
          <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
            <SectionTitle title="常见失败原因" hint="近 30 天" className="w-full" />
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_STAMP_FAILURES.map((f) => (
              <li key={f.cause} className="px-5 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-medium">{f.cause}</span>
                  <Pill>{f.stage}</Pill>
                  <Pill tone={f.autoRetry ? 'green' : 'yellow'}>{f.autoRetry ? '自动重试' : '需人工'}</Pill>
                  <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">{f.last30} 次</span>
                </div>
                <div className="mt-0.5 text-[10.5px] text-muted-foreground">{f.advice}</div>
              </li>
            ))}
          </ul>
        </WorkCard>
      ) : null}

      {state.status || state.error ? (
        <div className="rounded-[6px] border border-border bg-secondary/30 px-2.5 py-1.5 text-[11.5px]">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">会话状态</span>
            <StatusBadge tone={sessionTone(state.status)} size="xs">
              {state.status || '（未返回）'}
            </StatusBadge>
          </div>
          {state.error ? (
            <p className="mt-1 leading-[1.6] text-status-red">{state.error}</p>
          ) : null}
          {state.phase === 'timeout' ? (
            <p className="mt-1 leading-[1.6] text-status-yellow">
              等待超过 15 分钟仍未结束。任务可能仍在后台运行，请到 OA 里确认结果，不要重复提交。
            </p>
          ) : null}
        </div>
      ) : null}
      </div>

      {/* 右栏：一卡多段（照 deal-detail 的 DetailRail） */}
      <WorkCard padded={false} className="xl:sticky xl:top-3">
        <RailSection title="怎么用">
          <StepItem index={1} title="填文件绝对路径" desc="在已绑定的文件夹里" state="current" />
          <StepItem index={2} title="反查合同" desc="按路径找到归属合同" state="todo" />
          <StepItem index={3} title={meta.verb} desc="服务端在 OA 里执行" state="todo" />
        </RailSection>

        <RailSection title="目标文件">
          <dl>
            <KeyValueRow label="所属合同">
              <span className="block truncate text-[12px]" title={found?.contract_name ?? ''}>
                {found?.contract_name || '未反查'}
              </span>
            </KeyValueRow>
            <KeyValueRow label="OA 案号">
              <span className="block truncate text-[12px] text-muted-foreground">
                {found?.oa_case_number || '—'}
              </span>
            </KeyValueRow>
            <KeyValueRow label="文件数">
              <span className="text-[12px] tabular-nums">{list.length || 0}</span>
            </KeyValueRow>
          </dl>
        </RailSection>

        <RailSection title="注意">
          <div className="rounded-[8px] border border-status-yellow/40 bg-status-yellow-bg/60 px-2.5 py-2">
            <div className="text-[11px] font-medium">必须先反查</div>
            <p className="mt-0.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              反查确认文件属于哪份合同后，{meta.verb}才会启用 —— 避免把 A 案的文件盖到 B 案上。
            </p>
          </div>
        </RailSection>
      </WorkCard>
    </div>
    </div>
  )
}

function PhaseBadge({ phase, ticks }: { phase: AutoPhase; ticks: number }) {
  if (phase === 'idle') return null
  const map: Record<AutoPhase, { tone: 'neutral' | 'blue' | 'green' | 'red' | 'yellow'; text: string }> = {
    idle: { tone: 'neutral', text: '待启动' },
    submitting: { tone: 'blue', text: '提交中' },
    running: { tone: 'blue', text: '执行中' },
    done: { tone: 'neutral', text: '已结束' },
    timeout: { tone: 'yellow', text: '超时' },
  }
  const m = map[phase]
  return (
    <>
      <StatusBadge tone={m.tone} size="xs">
        {m.text}
      </StatusBadge>
      {ticks > 0 && (phase === 'running' || phase === 'submitting') ? (
        <span className={cn('text-[10.5px] tabular-nums text-muted-foreground')}>已轮询 {ticks} 次</span>
      ) : null}
    </>
  )
}

function sessionTone(status: string): 'neutral' | 'blue' | 'green' | 'red' {
  const s = (status || '').toLowerCase()
  if (s === 'success' || s === 'finished' || s === 'completed') return 'green'
  if (s === 'failed' || s === 'error') return 'red'
  if (s === 'running' || s === 'pending' || s === 'processing' || s === 'in_progress') return 'blue'
  return 'neutral'
}
