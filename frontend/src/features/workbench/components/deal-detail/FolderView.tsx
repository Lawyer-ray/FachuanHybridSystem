import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, FileText, FolderClosed, Loader2 } from 'lucide-react'

import { withDownloadTicket } from '@/lib/download-ticket'
import { errMessage } from '@/lib/errors'
import { listCaseFolderEntries } from '../../api'
import type { CaseFolderBindingInfo } from '../../types'
import { workbenchKeys } from '../../hooks/use-workbench-data'

/**
 * 案件卡「文件夹视图」：绑定文件夹的只读浏览（逐层下钻 + 面包屑）。
 * 手工整理的目录结构（如「2-邮件往来/2026.09.29-收到法院裁定书」）原样
 * 透出，与日志视图互补——后者只含 AI / 系统写入的记录。
 */

/** 文件大小短格式（B / KB / MB） */
function fmtSize(n: number): string {
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return Math.round(n / 1024) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

/** 单文件新标签预览：folder-file 端点与全局鉴权同源（JWT 头 / ?ticket=），换票后直开 */
async function previewFile(caseId: number, subpath: string) {
  const url = '/api/v1/cases/' + caseId + '/folder-file?subpath=' + encodeURIComponent(subpath)
  window.open(await withDownloadTicket(url), '_blank', 'noopener')
}

function Hint({ text }: { text: string }) {
  return <div className="py-2 text-xs text-muted-foreground/70">{text}</div>
}

export function FolderView({ caseId, binding }: { caseId: number; binding: CaseFolderBindingInfo }) {
  const [subpath, setSubpath] = useState('')
  const q = useQuery({
    queryKey: workbenchKeys.caseFolderEntries(caseId, subpath),
    queryFn: () => listCaseFolderEntries(caseId, subpath),
    staleTime: 60_000,
    retry: false,
  })

  const rootName = binding.folder_path_display.split('/').filter(Boolean).pop() || '绑定文件夹'
  const crumbs = subpath.split('/').filter(Boolean)
  const data = q.data

  return (
    <div className="px-5 pt-2 pb-4 max-[680px]:px-3.5">
      {/* 面包屑：根目录可点回根，中间段逐级回退 */}
      <div className="mb-2 flex flex-wrap items-center gap-1 text-[12px] text-muted-foreground">
        <button
          type="button"
          className={'rounded px-1 py-0.5 transition-colors hover:text-foreground ' + (subpath ? 'cursor-pointer' : 'font-[620] text-secondary-foreground')}
          title={binding.folder_path_display}
          onClick={() => setSubpath('')}
        >
          {rootName}
        </button>
        {crumbs.map((seg, i) => {
          const isLast = i === crumbs.length - 1
          return (
            <span key={seg + i} className="flex items-center gap-1">
              <span className="text-border">/</span>
              {isLast ? (
                <span className="px-1 py-0.5 font-[620] text-secondary-foreground">{seg}</span>
              ) : (
                <button
                  type="button"
                  className="cursor-pointer rounded px-1 py-0.5 transition-colors hover:text-foreground"
                  onClick={() => setSubpath(crumbs.slice(0, i + 1).join('/'))}
                >
                  {seg}
                </button>
              )}
            </span>
          )
        })}
      </div>

      {q.isPending ? (
        <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          正在读取文件夹…
        </div>
      ) : q.isError ? (
        <Hint text={errMessage(q.error, '文件夹读取失败')} />
      ) : !data || !data.browsable ? (
        <Hint text={data?.message ?? '文件夹无法浏览'} />
      ) : data.folders.length === 0 && data.files.length === 0 ? (
        <Hint text="文件夹是空的" />
      ) : (
        <div className="flex flex-col">
          {data.folders.map((f) => (
            <button
              key={f.subpath}
              type="button"
              className="flex cursor-pointer items-center gap-2 rounded-[7px] px-2 py-[7px] text-left transition-colors hover:bg-secondary"
              onClick={() => setSubpath(f.subpath)}
            >
              <FolderClosed className="size-[15px] flex-none text-muted-foreground/70" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-secondary-foreground" title={f.name}>
                {f.name}
              </span>
              <ChevronRight className="size-3.5 flex-none text-border" />
            </button>
          ))}
          {data.files.map((f) => (
            <button
              key={f.subpath}
              type="button"
              className="flex cursor-pointer items-center gap-2 rounded-[7px] px-2 py-[7px] text-left transition-colors hover:bg-secondary"
              title={'预览 ' + f.name}
              onClick={() => void previewFile(caseId, f.subpath)}
            >
              <FileText className="size-[15px] flex-none text-muted-foreground/70" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-secondary-foreground">{f.name}</span>
              <span className="flex-none text-[11px] text-muted-foreground/80 tabular-nums">
                {f.modified_at.slice(0, 10)} · {fmtSize(f.size)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
