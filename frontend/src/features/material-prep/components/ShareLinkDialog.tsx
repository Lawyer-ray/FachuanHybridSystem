/**
 * 生成客户上传链接的弹窗：标题 / 客户称呼 / 说明 / 绑定项目 / 有效期，
 * 创建成功后切换为「复制链接」结果视图（token 明文仅此一次，关掉即不可再取）。
 */

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Check, Copy, Loader2, Search } from 'lucide-react'
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
import { Textarea } from '@/components/ui/textarea'
import { buildShareUrl, createUploadLink, searchContracts, type ContractHit } from '../api'

const EXPIRES_OPTIONS = [
  { days: 1, label: '1 天' },
  { days: 7, label: '7 天' },
  { days: 30, label: '30 天' },
  { days: 90, label: '90 天' },
]

/** 项目选择器：输入关键字检索委托合同，点选后回显为可撤销的选中条目 */
function ContractPicker({
  selected,
  onSelect,
}: {
  selected: ContractHit | null
  onSelect: (hit: ContractHit | null) => void
}) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<ContractHit[]>([])
  const [searching, setSearching] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (!q.trim()) {
      setHits([])
      setSearching(false)
      return
    }
    setSearching(true)
    timerRef.current = setTimeout(() => {
      searchContracts(q)
        .then(setHits)
        .catch(() => setHits([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [q])

  if (selected) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
        <span className="min-w-0 truncate">
          {selected.name}
          {selected.filing_number ? <span className="ml-2 text-xs text-muted-foreground">{selected.filing_number}</span> : null}
        </span>
        <button type="button" className="shrink-0 text-xs text-secondary-foreground hover:text-foreground" onClick={() => onSelect(null)}>
          清除
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-2 rounded-md border px-3">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          placeholder="按项目（委托合同）名称检索后绑定，可不选"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {searching && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
      </div>
      {hits.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-44 w-full overflow-auto rounded-md border bg-popover shadow-md">
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-sm hover:bg-secondary"
                onClick={() => {
                  onSelect(h)
                  setQ('')
                  setHits([])
                }}
              >
                <span className="block truncate">{h.name}</span>
                {h.filing_number && <span className="block text-xs text-muted-foreground">{h.filing_number}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** 复制框：一行 URL + 复制按钮（成功后图标打勾反馈） */
export function ShareUrlBox({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard
      .writeText(url)
      .then(() => {
        setCopied(true)
        toast.success('已复制链接')
        setTimeout(() => setCopied(false), 2000)
      })
      .catch(() => toast.error('复制失败，请手动选择复制'))
  }
  return (
    <div className="flex items-center gap-2">
      <Input readOnly value={url} className="font-mono text-xs" onFocus={(e) => e.target.select()} />
      <Button type="button" size="sm" variant="outline" onClick={copy}>
        {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
        复制
      </Button>
    </div>
  )
}

export function ShareLinkDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated?: () => void }) {
  const [title, setTitle] = useState('')
  const [clientName, setClientName] = useState('')
  const [note, setNote] = useState('')
  const [contract, setContract] = useState<ContractHit | null>(null)
  const [expiresDays, setExpiresDays] = useState(30)
  const [busy, setBusy] = useState(false)
  const [resultUrl, setResultUrl] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setTitle('')
      setClientName('')
      setNote('')
      setContract(null)
      setExpiresDays(30)
      setResultUrl(null)
      setBusy(false)
    }
  }, [open])

  const submit = () => {
    if (!title.trim() || busy) return
    setBusy(true)
    createUploadLink({
      title: title.trim(),
      note: note.trim(),
      client_name: clientName.trim(),
      contract_id: contract?.id ?? null,
      expires_days: expiresDays,
    })
      .then((created) => {
        setResultUrl(buildShareUrl(created.token))
        onCreated?.()
      })
      .catch((e: unknown) => {
        toast.error(e instanceof Error ? e.message : '创建失败，请重试')
      })
      .finally(() => setBusy(false))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{resultUrl ? '链接已生成' : '向客户收取材料'}</DialogTitle>
          <DialogDescription>
            {resultUrl
              ? '把链接通过微信/短信发给客户，客户打开即可免登录上传。链接明文只显示这一次，关闭后可「换发新链接」。'
              : '生成一个一次性上传链接发给客户；可绑定项目，客户传来的材料包会自动归属到您名下。'}
          </DialogDescription>
        </DialogHeader>

        {resultUrl ? (
          <div className="space-y-4 py-2">
            <ShareUrlBox url={resultUrl} />
            <p className="text-xs text-muted-foreground">
              有效期 {expiresDays} 天{contract ? ` · 已绑定项目「${contract.name}」` : ''}。客户传的材料包会出现在「材料预处理」桌面（来源：客户链接上传）。
            </p>
          </div>
        ) : (
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">标题 *</label>
              <Input value={title} autoFocus maxLength={200} placeholder="如：张三·买卖合同纠纷·证据材料" onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="grid grid-cols-[1fr_130px] gap-3">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">客户称呼</label>
                <Input value={clientName} maxLength={100} placeholder="选填，如 张三" onChange={(e) => setClientName(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">有效期</label>
                <select
                  className="h-9 w-full rounded-md border bg-transparent px-2 text-sm"
                  value={expiresDays}
                  onChange={(e) => setExpiresDays(Number(e.target.value))}
                >
                  {EXPIRES_OPTIONS.map((o) => (
                    <option key={o.days} value={o.days}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">绑定项目</label>
              <ContractPicker selected={contract} onSelect={setContract} />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">给客户的说明</label>
              <Textarea value={note} maxLength={500} placeholder="选填，展示在客户上传页，如：请上传合同原件与微信聊天记录" onChange={(e) => setNote(e.target.value)} />
            </div>
          </div>
        )}

        <DialogFooter>
          {resultUrl ? (
            <Button onClick={() => onOpenChange(false)}>完成</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
                取消
              </Button>
              <Button onClick={submit} disabled={!title.trim() || busy}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                生成链接
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
