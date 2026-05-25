import { useState } from 'react'
import { useNavigate } from 'react-router'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ArrowLeft } from 'lucide-react'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { HotTopicList } from './HotTopicList'
import { InspirationSection } from './InspirationSection'
import { CreateTaskDialog } from './CreateTaskDialog'
import { PATHS } from '@/routes/paths'
import type { TopicSuggestion } from '../types'

export function InspirationPage() {
  const navigate = useNavigate()
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
        {/* 页面标题栏 */}
        <div className="flex items-center gap-3 pb-4 border-b">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => navigate(PATHS.ADMIN_TOOLS_CONTENT_OPS)}
          >
            <ArrowLeft className="w-3.5 h-3.5 mr-1" />
            返回工作台
          </Button>
          <div>
            <h1 className="text-xl font-bold tracking-tight">选题灵感</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              从各大平台热搜中发现法律相关选题，AI 智能筛选推荐
            </p>
          </div>
        </div>

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
