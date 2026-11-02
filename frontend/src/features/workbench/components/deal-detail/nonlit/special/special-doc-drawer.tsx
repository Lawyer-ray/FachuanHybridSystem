/**
 * 关厂清盘 · 交付物抽屉（点交付物行打开）
 *
 * 律师看见「职工安置方案与补偿测算表 · 34 页 · 撰写中」时，紧接着要问的一定是
 * 「谁传的、什么时候传的、改过几版、这版能不能发给客户」。抽屉把这几件事摊开，
 * 并给出四个动作：下载 / 重命名 / 删除 / 重新起草。
 *
 * **预览是占位但要说实话**：关厂清盘的交付物还没有落到合同文件夹（阶段树是演示
 * 数据），所以这里画的是「首页缩略 + 页码列表」的骨架，而不是假装渲染了正文。
 * 真实预览走 `FilePreviewCard`（云端 Office），入口在阶段表里点有 subpath 的文件。
 */

import { useState } from 'react'
import { Download, FileDown, FileSignature, Pencil, Trash2 } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_NL1_DOC_HISTORY, type DemoDeliverable } from '../../demo-nonlit'
import { EmptyHint, Inset, MiniButton, SpecialDrawer, TonePill, type Tone } from './special-bits'
import { versionRowsOf } from './special-liquidation-model'

export interface DrawerDoc extends DemoDeliverable {
  /** 所属阶段（改名 / 删除要定位到具体阶段下的那一行） */
  phaseId: string
  /** 所属阶段名（副标题用） */
  phaseName: string
  /** 所属阶段编号 */
  phaseSeq: string
}

const STATUS_TEXT: Record<DemoDeliverable['status'], string> = { done: '已定稿', drafting: '撰写中', pending: '待开始' }
const STATUS_TONE: Record<DemoDeliverable['status'], Tone> = { done: 'green', drafting: 'yellow', pending: 'neutral' }

