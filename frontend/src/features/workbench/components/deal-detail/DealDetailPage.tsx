import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { ambiguousStages, chainSteps, chainSummary } from './detail-domain'
import { CaseSection, NextStageRow } from './CaseSection'
import { ChainStepper } from './ChainStepper'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { FilePreviewCard } from './FilePreviewCard'
import { ContractFileOverlays } from './ContractFileOverlays'
import { ResizeHandle } from './ResizeHandle'
import { useResizablePanel } from './use-resizable-panel'
import { soonToast, useDealCopilotContext, useDealDetailPage } from './use-deal-detail-page'
import { DetailError } from './ui'

/**
 * 52 号定则：过去在时间轴（案件节日志按日叙事），未来在右栏（期限只在这里预警）。
 * 左列只放案件本身（程序链 + 下一步），合同层面的当事人/收款/补充协议/要素全在右栏卡里。
 * 数据组装与助手上下文绑定在 use-deal-detail-page，与 NonLitDetailPage 共用。
 */
export function DealDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  /**
   * 正在发起审查的文件（null = 抽屉关闭）。
   * 诉讼页的合同也要能走 AI 审查——起诉状/和解协议同样是「AI 出建议、律师逐条决策」。
   */
  const [reviewTarget, setReviewTarget] = useState<{ subpath: string; name: string } | null>(null)
  const { valid, d, deal, plan, ordered, deadlines, contacts, money, next } = useDealDetailPage(id)
  /** 预览栏宽度：可拖拽、记住偏好（与非诉页同一套 hook，各记各的 key） */
  const panel = useResizablePanel({
    storageKey: 'fachuan:deal:preview-width',
    defaultWidth: 720,
    min: 360,
    maxRatio: 0.68,
  })
  const {
    width: panelWidth,
    dragging: panelDragging,
    containerRef: panelContainerRef,
    onPointerDown: panelPointerDown,
    setWidth: panelSetWidth,
  } = panel
  /** stepper 跳转后的短暂高亮环（案件 id） */
  const [hl, setHl] = useState<number | null>(null)
  /**
   * 合同文件夹里正在预览的文件（null = 未选中）。
   *
   * 诉讼页的文件夹在右栏（左栏是案件程序链），所以预览也在右栏就地展开：
   * 律师核对合同原文时要对照同一栏的期限/当事人，跳走或弹窗都会让对照失效。
   */
  const [picked, setPicked] = useState<
    { subpath: string; name: string; size?: number; modified_at?: string; mtime?: number } | null
  >(null)

  const steps = useMemo(() => chainSteps(plan), [plan])
  const ambiguous = useMemo(() => ambiguousStages(plan), [plan])

  /* 创建类动作本轮先占位（样式定稿后接表单）：记日志 / 新增期限 / 新建下一程序案件 / 记收款 */
  const soon = useCallback((what: string) => soonToast(what), [])
  const onAddLog = useCallback(() => soon('记办案日志'), [soon])
  const onAddDue = useCallback(() => soon('新增期限'), [soon])
  const onCreateNext = useCallback(() => soon('新建' + (next ?? '') + '案件'), [soon, next])
  const onAddPayment = useCallback(() => soon('记收款'), [soon])

  // 本页就是「这个委托」——把全局助手绑到该委托的业务上下文（详见 use-deal-detail-page）
  useDealCopilotContext(deal, '委托详情')

  const jump = useCallback((caseId: number) => {
    document.getElementById('case-' + caseId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setHl(caseId)
  }, [])
  useEffect(() => {
    if (hl == null) return
    const t = window.setTimeout(() => setHl(null), 1800)
    return () => window.clearTimeout(t)
  }, [hl])

  if (!valid) return <Navigate to="/projects" replace />
  if (d.isLoading) {
    return (
      <div className="flex flex-col items-center gap-2 py-[90px] text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        正在加载委托…
      </div>
    )
  }
  if (d.error || !deal) {
    return <DetailError error={d.error ?? '委托不存在'} onRetry={() => d.refetch()} />
  }
  return (
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader
        deal={deal}
        onAddDue={onAddDue}
        onAddLog={onAddLog}
      />

      <ChainStepper steps={steps} summary={chainSummary(plan)} onJump={jump} />

      {/* AI 助手入口只在导航栏（全局侧边栏 CopilotPanel，⌘J 同效）：页面内既不挂
          对话区、页头也不放按钮，避免与导航栏入口重复 */}
      {/* 与诉讼页一致：一旦在预览合同就扩宽右栏，让 OnlyOffice 有足够宽度
          渲染 A4 正文（窄栏里只看得到半行字，等于没预览）。 */}
      {/* 与诉讼页一致：一旦在预览合同就扩宽右栏，让 OnlyOffice 有足够宽度
          渲染 A4 正文（窄栏里只看得到半行字，等于没预览）。
          有预览时用 flex + 可拖分隔条，宽度交给用户，写死断点只能猜折中值。 */}
      <div
        ref={panelContainerRef}
        className={
          picked
            ? 'flex items-start gap-[8px] max-[1024px]:flex-col max-[1024px]:gap-[18px]'
            : 'grid items-start gap-[18px] max-[1024px]:grid-cols-1 grid-cols-[minmax(0,1fr)_400px] min-[1900px]:grid-cols-[minmax(0,1fr)_440px] min-[2400px]:grid-cols-[minmax(0,1fr)_480px]'
        }
      >
        <div className="min-w-0 flex-1">
          {d.casesError ? (
            <div className="rounded-[12px] border border-destructive/30 bg-destructive/5 px-5 py-4 text-sm text-destructive">
              {d.casesError} ·{' '}
              <button type="button" className="cursor-pointer underline underline-offset-3" onClick={() => d.refetch()}>
                重试
              </button>
            </div>
          ) : plan.length === 0 ? (
            <div className="rounded-[12px] border border-border bg-card px-5 py-8 text-center text-[13px] text-muted-foreground shadow-sm">
              合同没有勾选代理阶段，也还没有立案的程序
            </div>
          ) : (
            /* 超宽屏瀑布流两列：卡片高度本就不同，columns 顺次填充不留 grid 行对齐的空格子。
               仅两案及以上才分栏——单案分栏会让卡片只占半宽、右侧留白反而更空 */
            <div
              className={
                'space-y-[18px] ' +
                (ordered.length >= 2
                  ? 'min-[1900px]:columns-2 min-[1900px]:gap-[18px] min-[1900px]:space-y-0'
                  : '')
              }
            >
              {ordered.map((c) => (
                <div
                  key={c.id}
                  className={ordered.length >= 2 ? 'min-[1900px]:mb-[18px] min-[1900px]:break-inside-avoid' : ''}
                >
                  <CaseSection
                    c={c}
                    ambiguous={ambiguous.has(c.proc)}
                    highlighted={hl === c.id}
                    onAddLog={onAddLog}
                  />
                </div>
              ))}
            </div>
          )}
          {next && !d.casesError && (
            <div className="mt-[18px]">
              <NextStageRow stage={next} onCreate={onCreateNext} />
            </div>
          )}
        </div>

        {picked && (
          <ResizeHandle
            dragging={panelDragging}
            onPointerDown={panelPointerDown}
            onKeyAdjust={(dir) => panelSetWidth((w) => Math.max(320, w + dir * 40))}
            label="调整预览栏宽度"
          />
        )}

        <div
          className="min-w-0"
          style={picked ? { width: panelWidth, flex: 'none' } : undefined}
        >
        <DetailRail
          deadlines={deadlines}
          today={d.today}
          contactGroups={contacts}
          team={deal.team}
          deal={deal}
          moneyRows={money}
          onAddDue={onAddDue}
          onAddPayment={onAddPayment}
          onOpenFile={setPicked}
          onReviewFile={(f) => setReviewTarget(f)}
          folderPreview={
            picked ? (
              <div className="mb-2.5 flex h-[min(70vh,720px)] min-h-[420px] flex-col">
                <FilePreviewCard
                  kind="contract"
                  ownerId={deal.id}
                  file={picked}
                  onClose={() => setPicked(null)}
                  onOpenEditor={(f) => {
                    const next = new URLSearchParams(searchParams)
                    next.set('file', f.subpath)
                    if (picked?.mtime !== undefined) next.set('mtime', String(picked.mtime))
                    else next.delete('mtime')
                    setSearchParams(next)
                  }}
                  onReview={(f) => setReviewTarget(f)}
                />
              </div>
            ) : null
          }
        />
        </div>
      </div>

      <ContractFileOverlays
        ownerId={deal.id}
        client={deal.parties?.client}
        other={deal.parties?.other}
        reviewTarget={reviewTarget}
        onReviewClose={() => setReviewTarget(null)}
        onReviewStart={(f) => setReviewTarget(f)}
      />
    </main>
  )
}
