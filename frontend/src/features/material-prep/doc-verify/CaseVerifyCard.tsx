/**
 * 案件详情页里的「回传件核对」历史卡：这案核过几次、每次结论是什么、结论怎么变的。
 *
 * 与材料准备页的 `PendingRuns` 分工：那边答「现在还有几件等着我裁决」，这里答
 * 「过去核过什么」——**必须含已裁决的**，否则律师看不到某件结论是怎么被翻过来的
 * （后端 `/runs` 就是为此把已裁决件一起返回的，见 `services/verify/query.py`）。
 *
 * ## 数据只有一个来源
 *
 * 全卡只读 `listCaseRuns`（`GET /doc-verify/runs`，按案件分页 + 可带 state）。
 * 不为了「这条裁没裁过」去拼 `/unverified` 或 `/runs/{id}`：两个接口各有一种
 * 口径，拼出来的列表在两次请求之间新增一条核对就会自相矛盾。
 *
 * ## 为什么这里不做上传 / 发起核对
 *
 * `runFromMaterial` 要先选收件箱里的某个附件（message_id + part_index），那套选择
 * 界面还没定；在案件详情页里放半套入口，律师点下去只会得到一个「选不了附件」的
 * 空表单。所以卡片底部只写一句指向材料准备页的提示，发起入口仍留在那边。
 */
import { useMemo, useState, type ReactNode } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { Link } from 'react-router'

import { materialPrep } from '@/app/paths'
import { pad2 } from '@/lib/date'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

import { listCaseRuns, type FindingOut, type VerifyRunOut } from './api'

/** 每页条数：20 条够看清「核过几次」，再多首屏就该滚了。 */
const PAGE_SIZE = 20

/**
 * 每行最多摊开几条发现项。取 2（待裁决清单那边是 3）：这张卡是**历史**，
 * 一行要同时放结论、时间、覆盖率；发现项多摊一条，列表就少看见一条记录。
 * 折掉的条数显式写「还有 N 条未显示」，不假装这就是全部。
 */
const FINDINGS_SHOWN = 2

/**
 * 需律师裁决的两个状态（与后端 `domain/states.py` 的 `BLOCKING_STATES` 逐字对应）。
 * 只用来数「本页还有几条要处理」，不拿来判某一行**是否已处置**——见下方
 * `pendingShown` 的注释。
 */
const BLOCKING_STATES: readonly string[] = ['changed', 'unverifiable']

/**
 * 状态筛选档。`states` 里放的是后端 `state` 参数的**原值**，空数组 = 不带 state（全部）。
 *
 * ## 为什么「待裁决 / 已通过」各发两条请求，而不是让后端一把筛完
 *
 * 后端 `state` 参数只收**一个**值（`services/verify/query.py::list_case_runs` 按单值
 * filter，非法值直接 422），而这两档各对应两个后端状态（`BLOCKING_STATES` /
 * `PASS_STATES`）。可选的两种做法：
 *
 * - 拉全量再在前端按 state 切片：那样「筛选」是假的——首页只拿到 20 条时切片结果
 *   与真实分布无关，`total` 也变成未过滤的总数；
 * - 每个状态各发一条请求，按后端筛完的结果合并（本实现）。
 *
 * 选后者：筛选与分页都由后端出数，`hasMore` 也按各状态自己的 `total` 判。
 * 代价是这两档每次翻页发两条请求；历史卡的量级（几十条）下，这比前端切片可信。
 */
interface RunFilter {
  key: 'all' | 'pending' | 'passed'
  label: string
  states: readonly string[]
  /** 悬浮说明：口径看不出字面含义的档位要说清楚，否则律师不知道一条记录「去哪了」 */
  hint: string
}

const RUN_FILTERS: Record<RunFilter['key'], RunFilter> = {
  all: { key: 'all', label: '全部', states: [], hint: '本案的全部核对记录（含已裁决的）' },
  pending: {
    key: 'pending',
    label: '待裁决',
    states: BLOCKING_STATES,
    hint: '检出问题（changed）与无法核对（unverifiable）',
  },
  passed: {
    key: 'passed',
    label: '已通过',
    states: ['identical', 'verified_clean'],
    hint: '字节相同，或正文逐页比过且无差异；「未发现差异」是没比正文，不算通过',
  },
}

