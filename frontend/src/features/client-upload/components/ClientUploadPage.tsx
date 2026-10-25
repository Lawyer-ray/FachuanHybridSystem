/**
 * 客户上传单页（公开路由 /u/:token，无登录壳层）。
 *
 * 布局自足：不在 AppShell 内（无导航栏/侧栏），移动端（微信内置浏览器）
 * 优先——大按钮、全宽拖放区、逐文件进度。三态：加载中 / 链接无效 / 正常。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { CheckCircle2, FilePlus2, Loader2, UploadCloud } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { getLinkInfo, listUploadedFiles, uploadFiles } from '../api'
import { ACCEPT_ATTR, CLOSED_STATE_TEXT, type LinkState, type PublicFileItem, type PublicLinkInfo } from '../types'

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${bytes}B`
}

function stateHint(state: LinkState): string {
  if (state === 'open') return ''
  return `${CLOSED_STATE_TEXT[state]}，请联系律师重新获取链接`
}

export function ClientUploadPage() {
  const { token = '' } = useParams()
  const [info, setInfo] = useState<PublicLinkInfo | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [uploaded, setUploaded] = useState<PublicFileItem[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [remark, setRemark] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [doneCount, setDoneCount] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([getLinkInfo(token), listUploadedFiles(token)])
      .then(([linkInfo, items]) => {
        if (cancelled) return
        setInfo(linkInfo)
        setUploaded(items)
      })
      .catch(() => {
        if (!cancelled) setInvalid(true)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const addFiles = useCallback((incoming: FileList | null) => {
    if (!incoming || incoming.length === 0) return
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`))
      const merged = [...prev]
      for (const f of Array.from(incoming)) {
        const key = `${f.name}:${f.size}`
        if (!seen.has(key)) {
          merged.push(f)
          seen.add(key)
        }
      }
      return merged
    })
    setDoneCount(null)
    setError('')
  }, [])

  const submit = useCallback(async () => {
    if (!info || files.length === 0 || busy) return
    setBusy(true)
    setProgress(0)
    setError('')
    try {
      const result = await uploadFiles(token, files, remark, setProgress)
      setUploaded(await listUploadedFiles(token))
      setDoneCount(result.files.length)
      setFiles([])
      setRemark('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传失败，请重试')
    } finally {
      setBusy(false)
    }
  }, [info, files, busy, token, remark])

  if (invalid) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-base font-medium">链接不存在或已关闭</p>
        <p className="text-sm text-secondary-foreground">请向律师核对上传链接是否正确、是否仍在有效期内。</p>
      </main>
    )
  }

  if (!info) {
    return (
      <main className="flex min-h-dvh items-center justify-center gap-2 text-sm text-secondary-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 正在打开…
      </main>
    )
  }

  const closed = info.state !== 'open'

  return (
    <main className="mx-auto min-h-dvh max-w-xl px-4 pb-16 pt-10 sm:px-6">
      <header className="mb-8">
        <h1 className="text-xl font-semibold leading-snug">{info.title}</h1>
        <p className="mt-2 text-sm text-secondary-foreground">
          {info.lawyer_name ? `${info.lawyer_name}律师 ` : ''}
          {info.contract_name ? `· ${info.contract_name}` : ''}
          {info.client_name ? ` · ${info.client_name}` : ''}
        </p>
        {info.note && <p className="mt-3 rounded-lg bg-secondary px-3 py-2 text-sm leading-6">{info.note}</p>}
      </header>

      {closed ? (
        <section className="rounded-xl border border-dashed border-zinc-300 px-4 py-12 text-center text-sm text-secondary-foreground">
          {stateHint(info.state)}
        </section>
      ) : (
        <>
          <section
            className="cursor-pointer rounded-xl border-2 border-dashed border-zinc-300 px-4 py-10 text-center transition-colors hover:border-zinc-400"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              addFiles(e.dataTransfer.files)
            }}
          >
            <UploadCloud className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">点击选择文件，或把文件拖到这里</p>
            <p className="mt-2 text-xs text-muted-foreground">
              支持 PDF / Word / Excel / PPT / 图片 / 压缩包；单个文件 ≤ 50MB，压缩包 ≤ 200MB
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT_ATTR}
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </section>

          {files.length > 0 && (
            <ul className="mt-4 space-y-2">
              {files.map((f) => (
                <li key={`${f.name}:${f.size}`} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
                  <span className="min-w-0 truncate">{f.name}</span>
                  <span className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                    {formatSize(f.size)}
                    <button
                      type="button"
                      className="text-secondary-foreground hover:text-foreground"
                      disabled={busy}
                      onClick={() => setFiles((prev) => prev.filter((x) => x !== f))}
                    >
                      移除
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4">
            <Textarea
              value={remark}
              disabled={busy}
              maxLength={500}
              placeholder="给律师的备注（选填），如：这是第一批证据材料"
              onChange={(e) => setRemark(e.target.value)}
            />
          </div>

          {busy && (
            <div className="mt-4">
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                <div className="h-full rounded-full bg-primary transition-[width] duration-200" style={{ width: `${progress}%` }} />
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">正在上传 {progress}%（请勿关闭页面）</p>
            </div>
          )}

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

          {doneCount != null && (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-emerald-600">
              <CheckCircle2 className="h-4 w-4" /> 已提交 {doneCount} 份材料，律师收到后会与您联系
            </p>
          )}

          <Button className="mt-4 w-full" size="lg" disabled={files.length === 0 || busy} onClick={() => void submit()}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />}
            {busy ? '上传中…' : `提交 ${files.length > 0 ? `${files.length} 个文件` : ''}`}
          </Button>

          {uploaded.length > 0 && (
            <section className="mt-10">
              <h2 className="mb-3 text-sm font-medium text-secondary-foreground">已提交的材料（{uploaded.length}）</h2>
              <ul className="space-y-1.5">
                {uploaded.map((item, i) => (
                  <li key={`${item.filename}:${item.size}:${i}`} className="flex items-center justify-between gap-3 rounded-lg bg-secondary/60 px-3 py-2 text-sm">
                    <span className="min-w-0 truncate">{item.filename}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatSize(item.size)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <footer className="mt-10 text-center text-xs text-muted-foreground">
            本链接由律师一对一发送，请勿转发他人 · 剩余容量 {formatSize(info.remaining_bytes)}
          </footer>
        </>
      )}
    </main>
  )
}
