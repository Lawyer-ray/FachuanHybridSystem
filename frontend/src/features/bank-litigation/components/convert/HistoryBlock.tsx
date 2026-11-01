import { useEffect, useState } from 'react'
import { FileUp, RefreshCw } from 'lucide-react'

import { LoadingBlock } from '@/components/shared/AsyncState'
import { EmptyBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'

import { listConvertRecords } from '../../api'
import type { ConvertRecordList } from '../../api'
import { ActionButton, Pill, SectionTitle, WorkCard } from '../ui'
import { DEMO_CONVERT_LOG } from '../demo-data'

// ───────────────────────── 历史记录 ─────────────────────────

export function HistoryBlock({ caseId, onCount }: { caseId: number; onCount?: (n: number) => void }) {
  const [state, setState] = useState<{ loading: boolean; data: ConvertRecordList | null; error: string | null }>({
    loading: true,
    data: null,
    error: null,
  })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true }))
    listConvertRecords()
      .then((d) => alive && setState({ loading: false, data: d, error: null }))
      .catch((e) => alive && setState({ loading: false, data: null, error: errMessage(e, '加载失败') }))
    return () => {
      alive = false
    }
  }, [nonce])

  const items = state.data?.items ?? []
  // 只展示与本案相关的记录：后端记录里带业务标识，没有就展示全部
  const related = items.filter((r) => {
    const anyR = r as unknown as { case_id?: number | null }
    return anyR.case_id == null || anyR.case_id === caseId
  })
  // 后端无记录（或接口不可用）时铺演示记录：空表在这一页是最差的画面，
  // 律师看不到「转过什么」就不敢点转换。演示记录不参与任何判断，只填行。
  const useDemo = !state.loading && related.length === 0
  const rows = useDemo
    ? DEMO_CONVERT_LOG.map((r) => ({
        id: r.id,
        original_name: r.originalName,
        mbid_name: r.typeName,
        created_at: r.at,
        pages: r.pages,
        ms: r.ms,
        ok: r.ok,
      }))
    : related.slice(0, 15).map((r) => {
        const row = r as unknown as {
          id: number
          original_name?: string
          mbid_name?: string
          created_at?: string
        }
        return {
          id: row.id,
          original_name: row.original_name,
          mbid_name: row.mbid_name,
          created_at: (row.created_at ?? '').slice(0, 16).replace('T', ' '),
          pages: null as number | null,
          ms: null as number | null,
          ok: true,
        }
      })
  const rowCount = useDemo ? rows.length : related.length

  // 把条数回传给父级，用于顶部统计格（避免父级再拉一次接口）
  useEffect(() => {
    if (!state.loading && !state.error) onCount?.(rowCount)
  }, [state.loading, state.error, rowCount, onCount])

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle
          title="转换记录"
          hint={useDemo ? `共 ${rowCount} 条 · 样例数据` : `共 ${rowCount} 条 · 最新在上`}
          className="w-full"
          action={
            <ActionButton sm onClick={() => setNonce((n) => n + 1)}>
              <RefreshCw className="size-3" /> 刷新
            </ActionButton>
          }
        />
      </div>

      {state.loading ? (
        <div className="px-5 py-6">
          <LoadingBlock text="加载记录…" size="sm" />
        </div>
      ) : rows.length ? (
        <>
          {state.error ? (
            <p className="border-b border-border-light px-5 py-2 text-[10.5px] text-status-red">
              后端记录读取失败（{state.error}），下面为样例数据。
            </p>
          ) : null}
          <ul className="divide-y divide-border-light">
            {rows.map((row) => (
              <li key={row.id} className="flex items-center gap-3 px-5 py-2.5 text-[11.5px]">
                <FileUp className="size-3.5 flex-none text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate" title={row.original_name}>
                  {row.original_name || `记录 #${row.id}`}
                </span>
                <span className="w-[132px] flex-none truncate text-[11px] text-muted-foreground" title={row.mbid_name}>
                  {row.mbid_name || '—'}
                </span>
                <span className="w-[56px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
                  {row.pages != null ? `${row.pages} 页` : '—'}
                </span>
                <span className="w-[72px] flex-none text-right text-[11px] tabular-nums text-muted-foreground">
                  {row.ms != null ? `${row.ms.toLocaleString('en-US')} ms` : '—'}
                </span>
                <span className="w-[116px] flex-none text-right text-[10.5px] tabular-nums text-muted-foreground">
                  {row.created_at}
                </span>
                <span className="w-[52px] flex-none text-right">
                  <Pill tone={row.ok ? 'green' : 'red'}>{row.ok ? '成功' : '失败'}</Pill>
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="px-5 py-8">
          <EmptyBlock>还没有转换记录。</EmptyBlock>
        </div>
      )}
    </WorkCard>
  )
}
