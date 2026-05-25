import { useState } from 'react'
import { useNavigate } from 'react-router'
import { motion, AnimatePresence } from 'framer-motion'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Plus, Sparkles, FileInput, ArrowRight } from 'lucide-react'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { TopicInspiration } from './TopicInspiration'
import { DirectInput } from './DirectInput'
import { TaskList } from './TaskList'
import { TaskDetail } from './TaskDetail'
import { CreateTaskDialog } from './CreateTaskDialog'
import { PATHS } from '@/routes/paths'
import type { TopicSuggestion } from '../types'

export function ContentWorkbench() {
  const navigate = useNavigate()
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [dialogKeyword, setDialogKeyword] = useState('')
  const [dialogCaseSummary, setDialogCaseSummary] = useState('')

  const handleSelectTopic = (topic: TopicSuggestion) => {
    setDialogKeyword(topic.suggested_keyword)
    setDialogCaseSummary(`${topic.title}：${topic.description}`)
    setDialogOpen(true)
  }

  const handleSelectTask = (taskId: number) => {
    setSelectedTaskId(taskId)
    setDetailOpen(true)
  }

  return (
    <ErrorBoundary>
      <motion.div
        className="flex flex-col h-[calc(100vh-8rem)]"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        {/* 页面标题栏 */}
        <div className="flex items-center justify-between pb-4 border-b">
          <div>
            <h1 className="text-xl font-bold tracking-tight">内容运营</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              AI 驱动的法律内容创作 — 从选题到生成文章和播客音频
            </p>
          </div>
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            新建任务
          </Button>
        </div>

        {/* 主内容区 */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-0 lg:divide-x min-h-0 mt-4">
          {/* 左侧：任务列表（主区域） */}
          <div className="min-w-0 overflow-hidden flex flex-col">
            <TaskList
              selectedTaskId={selectedTaskId}
              onSelectTask={handleSelectTask}
            />
          </div>

          {/* 右侧：创作工具（辅助区域） */}
          <div className="min-w-0 overflow-hidden flex flex-col pl-0 lg:pl-5">
            <Tabs defaultValue="topics" className="flex flex-col flex-1 min-h-0">
              <TabsList className="self-start">
                <TabsTrigger value="topics" className="text-xs">
                  <Sparkles className="w-3.5 h-3.5 mr-1" />
                  选题灵感
                </TabsTrigger>
                <TabsTrigger value="direct" className="text-xs">
                  <FileInput className="w-3.5 h-3.5 mr-1" />
                  直投内容
                </TabsTrigger>
              </TabsList>

              <div className="flex-1 min-h-0 overflow-y-auto mt-3">
                <AnimatePresence mode="wait">
                  <TabsContent value="topics" className="mt-0" asChild>
                    <motion.div
                      key="topics"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.2 }}
                    >
                      <div className="space-y-3">
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full h-8 text-xs justify-between"
                          onClick={() => navigate(PATHS.ADMIN_TOOLS_CONTENT_OPS_INSPIRATION)}
                        >
                          <span className="flex items-center gap-1">
                            <Sparkles className="w-3.5 h-3.5" />
                            查看完整灵感页（热搜 + AI 筛选）
                          </span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </Button>
                        <TopicInspiration onSelectTopic={handleSelectTopic} />
                      </div>
                    </motion.div>
                  </TabsContent>
                </AnimatePresence>

                <AnimatePresence mode="wait">
                  <TabsContent value="direct" className="mt-0" asChild>
                    <motion.div
                      key="direct"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.2 }}
                    >
                      <DirectInput onTaskCreated={handleSelectTask} />
                    </motion.div>
                  </TabsContent>
                </AnimatePresence>
              </div>
            </Tabs>
          </div>
        </div>

        {/* 创建任务对话框 */}
        <CreateTaskDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          defaultKeyword={dialogKeyword}
          defaultCaseSummary={dialogCaseSummary}
          defaultMode={dialogKeyword ? 'search' : 'direct'}
        />

        {/* 任务详情侧面板 */}
        <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
          <SheetContent
            side="right"
            className="w-full sm:max-w-xl p-0"
            showCloseButton={false}
          >
            <SheetHeader className="border-b px-5 py-3 flex-row items-center justify-between space-y-0">
              <SheetTitle className="text-base font-semibold">任务详情</SheetTitle>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => setDetailOpen(false)}
              >
                关闭
              </Button>
            </SheetHeader>
            <div className="flex-1 overflow-y-auto p-5">
              {selectedTaskId && <TaskDetail taskId={selectedTaskId} />}
            </div>
          </SheetContent>
        </Sheet>
      </motion.div>
    </ErrorBoundary>
  )
}