export function SpecialDocDrawer({
  doc,
  open,
  onClose,
  onDownload,
  onRename,
  onDelete,
  onRedraft,
}: {
  /** null = 抽屉关闭 */
  doc: DrawerDoc | null
  open: boolean
  onClose: () => void
  onDownload: (name: string) => void
  onRename: (name: string, next: string) => void
  onDelete: (name: string) => void
  onRedraft: (name: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  if (!doc) return null

  const versions = versionRowsOf(doc.name, DEMO_NL1_DOC_HISTORY)
  const current = versions.find((v) => v.current) ?? null
  /** 预览占位只抽 6 页指纹，不按真实页数铺满——抽屉里没人会滚 34 页缩略图 */
  const pageChips = Array.from({ length: Math.min(doc.pages, 6) }, (_, i) => i + 1)

  const commitRename = () => {
    const next = draft.trim()
    if (next) onRename(doc.name, next)
    setEditing(false)
  }

  return (
    <SpecialDrawer
      open={open}
      onClose={onClose}
      title={doc.name}
      subtitle={`${doc.phaseSeq} ${doc.phaseName} · ${doc.pages} 页 · ${doc.updatedAt} 由 ${doc.owner} 上传`}
      badge={<TonePill tone={STATUS_TONE[doc.status]}>{STATUS_TEXT[doc.status]}</TonePill>}
      footer={
        <>
          <MiniButton onClick={() => onDownload(doc.name)} title="下载当前版本">
            <Download className="size-3" /> 下载
          </MiniButton>
          <MiniButton
            onClick={() => {
              setDraft(doc.name)
              setEditing(true)
            }}
          >
            <Pencil className="size-3" /> 重命名
          </MiniButton>
          <MiniButton onClick={() => onRedraft(doc.name)} title="按当前版本重新起草一版草稿">
            <FileSignature className="size-3" /> 重新起草
          </MiniButton>
          <MiniButton tone="danger" onClick={() => onDelete(doc.name)} title="删除后版本历史一并移除">
            <Trash2 className="size-3" /> 删除
          </MiniButton>
        </>
      }
    >
      <div className="flex flex-col gap-2.5">
        {editing ? (
          <Inset className="border-status-blue/40 bg-status-blue-bg/40">
            <div className="mb-1.5 text-[10.5px] font-medium text-status-blue">重命名交付物</div>
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename()
                  if (e.key === 'Escape') setEditing(false)
                }}
                className="h-[28px] min-w-0 flex-1 rounded-[6px] border border-input bg-card px-2 text-[12.5px] outline-none focus:border-ring"
              />
              <MiniButton onClick={commitRename}>保存</MiniButton>
              <MiniButton onClick={() => setEditing(false)}>取消</MiniButton>
            </div>
            <div className="mt-1 text-[10.5px] text-muted-foreground">改名只改展示名，文件名保持不动</div>
          </Inset>
        ) : null}

        {/* 元信息 */}
        <div className="grid grid-cols-2 gap-2">
          <MetaCell k="页数" v={`${doc.pages} 页`} />
          <MetaCell k="版本" v={current?.version ?? (doc.status === 'pending' ? '—' : 'v1')} />
          <MetaCell k="上传时间" v={doc.updatedAt} />
          <MetaCell k="上传人" v={doc.owner} />
        </div>

        {/* 预览占位 */}
        <div>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-[11px] font-[650] tracking-[0.06em] text-muted-foreground/85">文件预览</span>
            <TonePill tone="neutral">占位</TonePill>
            <span className="ml-auto text-[10px] text-muted-foreground">真实预览走云端 Office</span>
          </div>
          {doc.status === 'pending' ? (
            <EmptyHint>计划中的交付物还没有文件，先「重新起草」生成草稿</EmptyHint>
          ) : (
            <div className="flex gap-2.5">
              <div className="h-[132px] w-[104px] flex-none overflow-hidden rounded-[6px] border border-border-light bg-background px-2 py-2">
                <div className="text-[7px] leading-[1.6] font-[620] text-secondary-foreground">{doc.name}</div>
                <div className="mt-1 flex flex-col gap-[3px]">
                  {Array.from({ length: 9 }, (_, i) => (
                    <div
                      key={i}
                      className="h-[3px] rounded-full bg-secondary-foreground/15"
                      style={{ width: `${90 - ((i * 13) % 45)}%` }}
                    />
                  ))}
                </div>
                <div className="mt-1.5 text-[6px] tabular-nums text-muted-foreground">第 1 页 / 共 {doc.pages} 页</div>
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-1 text-[10.5px] text-muted-foreground">页索引（点页码定位）</div>
                <div className="flex flex-wrap gap-1">
                  {pageChips.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => onDownload(doc.name)}
                      title={`第 ${n} 页`}
                      className="size-[26px] rounded-[6px] border border-border-light bg-background text-[11px] tabular-nums text-secondary-foreground transition-colors hover:border-input hover:bg-secondary"
                    >
                      {n}
                    </button>
                  ))}
                  {doc.pages > 6 ? (
                    <span className="grid h-[26px] place-items-center rounded-[6px] border border-dashed border-border-light px-1.5 text-[10.5px] tabular-nums text-muted-foreground">
                      …共 {doc.pages} 页
                    </span>
                  ) : null}
                </div>
                <div className="mt-2 rounded-[6px] bg-secondary/40 px-2 py-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
                  预览需要 Office 引擎；关厂清盘这批交付物尚未落到合同文件夹，故显示骨架。
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 版本历史 */}
        <div>
          <div className="mb-1.5 text-[11px] font-[650] tracking-[0.06em] text-muted-foreground/85">
            版本历史（{versions.length} 版）
          </div>
          {versions.length === 0 ? (
            <EmptyHint>还没上传过文件，无版本记录</EmptyHint>
          ) : (
            <div className="flex flex-col gap-1.5">
              {versions.map((v) => (
                <Inset key={v.version} className={cn(v.current && 'border-status-green/40 bg-status-green-bg/30')}>
                  <div className="flex items-center gap-2">
                    <span className="text-[11.5px] font-[620] tabular-nums">{v.version}</span>
                    {v.current ? <TonePill tone="green">当前版</TonePill> : null}
                    <span className="text-[10.5px] tabular-nums text-muted-foreground">{v.at}</span>
                    <span className="text-[10.5px] text-muted-foreground">{v.who}</span>
                    <span className="ml-auto text-[10.5px] tabular-nums text-muted-foreground">{v.pages} 页</span>
                    <button
                      type="button"
                      onClick={() => onDownload(`${doc.name} ${v.version}`)}
                      title="下载该版本"
                      className="text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <FileDown className="size-3" />
                    </button>
                  </div>
                  <div className="mt-0.5 text-[11px] leading-[1.6] text-secondary-foreground">{v.note}</div>
                </Inset>
              ))}
            </div>
          )}
        </div>
      </div>
    </SpecialDrawer>
  )
}

function MetaCell({ k, v }: { k: string; v: string }) {
  return (
    <Inset>
      <div className="text-[10px] text-muted-foreground">{k}</div>
      <div className="mt-0.5 truncate text-[12.5px] font-[550] tabular-nums" title={v}>
        {v}
      </div>
    </Inset>
  )
}
