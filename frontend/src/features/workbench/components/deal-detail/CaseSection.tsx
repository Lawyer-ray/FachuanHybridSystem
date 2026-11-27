import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { toast } from 'sonner'

import { EmptyBlock } from '@/components/shared/AsyncState'
import { withDownloadTicket } from '@/lib/download-ticket'
import { getCaseFolderBinding } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import type { DealCase } from '../../types'
import { caseMetaParts, legalStatusGroups, shortDocName, splitLinkText, timelineEntries } from './detail-domain'
import type { FolderEntryMutation } from './folder-tree-types'
import { FolderTree } from './FolderTree'
import { ActionButton, Card, Chip, MetaLine, Pill, StateDot } from './ui'

/**
 * 附件新标签预览：media 走一次性 ticket（60s 单次），失败时后端 403 兜底。
 *
 * 空地址不能点：`mediaUrl` 来自 `media_url || ''`，历史日志里可能没有原件，
 * 点下去只会开一个空白标签页（看着像系统坏了）。
 */
async function openAttachment(mediaUrl: string) {
  try {
    window.open(await withDownloadTicket(mediaUrl), '_blank', 'noopener')
  } catch {
    toast.error('附件打不开，请重试')
  }
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
  onOpenFile,
  onDraft,
  selectedSubpath,
  onFolderMutated,
}: {
  c: DealCase
  /** 同阶段多案（如按被告分立）时节标题带案名才分得清 */
  ambiguous: boolean
  /** stepper 跳转后的短暂高亮环 */
  highlighted: boolean
  /** 记日志：归属就是这张卡代表的案件（合同没有时间轴） */
  onAddLog: (c: { id: number; label: string }) => void
  /**
   * 点文件行 = 打开 OnlyOffice 预览（而不是 window.open 下载）。
   *
   * 案件文件是诉讼项目的文件主体（起诉状/证据/判决书），以前只能下载——
   * 浏览器没有 docx 渲染器，`window.open` 必然落到本地磁盘。预览画布由
   * 详情页统一持有（右栏，与合同文件同一套 FilePreviewCard）。
   */
  onOpenFile?: (f: { subpath: string; name: string; size?: number; modified_at?: string }) => void
  /**
   * 「生成文书」——按案件开起草弹窗。
   *
   * 入口放在案件节而不是页头：文书（起诉状/答辩状/管辖权异议）属于**具体案件**，
   * 一个委托下可能挂着多个阶段案，页头放一个按钮就得让律师再猜「生成到哪个案」；
   * 合同侧文书当前不接（文件夹模板没有对应节点，后端会返回 created=false）。
   */
  onDraft?: (caseId: number) => void
  /** 当前预览中的 subpath（属于本案件时行高亮，知道「看的就是这份」） */
  selectedSubpath?: string | null
  /** 树内改名/删除 → 页面据此关掉正在预览的那份（见 FolderTree 的 onEntryMutated） */
  onFolderMutated?: (e: FolderEntryMutation) => void
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
  /**
   * 默认落在哪个视图。
   *
   * 判「可达」而不只是「有绑定」：硬盘路径被拔掉/无权限时 binding 仍然存在，
   * 但点进文件夹只会看到一片空——先给律师看日志，他要看文件夹可以自己切。
   * 绑定查询在途时不抢先判成「没有绑定」（否则会先闪一下「还没有项目日志」，
   * 再整块跳成文件夹视图）。
   */
  const canBrowse = binding != null && binding.is_accessible
  const view: 'logs' | 'folder' = viewOverride ?? (canBrowse ? 'folder' : 'logs')

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
          {onDraft && (
            <ActionButton sm onClick={() => onDraft(c.id)} title="按文书类型起草一份新文书，落进本案文件夹">
              ＋ 生成文书
            </ActionButton>
          )}
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
            <ActionButton sm onClick={() => onAddLog({ id: c.id, label: c.proc })} title="记一条项目日志（可顺手约一个期限）">
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

      {bindingQ.isError && (
        <div className="px-5 pt-1 text-[11.5px] text-muted-foreground max-[680px]:px-3.5">
          案件文件夹状态读取失败
          <button
            type="button"
            className="ml-2 cursor-pointer underline underline-offset-2 hover:text-foreground"
            onClick={() => void bindingQ.refetch()}
          >
            重试
          </button>
        </div>
      )}

      {bindingQ.isPending ? (
        <div className="px-5 pt-2 pb-4 text-xs text-muted-foreground max-[680px]:px-3.5">正在读取案件材料…</div>
      ) : view === 'folder' && binding ? (
        <div className="px-5 pt-2 pb-4 max-[680px]:px-3.5">
          <FolderTree
            kind="case"
            ownerId={c.id}
            onOpenFile={onOpenFile}
            selectedSubpath={selectedSubpath ?? null}
            onEntryMutated={onFolderMutated}
          />
        </div>
      ) : (
        <div className="px-5 pt-3.5 pb-1.5 max-[680px]:px-3.5">
          {entries.length === 0 ? (
            <EmptyBlock className="justify-start px-0 py-2 text-left text-xs text-muted-foreground/70">
              还没有项目日志
            </EmptyBlock>
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
                      {e.n > 1 && <MergedTimes dates={e.dates} />}
                    </span>
                  )}
                  {e.atts.length > 0 && (
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {e.atts.map((a) => {
                        // 没有原件（media_url 为空）就别装成按钮：点开只会得到空白页
                        const clickable = Boolean(a.mediaUrl)
                        const Tag = clickable ? 'button' : 'span'
                        return (
                        <Tag
                          key={a.id}
                          {...(clickable ? { type: 'button' as const, onClick: () => void openAttachment(a.mediaUrl) } : {})}
                          title={clickable ? '预览 ' + a.name : a.name + '（原件未上传）'}
                          className={
                            'inline-flex max-w-full min-w-0 items-center rounded-[6px] border border-border-light bg-background px-2 py-[1px] text-[11px] text-muted-foreground ' +
                            (clickable ? 'cursor-pointer transition-colors hover:border-input hover:text-foreground' : 'opacity-70')
                          }
                        >
                          {/* 左列在 AI 工作区展开时压到 ~300px：宽度全部交给容器
                              （max-w-full），flex 子项 min-w-0 才能让 truncate 生效。
                              chip 用短名（去 _ 后缀与扩展名），委托人尾巴在时间轴
                              里是噪音；hover title 看全名 */}
                          <span className="min-w-0 truncate" title={a.name}>
                            📎 {shortDocName(a.name)}
                          </span>
                        </Tag>
                        )
                      })}
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

/**
 * 合并日志的「×N」：点开看每次发生的日期。
 *
 * 合并行显示的是最新一次，`×N` 只说明次数——律师要的往往是**第一次**是什么时候
 * （比如「对方已经催了三次」的起点），所以把日期清单挂在 ×N 上，点一下展开。
 */
function MergedTimes({ dates }: { dates: string[] }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="ml-2">
      <button
        type="button"
        className="cursor-pointer underline decoration-dotted underline-offset-2 hover:text-foreground"
        title={open ? '收起每次日期' : '相同内容的日志已合并，点开看每次日期'}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        ×{dates.length}
      </button>
      {open && (
        <span className="mt-0.5 block text-[11px] text-muted-foreground/70">
          各次：{dates.join('、')}
        </span>
      )}
    </span>
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
        <ActionButton onClick={onCreate} title={'在当前委托下新建一个' + stage + '案件'}>
          ＋ 新建{stage}案件
        </ActionButton>
      </span>
    </Card>
  )
}
