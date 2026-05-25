import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
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

// User-scoped localStorage key for favorite model
function getFavoriteKey(): string {
  try {
    // Try to get user ID from JWT payload in localStorage
    const token = localStorage.getItem('access_token')
    if (token) {
      const payload = JSON.parse(atob(token.split('.')[1]))
      return `content_ops_favorite_model_${payload.user_id || 'default'}`
    }
  } catch {
    // ignore
  }
  return 'content_ops_favorite_model_default'
}

export function TopicInspiration({ onSelectTopic }: TopicInspirationProps) {
  const { data: topics, isFetching, refetch, error: topicsError } = useTopicSuggestions()
  const { data: modelsData, isLoading: modelsLoading } = useQuery({
    queryKey: ['workbench', 'models'],
    queryFn: () => workbenchApi.get('models').json<ModelsResponse>(),
    staleTime: 5 * 60 * 1000,
  })
  const [hasRequested, setHasRequested] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [favoriteModel, setFavoriteModel] = useState<string>(
    () => localStorage.getItem(getFavoriteKey()) || ''
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
    const key = getFavoriteKey()
    const newFav = favoriteModel === modelId ? '' : modelId
    setFavoriteModel(newFav)
    if (newFav) {
      localStorage.setItem(key, newFav)
    } else {
      localStorage.removeItem(key)
    }
  }

  return (
    <div className="space-y-3">
      {/* 操作栏 */}
      <div className="flex items-center gap-2">
        {modelsLoading ? (
          <Skeleton className="h-7 w-28" />
        ) : models.length > 0 ? (
          <Popover open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="h-7 text-[11px] gap-1 max-w-[160px]">
                <span className="truncate">
                  {models.find((m) => m.id === selectedModel)?.name || selectedModel || '选择模型'}
                </span>
                <ChevronDown className="size-3 shrink-0" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-0" align="start">
              <ScrollArea className="h-[200px]">
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
                              'size-3.5 shrink-0',
                              selectedModel === model.id ? 'opacity-100' : 'opacity-0',
                            )}
                          />
                          <span className="truncate text-xs">{model.name || model.id}</span>
                        </button>
                        <button
                          onClick={(e) => handleToggleFavorite(model.id, e)}
                          className={cn(
                            'shrink-0 p-0.5 rounded-sm transition-colors',
                            isFav
                              ? 'text-yellow-500 hover:text-yellow-600'
                              : 'text-muted-foreground/30 hover:text-muted-foreground',
                          )}
                          title={isFav ? '取消收藏' : '收藏为默认模型'}
                        >
                          <Star className={cn('size-3', isFav && 'fill-current')} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>
            </PopoverContent>
          </Popover>
        ) : null}

        <Button onClick={handleSuggest} disabled={isFetching} size="sm" className="h-7 text-xs">
          {isFetching ? (
            <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
          ) : (
            <Sparkles className="w-3.5 h-3.5 mr-1" />
          )}
          {hasRequested ? '换一批' : 'AI 推荐'}
        </Button>
      </div>

      {/* 空状态 */}
      {!hasRequested && !topics && !topicsError && (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center mb-2">
            <Lightbulb className="w-5 h-5 text-muted-foreground" />
          </div>
          <p className="text-xs text-muted-foreground">
            点击「AI 推荐」获取法律故事选题
          </p>
        </div>
      )}

      {/* 错误状态 */}
      {topicsError && (
        <div className="text-center py-8 text-xs text-destructive">
          <p>选题推荐获取失败</p>
          <p className="text-muted-foreground mt-1">
            {topicsError && typeof topicsError === 'object' && 'message' in topicsError
              ? String((topicsError as { message: string }).message)
              : '请稍后重试'}
          </p>
        </div>
      )}

      {/* 加载骨架 */}
      {isFetching && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="pb-2 py-3">
                <div className="h-3.5 bg-muted rounded w-3/4" />
                <div className="h-3 bg-muted rounded w-full mt-1.5" />
                <div className="h-3 bg-muted rounded w-2/3 mt-1" />
              </CardHeader>
              <CardContent className="pb-3">
                <div className="h-4 bg-muted rounded w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 选题列表 */}
      {topics && topics.length > 0 && !isFetching && (
        <motion.div
          className="space-y-2"
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
                hidden: { opacity: 0, y: 8 },
                visible: { opacity: 1, y: 0 },
              }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <Card
                className="cursor-pointer transition-all hover:border-primary/50 hover:shadow-sm group"
                onClick={() => onSelectTopic(topic)}
              >
                <CardContent className="p-3 space-y-1.5">
                  <p className="text-sm font-medium group-hover:text-primary transition-colors leading-snug">
                    {topic.title}
                  </p>
                  <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                    {topic.description}
                  </p>
                  <div className="flex items-center gap-2 pt-0.5">
                    <Badge variant="secondary" className="text-[10px] h-5">
                      <Search className="w-2.5 h-2.5 mr-0.5" />
                      {topic.suggested_keyword}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                      点击创建 →
                    </span>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      {topics && topics.length === 0 && !isFetching && (
        <div className="text-center py-8 text-xs text-muted-foreground">
          暂无选题建议，请稍后重试
        </div>
      )}
    </div>
  )
}
