import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileStack,
  Loader2,
  Play,
  RotateCcw,
  Upload,
  XCircle,
} from 'lucide-react'

import { StatusBadge, type Tone } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import {
  bindMaterials,
  confirmSplitJob,
  createSplitJob,
  downloadSplitZip,
  getSplitJob,
  uploadCaseMaterials,
  type PdfSplitJob,
  type PdfSplitSegment,
} from '../api'

/**
 * 整包 PDF → 自动分段 → 归案（场景 2 的真正起点）。
 *
 * ═══ 为什么这是第一步 ═══
 * 律师从银行拿到的不是分好的材料，是**一叠扫描件**（几十页什么都混在一起）。
 * 系统要做的第一件事就是把它拆开、认出来、重命名、归到案件里 ——
 * 拆完之后「材料齐备度」「起诉条件」「一张网立案」才有东西可算。
 *
 * ═══ 五步状态机 ═══
 * idle → uploading → splitting(轮询) → review(人工复核) → confirming → done
 *                       ↘ failed / timeout
 *
 * 复核这一步**必须保留**：机器分段再准也可能分错（实测 10 段里就有 1 段
 * low_confidence），直接往下走会把错的分段带进正式卷宗。
 */

const POLL_MS = 2500
const MAX_POLLS = 240 // 10 分钟

type Phase = 'idle' | 'uploading' | 'splitting' | 'review' | 'confirming' | 'importing' | 'done' | 'failed'

/** 分段状态 → 语气。低置信度用黄色，未识别用红色。 */
function segTone(flag: string | null | undefined): Tone {
  if (flag === 'low_confidence') return 'yellow'
  if (flag === 'unrecognized' || flag === 'ocr_failed') return 'red'
  return 'neutral'
}

