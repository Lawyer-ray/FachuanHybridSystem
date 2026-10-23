import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { withDownloadTicket } from '@/lib/download-ticket'
import { getCaseFolderBinding } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import type { DealCase } from '../../types'
import { caseMetaParts, legalStatusGroups, shortDocName, splitLinkText, timelineEntries } from './detail-domain'
import { FolderTree } from './FolderTree'
import { ActionButton, Card, Chip, MetaLine, Pill, StateDot } from './ui'

/** 附件新标签预览：media 走一次性 ticket（60s 单次），失败时后端 403 兜底 */
async function openAttachment(mediaUrl: string) {
  window.open(await withDownloadTicket(mediaUrl), '_blank', 'noopener')
}

/** 视图切换小段按钮（日志 / 文件夹） */
function SegBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'cursor-pointer rounded-[5px] px-2 py-[2px] text-[11px] leading-[1.5] transition-colors ' +
        (active ? 'bg-secondary font-[620] text-secondary-foreground' : 'text-muted-foreground hover:text-foreground')
      }
    >
      {children}
    </button>
  )
}

/**
 * 程序节（一桩案件）：状态点 + 阶段名 + 已结/在办 + 案号 chips ＋ meta 行（机构/收案/案由/标的/保全）
 * ＋ 诉讼地位行 ＋ 该案内容（日志时间轴或绑定文件夹浏览，可切换；绑定可达时默认文件夹——
 * 手工整理的目录比 AI 写入的日志更一目了然）。同阶段多案时补案名消歧。
 */