/** 筛选档的固定顺序（「全部」永远在最左，律师的心智顺序） */
const FILTER_KEYS: readonly RunFilter['key'][] = ['all', 'pending', 'passed']

/** 该案某档记录的 query key：换案件、换档位各自一份缓存，不互相污染。 */
function caseRunsKey(caseId: number, filterKey: RunFilter['key']) {
  return ['doc-verify-case-runs', caseId, filterKey] as const
}

/** 时间倒序，与后端 `-created_at,-id` 同口径；`created_at` 解析不出来时退回 id 倒序。 */
function newestFirst(a: VerifyRunOut, b: VerifyRunOut): number {
  const ta = Date.parse(a.created_at)
  const tb = Date.parse(b.created_at)
  if (Number.isFinite(ta) && Number.isFinite(tb) && ta !== tb) return tb - ta
  return b.id - a.id
}

/**
 * 按 id 去重。翻页期间新核了一条，offset 会整体后移，同一条记录可能在两页都出现；
 * 不去重的话 React key 重复，列表会少渲染或错位。
 */
function dedupeRuns(runs: VerifyRunOut[]): VerifyRunOut[] {
  const seen = new Set<number>()
  const out: VerifyRunOut[] = []
  for (const run of runs) {
    if (seen.has(run.id)) continue
    seen.add(run.id)
    out.push(run)
  }
  return out
}

interface RunsPage {
  /** 本页记录（两状态档位时已按时间倒序合并） */
  items: VerifyRunOut[]
  /** 本页之后还有记录：任一状态在 `offset + PAGE_SIZE` 之后仍有行才算「还有」 */
  hasMore: boolean
  /** 当前筛选下的总条数（后端 `total` 是**过滤后**的总数，见 `RunPageOut`） */
  total: number
}

/**
 * 取一页。单状态档位（全部）是一条请求；两状态档位各发一条再合并——
 * 服务端各筛各的，`total` 相加即该档真实总数。
 */
async function fetchRunsPage(
  caseId: number,
  states: readonly string[],
  offset: number,
  signal: AbortSignal,
): Promise<RunsPage> {
  const pages = await Promise.all(
    (states.length > 0 ? states : [undefined]).map((state) =>
      listCaseRuns({ case_id: caseId, ...(state ? { state } : {}), limit: PAGE_SIZE, offset }, signal),
    ),
  )
  return {
    items: pages.flatMap((page) => page.items).sort(newestFirst),
    total: pages.reduce((sum, page) => sum + page.total, 0),
    hasMore: pages.some((page) => offset + page.items.length < page.total),
  }
}

/** 覆盖度（后端 `domain/compare.py` 写、`services/verify/query.py` 原样回传；缺键按「不知道」处理）。 */
interface PageCoverage {
  total: number | null
  withText: number | null
  noText: number
}

