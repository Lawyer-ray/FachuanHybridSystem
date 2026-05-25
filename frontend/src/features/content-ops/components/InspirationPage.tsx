import { useState } from 'react'
import { motion } from 'framer-motion'
import { Separator } from '@/components/ui/separator'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { HotTopicList } from './HotTopicList'
import { InspirationSection } from './InspirationSection'
import { CreateTaskDialog } from './CreateTaskDialog'
import type { TopicSuggestion } from '../types'

export function InspirationPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogKeyword, setDialogKeyword] = useState('')
  const [dialogCaseSummary, setDialogCaseSummary] = useState('')

  const handleSelectTopic = (topic: TopicSuggestion) => {
    setDialogKeyword(topic.suggested_keyword)
    setDialogCaseSummary(`${topic.title}：${topic.description}`)
    setDialogOpen(true)
  }

  return (
    <ErrorBoundary>
      <motion.div
        className="flex flex-col min-h-[calc(100vh-8rem)]"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        {/* 主内容区 */}
        <div className="flex-1 space-y-6 py-6">
          {/* 热门话题区域 */}
          <HotTopicList />

          <Separator />

          {/* AI 灵感区域 */}
          <InspirationSection onSelectTopic={handleSelectTopic} />
        </div>

        {/* 创建任务对话框 */}
        <CreateTaskDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          defaultKeyword={dialogKeyword}
          defaultCaseSummary={dialogCaseSummary}
          defaultMode="search"
        />
      </motion.div>
    </ErrorBoundary>
  )
}
