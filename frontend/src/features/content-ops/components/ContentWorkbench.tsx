import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Plus, Sparkles, FileInput, LayoutList } from 'lucide-react'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { TopicInspiration } from './TopicInspiration'
import { DirectInput } from './DirectInput'
import { TaskList } from './TaskList'
import { TaskDetail } from './TaskDetail'
import { CreateTaskDialog } from './CreateTaskDialog'
import type { TopicSuggestion } from '../types'

export function ContentWorkbench() {
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
        className="space-y-6"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
      >
        {/* 页面标题 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">内容运营</h1>
            <p className="text-sm text-muted-foreground mt-1">
              AI 驱动的法律内容创作工作台 — 从选题到生成文章和播客音频
            </p>
          </div>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-1.5" />
            新建任务
          </Button>
        </div>

        {/* 主内容区 */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
          {/* 左侧：创作区 */}
          <div className="space-y-6 min-w-0">
            <Tabs defaultValue="topics">
              <TabsList>
                <TabsTrigger value="topics">
                  <Sparkles className="w-4 h-4 mr-1" />
                  选题灵感
                </TabsTrigger>
                <TabsTrigger value="direct">
                  <FileInput className="w-4 h-4 mr-1" />
                  直投内容
                </TabsTrigger>
              </TabsList>

              <AnimatePresence mode="wait">
                <TabsContent value="topics" className="mt-4" asChild>
                  <motion.div
                    key="topics"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    transition={{ duration: 0.2 }}
                  >
                    <TopicInspiration onSelectTopic={handleSelectTopic} />
                  </motion.div>
                </TabsContent>
              </AnimatePresence>

              <AnimatePresence mode="wait">
                <TabsContent value="direct" className="mt-4" asChild>
                  <motion.div
                    key="direct"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    transition={{ duration: 0.2 }}
                  >
                    <DirectInput onTaskCreated={handleSelectTask} />
                  </motion.div>
                </TabsContent>
              </AnimatePresence>
            </Tabs>
          </div>

          {/* 右侧：任务列表 */}
          <div className="lg:border-l lg:pl-6">
            <Card className="border-0 shadow-none bg-muted/30">
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <LayoutList className="w-4 h-4 text-muted-foreground" />
                  <h3 className="text-sm font-medium">任务记录</h3>
                </div>
                <TaskList
                  selectedTaskId={selectedTaskId}
                  onSelectTask={handleSelectTask}
                />
              </CardContent>
            </Card>
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
            className="w-full sm:max-w-2xl p-0"
            showCloseButton={false}
          >
            <SheetHeader className="border-b px-6 py-4 flex-row items-center justify-between space-y-0">
              <SheetTitle className="text-lg font-semibold">任务详情</SheetTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDetailOpen(false)}
              >
                关闭
              </Button>
            </SheetHeader>
            <motion.div
              className="flex-1 overflow-y-auto p-6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2, delay: 0.1 }}
            >
              {selectedTaskId && <TaskDetail taskId={selectedTaskId} />}
            </motion.div>
          </SheetContent>
        </Sheet>
      </motion.div>
    </ErrorBoundary>
  )
}
