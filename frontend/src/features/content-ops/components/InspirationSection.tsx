import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Sparkles, Lightbulb, ChevronsUpDown, Check, Plus } from 'lucide-react'
import { useInspiration } from '../hooks/use-content-ops'
import { useQuery } from '@tanstack/react-query'
import { createFeatureApiClient } from '@/lib/api'
import type { TopicSuggestion } from '../types'
import { cn } from '@/lib/utils'

interface InspirationSectionProps {
  onSelectTopic: (topic: TopicSuggestion) => void
}

interface LLMModel {
  id: string
  name: string
  backend: string
  max_model_len: number
}

interface ModelsResponse {
  models: LLMModel[]
  default_model: string
}

function getStoredFavoriteModel(): string | null {
  try {
    const token = localStorage.getItem('access_token')
    if (!token) return null
    const payload = JSON.parse(atob(token.split('.')[1]))
    const userId = payload.user_id || payload.sub
    return localStorage.getItem(`content_ops_favorite_model_${userId}`)
  } catch {
    return null
  }
}

function storeFavoriteModel(modelId: string) {
  try {
    const token = localStorage.getItem('access_token')
    if (!token) return
    const payload = JSON.parse(atob(token.split('.')[1]))
    const userId = payload.user_id || payload.sub
    localStorage.setItem(`content_ops_favorite_model_${userId}`, modelId)
  } catch {
    // ignore
  }
}

export function InspirationSection({ onSelectTopic }: InspirationSectionProps) {
  const { data, error, isFetching, refetch } = useInspiration()
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false)

  const { data: modelsData } = useQuery({
    queryKey: ['workbench', 'models'],
    queryFn: () => createFeatureApiClient('workbench').get('models').json<ModelsResponse>(),
  })

  const [selectedModel, setSelectedModel] = useState<string>('')

  useEffect(() => {
    if (modelsData && !selectedModel) {
      const stored = getStoredFavoriteModel()
      if (stored && modelsData.models.some((m) => m.id === stored)) {
        setSelectedModel(stored)
      } else if (modelsData.default_model) {
        setSelectedModel(modelsData.default_model)
      } else if (modelsData.models.length > 0) {
        setSelectedModel(modelsData.models[0].id)
      }
    }
  }, [modelsData, selectedModel])

  const handleModelSelect = (modelId: string) => {
    setSelectedModel(modelId)
    storeFavoriteModel(modelId)
    setModelSelectorOpen(false)
  }

  const handleGenerate = () => {
    refetch(selectedModel || undefined)
  }

  const currentModelName = modelsData?.models.find((m) => m.id === selectedModel)?.name || selectedModel

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          AI 法律灵感
        </h2>
        <div className="flex items-center gap-2">
          <Popover open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="h-7 text-xs max-w-[180px] truncate">
                {currentModelName || '选择模型'}
                <ChevronsUpDown className="w-3 h-3 ml-1 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[250px] p-0" align="end">
              <Command>
                <CommandInput placeholder="搜索模型..." className="h-8" />
                <CommandList>
                  <CommandEmpty>未找到模型</CommandEmpty>
                  <CommandGroup>
                    {modelsData?.models.map((model) => (
                      <CommandItem
                        key={model.id}
                        value={model.id}
                        onSelect={() => handleModelSelect(model.id)}
                        className="text-xs"
                      >
                        <Check className={cn('mr-2 h-3 w-3', selectedModel === model.id ? 'opacity-100' : 'opacity-0')} />
                        {model.name}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>

          <Button size="sm" className="h-7 text-xs" onClick={handleGenerate} disabled={isFetching}>
            <Sparkles className="w-3.5 h-3.5 mr-1" />
            {isFetching ? '生成中...' : 'AI 灵感推荐'}
          </Button>
        </div>
      </div>

      {!data && !isFetching && !error && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <Lightbulb className="w-10 h-10 mb-3 opacity-30" />
          <p className="text-sm">点击「AI 灵感推荐」，从热搜话题中发现法律选题</p>
        </div>
      )}

      {isFetching && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-lg" />
          ))}
        </div>
      )}

      {error && (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={handleGenerate}>
            重试
          </Button>
        </div>
      )}

      {data && data.length > 0 && (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {data.map((topic, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: Math.min(i * 0.05, 0.3) }}
            >
              <Card
                className="p-4 hover:shadow-md transition-all duration-200 cursor-pointer group h-full"
                onClick={() => onSelectTopic(topic)}
              >
                <h4 className="text-sm font-semibold leading-snug group-hover:text-primary transition-colors">
                  {topic.title}
                </h4>
                <p className="text-xs text-muted-foreground mt-2 line-clamp-3 leading-relaxed">
                  {topic.description}
                </p>
                {topic.suggested_keyword && (
                  <Badge variant="secondary" className="mt-3 text-[10px]">
                    {topic.suggested_keyword}
                  </Badge>
                )}
                <div className="flex items-center gap-1 mt-3 text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                  <Plus className="w-3 h-3" />
                  创建任务
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      {data && data.length === 0 && !isFetching && (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <p className="text-sm">未找到与法律相关的热搜话题，请尝试刷新热点后重试</p>
        </div>
      )}
    </div>
  )
}