function countOf(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * 覆盖度、覆盖率文案、严重度徽标这三段与 `PendingRuns` 里的同名实现**逐字同口径**：
 * 同一份 `coverage` / `findings` 在两个界面给出两种说法，律师只会信对自己有利的那句。
 * 那边是组件文件且未对外导出（本卡改动的文件边界也不含它），故照抄一份——
 * 改任何一处都要两处一起改。
 */
function pageCoverageOf(coverage: VerifyRunOut['coverage']): PageCoverage {
  const total = countOf(coverage.pages_total)
  const noText = countOf(coverage.pages_no_text)
  return {
    total,
    // 后端总会给 pages_with_text；缺的时候按总页数减缺文本页推，总页数也没有就承认不知道
    withText: countOf(coverage.pages_with_text) ?? (total != null && noText != null ? total - noText : null),
    noText: noText ?? 0,
  }
}

/**
 * 覆盖率一句话。
 *
 * `pages_no_text > 0` 必须显式写出来：那几页是图片/无文本层，比对根本没看到内容，
 * 只写「覆盖率 8/10 页」会让律师以为是随便抽了 8 页看看。
 */
function coverageTextOf(page: PageCoverage): string {
  if (page.total == null || page.withText == null) return '覆盖度：未知'
  const base = `覆盖率 ${page.withText}/${page.total} 页`
  return page.noText > 0 ? `${base} · ${page.noText} 页无文本层，未核对` : base
}

interface SeverityStyle {
  /** 给律师看的档位名，与后端 `domain/contracts.py` 的 Severity 一一对应 */
  label: string
  chip: string
  title: string
}

const SEVERITY_RED: SeverityStyle = {
  label: '红线',
  chip: 'bg-red-50 text-red-700 ring-red-200',
  title: 'text-red-700',
}
const SEVERITY_YELLOW: SeverityStyle = {
  label: '疑似',
  chip: 'bg-amber-50 text-amber-700 ring-amber-200',
  title: 'text-amber-800',
}
const SEVERITY_GRAY: SeverityStyle = {
  label: '无法核对',
  chip: 'bg-zinc-100 text-zinc-600 ring-zinc-200',
  title: 'text-zinc-600',
}

/**
 * severity → 展示样式。三档是三种处置（红线不得放行 / 疑似待确认 / 无法核对），
 * 不是三种装饰。未知值按 gray 渲染：把不认识的档位画成红线会制造假警报。
 */
function severityStyle(severity: string): SeverityStyle {
  if (severity === 'red') return SEVERITY_RED
  if (severity === 'yellow') return SEVERITY_YELLOW
  return SEVERITY_GRAY
}

/** 一条发现项：档位徽标 + 标题 + `expected → actual`（后端为空串时不渲染箭头）。 */
function FindingLine({ finding }: { finding: FindingOut }) {
  const style = severityStyle(finding.severity)
  const pair =
    finding.expected || finding.actual ? `${finding.expected || '（空）'} → ${finding.actual || '（空）'}` : ''
  return (
    <div className="flex items-start gap-1.5 text-[11.5px] leading-relaxed">
      <span className={cn('mt-px flex-none rounded px-1 text-[10px] leading-4 ring-1 ring-inset', style.chip)}>
        {style.label}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn('font-medium', style.title)}>{finding.title}</span>
        {pair && <span className="ml-1 text-muted-foreground">{pair}</span>}
      </span>
    </div>
  )
}

/** 核对时间：ISO（可能带时区偏移）→ 本地 "YYYY-MM-DD HH:mm"；解析失败原样返回，不编一个时间出来。 */
function runTimeText(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return iso
  return `${at.getFullYear()}-${pad2(at.getMonth() + 1)}-${pad2(at.getDate())} ${pad2(at.getHours())}:${pad2(at.getMinutes())}`
}

/** 一次核对：文书名 + 当时的结论 + 时间 + 覆盖率，再摊开前两条发现项。 */
function RunRow({ run }: { run: VerifyRunOut }) {
  const shown = run.findings.slice(0, FINDINGS_SHOWN)
  const hidden = run.findings.length - shown.length
  return (
    <div className="mt-2 rounded-[9px] border border-border-light bg-background p-2.5">
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate text-[13px] font-[550]" title={run.doc_type}>
          {run.doc_type}
        </span>
        <span className="flex-none text-[11px] text-muted-foreground">{run.state_label}</span>
        <span className="flex-none text-[11px] text-muted-foreground/80 tabular-nums">
          {runTimeText(run.created_at)}
        </span>
      </div>
      <div className="mt-0.5 text-[11.5px] text-muted-foreground">{coverageTextOf(pageCoverageOf(run.coverage))}</div>
      {shown.length > 0 && (
        <div className="mt-1.5 flex flex-col gap-1">
          {shown.map((finding, i) => (
            <FindingLine key={`${finding.code}-${finding.page ?? 'x'}-${i}`} finding={finding} />
          ))}
          {hidden > 0 && <div className="text-[11px] text-muted-foreground">还有 {hidden} 条未显示</div>}
        </div>
      )}
    </div>
  )
}

/** 筛选小段按钮：与案件卡里「日志 / 文件夹」的段按钮同一套尺寸与配色。 */
function FilterBtn({
  active,
  hint,
  onClick,
  children,
}: {
  active: boolean
  hint: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={hint}
      aria-pressed={active}
      onClick={onClick}
      className={
        'cursor-pointer rounded-[5px] px-2 py-[2px] text-[11px] leading-[1.5] transition-colors ' +
        (active
          ? 'bg-secondary font-[620] text-secondary-foreground'
          : 'text-muted-foreground hover:text-foreground')
      }
    >
      {children}
    </button>
  )
}

/**
 * 某案件的核对历史卡（嵌在案件卡下方，不另起一张大标题卡片）。
 *
 * 空态写「本案还没有核对记录」而不是整块消失：律师回看一个案子时，「这案一次都
 * 没核过」本身就是结论，缺了它律师会以为是没加载出来。
 */
