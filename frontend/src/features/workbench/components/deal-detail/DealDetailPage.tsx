import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  ambiguousStages,
  buildDeadlines,
  buildStagePlan,
  chainSteps,
  chainSummary,
  contactGroups as groupContacts,
  moneyRows,
  nextStage,
  planCases,
} from './detail-domain'
import { CaseSection, NextStageRow } from './CaseSection'
import { ChainStepper } from './ChainStepper'
import { openCopilot } from '@/features/copilot/launch'
import { useMediaQuery } from '@/hooks/use-media'

import { DetailHeader } from './DetailHeader'
import { DetailRail } from './DetailRail'
import { useDealAiResize } from './use-deal-ai-resize'
import { useDealDetail } from './use-deal-detail'

const AI_OPEN_KEY = 'deal:ai-open'

// 详情页专属 AI 工作区（宽屏三列布局的第三列，非全局浮层）：走动态
// import 保持 copilot 域的懒加载边界——静态引入会把 react-markdown 等
// 拖进办案 chunk
const CopilotEmbedLazy = lazy(() => import('@/features/copilot').then((m) => ({ default: m.CopilotEmbed })))

/**
 * 52 号定则：过去在时间轴（案件节日志按日叙事），未来在右栏（期限只在这里预警）。
 * 左列只放案件本身（程序链 + 下一步），合同层面的当事人/收款/补充协议/要素全在右栏卡里。
 */
