/**
 * 系统状态三卡片：后端服务 / Django-Q 任务队列 / LLM 网关。
 *
 * 全部只读聚合数据（无任务载荷），律师即可查看。三卡各自独立 useQuery，
 * 任何一张失败不拖垮另两张；「刷新」统一 invalidate settings 前缀。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'
import {
  fetchAgentUsage,
  fetchLlmModels,
  fetchQClusterStatus,
  probeBackend,
  testLlmConnection,
  type QClusterStatus,
} from '../api'

type CardState = 'loading' | 'ok' | 'warn' | 'error' | 'unknown'

const STATE_DOT: Record<CardState, string> = {
  loading: 'bg-muted-foreground/40 animate-pulse',
  ok: 'bg-status-green',
  warn: 'bg-status-yellow',
  error: 'bg-status-red',
  unknown: 'bg-muted-foreground',
}

const STATE_TEXT: Record<CardState, string> = {
  loading: 'text-muted-foreground',
  ok: 'text-status-green',
  warn: 'text-status-yellow',
  error: 'text-status-red',
  unknown: 'text-muted-foreground',
}

function StatusCard({
  title,
  state,
  stateText,
  children,
}: {
  title: string
  state: CardState
  stateText: string
  children?: React.ReactNode
}) {
  return (
    <div className="rounded-xl border bg-card p-[18px]">
      <div className="flex items-center gap-2">
        <span className={`size-2 flex-none rounded-full ${STATE_DOT[state]}`} />
        <span className="text-[13px] font-semibold">{title}</span>
        <span className={`ml-auto text-[11.5px] font-medium ${STATE_TEXT[state]}`}>{stateText}</span>
      </div>
      {children ? <div className="mt-3 space-y-1.5 text-[12px] leading-[1.7] text-muted-foreground">{children}</div> : null}
    </div>
  )
}

/** 行式键值（值右对齐、tabular，多行数据扫一眼就能对上） */
function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span>{label}</span>
      <span className="font-medium tabular-nums text-foreground">{value}</span>
    </div>
  )
}

/** Django-Q 状态判定：心跳数 0=没集群在跑，>1=多棵进程树抢同一队列（僵尸集群） */
function qState(data: QClusterStatus | undefined): { state: CardState; text: string } {
  if (!data) return { state: 'loading', text: '读取中…' }
  if (data.clusters === null) return { state: 'unknown', text: '无法探测' }
  if (data.clusters === 0) return { state: 'error', text: '无集群心跳' }
  if (data.clusters === 1) return { state: 'ok', text: '运行中' }
  return { state: 'warn', text: `疑似僵尸集群 ×${data.clusters}` }
}

function BackendCard() {
  const q = useQuery({ queryKey: ['settings', 'backend-probe'], queryFn: probeBackend })
  if (q.isLoading) {
    return (
      <StatusCard title="后端服务" state="loading" stateText="探测中…">
        <Row label="接口延迟" value="—" />
      </StatusCard>
    )
  }
  if (q.isError) {
    return (
      <StatusCard title="后端服务" state="error" stateText="无法连接">
        <p className="text-status-red">{errMessage(q.error, '请求失败')}</p>
      </StatusCard>
    )
  }
  const ms = q.data ?? 0
  // 局域网正常在两位数；过千说明后端假死或网络异常，黄牌提示但不算不可用
  return (
    <StatusCard title="后端服务" state={ms > 1000 ? 'warn' : 'ok'} stateText={`在线 · ${ms}ms`}>
      <Row label="接口延迟" value={`${ms}ms`} />
    </StatusCard>
  )
}

