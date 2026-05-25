import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Flame, ExternalLink } from 'lucide-react'
import { HOT_TOPIC_SOURCE_LABEL } from '../types'
import type { HotTopic } from '../types'

interface HotTopicCardProps {
  topic: HotTopic
  translatedTitle?: string
}

const sourceColors: Record<string, string> = {
  toutiao: 'bg-red-100 text-red-700',
  baidu: 'bg-blue-100 text-blue-700',
  weibo: 'bg-orange-100 text-orange-700',
  zhihu: 'bg-sky-100 text-sky-700',
  douyin: 'bg-pink-100 text-pink-700',
}

function formatHeat(heat: number | null): string {
  if (heat === null) return ''
  if (heat >= 10000) return `${(heat / 10000).toFixed(1)}万`
  return heat.toString()
}

export function HotTopicCard({ topic, translatedTitle }: HotTopicCardProps) {
  return (
    <a
      href={topic.url || '#'}
      target="_blank"
      rel="noopener noreferrer"
      className="block group"
    >
      <Card className="p-3 hover:shadow-md transition-all duration-200 cursor-pointer h-full">
        <div className="flex items-start gap-2">
          <span className="text-xs font-mono text-muted-foreground w-5 text-center shrink-0 pt-0.5">
            {topic.rank}
          </span>
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-medium leading-snug group-hover:text-primary transition-colors line-clamp-2">
              {translatedTitle || topic.title}
            </h4>
            {translatedTitle && (
              <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">
                {topic.title}
              </p>
            )}
            <div className="flex items-center gap-2 mt-1.5">
              <Badge
                variant="secondary"
                className={`text-[10px] px-1.5 py-0 h-4 ${sourceColors[topic.source] || 'bg-gray-100 text-gray-700'}`}
              >
                {HOT_TOPIC_SOURCE_LABEL[topic.source] || topic.source}
              </Badge>
              {topic.heat !== null && (
                <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                  <Flame className="w-3 h-3 text-orange-400" />
                  {formatHeat(topic.heat)}
                </span>
              )}
              <ExternalLink className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ml-auto" />
            </div>
          </div>
        </div>
      </Card>
    </a>
  )
}