export function DealDetailPage() {
  const { id } = useParams<{ id: string }>()
  const contractId = Number(id)
  const valid = Number.isInteger(contractId) && contractId > 0
  const d = useDealDetail(valid ? contractId : null)
  /** stepper 跳转后的短暂高亮环（案件 id） */
  const [hl, setHl] = useState<number | null>(null)
  // AI 工作区（宽屏专属）：长在详情页布局里的第三列——左列案件卡压缩但不
  // 遮挡，对话区 sticky 满视口高、宽度可拖（默认 640，为未来 OnlyOffice
  // 文档预览预留内部再分栏的空间）。窄屏（<1280）装不下三列，页头按钮
  // 回落到全局浮层面板（既有形态）。
  const [aiOpen, setAiOpen] = useState(() => {
    try {
      return localStorage.getItem(AI_OPEN_KEY) === '1'
    } catch {
      return false
    }
  })
  const isXlUp = useMediaQuery('(min-width: 1280px)')
  const { width: aiWidth, setGridRef, onHandlePointerDown } = useDealAiResize()
  const aiActive = aiOpen && isXlUp

  const deal = d.deal
  // 程序计划以合同勾选的代理阶段为纲、案件实际阶段为实：勾了没立的是未启动，立了没勾的照样展示
  const plan = useMemo(() => buildStagePlan(deal?.stages ?? [], d.cases), [deal?.stages, d.cases])
  const ordered = useMemo(() => planCases(plan), [plan])
  const steps = useMemo(() => chainSteps(plan), [plan])
  const next = nextStage(plan)
  const deadlines = useMemo(
    () => buildDeadlines(d.contractReminders, ordered, d.caseReminders, d.today),
    [d.contractReminders, ordered, d.caseReminders, d.today],
  )
  const contacts = useMemo(() => groupContacts(ordered), [ordered])
  const ambiguous = useMemo(() => ambiguousStages(plan), [plan])
  const money = useMemo(() => (deal ? moneyRows(deal, ordered) : []), [deal, ordered])

  /* 创建类动作本轮先占位（样式定稿后接表单）：记日志 / 新增期限 / 新建下一程序案件 / 记收款 */
  const soon = useCallback((what: string) => toast.info(what + '正在开发中'), [])
  const onAddLog = useCallback(() => soon('记办案日志'), [soon])
  const onAddDue = useCallback(() => soon('新增期限'), [soon])
  const onCreateNext = useCallback(() => soon('新建' + (next ?? '') + '案件'), [soon, next])
  const onAddPayment = useCallback(() => soon('记收款'), [soon])

  /* 工作区高度动态适配：sticky 只保证「滚动后贴顶」，初始位置仍在文档流里
     （页头 + stepper 之下，标题折行时更低）——按满视口高的固定值会把输入框
     顶出第一屏。改为 innerHeight − max(容器实际 top, navbar+14) − 14：
     首屏输入框贴视口底，滚动 sticky 生效后贴满视口高，滚动/resize 实时跟。 */
  const aiDockRef = useRef<HTMLDivElement>(null)
  const [aiDockH, setAiDockH] = useState<number | null>(null)
  useEffect(() => {
    if (!aiActive) {
      setAiDockH(null)
      return
    }
    const el = aiDockRef.current
    if (!el) return
    const navTop =
      (Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--app-navbar-h')) || 54) + 14
    const measure = () => {
      const floor = Math.max(el.getBoundingClientRect().top, navTop)
      setAiDockH(Math.max(340, window.innerHeight - floor - 14))
    }
    measure()
    // 数据刚到、字体/图片陆续就位会让首测的 top 漂移：下一帧再校一次
    requestAnimationFrame(measure)
    window.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('scroll', measure)
      window.removeEventListener('resize', measure)
    }
    // 依赖 deal：记忆直开（aiOpen 初始即 true）时首渲染还在 loading，
    // 容器未挂载、el 为 null；数据到达后必须重跑才能拿到真实元素
  }, [aiActive, deal])

  const toggleAi = useCallback(() => {
    setAiOpen((v) => {
      try {
        localStorage.setItem(AI_OPEN_KEY, v ? '0' : '1')
      } catch {
        /* 忽略持久化失败 */
      }
      return !v
    })
  }, [])

  // 页面感知精确覆盖：通用助手注入的锚点带上委托名与 contract_id，
  // 模型可拿 id 用 get_contract / read_folder_file 等工具了解页面内容
  useEffect(() => {
    if (!deal) return
    void import('@/features/copilot/store').then((m) => {
      m.useCopilot.getState().setPageHint(`委托详情 · ${deal.client}（contract_id=${deal.id}）`)
    })
  }, [deal])

  const jump = useCallback((caseId: number) => {
    document.getElementById('case-' + caseId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setHl(caseId)
  }, [])
  useEffect(() => {
    if (hl == null) return
    const t = window.setTimeout(() => setHl(null), 1800)
    return () => window.clearTimeout(t)
  }, [hl])

  if (!valid) return <Navigate to="/cases" replace />
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
  if (!deal.lit) {
    return (
      <NonLitNotice name={deal.client} />
    )
  }

  return (
    <main className="app-page-enter mx-auto max-w-[1280px] px-[30px] pt-[26px] pb-20 min-[1400px]:max-w-[1400px] min-[1900px]:max-w-[1760px] min-[2400px]:max-w-[2200px] min-[2600px]:max-w-[2480px] max-[680px]:px-3 max-[680px]:pt-4">
      <DetailHeader
        deal={deal}
        onAddDue={onAddDue}
        onAddLog={onAddLog}
        onOpenAi={
          isXlUp
            ? toggleAi
            : // 窄屏装不下专属工作区，回落全局浮层（openCopilot 零依赖模块，静态引入无负担）
              () => openCopilot({ origin: 'contract', refId: deal.id, title: deal.client })
        }
      />

      <ChainStepper steps={steps} summary={chainSummary(plan)} onJump={jump} />

      <div
        ref={setGridRef}
        className="grid grid-cols-[minmax(0,1fr)_400px] items-start gap-[18px] max-[1024px]:grid-cols-1 min-[1900px]:grid-cols-[minmax(0,1fr)_440px] min-[2400px]:grid-cols-[minmax(0,1fr)_480px]"
        style={
          aiActive
            ? ({
                '--deal-ai-w': `${aiWidth}px`,
                gridTemplateColumns: 'minmax(320px,1fr) 400px var(--deal-ai-w)',
              } as React.CSSProperties)
            : undefined
        }
      >
        <div className="min-w-0">
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
                (ordered.length >= 2 && !aiActive
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

        <DetailRail
          deadlines={deadlines}
          today={d.today}
          contactGroups={contacts}
          team={deal.team}
          deal={deal}
          moneyRows={money}
          onAddDue={onAddDue}
          onAddPayment={onAddPayment}
        />

        {aiActive && (
          /* 工作区列：sticky 满视口高（页头下），页面滚动时对话区不动——
             律师边滚案件日志边对话；左缘把手拖宽（--deal-ai-w 驱动 grid 列） */
          <div
            ref={aiDockRef}
            className="sticky top-[calc(var(--app-navbar-h)_+_14px)] h-[calc(100dvh_-_var(--app-navbar-h)_-_28px)] min-w-0"
            style={aiDockH ? { height: aiDockH } : undefined}
          >
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="调整 AI 工作区宽度"
              className="absolute top-0 bottom-0 left-0 z-30 w-1.5 -translate-x-1/2 cursor-col-resize touch-none transition-colors hover:bg-foreground/25"
              onPointerDown={onHandlePointerDown}
            />
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center rounded-[12px] border border-border bg-card text-[12.5px] text-muted-foreground shadow-sm">
                  正在载入 AI 助手…
                </div>
              }
            >
              <CopilotEmbedLazy origin="contract" refId={deal.id} title={deal.client} />
            </Suspense>
          </div>
        )}
      </div>
    </main>
  )
}

function DetailError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <main className="app-page-enter mx-auto max-w-lg px-6 pt-[80px]">
      <div className="rounded-[14px] border border-destructive/30 bg-destructive/5 px-5 py-4 text-center text-sm text-destructive">
        {error}
        <button type="button" className="ml-3 cursor-pointer underline underline-offset-3" onClick={onRetry}>
          重试
        </button>
        <Link to="/cases" className="ml-3 cursor-pointer underline underline-offset-3">
          返回办案
        </Link>
      </div>
    </main>
  )
}

/** 非诉委托（专项 / 常法）详情页另轮设计（53/54 号），直达时明确说没做而不是硬渲染诉讼骨架 */
function NonLitNotice({ name }: { name: string }) {
  return (
    <main className="app-page-enter mx-auto max-w-lg px-6 pt-[80px] text-center">
      <div className="mb-2 truncate text-sm font-[550] text-secondary-foreground" title={name}>
        {name}
      </div>
      <div className="rounded-[14px] border border-border bg-card px-5 py-6 text-[13px] text-muted-foreground shadow-sm">
        非诉详情页正在设计中，档案快览可回办案主页右键行打开
        <div className="mt-3">
          <Link to="/cases" className="cursor-pointer underline underline-offset-3">
            返回办案
          </Link>
        </div>
      </div>
    </main>
  )
}
