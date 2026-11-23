import { Fragment, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, FileCode2 } from 'lucide-react'

import { blockKeyOf, reviewHintOf } from '../../draft'
import type { EngineDisagreement, Inconsistency, Segment } from '../../types'
import { rectPrecisionOf } from '../../types'
import { SegmentQualityHint, type DocHintPage } from './SegmentQualityHint'
import { SegmentMarkdownView, type MarkdownViewMode } from './SegmentMarkdownView'
import { BlockRow } from './SegmentRow'
import { PageAnchoredHints } from './PageAnchoredHints'
import { SuspectsPanel } from './SuspectsPanel'
import { SegmentMarkdownTabs } from './SegmentMarkdownTabs'
import { groupDisagreementsByPage, groupDocHintsByPage } from './segment-markdown-page-groups'

/**
 * 右侧栏的「Markdown 正文」面板（云端识别的取字结果）。
 *
 * ## 为什么需要它
 *
 * 自动分段一直在产出 `seg.md`，但此前**没有任何 UI 展示**——只被「识别当事人」
 * 与「推断文本」在后台消费掉。律师看不到机器读出了什么，等于整条识别链路是黑盒。
 *
 * ## 为什么在右栏而不是嵌在每段页面之上
 *
 * 一版曾把它放在段头下方。正文动辄数千字，展开后把这些段落之间的页面全推到
 * 屏幕外，「边看正文边对照原页」反而做不到。右栏与页面流并排常驻，
 * 滚动互不干扰，才是「原文对照」的正确形态。
 *
 * ## 对照靠双击，不靠单击
 *
 * 单击只是选中一行文字（阅读时的自然动作），**双击**才跳转并在原页亮出定位框。
 * 默认状态下页面上的识别框全部按常态显示——不预先高亮任何一条，
 * 否则一进阅读器满屏都是「重点」，反而看不出哪条对应哪里。
 *
 * 高亮是**互斥**的：定位一个块时其余框淡化，只留这一条 + 它的原页位置。
 *
 * ## 可疑点标记
 *
 * 识别不可能全对（OCR 认错数字/日期、表格拍平、空块……），但律师没法拿一段几千字
 * 的正文逐字核对原页——于是 `findSuspects` 给出可疑点，这里在正文下方挂一个可折叠
 * 清单（每条带命中原文 + 「查看原页」）。
 *
 * **为什么不在行内画小圆点**：`findSuspects` 的行号是 markdown 行号，而面板渲染的是
 * `blocks`，两者无对应关系（一个表格块在 md 里展开成几十行），按行号画必然指错行。
 * 标注指错比不标注更糟——律师会连带不信其它正确的标注。详细权衡见 `SuspectsPanel.tsx`。
 *
 * ## 质量提示（图纸 / 稀疏页）
 *
 * 可疑点是「这几个字可能认错了」，质量提示是「这一段根本看不出内容」——两件事。
 * 所以提示条放在标题下方（进面板第一眼就看到），而不是混进正文后的可疑点清单。
 */
