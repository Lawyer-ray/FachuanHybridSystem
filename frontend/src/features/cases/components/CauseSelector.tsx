/**
 * CauseSelector - 案由搜索选择器
 *
 * Requirements: 11.1, 11.2, 11.3
 */

import { useState, useEffect, useRef } from 'react'
import { Search, Loader2 } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { useCauseSearch } from '../hooks/use-reference-data'

export interface CauseSelectorProps {
  value: string | null
  onChange: (value: string) => void
  caseType?: string
  disabled?: boolean
}

export function CauseSelector({ value, onChange, caseType, disabled }: CauseSelectorProps) {
  const [search, setSearch] = useState(value || '')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  // Sync external value changes
  useEffect(() => {
    setSearch(value || '')
  }, [value])

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const { data: results, isLoading } = useCauseSearch(debouncedSearch, caseType)

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
        <Input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setOpen(true)
          }}
          onFocus={() => { if (search.length >= 1) setOpen(true) }}
          placeholder="搜索案由..."
          disabled={disabled}
          className="h-9 pl-9"
        />
        {isLoading && (
          <Loader2 className="text-muted-foreground absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin" />
        )}
      </div>

      {open && results && results.length > 0 && (
        <div className="bg-popover text-popover-foreground absolute z-50 mt-1 max-h-60 w-full overflow-y-auto rounded-md border shadow-md">
          {results.map((item) => (
            <button
              key={item.id}
              type="button"
              className="hover:bg-accent hover:text-accent-foreground w-full px-3 py-2 text-left text-sm transition-colors"
              onClick={() => {
                onChange(item.name)
                setSearch(item.name)
                setOpen(false)
              }}
            >
              {item.name}
            </button>
          ))}
        </div>
      )}

      {open && debouncedSearch.length >= 1 && !isLoading && results && results.length === 0 && (
        <div className="bg-popover text-muted-foreground absolute z-50 mt-1 w-full rounded-md border px-3 py-4 text-center text-sm shadow-md">
          未找到匹配案由
        </div>
      )}
    </div>
  )
}

export default CauseSelector
