import { useCallback, useState } from 'react'
import { ArrowUpRight, Download, FileSearch, Loader2, X } from 'lucide-react'

import { OfficeView } from '@/components/shared/onlyoffice/OfficeView'
import { withDownloadTicket } from '@/lib/download-ticket'
import { folderFileUrl, type FolderOwnerKind } from '../../api'
import { FileKindChip } from './FileKindBadge'
import { fmtSize } from './folder-tree-types'

/**
 * 右栏内嵌预览卡：点文件夹里的文件就地展开，**不离开当前页面**。
 *
 * **为什么是页内而非弹窗/整页**：
 * - 律师看合同时常要对照右栏的期限、当事人、收费——弹窗一盖，对照就废了；
 * - 大多数时候只是想「确认一下这份是哪个版本、有没有盖章」，不需要占满全屏；
 * - 页内展开的关闭成本是零（点 ✕ 就回到原状），整页跳转要付一次路由往返。
 *
 * 真要改合同时才升级到整页编辑器（`onOpenEditor`）——那里需要宽度放分页、
 * 修订标记与批注栏，页内塞不下。
 *
 * **只读**：这里不做保存。改动一律走整页编辑器或 AI 审查，避免同一个文件
 * 出现「页内改一半、整页改一半」的两套落盘路径。
 */
export function FilePreviewCard({
  kind,
  ownerId,
  file,
  onClose,
  onOpenEditor,
  onReview,
}: {
  kind: FolderOwnerKind
  ownerId: number
  file: { subpath: string; name: string; size?: number; modified_at?: string }
  onClose: () => void
  /** 「打开编辑器」——升级到整页（可改、可存） */
  onOpenEditor: (f: { subpath: string; name: string }) => void
  /** 「AI 审查」——仅 docx（流水线只吃 docx） */
  onReview?: (f: { subpath: string; name: string }) => void
}) {
  const [downloading, setDownloading] = useState(false)
  const fileUrl = folderFileUrl(kind, ownerId, file.subpath)
  const isDocx = /\.docx$/i.test(file.name)

  const download = useCallback(async () => {
    setDownloading(true)
    try {
      // 票据一次性：每次下载现换，不能缓存复用
      const url = await withDownloadTicket(fileUrl)
      const a = document.createElement('a')
      a.href = url
      a.download = file.name
      a.rel = 'noopener'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      setDownloading(false)
    }
  }, [fileUrl, file.name])

  return (
    <div className="overflow-hidden rounded-[10px] border border-border bg-card">
      {/* 头部：类型 + 文件名 + 关闭 */}
      <div className="flex items-center gap-2 border-b border-border-light px-3 py-2">
        <FileKindChip name={file.name} />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-[620]" title={file.name}>
          {file.name}
        </span>
        <button
          type="button"
          aria-label="收起预览"
          onClick={onClose}
          className="grid size-6 flex-none place-items-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>

      {/* 画布：固定高度，不随文档变长把下方信息推走 */}
      <div className="h-[360px] bg-[#f6f6f7]">
        <OfficeView fileUrl={fileUrl} fileName={file.name} mode="view" />
      </div>

      {/* 元信息 + 操作 */}
      <div className="border-t border-border-light px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
          {file.modified_at && <span className="tabular-nums">{file.modified_at.slice(0, 10)}</span>}
          {file.size ? <span>· {fmtSize(file.size)}</span> : null}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => onOpenEditor({ subpath: file.subpath, name: file.name })}
            className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-foreground bg-foreground px-2.5 text-[11.5px] font-semibold text-background transition-opacity hover:opacity-85"
          >
            <ArrowUpRight className="size-3.5" />
            打开编辑器
          </button>

          {onReview && isDocx && (
            <button
              type="button"
              onClick={() => onReview({ subpath: file.subpath, name: file.name })}
              className="inline-flex h-[27px] items-center gap-1 rounded-[7px] border border-border bg-card px-2.5 text-[11.5px] font-[550] text-secondary-foreground transition-colors hover:bg-secondary"
            >
              <FileSearch className="size-3.5" />
              AI 审查
            </button>
          )}

          <button
            type="button"
            onClick={() => void download()}
            disabled={downloading}
            className="ml-auto inline-flex h-[27px] items-center gap-1 rounded-[7px] px-2 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-60"
          >
            {downloading ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3" />}
            下载
          </button>
        </div>
      </div>
    </div>
  )
}