export function SegmentMarkdown({
  seg,
  open,
  onToggleOpen,
  focusedBlockKey,
  onLocateBlock,
  editRequestKey,
  editRequestSeed = null,
  onEditRequestHandled,
  onEditMarkdown,
  onEditBlock,
  onRemoveBlock,
  graphicPages = [],
  docPages = [],
  onGotoPage,
  engineItems = [],
  engineKeys = [],
  engineChecked = [],
  onToggleEngineChecked,
  onJumpEngine,
  onAdoptEngine,
  onEditEngine,
  inconsistencies = [],
}: {
  seg: Segment | null
  /** 展开态由父级持有（右栏其它块共用同一个折叠开关，避免各自记住状态） */
  open: boolean
  onToggleOpen: () => void
  /** 当前高亮的块 key；null = 不高亮任何框 */
  focusedBlockKey: string | null
  /** 双击某一条 → 滚到原页并高亮该框（传 null 表示取消） */
  onLocateBlock: (key: string | null) => void
  /**
   * 「请对这块进入修改态」的一次性请求（来自页面框双击）。
   * 消费后要调 `onEditRequestHandled` 清空，否则后续同块高亮会反复弹输入框。
   */
  editRequestKey?: string | null
  /** 进入修改态时要预填的文本（缺省用本行原文） */
  editRequestSeed?: string | null
  onEditRequestHandled?: () => void
  /** 手改正文（识别错字/表格拍平时律师自己修）——没有定位块时的整段编辑 */
  onEditMarkdown?: (md: string) => void
  /** 改某一行（定位块）的文字；同步进 Markdown 正文 */
  onEditBlock?: (key: string, text: string) => void
  /** 删掉一个画错的定位框（只删坐标，不动正文） */
  onRemoveBlock?: (key: string) => void
  /** 本段页范围里疑似图纸/照片的页号（来自 summary.page_quality，旧任务为空） */
  graphicPages?: number[]
  /** 本段覆盖的证件页与各自未读出的字段（`page_quality.doc_hints`，旧任务为空） */
  docPages?: DocHintPage[]
  /** 点提示条跳原页；不传则提示条不可点（只陈述事实） */
  onGotoPage?: (page: number) => void
  /** 全卷引擎分歧（会先按本段页范围过滤，再按页号挂到该页第一行之前） */
  engineItems?: EngineDisagreement[]
  /** 与 `engineItems` 一一对应的唯一键 */
  engineKeys?: string[]
  engineChecked?: string[]
  onToggleEngineChecked?: (key: string, checked: boolean) => void
  onJumpEngine?: (pageNo: number, key: string) => void
  onAdoptEngine?: (pageNo: number, text: string, disagreeKey?: string) => void
  /** 「修改」：两侧都不对时进编辑态 */
  onEditEngine?: (pageNo: number, text: string, disagreeKey?: string) => void
  /** 全卷不一致统计：用于「更推荐改成什么」 */
  inconsistencies?: Inconsistency[]
}) {
  // 正在编辑的那一行的 key；null = 全部只读
  const [editingKey, setEditingKey] = useState<string | null>(null)
  /** 进入编辑态时要预填的文本（「两个引擎都不对」时点采用，用该侧全文作起点） */
  const [editSeed, setEditSeed] = useState<string | null>(null)
  /**
   * 右栏正文看见的是哪一种：分块 / 渲染 / 源码（+ 编辑整段）。
   *
   * **只有这一份视图状态**。此前是「父级的 rawView 布尔」+「子组件自己的三态」两套
   * 切换器叠着，切到原始 Markdown 之后控件从两个变三个、选中态还换一套样式——
   * 一个侧边栏里三行控件就是这么来的。tab、✎、页面框双击三个入口都改这一个状态。
   */
  const [view, setView] = useState<MarkdownViewMode | 'blocks'>('blocks')

  /**
   * 页面框双击 → 自动进入这一行的修改态。
   *
   * 用 effect 而不是在渲染里直接 setEditingKey：渲染期改 state 会触发
   * React 的重渲染警告，而且这个信号是「事件驱动的副作用」，本就属于 effect。
   * 消费完立即回调清空，保证一次性语义（否则同一块再高亮会又弹一次输入框）。
   */
  useEffect(() => {
    if (!editRequestKey) return
    if (!onEditBlock) {
      // 没有逐块编辑能力（无定位块的段）：退回整段编辑
      if (onEditMarkdown) setView('edit')
    } else {
      // 逐块编辑只在「分块」视图里有行可改：从源码/渲染视图切回来
      setView('blocks')
      setEditSeed(editRequestSeed)
      setEditingKey(editRequestKey)
    }
    onEditRequestHandled?.()
  }, [editRequestKey, editRequestSeed, onEditBlock, onEditMarkdown, onEditRequestHandled])


  if (!seg) return null

  // 人工拆分 / 本地 OCR / 旧任务都没有 md：明确说"没有"，而不是渲染空白
  if (!seg.md) {
    if (seg.manual) return null
    return (
      <div className="flex flex-col gap-1">
        {/* 没有正文恰恰是最该说清「要复核什么」的情况：律师连读的地方都没有 */}
        <SegmentQualityHint review={reviewHintOf(seg)} />
        <div className="flex items-start gap-1.5 rounded-lg border border-zinc-200 bg-secondary/40 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
          <FileCode2 className="mt-0.5 h-3 w-3 flex-none opacity-60" aria-hidden />
          <span>该段没有 Markdown 正文（本地 OCR 或人工拆分不产出正文重建）</span>
        </div>
      </div>
    )
  }

  const blocks = seg.blocks ?? []

  // 按页分组（分歧 / 证件页提示 / 图纸页）是纯函数，见 segment-markdown-page-groups.ts
  const byPage = groupDisagreementsByPage({
    engineItems,
    engineKeys,
    pageNos: seg.refs.map((r) => r.p),
  })
  const { docByPage, graphicPages: graphicSet, orphanHintPages } = groupDocHintsByPage({
    docPages,
    graphicPages,
    blocks,
  })
  /**
   * 没有定位块（本地 OCR / 旧任务）时没有「分块」这一档，落到渲染视图。
   * 归一在这里做而不是 useState 初值：hooks 必须跑在 `seg` 早返回之前，那时还拿不到 blocks。
   */
  const tab: MarkdownViewMode | 'blocks' = view === 'blocks' && blocks.length === 0 ? 'render' : view

  return (
    <div className="@container flex flex-col gap-1.5">
      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={open}
        className="flex w-full items-center gap-1 px-1 text-left text-sm font-medium transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 flex-none" aria-hidden />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-none" aria-hidden />
        )}
        <FileCode2 className="h-3.5 w-3.5 flex-none opacity-70" aria-hidden />
        <span>Markdown 正文</span>
        <span className="ml-auto flex-none text-[11px] font-normal tabular-nums text-muted-foreground">
          {seg.md.length} 字
        </span>
      </button>

      {/* 段级提示紧贴标题之下：自动分段切错边界/起错名，错的可能是整段（把别的材料
          末尾混进来），必须在律师开始读之前说。逐页的问题（证件页缺字段 / 图纸页）
          不在这儿——它们挂到正文里对应页的第一行之前，见 PageAnchoredHints。 */}
      <SegmentQualityHint review={reviewHintOf(seg)} flags={seg.qualityFlags} />

      {/* 块改动没同步进正文：必须说出来。静默留旧值就是「以为改好了其实没改」，
          折叠态也要看得见，否则律师根本不知道有这回事。 */}
      {seg.mdDrift && (
        <p className="rounded-lg border border-amber-300 bg-amber-50/60 px-2.5 py-1.5 text-[11px] leading-relaxed text-amber-800">
          有一处块改动没能同步进 Markdown 正文（改前的原文已对不上）。请切到「源码」核对整段，否则下游拿到的还是旧文字。
        </p>
      )}

      {open && (
        <div className="flex flex-col gap-1">
          {/* 唯一的视图切换器（见 SegmentMarkdownTabs：tab / ✎ / 双击三个入口
              改的是同一个 view 状态；编辑态整行不渲染，免得不小心丢掉未保存正文） */}
          {tab !== 'edit' && (
            <SegmentMarkdownTabs
              tab={tab}
              hasBlocks={blocks.length > 0}
              onSelect={setView}
              focusedBlockKey={focusedBlockKey}
              onLocateBlock={onLocateBlock}
              onEditMarkdown={onEditMarkdown}
            />
          )}

          {/* 默认「列表即正文」：每行就是原文的一段，改动直接在这行上做，双击能定位原页。
              渲染 / 源码是**切换**过去的另两个视图（看表格/标题结构、整段修订），
              不是并排再渲染一份——同一段内容出现两次，看的人要来回比对"刚才改的是不是这一行"。 */}
          {tab === 'blocks' ? (
            blocks.map((b, i) => {
              const key = blockKeyOf(seg, b, i)
              // 该页第一行之前挂上这一页的分歧：律师读到 P1 的正文前，
              // 先看到「P1 有 2 处两引擎读得不一样」。
              // 判据用「上一行的页号不同」，而不是「本行是第 0 行」——
              // 一个 block 可能有多行同页，插在首行前才自然。
              const isFirstOfPage = i === 0 || blocks[i - 1]!.page !== b.page
              const pageBucket = isFirstOfPage ? byPage.get(b.page) : undefined
              return (
                <Fragment key={key}>
                  {isFirstOfPage && (
                    <PageAnchoredHints
                      page={b.page}
                      bucket={pageBucket}
                      docByPage={docByPage}
                      graphicPages={graphicSet}
                      onGotoPage={onGotoPage}
                      seg={seg}
                      engineChecked={engineChecked}
                      onJumpEngine={onJumpEngine}
                      onToggleEngineChecked={onToggleEngineChecked}
                      onAdoptEngine={onAdoptEngine}
                      onEditEngine={onEditEngine}
                      inconsistencies={inconsistencies}
                    />
                  )}
                  <BlockRow
                    key={key}
                    blockKey={key}
                    text={b.text || ''}
                    page={b.page}
                    approx={b.rect.approx}
                    // 后端 precision 是 string（openapi 里没做成枚举），用 rectPrecisionOf 收窄成
                    // 四档联合类型；旧草稿没有该字段时它按 approx 退化，与画框同一口径。
                    precision={rectPrecisionOf(b.rect)}
                    active={key === focusedBlockKey}
                    editing={editingKey === key}
                    seedText={editingKey === key ? editSeed : null}
                    onLocate={onLocateBlock}
                    onRemove={onRemoveBlock}
                    onStartEdit={
                      onEditBlock
                        ? (k) => {
                            setEditSeed(null)
                            setEditingKey(k)
                          }
                        : undefined
                    }
                    onCommitEdit={(text) => {
                      onEditBlock?.(key, text)
                      setEditingKey(null)
                      setEditSeed(null)
                    }}
                    onCancelEdit={() => {
                      setEditingKey(null)
                      setEditSeed(null)
                    }}
                  />
                </Fragment>
              )
            })
          ) : (
            <SegmentMarkdownView
              md={seg.md}
              mode={tab}
              onModeChange={setView}
              onCommit={onEditMarkdown}
            />
          )}

          {/* 落不到正文行的提示页（图纸页多半一个字都没取出来）：只能自己成行 */}
          {tab === 'blocks' && orphanHintPages.length > 0 && (
            <div className="flex flex-col gap-1">
              {orphanHintPages.map((page) => (
                <PageAnchoredHints
                  key={`hint-${page}`}
                  page={page}
                  docByPage={docByPage}
                  graphicPages={graphicSet}
                  onGotoPage={onGotoPage}
                  seg={seg}
                  engineChecked={engineChecked}
                  onJumpEngine={onJumpEngine}
                  onToggleEngineChecked={onToggleEngineChecked}
                  onAdoptEngine={onAdoptEngine}
                  onEditEngine={onEditEngine}
                  inconsistencies={inconsistencies}
                />
              ))}
            </div>
          )}

          {/* 可疑点清单：放在正文之后。先读正文，读到觉得不对的地方再回头查清单。 */}
          <SuspectsPanel seg={seg} onLocate={onLocateBlock} />
        </div>
      )}
    </div>
  )
}
