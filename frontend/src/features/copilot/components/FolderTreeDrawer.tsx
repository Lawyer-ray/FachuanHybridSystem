/**
 * 合同材料抽屉：绑定文件夹目录树（懒加载），文件节点可拖入输入区成引用。
 *
 * 数据源 ``GET /contracts/{id}/folder-entries?subpath=``（非递归，逐层取）；
 * 拖拽走自定义 MIME（FOLDER_REF_MIME）携带 ``{contractId, subpath, name}``，
 * 与系统外文件拖入（原生 Files 通道 → 上传流）区分。只读展示：命名/移动
 * 等管理操作仍在工作台详情页的文件夹树完成，本抽屉专注「找材料 → 拖引用」。
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen, RefreshCw, X } from 'lucide-react'

import { fetchContractFolderEntries } from '../api'
import { FOLDER_REF_MIME } from '../types'

function Level({
  contractId,
  subpath,
  depth,
  expanded,
  toggle,
}: {
  contractId: number
  subpath: string
  depth: number
  expanded: Set<string>
  toggle: (subpath: string) => void
}) {
  const query = useQuery({
    queryKey: ['copilot', 'folder-entries', contractId, subpath],
    queryFn: () => fetchContractFolderEntries(contractId, subpath),
    staleTime: 30_000,
    retry: false,
  })

  if (query.isPending) {
    return (
      <p className="px-2 py-1 text-[11.5px] text-muted-foreground" style={{ paddingLeft: depth * 14 + 8 }}>
        加载中…
      </p>
    )
  }
  if (query.isError || !query.data) {
    return (
      <p className="px-2 py-1 text-[11.5px] text-muted-foreground" style={{ paddingLeft: depth * 14 + 8 }}>
        目录不可达（{query.error instanceof Error ? query.error.message : '未知原因'}）
      </p>
    )
  }
  const entries = query.data
  if (!entries.browsable) {
    return (
      <p className="px-2 py-1 text-[11.5px] text-muted-foreground" style={{ paddingLeft: depth * 14 + 8 }}>
        {entries.message ?? '该合同未绑定文件夹'}
      </p>
    )
  }
  if (entries.folders.length === 0 && entries.files.length === 0) {
    return (
      <p className="px-2 py-1 text-[11.5px] text-muted-foreground" style={{ paddingLeft: depth * 14 + 8 }}>
        （空目录）
      </p>
    )
  }

  return (
    <>
      {entries.folders.map((folder) => {
        const open = expanded.has(folder.subpath)
        return (
          <div key={folder.subpath}>
            <button
              type="button"
              className="flex w-full items-center gap-1 rounded-[6px] py-1 pr-1.5 text-left text-[12px] text-foreground transition-colors hover:bg-secondary"
              style={{ paddingLeft: depth * 14 + 2 }}
              onClick={() => toggle(folder.subpath)}
              aria-expanded={open}
              draggable
              onDragStart={(e) => {
                // 目录拖入输入区成「目录引用」：AI 先列目录再按需读文件
                e.dataTransfer.setData(
                  FOLDER_REF_MIME,
                  JSON.stringify({ kind: 'contract', ownerId: contractId, subpath: folder.subpath, name: folder.name, isFolder: true }),
                )
                e.dataTransfer.effectAllowed = 'copyLink'
              }}
            >
              {open ? (
                <ChevronDown className="h-3.5 w-3.5 flex-none text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 flex-none text-muted-foreground" />
              )}
              {open ? (
                <FolderOpen className="h-3.5 w-3.5 flex-none text-primary" />
              ) : (
                <Folder className="h-3.5 w-3.5 flex-none text-muted-foreground" />
              )}
              <span className="min-w-0 flex-1 truncate">{folder.name}</span>
            </button>
            {open && (
              <Level
                contractId={contractId}
                subpath={folder.subpath}
                depth={depth + 1}
                expanded={expanded}
                toggle={toggle}
              />
            )}
          </div>
        )
      })}
      {entries.files.map((file) => (
        <div
          key={file.subpath}
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData(
              FOLDER_REF_MIME,
              JSON.stringify({ kind: 'contract', ownerId: contractId, subpath: file.subpath, name: file.name }),
            )
            e.dataTransfer.effectAllowed = 'copyLink'
          }}
          className="flex cursor-grab items-center gap-1 rounded-[6px] py-1 pr-1.5 text-[12px] text-foreground transition-colors hover:bg-secondary active:cursor-grabbing"
          style={{ paddingLeft: depth * 14 + 20 }}
          title={`${file.subpath} · 拖到输入区引用`}
        >
          <FileText className="h-3.5 w-3.5 flex-none text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">{file.name}</span>
        </div>
      ))}
    </>
  )
}

export function FolderTreeDrawer({ contractId, onClose }: { contractId: number; onClose: () => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const queryClient = useQueryClient()
  const toggle = (subpath: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(subpath)) next.delete(subpath)
      else next.add(subpath)
      return next
    })
  }

  return (
    <div className="absolute inset-y-0 right-0 z-20 flex w-60 max-w-[80%] flex-col border-l border-border bg-card shadow-[-8px_0_24px_rgba(0,0,0,0.06)]">
      <div className="flex h-9 flex-none items-center gap-1 border-b border-border px-2">
        <FolderOpen className="h-3.5 w-3.5 flex-none text-primary" />
        <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-foreground">合同材料</span>
        <button
          type="button"
          className="flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={() => void queryClient.invalidateQueries({ queryKey: ['copilot', 'folder-entries', contractId] })}
          aria-label="刷新目录"
          title="刷新目录（文件有变动时）"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          onClick={onClose}
          aria-label="收起合同材料目录"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
        <Level contractId={contractId} subpath="" depth={0} expanded={expanded} toggle={toggle} />
      </div>
      <p className="flex-none border-t border-border px-2 py-1.5 text-[10.5px] leading-relaxed text-muted-foreground">
        把文件拖到输入区即成引用；AI 直接读文件夹里的原文件，无需上传。
      </p>
    </div>
  )
}
