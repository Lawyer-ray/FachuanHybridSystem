import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { errMessage } from '@/lib/errors'

import { bindContractFolder, getContractFolderBinding } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import type { FolderEntryMutation } from './folder-tree-types'
import { FolderTree } from './FolderTree'
import { RailAction } from './ui'

/**
 * 右栏「合同文件夹」一节（诉讼页与非诉页共用）。
 *
 * **先查绑定，再决定要不要拉目录**：合同没有绑定文件夹时，`folder-entries` 会
 * 回 404——界面只是兜底成一行错误，控制台却一直有噪音，而且律师根本不知道
 * 「是没绑还是文件夹坏了」。现在未绑定就给一句话 + 一个手工绑定的入口。
 *
 * 绑定要的是**服务器上的绝对路径**（本地存储），这也是项目文件夹的真实形态：
 * 律师的卷宗就在「新工作/200-诉讼/…」这种目录里，不在我们的库里。
 */
export function ContractFolderSection({
  contractId,
  selectedSubpath,
  onOpenFile,
  onReviewFile,
  onFolderMutated,
}: {
  contractId: number
  /** 当前预览中的文件（树里那一行高亮） */
  selectedSubpath?: string | null
  onOpenFile?: (f: { subpath: string; name: string; size?: number; modified_at?: string }) => void
  onReviewFile?: (f: { subpath: string; name: string }) => void
  onFolderMutated?: (e: FolderEntryMutation) => void
}) {
  const qc = useQueryClient()
  const bindingQ = useQuery({
    queryKey: ['workbench', 'contract-folder-binding', contractId],
    queryFn: () => getContractFolderBinding(contractId),
    staleTime: 5 * 60_000,
  })
  const [bindOpen, setBindOpen] = useState(false)
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const binding = bindingQ.data ?? null

  async function submitBind() {
    const v = path.trim()
    if (!v || busy) return
    setBusy(true)
    setError(null)
    try {
      await bindContractFolder(contractId, v)
      toast.success('已绑定合同文件夹')
      void qc.invalidateQueries({ queryKey: ['workbench', 'contract-folder-binding', contractId] })
      void qc.invalidateQueries({ queryKey: workbenchKeys.folderEntries('contract', contractId) })
      setBindOpen(false)
      setPath('')
    } catch (e) {
      setError(errMessage(e, '绑定失败，请检查路径是否存在'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border-t border-border-light px-[18px] pt-3.5 pb-[15px]">
      <div className="mb-1 flex items-center gap-2">
        <h4 className="text-[11px] font-[650] tracking-[0.07em] text-muted-foreground/80">合同文件夹</h4>
        <span className="ml-auto">{binding && <RailAction onClick={() => setBindOpen(true)}>改绑定</RailAction>}</span>
      </div>

      {bindingQ.isPending ? (
        <div className="flex items-center gap-1.5 py-2 text-[11.5px] text-muted-foreground">
          <Loader2 className="size-3 animate-spin" /> 正在读取绑定…
        </div>
      ) : bindingQ.isError ? (
        <div className="flex flex-wrap items-center gap-2 py-1.5 text-[11.5px] text-muted-foreground">
          <span>文件夹绑定读取失败</span>
          <button
            type="button"
            className="cursor-pointer underline underline-offset-2 hover:text-foreground"
            onClick={() => void bindingQ.refetch()}
          >
            重试
          </button>
        </div>
      ) : !binding ? (
        <div className="flex flex-col items-start gap-1.5 py-1.5">
          <p className="text-[11.5px] leading-[1.6] text-muted-foreground">
            这个项目还没有绑定合同文件夹——绑定后才能在这里看合同文件、发起 AI 审查。
          </p>
          <RailAction onClick={() => setBindOpen(true)}>＋ 绑定文件夹</RailAction>
        </div>
      ) : (
        <FolderTree
          kind="contract"
          ownerId={contractId}
          maxH="max-h-[420px]"
          selectedSubpath={selectedSubpath ?? null}
          onOpenFile={onOpenFile}
          onReviewFile={onReviewFile}
          onEntryMutated={onFolderMutated}
        />
      )}

      <Dialog open={bindOpen} onOpenChange={(v) => !v && !busy && setBindOpen(false)}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>{binding ? '改绑合同文件夹' : '绑定合同文件夹'}</DialogTitle>
            <DialogDescription>
              填这台机器上卷宗所在目录的绝对路径。绑定后右栏这里显示目录树，
              产物（起诉状、证据目录…）也从这里读写。
            </DialogDescription>
          </DialogHeader>
          <Input
            aria-label="文件夹路径"
            autoFocus
            value={path}
            placeholder={binding?.folder_path ?? '例：/Users/xxx/新工作/200-诉讼/2026.11.16-[民商事]某某诉某某案'}
            onChange={(e) => setPath(e.target.value)}
          />
          {error && <p className="text-[12px] text-status-red">{error}</p>}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setBindOpen(false)} disabled={busy}>
              取消
            </Button>
            <Button onClick={() => void submitBind()} disabled={busy || path.trim() === ''}>
              {busy && <Loader2 className="mr-1 size-3.5 animate-spin" />}
              绑定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
