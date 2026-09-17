import { useEffect, useMemo, useRef, useState } from 'react'
import { LoaderCircle, User, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { searchClients } from '../../api'
import type { ClientHit } from '../../types'

const SEP = '、'

/**
 * 当事人标签检索填报：委托人 / 对方当事人字段专用。
 * 字段本身是可输入框，输入姓名或单位实时从后端客户库模糊检索出下拉候选；
 * 选择一项变成一个可删除的标签，可继续输入添加多个；回车可把自由文本直接填入。
 * 交互贴合「输入 → 出下拉 → 选中变标签、标签可删」的预期。
 */
export function PartyPicker({
  value,
  onChange,
  placeholder,
  isOurClient,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  /** 检索范围：委托人为我方当事人(true)，对方当事人(false) */
  isOurClient: boolean
}) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<ClientHit[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const tags = useMemo(() => value.split(SEP).map((s) => s.trim()).filter(Boolean), [value])
  const tagSet = useMemo(() => new Set(tags), [tags])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const startSearch = (kw: string) => {
    setQ(kw)
    if (timer.current) clearTimeout(timer.current)
    const t = kw.trim()
    if (!t) {
      setHits([])
      setLoading(false)
      setOpen(true)
      return
    }
    setLoading(true)
    setOpen(true)
    timer.current = setTimeout(async () => {
      try {
        const list = await searchClients(t, isOurClient)
        setHits(list.slice(0, 12))
      } catch {
        setHits([])
      } finally {
        setLoading(false)
      }
    }, 240)
  }

  const addTag = (name: string) => {
    const n = name.trim()
    if (!n || tagSet.has(n)) {
      setQ('')
      return
    }
    onChange(value ? `${value}${SEP}${n}` : n)
    setQ('')
    setHits([])
  }

  const removeTag = (n: string) => {
    onChange(tags.filter((t) => t !== n).join(SEP))
  }

  return (
    <div ref={wrapRef} className="relative">
      <div
        className={cn(
          'flex min-h-8 flex-wrap items-center gap-1 rounded-md border border-input bg-background px-2 py-1.5 text-[13px] transition-colors',
          open && 'border-primary ring-1 ring-ring',
        )}
      >
        {tags.map((t) => (
          <span
            key={t}
            className="flex shrink-0 items-center gap-0.5 rounded-full bg-secondary px-2 py-0.5 text-[12px] text-secondary-foreground"
          >
            {t}
            <button
              type="button"
              aria-label={`删除 ${t}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => removeTag(t)}
              className="text-secondary-foreground/60 transition-colors hover:text-destructive"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          value={q}
          onChange={(e) => startSearch(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              addTag(q)
            } else if (e.key === 'Escape') {
              setOpen(false)
            } else if (e.key === 'Backspace' && !q && tags.length) {
              removeTag(tags[tags.length - 1])
            }
          }}
          placeholder={tags.length ? '' : placeholder}
          className="h-5 min-w-[52px] flex-none bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
        />
      </div>

      {open && q.trim() && (
        <div className="absolute left-0 right-0 z-20 mt-1 max-h-52 overflow-y-auto rounded-md border border-border bg-popover py-0.5 shadow-md">
          {loading && (
            <span className="flex items-center gap-1.5 px-2 py-2 text-[12px] text-muted-foreground">
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              检索中…
            </span>
          )}
          {!loading && hits.length === 0 && (
            <span className="block px-2 py-2 text-[12px] text-muted-foreground">
              没有匹配的当事人，回车可直接填入
            </span>
          )}
          {!loading &&
            hits.map((h) => (
              <button
                key={h.id}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addTag(h.name)}
                className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[13px] hover:bg-secondary"
              >
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-secondary">
                  <User className="h-3 w-3 text-secondary-foreground" />
                </span>
                <span className="min-w-0 flex-1 truncate">{h.name}</span>
                {tagSet.has(h.name) && (
                  <span className="shrink-0 text-[11px] text-muted-foreground">已选</span>
                )}
              </button>
            ))}
        </div>
      )}
    </div>
  )
}
