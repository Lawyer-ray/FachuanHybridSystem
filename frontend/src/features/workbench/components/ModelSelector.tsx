/** 模型选择器组件（支持收藏） */

import { useState } from 'react'
import { Check, ChevronDown, Star } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useWorkbenchStore } from '../stores/workbench-store'

interface ModelSelectorProps {
  disabled?: boolean
}

export function ModelSelector({ disabled }: ModelSelectorProps) {
  const [open, setOpen] = useState(false)
  const { models, modelsLoading, selectedModel, favoriteModel, setSelectedModel, setFavoriteModel } =
    useWorkbenchStore()

  if (modelsLoading) {
    return <Skeleton className="h-5 w-24" />
  }

  if (models.length === 0) {
    return <span className="text-xs text-muted-foreground">暂无模型</span>
  }

  const selectedId = selectedModel || models[0]?.id || ''
  const selected = models.find((m) => m.id === selectedId)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          disabled={disabled}
          className={cn(
            'flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors',
            'rounded px-1.5 py-0.5 hover:bg-accent',
            disabled && 'opacity-50 pointer-events-none',
          )}
        >
          <span className="truncate max-w-[160px]">
            {selected ? selected.name || selected.id : '选择模型'}
          </span>
          <ChevronDown className="size-3 shrink-0" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="end">
        <ScrollArea className="h-[240px]">
          <div className="p-1">
            {models.map((model) => {
              const isFav = favoriteModel === model.id
              return (
                <div
                  key={model.id}
                  className={cn(
                    'flex w-full items-center gap-1.5 rounded-sm px-1 py-1.5 text-sm hover:bg-accent group',
                    selectedId === model.id && 'bg-accent',
                  )}
                >
                  <button
                    onClick={() => {
                      setSelectedModel(model.id)
                      setOpen(false)
                    }}
                    className="flex flex-1 items-center gap-2 min-w-0"
                  >
                    <Check
                      className={cn(
                        'size-4 shrink-0',
                        selectedId === model.id ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    <span className="truncate">{model.name || model.id}</span>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setFavoriteModel(isFav ? '' : model.id)
                    }}
                    className={cn(
                      'shrink-0 p-1 rounded-sm transition-colors',
                      isFav
                        ? 'text-yellow-500 hover:text-yellow-600'
                        : 'text-muted-foreground/30 hover:text-muted-foreground',
                    )}
                    title={isFav ? '取消收藏' : '收藏为默认模型'}
                  >
                    <Star className={cn('size-3.5', isFav && 'fill-current')} />
                  </button>
                </div>
              )
            })}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