export function CaseVerifyCard({ caseId }: { caseId: number }) {
  const [filterKey, setFilterKey] = useState<RunFilter['key']>('all')
  const filter = RUN_FILTERS[filterKey]

  const query = useInfiniteQuery({
    queryKey: caseRunsKey(caseId, filterKey),
    queryFn: ({ pageParam, signal }) => fetchRunsPage(caseId, filter.states, pageParam, signal),
    initialPageParam: 0,
    // 任一状态还有余量就允许再翻一页；两状态档位的 offset 同步后移，合并时再去重
    getNextPageParam: (lastPage, _pages, lastOffset) =>
      lastPage.hasMore ? lastOffset + PAGE_SIZE : undefined,
  })

  const runs = useMemo(
    () => dedupeRuns(query.data?.pages.flatMap((page) => page.items) ?? []).sort(newestFirst),
    [query.data],
  )
  const total = query.data?.pages[0]?.total ?? 0

  /**
   * 底部「有 N 条待裁决」只按**已加载的**记录数，且只作提示、不指向具体行。
   *
   * 为什么做不到「每一行判是否已处置」：后端 `VerifyRunOut` 目前没有裁决字段
   * （`services/verify/query.py::run_detail` 只回「这次核出了什么」），前端只靠
   * `listCaseRuns` 一个数据源时无从得知某条是否已被 accept/reject。逐行挂「去处理」
   * 会让已经采纳过的行也带入口，点过去在材料准备页的待裁决清单里根本找不到它——
   * 那比没有入口更糟。等后端补 `last_decision_action` 后，这里再按行显示
   * 「已采纳 / 已退回」并只给真正未处置的行放入口；在那之前不在前端拼两个接口模拟。
   */
  const pendingShown = runs.filter((run) => BLOCKING_STATES.includes(run.state)).length

  return (
    <section
      aria-label="回传件核对"
      className="mt-2.5 rounded-[12px] border border-border bg-card px-5 py-3 shadow-sm max-[680px]:px-3.5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <b className="text-[13px] font-[680]">回传件核对</b>
        {query.data && <span className="text-[11.5px] text-muted-foreground tabular-nums">共 {total} 条</span>}
        <span className="ml-auto flex rounded-[7px] border border-border-light p-[2px]">
          {FILTER_KEYS.map((key) => (
            <FilterBtn
              key={key}
              active={key === filterKey}
              hint={RUN_FILTERS[key].hint}
              onClick={() => setFilterKey(key)}
            >
              {RUN_FILTERS[key].label}
            </FilterBtn>
          ))}
        </span>
      </div>

      {query.isPending && (
        <div className="mt-1.5 flex items-center gap-2 text-[12px] text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> 加载中…
        </div>
      )}
      {query.isError && (
        <div className="mt-1.5 text-[12px] text-muted-foreground">
          核对记录加载失败：{errMessage(query.error, '未知错误')}
        </div>
      )}
      {query.data && runs.length === 0 && (
        <div className="mt-1.5 text-[12px] text-muted-foreground">
          {/* 「这一档没有」不能说成「本案没有」：筛到待裁决时为空，不等于一次都没核过 */}
          {filterKey === 'all' ? '本案还没有核对记录' : '这一档没有核对记录'}
        </div>
      )}

      {runs.map((run) => (
        <RunRow key={run.id} run={run} />
      ))}

      {query.data && (
        <div className="mt-2 flex items-center gap-2">
          {query.hasNextPage ? (
            <button
              type="button"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
              className="w-full rounded-[8px] border border-border px-2.5 py-1.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-60"
            >
              {query.isFetchingNextPage ? '加载中…' : '加载更多'}
            </button>
          ) : (
            total > 0 && <span className="text-[11px] text-muted-foreground">已全部加载</span>
          )}
        </div>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-light pt-2 text-[11px] text-muted-foreground">
        {pendingShown > 0 && (
          <Link
            to={materialPrep()}
            title="按已加载的记录统计；完整清单在材料准备页"
            className="cursor-pointer font-medium text-secondary-foreground underline decoration-border underline-offset-3 hover:decoration-foreground"
          >
            有 {pendingShown} 条待裁决 → 去材料准备页处理
          </Link>
        )}
        <span className="ml-auto">上传回传件、发起核对在材料准备页</span>
      </div>
    </section>
  )
}
