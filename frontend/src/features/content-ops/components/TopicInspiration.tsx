import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Sparkles, RefreshCw, Search, Lightbulb, Check, ChevronDown, Star } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTopicSuggestions } from '../hooks/use-content-ops'
import { createFeatureApiClient } from '@/lib/api'
import type { TopicSuggestion } from '../types'

interface LLMModel {
  id: string
  name: string
  backend: string
  max_model_len?: number
}

interface ModelsResponse {
  models: LLMModel[]
  default_model: string
  is_fallback: boolean
  error_message: string
}

const workbenchApi = createFeatureApiClient('workbench')

interface TopicInspirationProps {
  onSelectTopic: (topic: TopicSuggestion) => void
}

export function TopicInspiration({ onSelectTopic }: TopicInspirationProps) {
  const { data: topics, isFetching, refetch } = useTopicSuggestions()
  const { data: modelsData, isLoading: modelsLoading } = useQuery({
    queryKey: ['workbench', 'models'],
    queryFn: () => workbenchApi.get('models').json<ModelsResponse>(),
    staleTime: 5 * 60 * 1000,
  })
  const [hasRequested, setHasRequested] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [favoriteModel, setFavoriteModel] = useState<string>(
    () => localStorage.getItem('content_ops_favorite_model') || ''
  )
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false)

  const models = useMemo(() => modelsData?.models || [], [modelsData?.models])

  // 设置默认模型
  useEffect(() => {
    if (models.length > 0 && !selectedModel) {
      if (favoriteModel && models.find((m) => m.id === favoriteModel)) {
        setSelectedModel(favoriteModel)
      } else if (modelsData?.default_model) {
        setSelectedModel(modelsData.default_model)
      } else {
        setSelectedModel(models[0].id)
      }
    }
  }, [models, selectedModel, favoriteModel, modelsData?.default_model])

  const handleSuggest = () => {
    setHasRequested(true)
    refetch(selectedModel)
  }

  const handleToggleFavorite = (modelId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const newFav = favoriteModel === modelId ? '' : modelId
    setFavoriteModel(newFav)
    if (newFav) {
      localStorage.setItem('content_ops_favorite_model', newFav)
    } else {
      localStorage.removeItem('content_ops_favorite_model')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-medium">AI 选题推荐</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            AI 基于法律热点自动生成选题建议，点击选题直接创建检索任务
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* 模型选择器 */}
          {modelsLoading ? (
            <Skeleton className="h-8 w-32" />
          ) : models.length > 0 ? (
            <Popover open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 text-xs gap-1 max-w-[180px]">
                  <span className="truncate">
                    {models.find((m) => m.id === selectedModel)?.name || selectedModel || '选择模型'}
                  </span>
                  <ChevronDown className="size-3 shrink-0" />
                </Button>
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
                            selectedModel === model.id && 'bg-accent',
                          )}
                        >
                          <button
                            onClick={() => {
                              setSelectedModel(model.id)
                              setModelSelectorOpen(false)
                            }}
                            className="flex flex-1 items-center gap-2 min-w-0"
                          >
                            <Check
                              className={cn(
                                'size-4 shrink-0',
                                selectedModel === model.id ? 'opacity-100' : 'opacity-0',
                              )}
                            />
                            <span className="truncate">{model.name || model.id}</span>
                          </button>
                          <button
                            onClick={(e) => handleToggleFavorite(model.id, e)}
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
          ) : null}

          <Button
            onClick={handleSuggest}
            disabled={isFetching}
            size="sm"
          >
            {isFetching ? (
              <RefreshCw className="w-4 h-4 mr-1.5 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4 mr-1.5" />
            )}
            {hasRequested ? '换一批' : 'AI 推荐选题'}
          </Button>
        </div>
      </div>

      {!hasRequested && !topics && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
            <Lightbulb className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">
            点击上方按钮，AI 将为你推荐法律故事选题
          </p>
        </div>
      )}

      {isFetching && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="pb-2">
                <div className="h-4 bg-muted rounded w-3/4" />
                <div className="h-3 bg-muted rounded w-full mt-2" />
                <div className="h-3 bg-muted rounded w-2/3 mt-1" />
              </CardHeader>
              <CardContent>
                <div className="h-5 bg-muted rounded w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {topics && topics.length > 0 && !isFetching && (
        <motion.div
          className="grid gap-3 sm:grid-cols-2"
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.06 } },
          }}
        >
          {topics.map((topic: TopicSuggestion, index: number) => (
            <motion.div
              key={index}
              variants={{
                hidden: { opacity: 0, y: 12, scale: 0.97 },
                visible: { opacity: 1, y: 0, scale: 1 },
              }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
            >
              <Card
                className="cursor-pointer transition-all hover:border-primary/50 hover:shadow-sm group"
                onClick={() => onSelectTopic(topic)}
              >
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm group-hover:text-primary transition-colors">
                    {topic.title}
                  </CardTitle>
                  <CardDescription className="text-xs line-clamp-2">
                    {topic.description}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">
                      <Search className="w-3 h-3 mr-1" />
                      {topic.suggested_keyword}
                    </Badge>
                    <span className="text-xs text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                      点击创建任务 →
                    </span>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      {topics && topics.length === 0 && !isFetching && (
        <div className="text-center py-8 text-sm text-muted-foreground">
          暂无选题建议，请稍后重试
        </div>
      )}
    </div>
  )
}