export function CaseSection({
  c,
  ambiguous,
  highlighted,
  onAddLog,
}: {
  c: DealCase
  /** 同阶段多案（如按被告分立）时节标题带案名才分得清 */
  ambiguous: boolean
  /** stepper 跳转后的短暂高亮环 */
  highlighted: boolean
  onAddLog: () => void
}) {
  const legGroups = legalStatusGroups(c)
  const entries = timelineEntries(c)

  /* 绑定存在才显示切换；用户点过以点为准，否则可达即默认文件夹视图 */
  const bindingQ = useQuery({
    queryKey: workbenchKeys.caseFolderBinding(c.id),
    queryFn: () => getCaseFolderBinding(c.id),
    staleTime: 5 * 60_000,
    retry: false,
  })
  const binding = bindingQ.data ?? null
  const [viewOverride, setViewOverride] = useState<'logs' | 'folder' | null>(null)
  const view: 'logs' | 'folder' = viewOverride ?? (binding ? 'folder' : 'logs')

  return (
    <Card
      id={'case-' + c.id}
      className={
        'scroll-mt-[76px] transition-shadow duration-700 ' + (highlighted ? 'shadow-[0_0_0_3px_rgba(24,24,27,0.14)]' : '')
      }
    >
      <div className="flex flex-wrap items-baseline gap-2.5 px-5 pt-[15px] max-[680px]:px-3.5">
        <span className="relative top-[-1px]">
          <StateDot state={c.done ? 'done' : 'cur'} size={c.done ? 9 : 10} />
        </span>
        <b className="text-[15.5px] font-[720] tracking-[-0.015em]" title={c.name}>
          {c.proc}
        </b>
        <Pill>{c.done ? '已结' : '在办'}</Pill>
        {c.numbers.map((n) => (
          <Chip key={n}>{n}</Chip>
        ))}
        <span className="relative top-[-2px] ml-auto flex items-center gap-2">
          {binding && (
            <span className="flex rounded-[7px] border border-border-light p-[2px]">
              <SegBtn active={view === 'logs'} onClick={() => setViewOverride('logs')}>
                日志
              </SegBtn>
              <SegBtn active={view === 'folder'} onClick={() => setViewOverride('folder')}>
                文件夹
              </SegBtn>
            </span>
          )}
          {view === 'logs' && (
            <ActionButton sm onClick={onAddLog}>
              ＋ 记日志
            </ActionButton>
          )}
        </span>
      </div>
      {ambiguous && (
        <div className="truncate px-5 pt-1 text-xs text-muted-foreground max-[680px]:px-3.5" title={c.name}>
          {c.name}
        </div>
      )}

      <MetaLine
        parts={caseMetaParts(c)}
        className="px-5 pt-[7px] text-[12.5px] leading-[1.9] text-muted-foreground tabular-nums max-[680px]:px-3.5"
      />

      {legGroups.length > 0 && (
        <div className="mx-5 mt-[9px] flex flex-col gap-px rounded-[9px] border border-border-light bg-background px-3 py-2 text-[12.5px] leading-[1.9] text-muted-foreground max-[680px]:mx-3.5">
          {/* 一行一个地位，判决书逻辑顺序（原告 → 被告 → 第三人），排序在 legalStatusGroups */}
          {legGroups.map((g) => (
            <div key={g.status}>
              <b className="font-[620] text-secondary-foreground">{g.status}</b> {g.names.join('、')}
            </div>
          ))}
        </div>
      )}

      {view === 'folder' && binding ? (
        <div className="px-5 pt-2 pb-4 max-[680px]:px-3.5">
          <FolderTree kind="case" ownerId={c.id} />
        </div>
      ) : (
        <div className="px-5 pt-3.5 pb-1.5 max-[680px]:px-3.5">
          {entries.length === 0 ? (
            <div className="py-2 text-xs text-muted-foreground/70">还没有办案日志</div>
          ) : (
            entries.map((e, i) => (
              <div
                key={e.key}
                className={
                  'relative grid grid-cols-[80px_16px_1fr] pb-[15px] max-[680px]:grid-cols-[66px_14px_1fr] ' +
                  (i === entries.length - 1 ? 'pb-2' : '')
                }
              >
                {/* 竖线贯穿到下一条（最后一条不画），点用元素而非伪元素便于对齐 */}
                {i < entries.length - 1 && (
                  <span className="absolute top-3.5 -bottom-1 left-[87px] w-px bg-border-light max-[680px]:left-[72px]" />
                )}
                <span className="pt-px text-right text-xs whitespace-nowrap text-muted-foreground tabular-nums">{e.date}</span>
                <span className="relative">
                  <span className="absolute top-[6px] left-[5px] size-[7px] rounded-full bg-border" />
                </span>
                <span className="min-w-0 pl-1.5">
                  {/* 日志正文可能含法院短信里的长 URL：切分段渲染，URL 显示为
                      「查看链接」超链接（新标签打开）；纯文本段仍 break-words
                      防止不可断行串撑破窄屏 */}
                  <span className="block text-[13.5px] leading-[1.55] break-words text-secondary-foreground">
                    {splitLinkText(e.text).map((seg, si) =>
                      seg.kind === 'url' ? (
                        <a
                          key={si}
                          href={seg.value}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={seg.value}
                          className="cursor-pointer text-primary underline decoration-primary/40 underline-offset-3 hover:decoration-primary"
                        >
                          查看链接 ↗
                        </a>
                      ) : (
                        <span key={si}>{seg.value}</span>
                      ),
                    )}
                  </span>
                  {(e.who || e.n > 1) && (
                    <span className="mt-0.5 block text-[11.5px] text-muted-foreground/80 tabular-nums">
                      {e.who}
                      {e.n > 1 && (
                        <span className="ml-2" title={'相同内容的日志已合并（共 ' + e.n + ' 条）'}>
                          ×{e.n}
                        </span>
                      )}
                    </span>
                  )}
                  {e.atts.length > 0 && (
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {e.atts.map((a) => (
                        <button
                          key={a.id}
                          type="button"
                          title={'预览 ' + a.name}
                          onClick={() => void openAttachment(a.mediaUrl)}
                          className="inline-flex max-w-full min-w-0 cursor-pointer items-center rounded-[6px] border border-border-light bg-background px-2 py-[1px] text-[11px] text-muted-foreground transition-colors hover:border-input hover:text-foreground"
                        >
                          {/* 左列在 AI 工作区展开时压到 ~300px：宽度全部交给容器
                              （max-w-full），flex 子项 min-w-0 才能让 truncate 生效。
                              chip 用短名（去 _ 后缀与扩展名），委托人尾巴在时间轴
                              里是噪音；hover title 看全名 */}
                          <span className="min-w-0 truncate" title={a.name}>
                            📎 {shortDocName(a.name)}
                          </span>
                        </button>
                      ))}
                    </span>
                  )}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </Card>
  )
}

/** 「下一步」行：合同勾选、紧接最后一个已启动阶段之后、还没立案的那个程序 */
export function NextStageRow({ stage, onCreate }: { stage: string; onCreate: () => void }) {
  return (
    <Card className="flex flex-wrap items-center gap-3 px-5 py-3.5 max-[680px]:px-3.5">
      <span className="size-[11px] flex-none rounded-full border-[1.5px] border-dashed border-border" />
      <span className="text-sm font-[620] text-muted-foreground">{stage}</span>
      <span className="text-[12.5px] text-muted-foreground/70">未启动 · 合同已勾选的下一程序</span>
      <span className="ml-auto max-[680px]:ml-0">
        <ActionButton onClick={onCreate} title={'新建' + stage + '案件'}>
          ＋ 新建{stage}案件
        </ActionButton>
      </span>
    </Card>
  )
}