function QueueCard() {
  const q = useQuery({ queryKey: ['settings', 'q-cluster'], queryFn: fetchQClusterStatus })
  const s = qState(q.data)
  return (
    <StatusCard title="Django-Q 任务队列" state={s.state} stateText={s.text}>
      {q.isError ? (
        <p className="text-status-red">{errMessage(q.error, '读取失败')}</p>
      ) : q.data ? (
        <>
          <Row label="在线集群" value={q.data.clusters === null ? '无法探测' : `${q.data.clusters} 个`} />
          <Row label="排队中" value={`${q.data.queue_depth} 个任务`} />
          <Row label="今日成功 / 失败" value={`${q.data.succeeded_today} / ${q.data.failed_today}`} />
          {q.data.last_success_at ? <Row label="最近成功" value={q.data.last_success_at} /> : null}
          {q.data.clusters === null && q.data.broker_error ? (
            <p className="pt-1 text-[11px] text-muted-foreground/80">redis 探测失败：{q.data.broker_error}</p>
          ) : null}
          {q.data.clusters !== null && q.data.clusters > 1 ? (
            <p className="pt-1 text-[11px] text-status-yellow">
              多棵进程树在抢同一队列，定时任务可能被静默丢弃，请尽快清剿僵尸进程。
            </p>
          ) : null}
        </>
      ) : (
        <Row label="在线集群" value="—" />
      )}
    </StatusCard>
  )
}

function LlmCard() {
  const modelsQuery = useQuery({ queryKey: ['settings', 'llm-models'], queryFn: fetchLlmModels })
  const usageQuery = useQuery({ queryKey: ['settings', 'agent-usage'], queryFn: () => fetchAgentUsage(1) })
  const [modelId, setModelId] = useState('')
  const queryClient = useQueryClient()

  const models = modelsQuery.data ?? []
  const selected = modelId || models[0]?.id || ''

  const testConn = useMutation({
    mutationFn: () => testLlmConnection(selected),
    onSuccess: (res) => {
      if (res.ok) toast.success(`连接成功：${res.model ?? selected}（${res.backend ?? ''}）`)
      else toast.error(res.error || '连接失败')
    },
    onError: (err) => toast.error(errMessage(err, '连接失败')),
  })

  const state: CardState = modelsQuery.isError ? 'error' : modelsQuery.isLoading ? 'loading' : 'ok'
  const stateText = modelsQuery.isError
    ? '网关不可达'
    : modelsQuery.isLoading
      ? '读取中…'
      : `${models.length} 个模型`
  const usage = usageQuery.data

  return (
    <StatusCard title="LLM 网关" state={state} stateText={stateText}>
      {modelsQuery.isError ? (
        <p className="text-status-red">{errMessage(modelsQuery.error, '读取失败')}</p>
      ) : (
        <>
          {usage ? (
            <Row
              label="AI 任务（近 1 天）"
              value={`${usage.runs} 次 · 成功率 ${Math.round((1 - usage.error_rate) * 100)}%`}
            />
          ) : null}
          {usage && usage.runs > 0 ? (
            <Row label="平均耗时" value={`${(usage.avg_duration_ms / 1000).toFixed(1)}s`} />
          ) : null}
          <div className="flex items-center gap-2 pt-1.5">
            <select
              value={selected}
              onChange={(e) => setModelId(e.target.value)}
              disabled={models.length === 0}
              className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-[12px] outline-none disabled:opacity-50"
              aria-label="选择测试模型"
            >
              {models.length === 0 ? <option value="">（无可用模型）</option> : null}
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={testConn.isPending || !selected}
              onClick={() => testConn.mutate()}
            >
              {testConn.isPending ? <Loader2 className="size-3.5 animate-spin" /> : null}
              测试连接
            </Button>
          </div>
          {testConn.data ? (
            <p className={`text-[11.5px] ${testConn.data.ok ? 'text-status-green' : 'text-status-red'}`}>
              {testConn.data.ok
                ? `连接成功：${testConn.data.model ?? ''}（${testConn.data.backend ?? ''}）`
                : testConn.data.error || '连接失败'}
            </p>
          ) : null}
        </>
      )}
      {/* 模型列表变化（如刚配好网关）时刷新整组状态 */}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="mt-1 h-7 px-2 text-[11.5px]"
        onClick={() => void queryClient.invalidateQueries({ queryKey: ['settings'] })}
      >
        <RefreshCw className="size-3" />
        刷新
      </Button>
    </StatusCard>
  )
}

export function SystemStatus() {
  return (
    <div className="grid grid-cols-1 gap-[14px] @min-[560px]:grid-cols-2 @min-[900px]:grid-cols-3">
      <BackendCard />
      <QueueCard />
      {/* 第三张卡在中间档（两列 560–899）跨满整行，避免孤卡片参差 */}
      <div className="@min-[560px]:@max-[899px]:col-span-2">
        <LlmCard />
      </div>
    </div>
  )
}
