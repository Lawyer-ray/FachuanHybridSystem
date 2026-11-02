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

import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { errMessage } from '@/lib/errors'

import {
  bindMaterials,
  confirmSplitJob,
  createSplitJob,
  downloadSplitZip,
  getSplitJob,
  uploadCaseMaterials,
  type PdfSplitJob,
  type PdfSplitSegment,
  type SplitTemplate,
} from '../api'
import {
  ActionButton,
  Chip,
  InsetBlock,
  KeyValueRow,
  RailSection,
  StatCell,
  StatStrip,
  StepItem,
  WorkCard,
} from './ui'
import { HistoryTable } from './bundle/HistoryTable'
import { FaqList, RuleBook } from './bundle/RuleBook'
import { SegmentSnapshot, TemplateWall } from './bundle/TemplateWall'
import { SegmentsTable } from './bundle/SegmentsTable'
import { StepBar, type BundlePhase } from './bundle/StepBar'
import { guessSide, unzipToFiles } from './bundle/segs'

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

type Phase = BundlePhase

export function BundleSplitPanel({ caseId, stage }: { caseId: number; stage?: string | null }) {
  // 模板跟着案件阶段走：二审案必须用二审模板，否则整包里的判决书/上诉状
  // 会被模型按「立案材料」身份预设否定掉，全落 unrecognized。
  const isAppeal = /二审|重审二审|再审二审|提审/.test(stage ?? '') || /second_trial|retrial_second|rehearing_second|review/.test(stage ?? '')
  const template: SplitTemplate = isAppeal ? 'appeal_defense_v1' : 'filing_materials_v1'
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
  }, [template])

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
      const r = await createSplitJob(file, template)
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
      setError(errMessage(e, '分段任务提交失败'))
    }
  }, [template])

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
      setError(errMessage(e, '导入失败'))
    }
  }, [job, segs, caseId])

  // ── 渲染 ──
  const busy = phase === 'uploading' || phase === 'splitting' || phase === 'confirming' || phase === 'importing'

  return (
    <div className="flex flex-col gap-3">
      <StepBar phase={phase} />
      {phase === 'idle' ? (
        <div className="flex flex-col gap-3">
          {/* 左右分栏：左「上传 + 记录 + 明细」，右「模式 + 四步 + 风险 + 能力 + 规则 + 答疑」。
              整页只有 3 张卡（上传 / 左栏大卡 / 右栏大卡），卡内用淡线分段 ——
              原先 8 张独立小卡之间全是 18px 留白，1080p 下白色只覆盖 23%。 */}
          <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-[minmax(0,1fr)_372px]">
            <div className="flex flex-col gap-3">
              <WorkCard padded={false}>
                <div className="flex flex-col items-center justify-center gap-2.5 px-6 py-6">
                  <div className="flex size-10 items-center justify-center rounded-full bg-secondary">
                    <FileStack className="size-4.5 text-muted-foreground" />
                  </div>
                  <p className="text-[13px] font-medium text-foreground">
                    上传{isAppeal ? '二审答辩' : '一审起诉'}整包 PDF
                  </p>
                  <p className="max-w-[440px] text-center text-[11.5px] leading-[1.65] text-muted-foreground">
                    律师拿到的是一叠扫描件（几十页混在一起）。系统按每页内容自动拆成单份材料、
                    重命名，再归到本案。
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
                  <div className="mt-0.5 flex items-center gap-2">
                    <Button size="sm" onClick={() => fileRef.current?.click()}>
                      <Upload className="size-3.5" /> 选择整包 PDF
                    </Button>
                    <ActionButton sm title="按分隔页拆（扫描时插了空白分隔页）">
                      按分隔页拆
                    </ActionButton>
                  </div>
                  <p className="text-[10.5px] text-muted-foreground">
                    支持 .pdf，单包 ≤ 500 页 · 实测约 1.3 s/页
                  </p>
                </div>
                <RailSection title="本次拆分口径">
                  <StatStrip className="grid-cols-4">
                    <StatCell label="识别模式" value={isAppeal ? '二审答辩' : '一审起诉'} tone="blue" />
                    <StatCell label="拆分依据" value="按页内容" />
                    <StatCell label="归类方式" value="人工复核" tone="yellow" />
                    <StatCell label="OCR 档位" value="balanced" />
                  </StatStrip>
                </RailSection>
              </WorkCard>

              <HistoryTable />
              <SegmentSnapshot />
            </div>

            <WorkCard padded={false}>
              <RailSection title="识别模式">
                <div className="flex items-center gap-2">
                  <StatusBadge tone={isAppeal ? 'yellow' : 'blue'} size="sm">
                    {isAppeal ? '二审答辩材料' : '一审起诉材料'}
                  </StatusBadge>
                  <Chip>{isAppeal ? 'appeal_defense_v1' : 'filing_materials_v1'}</Chip>
                </div>
                <p className="mt-2 text-[11px] leading-[1.6] text-muted-foreground">
                  拆什么材料跟案件阶段走 —— 两套不能混用。当前阶段决定了用哪套模板。
                </p>
              </RailSection>

              <RailSection title="这一步做什么">
                <StepItem index={1} title="上传整包" desc="几十页混在一起的扫描件" state="current" />
                <StepItem index={2} title="自动分段" desc="按页内容切开并重命名" state="todo" />
                <StepItem index={3} title="人工复核" desc="核对页码与文件名" state="todo" />
                <StepItem index={4} title="归入本案" desc="成为正式卷宗材料" state="todo" />
              </RailSection>

              <RailSection title="风险提示">
                <InsetBlock className="border-status-yellow/40 bg-status-yellow-bg/40">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-yellow" />
                    <p className="text-[11px] leading-[1.6] text-muted-foreground">
                      低置信度与未识别的分段会在复核表里标出。归案后它们就是正式卷宗材料，
                      所以这一步请核对页码与文件名。
                    </p>
                  </div>
                </InsetBlock>
              </RailSection>

              <RailSection title="处理耗时（近 3 包）">
                <dl>
                  <KeyValueRow label="278 页整包">
                    <span className="tabular-nums">6 m 12 s</span>
                  </KeyValueRow>
                  <KeyValueRow label="188 页整包">
                    <span className="tabular-nums">3 m 06 s</span>
                  </KeyValueRow>
                  <KeyValueRow label="平均单页">
                    <span className="tabular-nums">1.3 s / 页</span>
                  </KeyValueRow>
                </dl>
              </RailSection>
            </WorkCard>
          </div>

          {/* 下方两块：识别能力墙 + 拆分规则 + 常见问题（整宽，铺满剩余高度） */}
          <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-2">
            <TemplateWall />
            <div className="flex flex-col gap-3">
              <RuleBook />
              <FaqList />
            </div>
          </div>
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

          <SegmentsTable segs={segs} />

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