export function BundleSplitPanel({ caseId }: { caseId: number }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [job, setJob] = useState<PdfSplitJob | null>(null)
  const [segs, setSegs] = useState<PdfSplitSegment[]>([])
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState('')
  const [imported, setImported] = useState(0)

  const fileRef = useRef<HTMLInputElement>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const reset = useCallback(() => {
    setPhase('idle')
    setJob(null)
    setSegs([])
    setError(null)
    setProgress('')
    setImported(0)
  }, [])

  /** 1+2. 上传整包 → 建任务 → 轮询到 review_required */
  const start = useCallback(async (file: File) => {
    setPhase('uploading')
    setError(null)
    setProgress('正在上传整包…')
    try {
      const r = await createSplitJob(file)
      if (!alive.current) return
      setPhase('splitting')
      setProgress('已提交，正在识别页面内容…')

      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((res) => setTimeout(res, POLL_MS))
        if (!alive.current) return
        const j = await getSplitJob(r.job_id)
        if (!alive.current) return
        setJob(j)

        const done = j.processed_pages ?? 0
        const total = j.total_pages ?? 0
        setProgress(
          j.status === 'exporting'
            ? '正在导出分段文件…'
            : `识别中 ${done}/${total || '?'} 页`,
        )

        if (j.status === 'review_required' || j.status === 'completed') {
          setSegs(j.segments ?? [])
          setPhase('review')
          return
        }
        if (j.status === 'failed' || j.status === 'cancelled') {
          setPhase('failed')
          setError(j.error_message || `分段${j.status === 'failed' ? '失败' : '已取消'}`)
          return
        }
      }
      if (!alive.current) return
      setPhase('failed')
      setError('识别超时（超过 10 分钟）。任务可能仍在后台运行，稍后重试或到列表中查看。')
    } catch (e) {
      if (!alive.current) return
      setPhase('failed')
      setError(errMessage(e))
    }
  }, [])

  /** 4+5. 确认分段 → 等导出 → 下载 → 逐个上传 → 归案 */
  const confirmAndImport = useCallback(async () => {
    if (!job) return
    setPhase('confirming')
    setError(null)
    setProgress('正在导出分段文件…')
    try {
      await confirmSplitJob(
        job.job_id,
        segs.map((s, i) => ({
          id: s.id,
          order: s.order ?? i + 1,
          page_start: s.page_start,
          page_end: s.page_end,
          segment_type: s.segment_type || 'unrecognized',
          filename: s.filename,
          confidence: s.confidence,
          review_flag: s.review_flag,
          source_method: s.source_method,
        })),
      )

      // 等导出完成
      let final: PdfSplitJob | null = null
      for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise((res) => setTimeout(res, POLL_MS))
        if (!alive.current) return
        const j = await getSplitJob(job.job_id)
        if (j.status === 'completed') {
          final = j
          break
        }
        if (j.status === 'failed' || j.status === 'cancelled') {
          throw new Error(j.error_message || '导出失败')
        }
      }
      if (!final) throw new Error('导出超时')

      // 下载 zip
      setPhase('importing')
      setProgress('正在下载分段文件…')
      const zip = await downloadSplitZip(job.job_id)
      if (!alive.current) return

      // 上传到案件
      setProgress('正在上传到案件…')
      const files = await unzipToFiles(zip)
      if (!files.length) throw new Error('分段结果为空')
      const up = await uploadCaseMaterials(caseId, files)
      if (!alive.current) return

      // 归案：用引擎识别的 segment_label 作为材料类型名。
      // ⚠️ 不要自己另起名字 —— 材料齐备度是按类型名做关键词匹配的，
      // 手工改名（比如把引擎给的「借款合同」写成「担保合同」）会让槽位判空。
      setProgress('正在归案…')
      const byName = new Map(files.map((f, i) => [f.name, up.attachment_ids[i]]))
      const items = segs
        .map((s) => {
          const att = byName.get(s.filename)
          if (!att) return null
          return {
            attachment_id: att,
            category: 'party',
            type_name: s.segment_label || s.filename.replace(/\.pdf$/i, ''),
            // ⚠️ category=party 时 side **必须是** our 或 opponent，不能为空：
            //    后端校验 `side not in {OUR, OPPONENT}` 直接报「当事人方向不合法」。
            //    我一开始把 party_identity 传 null（想着「身份材料不分方向」），
            //    结果整个归案失败。身份材料也是有方向的 —— 被告身份证属对方。
            side: guessSide(s),
          }
        })
        .filter((x): x is NonNullable<typeof x> => x !== null)

      const bound = await bindMaterials(caseId, items)
      if (!alive.current) return
      setImported(bound.saved_count)
      setPhase('done')
      setProgress('')
    } catch (e) {
      if (!alive.current) return
      setPhase('failed')
      setError(errMessage(e))
    }
  }, [job, segs, caseId])

  // ── 渲染 ──
  const busy = phase === 'uploading' || phase === 'splitting' || phase === 'confirming' || phase === 'importing'

  return (
    <div className="flex flex-col gap-3">
      <StepBar phase={phase} />

      {phase === 'idle' ? (
        <div className="flex flex-col items-center gap-2 rounded-[8px] border border-dashed border-zinc-300 px-4 py-8">
          <FileStack className="size-7 text-muted-foreground" />
          <p className="text-[12.5px] text-secondary-foreground">上传整包 PDF</p>
          <p className="max-w-[420px] text-center text-[11px] leading-[1.6] text-muted-foreground">
            律师从银行拿到的一叠扫描件（几十页混在一起）。系统会按每页内容
            自动拆成单份材料、重命名，再归到本案。
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void start(f)
              e.target.value = ''
            }}
          />
          <Button size="sm" className="mt-1" onClick={() => fileRef.current?.click()}>
            <Upload className="size-3.5" /> 选择整包 PDF
          </Button>
        </div>
      ) : null}

      {busy ? (
        <div className="flex items-center gap-2 rounded-[8px] border border-border bg-secondary/30 px-3 py-2.5">
          <Loader2 className="size-3.5 animate-spin text-status-blue" />
          <span className="text-[12px]">{progress || '处理中…'}</span>
          {job && phase === 'splitting' ? (
            <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
              {job.processed_pages ?? 0}/{job.total_pages ?? '?'} 页
            </span>
          ) : null}
        </div>
      ) : null}

      {phase === 'review' && segs.length ? (
        <>
          <div className="flex items-center gap-2 text-[11.5px]">
            <span className="text-muted-foreground">共识别</span>
            <span className="font-medium tabular-nums">{segs.length}</span>
            <span className="text-muted-foreground">份材料</span>
            {segs.some((s) => s.review_flag === 'low_confidence') ? (
              <StatusBadge tone="yellow" size="xs">
                {segs.filter((s) => s.review_flag === 'low_confidence').length} 份需复核
              </StatusBadge>
            ) : null}
            {segs.some((s) => s.review_flag === 'unrecognized') ? (
              <StatusBadge tone="red" size="xs">
                {segs.filter((s) => s.review_flag === 'unrecognized').length} 份未识别
              </StatusBadge>
            ) : null}
          </div>

          <div className="overflow-hidden rounded-[8px] border border-border">
            <div className="grid grid-cols-[42px_1fr_84px_64px] gap-2 border-b border-border bg-secondary/40 px-3 py-1.5 text-[10.5px] font-medium text-muted-foreground">
              <span>页</span>
              <span>文件名</span>
              <span>类型</span>
              <span className="text-right">置信度</span>
            </div>
            {segs.map((s) => (
              <div
                key={s.id ?? s.order}
                className="grid grid-cols-[42px_1fr_84px_64px] items-center gap-2 border-b border-border/60 px-3 py-1.5 last:border-b-0"
              >
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {s.page_start === s.page_end ? s.page_start : `${s.page_start}-${s.page_end}`}
                </span>
                <div className="min-w-0">
                  <div className="truncate text-[12px]" title={s.filename}>
                    {s.filename}
                  </div>
                  <div className="truncate text-[10.5px] text-muted-foreground">{s.segment_label}</div>
                </div>
                <StatusBadge tone={segTone(s.review_flag)} size="xs">
                  {s.review_flag === 'low_confidence'
                    ? '需复核'
                    : s.review_flag === 'unrecognized'
                      ? '未识别'
                      : '正常'}
                </StatusBadge>
                <span className="text-right text-[11px] tabular-nums text-muted-foreground">
                  {s.confidence != null ? s.confidence.toFixed(2) : '—'}
                </span>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Button size="xs" onClick={() => void confirmAndImport()}>
              <Play className="size-3" /> 确认并归案
            </Button>
            <Button size="xs" variant="ghost" onClick={reset}>
              <RotateCcw className="size-3" /> 重来
            </Button>
            <span className="text-[10.5px] text-muted-foreground">
              确认后会导出 {segs.length} 个 PDF 并自动挂到本案
            </span>
          </div>
        </>
      ) : null}

      {phase === 'done' ? (
        <div className="flex items-start gap-2 rounded-[8px] border border-status-green/40 bg-status-green-bg px-3 py-2.5">
          <CheckCircle2 className="mt-[2px] size-3.5 flex-none text-status-green" />
          <div className="text-[12px] leading-[1.6] text-status-green">
            <div className="font-medium">已归案 {imported} 份材料</div>
            <div className="mt-0.5 text-[11px] opacity-85">
              切到「起诉条件」看材料齐备度与起诉条件是否已自动更新。
            </div>
          </div>
          <Button size="xs" variant="ghost" className="ml-auto" onClick={reset}>
            再传一包
          </Button>
        </div>
      ) : null}

      {phase === 'failed' ? (
        <div className="flex items-start gap-2 rounded-[8px] border border-status-red/40 bg-status-red-bg px-3 py-2.5">
          <XCircle className="mt-[2px] size-3.5 flex-none text-status-red" />
          <div className="min-w-0 flex-1 text-[12px] leading-[1.6] text-status-red">
            <div className="font-medium">处理失败</div>
            <div className="mt-0.5 break-words text-[11px] opacity-90">{error}</div>
          </div>
          <Button size="xs" variant="ghost" className="ml-auto" onClick={reset}>
            重试
          </Button>
        </div>
      ) : null}

      <p className="flex items-start gap-1.5 text-[10.5px] leading-[1.65] text-muted-foreground">
        <AlertTriangle className="mt-[1px] size-3 flex-none" />
        分段由内容识别引擎完成，可能出错。低置信度与未识别的分段会在上表标出，
        确认前请核对页码与文件名 —— 归案后这些会成为正式卷宗材料。
      </p>
    </div>
  )
}

// ───────────────────────── 步骤条 ─────────────────────────

const STEPS: { key: Phase[]; label: string }[] = [
  { key: ['uploading', 'splitting'], label: '识别' },
  { key: ['review', 'confirming'], label: '复核' },
  { key: ['importing'], label: '归案' },
  { key: ['done'], label: '完成' },
]

function StepBar({ phase }: { phase: Phase }) {
  const idx = STEPS.findIndex((s) => s.key.includes(phase))
  return (
    <div className="flex items-center gap-1.5">
      {STEPS.map((s, i) => {
        const active = i === idx
        const passed = idx >= 0 && i < idx
        return (
          <div key={s.label} className="flex items-center gap-1.5">
            <span
              className={cn(
                'rounded-[5px] px-2 py-0.5 text-[11px]',
                active
                  ? 'bg-foreground font-medium text-background'
                  : passed
                    ? 'text-status-green'
                    : 'text-muted-foreground',
              )}
            >
              {s.label}
            </span>
            {i < STEPS.length - 1 ? <span className="text-[10px] text-border">›</span> : null}
          </div>
        )
      })}
    </div>
  )
}

/**
 * 判断一份材料属于我方还是对方。
 *
 * 依据依次为：文件名里的当事人标识 → 材料类型。
 * 这条规则故意保守：拿不准就算我方（立案材料绝大多数是我方提交的），
 * 因为 side 只是分类标签，判错不会拦住流程，但**留空会**（后端硬校验）。
 */
function guessSide(seg: PdfSplitSegment): 'our' | 'opponent' {
  const n = `${seg.filename} ${seg.segment_label ?? ''}`
  // 对方当事人的材料：被告/被上诉人/被申请人 的身份证、答辩状、上诉状
  if (/(被告|被上诉人|被申请人|对方)[^/]*(身份证|身份证明|答辩|上诉状)/.test(n)) return 'opponent'
  if (/^(被告|被上诉人|被申请人).*\.pdf$/i.test(seg.filename)) return 'opponent'
  return 'our'
}

// ───────────────────────── zip 解包 ─────────────────────────

/**
 * 把下载到的 zip 解成 File[]。
 *
 * 为什么自己解而不是让后端逐个给：
 * 整包一次下完少 10 次往返；而且后端 export 产物本来就是一个 zip。
 * 用浏览器内置 DecompressionStream + 手写中央目录解析太重，
 * 这里用最小可用的 zip 解析：只支持 store/deflate，足够（后端就是这个）。
 */
async function unzipToFiles(zip: Blob): Promise<File[]> {
  const buf = new Uint8Array(await zip.arrayBuffer())
  const entries = parseZipEntries(buf)
  const out: File[] = []
  for (const e of entries) {
    if (e.name.endsWith('/')) continue
    const data = await inflateEntry(buf, e)
    if (!data) continue
    // ZIP 里的中文名是 UTF-8（后端用 filename flag 0x800），这里已解好
    const name = e.name.split('/').pop() || e.name
    out.push(new File([data], name, { type: 'application/pdf' }))
  }
  return out
}

interface ZipEntry {
  name: string
  method: number
  compressedSize: number
  uncompressedSize: number
  localHeaderOffset: number
}

/** 解析中央目录（zip 尾部 EOCD → 中央目录 → 每个条目） */
function parseZipEntries(buf: Uint8Array): ZipEntry[] {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  // 找 EOCD（0x06054b50），从尾部往前扫
  let eocd = -1
  for (let i = buf.length - 22; i >= 0 && i > buf.length - 65558; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) return []
  const count = dv.getUint16(eocd + 10, true)
  let off = dv.getUint32(eocd + 16, true)
  const entries: ZipEntry[] = []
  const dec = new TextDecoder('utf-8')

  for (let i = 0; i < count; i++) {
    if (dv.getUint32(off, true) !== 0x02014b50) break
    const method = dv.getUint16(off + 10, true)
    const compressedSize = dv.getUint32(off + 20, true)
    const uncompressedSize = dv.getUint32(off + 24, true)
    const nameLen = dv.getUint16(off + 28, true)
    const extraLen = dv.getUint16(off + 30, true)
    const commentLen = dv.getUint16(off + 32, true)
    const localHeaderOffset = dv.getUint32(off + 42, true)
    const name = dec.decode(buf.subarray(off + 46, off + 46 + nameLen))
    entries.push({ name, method, compressedSize, uncompressedSize, localHeaderOffset })
    off += 46 + nameLen + extraLen + commentLen
  }
  return entries
}

/** 解压单个条目（store 直接切；deflate 走 DecompressionStream） */
async function inflateEntry(buf: Uint8Array, e: ZipEntry): Promise<Uint8Array | null> {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  const off = e.localHeaderOffset
  if (dv.getUint32(off, true) !== 0x04034b50) return null
  const nameLen = dv.getUint16(off + 26, true)
  const extraLen = dv.getUint16(off + 28, true)
  const start = off + 30 + nameLen + extraLen
  const raw = buf.subarray(start, start + e.compressedSize)
  if (e.method === 0) return raw // store
  if (e.method !== 8) return null // 只支持 deflate

  try {
    const ds = new DecompressionStream('deflate-raw')
    const stream = new Blob([raw]).stream().pipeThrough(ds)
    const out = new Uint8Array(await new Response(stream).arrayBuffer())
    return out
  } catch {
    return null
  }
}
