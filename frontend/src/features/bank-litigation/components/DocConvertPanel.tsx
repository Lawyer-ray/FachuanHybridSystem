import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Download, FileUp, Loader2, RefreshCw } from 'lucide-react'

import { EmptyBlock, ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'

import { convertToElemental, listConvertRecords, listMbidTypes } from '../api'
import { useCase } from '../hooks/use-cases'
import { suggestMbid } from '../utils'
import { SectionTitle, WorkCard } from './ui'
import type { ConvertRecordList, MbidList } from '../api'

/**
 * 要素式转换面板 —— 传统起诉状 → 法院要素式示范文本。
 *
 * ═══ 这个功能的关键认知 ═══
 * 转换**完全在后端**：前端只上传文件 + 选文书类型（mbid），后端生成 docx 回传。
 * 所以这一页不做任何「字段搬运」—— 字段解析、法条对应、格式规整都在服务端 service 里。
 * 早先原型里曾在前端按映射表重组字段，那是假转换：改了后端前端还在按老规则拼，
 * 两边各说各话，而且律师拿到手的 docx 与系统里看到的根本不是同一份。
 *
 * ═══ 响应是二进制，不是 JSON ═══
 * 见 api/index.ts 的 convertToElemental 注释。这里负责把 blob 存下来。
 */

export function DocConvertPanel({ caseId }: { caseId: number }) {
  const types = useTypeList()
  const kase = useCase(caseId)
  // 按案由自动匹配文书类型，律师可改。猜错不致命 —— 下拉框里永远能改。
  const [mbid, setMbid] = useState(() => suggestMbid(kase.data?.cause_of_action))
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  if (types.loading) return <LoadingBlock text="正在读取文书类型…" size="sm" />
  if (types.error) {
    return <ErrorBlock error={types.error} fallback="文书类型读取失败" onRetry={types.reload} />
  }

  const filingTypes = (types.data?.categories ?? []).filter((c) => c.category === '起诉状')
  const options = filingTypes.length ? filingTypes : (types.data?.categories ?? [])

  const onConvert = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      const blob = await convertToElemental(file, mbid)
      // 文件名：原文件名去扩展 + 「要素式」
      const base = file.name.replace(/\.(docx?|pdf)$/i, '')
      saveBlob(blob, `要素式-${base}.docx`)
      setDone(`已生成并下载：要素式-${base}.docx（${fmtSize(blob.size)}）`)
    } catch (e) {
      setError(errMessage(e, '请求失败'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3.5">
      {/* ══ ① 转换操作卡：步骤化（选类型 → 选文件 → 转换），每步带序号 ══ */}
      <WorkCard>
        <SectionTitle title="转换要素式文书" hint="传统起诉状 → 法院要素式示范文本" />

        {/* 第 1 步 */}
        <div className="mt-3 flex items-start gap-2.5">
          <span className="mt-[3px] flex size-4 flex-none items-center justify-center rounded-full bg-secondary text-[10px] font-semibold text-muted-foreground">
            1
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] text-muted-foreground">选文书类型（按案由已自动匹配，可改）</div>
        <div className="mt-1 flex items-center gap-2">
          <select
            value={mbid}
            onChange={(e) => setMbid(e.target.value)}
            className="h-[30px] min-w-0 flex-1 rounded-[6px] border border-input bg-background px-2 text-[12px] outline-none"
          >
            {options.map((g) => (
              <optgroup key={g.category} label={g.category}>
                {g.items.map((it) => (
                  <option key={it.mbid} value={it.mbid}>
                    {it.name}（{it.mbid}）
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
          </div>
        </div>

        {/* 第 2 步 */}
        <div className="mt-3 flex items-start gap-2.5">
          <span className="mt-[3px] flex size-4 flex-none items-center justify-center rounded-full bg-secondary text-[10px] font-semibold text-muted-foreground">
            2
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] text-muted-foreground">选一份传统起诉状</div>
            <input
              ref={inputRef}
              type="file"
              accept=".docx,.doc,.pdf"
              hidden
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setDone(null)
                setError(null)
              }}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-1 flex h-[34px] w-full items-center gap-2 rounded-[7px] border border-dashed border-zinc-300 px-2.5 text-left text-[11.5px] text-muted-foreground transition-colors hover:border-foreground hover:text-foreground"
            >
              <FileUp className="size-3.5 flex-none" />
              <span className="truncate">{file ? file.name : '选择 .docx / .doc / .pdf（≤20MB）'}</span>
            </button>
          </div>
        </div>

        {/* 第 3 步 */}
        <div className="mt-3 flex items-start gap-2.5">
          <span className="mt-[3px] flex size-4 flex-none items-center justify-center rounded-full bg-secondary text-[10px] font-semibold text-muted-foreground">
            3
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={!file || busy} onClick={() => void onConvert()}>
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                {busy ? '转换中…' : '转换并下载'}
              </Button>
              {file ? (
                <Button size="sm" variant="ghost" onClick={() => { setFile(null); setDone(null); setError(null) }}>
                  清空
                </Button>
              ) : (
                <span className="text-[10.5px] text-muted-foreground">先选文件再转换</span>
              )}
            </div>
            {error ? (
              <p className="mt-1.5 text-[11.5px] leading-[1.6] text-status-red">{error}</p>
            ) : null}
            {done ? (
              <p className="mt-1.5 text-[11.5px] leading-[1.6] text-status-green">{done}</p>
            ) : null}
          </div>
        </div>
      </WorkCard>

      {/* ══ ② 前提条件：单独一张提示卡，不再混在操作卡底部当长灰字 ══ */}
      <WorkCard className="border-status-yellow/40 bg-status-yellow-bg/40">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-yellow" />
          <div className="min-w-0">
            <div className="text-[12px] font-medium">转换需要后端开启开关</div>
            <p className="mt-1 text-[11px] leading-[1.65] text-muted-foreground">
              转换由后端完成：上传传统起诉状 + 文书类型，服务端生成要素式 docx 并回传，前端不做字段搬运。
              需开启 <code className="rounded bg-secondary px-1 py-[1px] font-mono text-[10.5px]">ZNSZJ_ENABLED</code>，
              未开启时接口返回 403。
            </p>
          </div>
        </div>
      </WorkCard>

      <HistoryBlock caseId={caseId} />
    </div>
  )
}

// ───────────────────────── 历史记录 ─────────────────────────

function HistoryBlock({ caseId }: { caseId: number }) {
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

  return (
    <section>
      <h3 className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold text-muted-foreground">
        转换记录
        <span className="font-normal tabular-nums">{related.length}</span>
        <Button variant="ghost" size="icon-xs" className="ml-auto" onClick={() => setNonce((n) => n + 1)}>
          <RefreshCw className="size-3" />
        </Button>
      </h3>

      {state.loading ? (
        <LoadingBlock text="加载记录…" size="sm" />
      ) : state.error ? (
        <p className="text-[11.5px] text-status-red">{state.error}</p>
      ) : related.length ? (
        <ul className="flex flex-col gap-1">
          {related.slice(0, 10).map((r) => {
            const row = r as unknown as {
              id: number
              original_name?: string
              mbid_name?: string
              created_at?: string
            }
            return (
              <li key={row.id} className="flex items-center gap-2 text-[11.5px]">
                <span className="min-w-0 flex-1 truncate" title={row.original_name}>
                  {row.original_name || `记录 #${row.id}`}
                </span>
                <StatusBadge tone="neutral" size="xs">
                  {row.mbid_name || '—'}
                </StatusBadge>
                <span className="flex-none tabular-nums text-muted-foreground">
                  {(row.created_at ?? '').slice(0, 16).replace('T', ' ')}
                </span>
              </li>
            )
          })}
        </ul>
      ) : (
        <EmptyBlock>还没有转换记录。</EmptyBlock>
      )}
    </section>
  )
}

// ───────────────────────── 小工具 ─────────────────────────

/** 文书类型列表（只拉一次，页面内共享） */
function useTypeList() {
  const [s, setS] = useState<{ loading: boolean; data: MbidList | null; error: string | null }>({
    loading: true,
    data: null,
    error: null,
  })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let alive = true
    setS((v) => ({ ...v, loading: true }))
    listMbidTypes()
      .then((d) => alive && setS({ loading: false, data: d, error: null }))
      .catch((e) => alive && setS({ loading: false, data: null, error: errMessage(e, '加载失败') }))
    return () => {
      alive = false
    }
  }, [nonce])

  return { ...s, reload: () => setNonce((n) => n + 1) }
}

/** 触发浏览器下载。文件名后端已按 content-disposition 给过，这里用调用方拼的名。 */
function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // 立刻 revoke 会让 Safari 偶发下载空文件
  setTimeout(() => URL.revokeObjectURL(href), 4000)
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
