import { useRef, useState } from 'react'
import { AlertTriangle, Download, FileUp, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'

import { convertToElemental } from '../api'
import { useCase } from '../hooks/use-cases'
import { suggestMbid } from '../utils'
import {
  ActionButton,
  InsetBlock,
  Pill,
  RailSection,
  SectionTitle,
  StatCell,
  StatStrip,
  StepItem,
  WorkCard,
} from './ui'
import { HistoryBlock } from './convert/HistoryBlock'
import { fmtSize, saveBlob, useTypeList } from './convert/convert-utils'
import {
  DEMO_CONVERT_MAPPING_DETAIL,
  DEMO_CONVERT_PREVIEW,
  DEMO_CONVERT_STATS,
  DEMO_CONVERT_TEMPLATES,
} from './demo-data'


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
  /** 转换记录条数（由 HistoryBlock 回传，顶部统计格用） */
  const [recordCount, setRecordCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  if (types.loading) return <LoadingBlock text="正在读取文书类型…" size="sm" />
  if (types.error) {
    return <ErrorBlock error={types.error} fallback="文书类型读取失败" onRetry={types.reload} />
  }

  const filingTypes = (types.data?.categories ?? []).filter((c) => c.category === '起诉状')
  const options = filingTypes.length ? filingTypes : (types.data?.categories ?? [])
  /** 当前选中类型的显示名（顶部统计格用） */
  const currentTypeName =
    options.flatMap((g) => g.items).find((it) => it.mbid === mbid)?.name ?? mbid

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
      {/* ══ 顶部三格统计：先把「用哪个类型、转了几次、上次什么时候」摆出来 ══ */}
      <StatStrip className="grid-cols-3">
        <StatCell label="文书类型" value={currentTypeName || '—'} />
        <StatCell label="转换次数" value={recordCount} tone={recordCount > 0 ? 'green' : 'neutral'} />
        <StatCell label="识别来源" value="按案由自动匹配" />
      </StatStrip>

      {/* ══ 转换统计 + 文书类型库：一卡两段铺满内容区宽度 ══ */}
      <WorkCard padded={false}>
        <RailSection title="转换统计" action={<Pill tone="green">本月失败 {DEMO_CONVERT_STATS.failed} 次</Pill>}>
          <StatStrip className="grid-cols-2 sm:grid-cols-4">
            <StatCell label="累计转换" value={`${DEMO_CONVERT_STATS.total.toLocaleString('en-US')} 次`} />
            <StatCell label="本月转换" value={`${DEMO_CONVERT_STATS.monthly} 次`} tone="blue" />
            <StatCell label="平均耗时" value={`${DEMO_CONVERT_STATS.avgMs.toLocaleString('en-US')} ms`} />
            <StatCell
              label="失败率"
              value={`${DEMO_CONVERT_STATS.failRate}%`}
              tone={DEMO_CONVERT_STATS.failRate > 5 ? 'red' : 'yellow'}
            />
          </StatStrip>
          <p className="mt-2 text-[10.5px] leading-[1.6] text-muted-foreground">
            失败集中在原文件格式不支持（扫描件无文字层）与后端开关未开两种情况，重试前先确认这两项。
          </p>
        </RailSection>

        <RailSection
          title="文书类型库"
          action={<span className="text-[10.5px] text-muted-foreground">共 {DEMO_CONVERT_TEMPLATES.length} 类 · 按本月用量排序</span>}
        >
          <div className="grid grid-cols-[76px_minmax(0,1fr)_140px_64px_56px] gap-2 border-b border-border-light pb-1 text-[10px] text-muted-foreground">
            <span>mbid</span>
            <span>文书名称</span>
            <span>适用案由</span>
            <span>模板版本</span>
            <span className="text-right">本月</span>
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_CONVERT_TEMPLATES.map((t) => (
              <li key={t.mbid} className="grid grid-cols-[76px_minmax(0,1fr)_140px_64px_56px] items-center gap-2 py-[6px]">
                <span className="truncate font-mono text-[10.5px] text-muted-foreground" title={t.mbid}>
                  {t.mbid}
                </span>
                <span className="min-w-0 truncate text-[11.5px]" title={t.name}>
                  {t.name}
                </span>
                <span className="min-w-0 truncate text-[11px] text-muted-foreground" title={t.cause}>
                  {t.cause}
                </span>
                <span className="text-[11px] tabular-nums text-secondary-foreground">{t.version}</span>
                <span className="text-right text-[11.5px] font-medium tabular-nums">{t.monthly}</span>
              </li>
            ))}
          </ul>
        </RailSection>
      </WorkCard>

      {/* ══ 左操作 / 右说明：两卡并排 ══ */}
      <div className="grid grid-cols-1 items-start gap-[18px] lg:grid-cols-[minmax(0,1fr)_300px]">
        <WorkCard>
          <SectionTitle title="转换要素式文书" hint="传统起诉状 → 法院要素式示范文本" />

          {/* 第 1 步 */}
          <div className="mt-3.5 flex items-start gap-2.5">
            <span className="mt-[3px] grid size-[18px] flex-none place-items-center rounded-full bg-foreground text-[10px] font-semibold text-background">
              1
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11.5px] text-muted-foreground">选文书类型（按案由已自动匹配，可改）</div>
              <InsetBlock className="mt-1.5">
                <select
                  value={mbid}
                  onChange={(e) => setMbid(e.target.value)}
                  aria-label="文书类型"
                  className="w-full bg-transparent text-[12.5px] outline-none"
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
              </InsetBlock>
            </div>
          </div>

          {/* 第 2 步 */}
          <div className="mt-3.5 flex items-start gap-2.5">
            <span className="mt-[3px] grid size-[18px] flex-none place-items-center rounded-full bg-foreground text-[10px] font-semibold text-background">
              2
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11.5px] text-muted-foreground">选一份传统起诉状</div>
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
                className="mt-1.5 flex w-full items-center gap-2 rounded-[9px] border border-dashed border-zinc-300 bg-secondary/20 px-3 py-3 text-left text-[11.5px] text-muted-foreground transition-colors hover:border-foreground hover:bg-secondary/40 hover:text-foreground"
              >
                <FileUp className="size-4 flex-none" />
                <span className="min-w-0 truncate">
                  {file ? `${file.name}（${fmtSize(file.size)}）` : '选择 .docx / .doc / .pdf（≤20MB）'}
                </span>
              </button>
            </div>
          </div>

          {/* 第 3 步 */}
          <div className="mt-3.5 flex items-start gap-2.5">
            <span className="mt-[3px] grid size-[18px] flex-none place-items-center rounded-full bg-foreground text-[10px] font-semibold text-background">
              3
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11.5px] text-muted-foreground">转换并下载要素式 docx</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <ActionButton dark disabled={!file || busy} onClick={() => void onConvert()}>
                  {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                  {busy ? '转换中…' : '转换并下载'}
                </ActionButton>
                {file ? (
                  <ActionButton
                    onClick={() => {
                      setFile(null)
                      setDone(null)
                      setError(null)
                    }}
                  >
                    清空
                  </ActionButton>
                ) : (
                  <span className="text-[10.5px] text-muted-foreground">先选文件再转换</span>
                )}
              </div>
              {error ? (
                <InsetBlock className="mt-2 border-status-red/40 bg-status-red-bg">
                  <p className="text-[11.5px] leading-[1.6] text-status-red">{error}</p>
                </InsetBlock>
              ) : null}
              {done ? (
                <InsetBlock className="mt-2 border-status-green/40 bg-status-green-bg">
                  <p className="text-[11.5px] leading-[1.6] text-status-green">{done}</p>
                </InsetBlock>
              ) : null}
            </div>
          </div>
        </WorkCard>

        {/* 右栏：前提条件 + 这一步做什么 */}
        <div className="flex flex-col gap-3.5">
          <WorkCard className="border-status-yellow/40 bg-status-yellow-bg/40">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-yellow" />
              <div className="min-w-0">
                <div className="text-[12px] font-[620]">转换需要后端开启开关</div>
                <p className="mt-1.5 text-[11px] leading-[1.7] text-muted-foreground">
                  转换由后端完成：上传传统起诉状 + 文书类型，服务端生成要素式 docx 并回传，
                  前端不做字段搬运 —— 否则改了后端、前端还在按老规则拼。
                </p>
                <InsetBlock className="mt-2 bg-background/70">
                  <div className="text-[10px] text-muted-foreground">需要的开关</div>
                  <code className="mt-0.5 block font-mono text-[11px]">ZNSZJ_ENABLED</code>
                  <div className="mt-1 text-[10px] text-muted-foreground">未开启时接口返回 403</div>
                </InsetBlock>
              </div>
            </div>
          </WorkCard>

          <WorkCard>
            <SectionTitle title="这一步做什么" />
            <div className="mt-3">
              <StepItem index={1} title="选对文书类型" desc="按案由自动匹配，可改" state="current" />
              <StepItem index={2} title="上传传统起诉状" desc="律师已写好的那份" state="todo" />
              <StepItem index={3} title="服务端转换" desc="生成要素式 docx" state="todo" />
              <StepItem index={4} title="下载并递交" desc="用于一张网立案" state="todo" />
            </div>
          </WorkCard>

          <WorkCard padded={false}>
            <div className="border-b border-border-light px-5 py-3">
              <SectionTitle
                title="转换内容"
                hint={`传统字段 → 要素式栏位 · ${DEMO_CONVERT_MAPPING_DETAIL.length} 项`}
              />
            </div>
            <ul className="divide-y divide-border-light">
              {DEMO_CONVERT_MAPPING_DETAIL.map((m) => (
                <li key={m.from} className="px-5 py-[7px]">
                  <div className="flex items-center gap-2">
                    <span className="w-[64px] flex-none text-[11.5px] text-secondary-foreground">{m.from}</span>
                    <span className="flex-none text-[10px] text-border">→</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground" title={m.to}>
                      {m.to}
                    </span>
                    <span
                      className={cn(
                        'flex-none text-[9.5px] font-semibold',
                        m.required ? 'text-status-red' : 'text-muted-foreground/70',
                      )}
                    >
                      {m.required ? '必填' : '选填'}
                    </span>
                  </div>
                  <div className="mt-[3px] truncate pl-[74px] text-[10px] text-muted-foreground" title={m.sample}>
                    例：{m.sample}
                  </div>
                </li>
              ))}
            </ul>
          </WorkCard>
        </div>
      </div>

      {/* ══ 转换前后对比：左传统起诉状摘要 vs 右要素式摘要 ══ */}
      <WorkCard padded={false}>
        <div className="border-b border-border-light px-5 py-3">
          <SectionTitle title="转换前后对比" hint="同一段事实，两种写法 · 预览已脱敏" />
        </div>
        <div className="grid grid-cols-1 gap-[18px] px-5 py-3.5 lg:grid-cols-2">
          {[true, false].map((legacySide) => (
            <div key={legacySide ? 'legacy' : 'elemental'} className="flex min-w-0 flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-[650] tracking-[0.06em] text-muted-foreground/80">
                  {legacySide ? '传统起诉状' : '要素式示范文本'}
                </span>
                <Pill tone={legacySide ? 'neutral' : 'blue'}>{legacySide ? '原稿' : '转换结果'}</Pill>
              </div>
              <ul className="flex flex-col gap-1.5">
                {DEMO_CONVERT_PREVIEW.map((p) => (
                  <li key={p.label} className="rounded-[9px] border border-border-light bg-background px-3 py-2">
                    <div className="flex items-baseline gap-2">
                      <span className="text-[10px] font-medium text-muted-foreground">{p.label}</span>
                      {!p.matched && !legacySide ? (
                        <span className="text-[9px] font-semibold text-status-blue">要素式新增</span>
                      ) : null}
                      {!p.matched && legacySide ? (
                        <span className="text-[9px] text-muted-foreground/70">原稿无此栏</span>
                      ) : null}
                    </div>
                    <p
                      className={cn(
                        'mt-1 whitespace-pre-line text-[11px] leading-[1.65]',
                        p.matched ? 'text-secondary-foreground' : 'text-muted-foreground/70',
                      )}
                    >
                      {legacySide ? p.legacy : p.elemental}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="border-t border-border-light px-5 py-2.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          转换只做<b className="font-medium text-secondary-foreground">栏位重组与格式规整</b>
          ，不改写事实表述 —— 新增的两栏（利息计算方式、是否同意调解）在传统起诉状里没有对应内容，
          转换后会留空并标黄，需律师补填后再递交。
        </div>
      </WorkCard>

      <HistoryBlock caseId={caseId} onCount={setRecordCount} />
    </div>
  )
}
