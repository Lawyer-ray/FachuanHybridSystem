import { useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { RefreshCw, WifiOff, Languages } from 'lucide-react'
import { useHotTopics, useRefreshHotTopics } from '../hooks/use-content-ops'
import { contentOpsApi } from '../api'
import { HOT_TOPIC_SOURCE_LABEL } from '../types'
import { HotTopicCard } from './HotTopicCard'
import { toast } from 'sonner'

const SOURCES = ['all', 'toutiao', 'baidu', 'douyin', '36kr', 'thepaper', 'legaltech'] as const

export function HotTopicList() {
  const [source, setSource] = useState<string>('all')
  const { data: topics, isLoading, error } = useHotTopics(source === 'all' ? undefined : source)
  const refreshMutation = useRefreshHotTopics()
  const [translations, setTranslations] = useState<Record<string, string>>({})
  const [isTranslating, setIsTranslating] = useState(false)

  const handleRefresh = () => {
    refreshMutation.mutate(source === 'all' ? undefined : source)
  }

  const handleTranslate = useCallback(async () => {
    if (!topics || topics.length === 0) return

    // 找出需要翻译的标题（英文标题）
    const needsTranslation = topics.filter(
      (t) => !translations[t.title] && /[a-zA-Z]/.test(t.title) && !/[一-龥]/.test(t.title)
    )
    if (needsTranslation.length === 0) {
      toast.info('没有需要翻译的标题')
      return
    }

    setIsTranslating(true)
    try {
      const { translations: result } = await contentOpsApi.translateTopics(
        needsTranslation.map((t) => t.title)
      )
      const newTranslations: Record<string, string> = {}
      needsTranslation.forEach((t, i) => {
        if (result[i] && result[i] !== t.title) {
          newTranslations[t.title] = result[i]
        }
      })
      setTranslations((prev) => ({ ...prev, ...newTranslations }))
      toast.success(`已翻译 ${Object.keys(newTranslations).length} 条标题`)
    } catch {
      toast.error('翻译失败，请重试')
    } finally {
      setIsTranslating(false)
    }
  }, [topics, translations])

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold">热门话题</h2>
        <div className="flex items-center gap-2">
          {source === 'legaltech' && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={handleTranslate}
              disabled={isTranslating}
            >
              <Languages className={`w-3.5 h-3.5 mr-1 ${isTranslating ? 'animate-pulse' : ''}`} />
              {isTranslating ? '翻译中...' : '一键翻译'}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={handleRefresh}
            disabled={refreshMutation.isPending}
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </div>

      <Tabs value={source} onValueChange={setSource} className="mb-4">
        <TabsList className="h-8">
          {SOURCES.map((src) => (
            <TabsTrigger key={src} value={src} className="text-xs px-3 h-6">
              {src === 'all' ? '全部' : HOT_TOPIC_SOURCE_LABEL[src] || src}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <WifiOff className="w-8 h-8 mb-2 opacity-50" />
          <p className="text-sm">获取热点话题失败</p>
          <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={handleRefresh}>
            重试
          </Button>
        </div>
      ) : topics && topics.length > 0 ? (
        <motion.div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {topics.map((topic, i) => (
            <motion.div
              key={`${topic.source}-${topic.rank}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: Math.min(i * 0.03, 0.5) }}
            >
              <HotTopicCard
                topic={topic}
                translatedTitle={translations[topic.title]}
              />
            </motion.div>
          ))}
        </motion.div>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <p className="text-sm">暂无热点数据</p>
          <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={handleRefresh}>
            获取热点
          </Button>
        </div>
      )}
    </div>
  )
}
