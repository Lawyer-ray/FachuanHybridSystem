/**
 * CaseFlowDemo - 案件全流程管理与智能文书生成演示
 * @module features/home/components/CaseFlowDemo
 *
 * 展示案件材料上传 → AI识别 → 文件夹生成 → 文书归档的完整流程
 */

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence, useInView } from 'framer-motion'
import {
  Upload,
  Sparkles,
  FolderOpen,
  FileText,
  Archive,
  Check,
  Loader2,
  ChevronRight,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { springConfig } from '../../constants'

// AI 识别结果数据
const AI_RECOGNITION_DATA = {
  caseType: '民间借贷纠纷',
  plaintiff: '张三',
  defendant: 'XX科技有限公司',
  amount: '¥500,000',
}

// 生成状态
type GenerationStatus = 'pending' | 'processing' | 'completed'

// 文件夹树结构
const FOLDER_TREE = {
  name: '张三诉XX公司民间借贷纠纷',
  children: [
    {
      name: '一审',
      children: [
        {
          name: '1-立案材料',
          children: [
            {
              name: '1-起诉状',
              children: [{ name: '起诉状.docx', isFile: true }],
            },
            {
              name: '2-当事人身份证明',
              children: [{ name: '张三身份证.pdf', isFile: true }],
            },
            {
              name: '3-委托代理手续',
              children: [
                { name: '授权委托书.docx', isFile: true },
                { name: '律师证复印件.pdf', isFile: true },
                { name: '所函.docx', isFile: true },
              ],
            },
          ],
        },
        {
          name: '2-证据材料',
          children: [
            { name: '借条.pdf', isFile: true },
            { name: '转账记录.pdf', isFile: true },
          ],
        },
      ],
    },
  ],
}

interface FolderNodeProps {
  node: {
    name: string
    isFile?: boolean
    children?: FolderNodeProps['node'][]
  }
  level: number
  isVisible: boolean
  delay: number
}

/**
 * 文件夹/文件节点组件
 */
function FolderNode({ node, level, isVisible, delay }: FolderNodeProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasChildren = node.children && node.children.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={isVisible ? { opacity: 1, x: 0 } : { opacity: 0, x: -20 }}
      transition={{ ...springConfig, delay }}
      className="select-none"
    >
      <div
        className={cn(
          'flex items-center gap-2 py-1.5 px-2 rounded-lg',
          'hover:bg-white/5 transition-colors cursor-pointer',
          level === 0 && 'font-semibold'
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => hasChildren && setIsExpanded(!isExpanded)}
      >
        {hasChildren && (
          <motion.span
            animate={{ rotate: isExpanded ? 90 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronRight className="h-3 w-3 text-gray-500" />
          </motion.span>
        )}
        {node.isFile ? (
          <FileText className="h-4 w-4 text-cyan-400" />
        ) : (
          <FolderOpen className="h-4 w-4 text-yellow-400" />
        )}
        <span className={cn('text-sm', node.isFile ? 'text-gray-300' : 'text-white')}>
          {node.name}
        </span>
        {isVisible && (
          <motion.span
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: delay + 0.2 }}
            className="ml-auto px-1.5 py-0.5 text-[10px] font-medium bg-green-500/20 text-green-400 rounded"
          >
            NEW
          </motion.span>
        )}
      </div>
      <AnimatePresence>
        {isExpanded && hasChildren && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {node.children?.map((child, index) => (
              <FolderNode
                key={child.name}
                node={child}
                level={level + 1}
                isVisible={isVisible}
                delay={delay + (index + 1) * 0.1}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export function CaseFlowDemo() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const isInView = useInView(sectionRef, { once: true, margin: '-100px' })

  const [stage, setStage] = useState<'upload' | 'recognizing' | 'generating' | 'completed'>('upload')
  const [folderStatus, setFolderStatus] = useState<GenerationStatus>('pending')
  const [docsStatus, setDocsStatus] = useState<GenerationStatus>('pending')
  const [archiveStatus, setArchiveStatus] = useState<GenerationStatus>('pending')
  const [showTree, setShowTree] = useState(false)

  // 自动播放动画
  useEffect(() => {
    if (!isInView) return

    const timeline = async () => {
      // 阶段1：上传
      await new Promise((r) => setTimeout(r, 1000))
      setStage('recognizing')

      // 阶段2：AI识别
      await new Promise((r) => setTimeout(r, 2000))
      setStage('generating')
      setFolderStatus('processing')

      // 阶段3：生成文件夹
      await new Promise((r) => setTimeout(r, 1500))
      setFolderStatus('completed')
      setShowTree(true)
      setDocsStatus('processing')

      // 阶段4：生成文书
      await new Promise((r) => setTimeout(r, 1500))
      setDocsStatus('completed')
      setArchiveStatus('processing')

      // 阶段5：归档完成
      await new Promise((r) => setTimeout(r, 1000))
      setArchiveStatus('completed')
      setStage('completed')
    }

    timeline()
  }, [isInView])

  const getStatusIcon = (status: GenerationStatus) => {
    switch (status) {
      case 'pending':
        return <span className="text-gray-500">—</span>
      case 'processing':
        return <Loader2 className="h-4 w-4 text-cyan-400 animate-spin" />
      case 'completed':
        return <Check className="h-4 w-4 text-green-400" />
    }
  }

  return (
    <section
      ref={sectionRef}
      id="case-flow"
      className="relative py-20 md:py-28 bg-gray-950"
    >
      {/* 背景装饰 */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/3 top-1/4 h-[400px] w-[400px] rounded-full bg-purple-600/5 blur-[100px]" />
        <div className="absolute right-1/4 bottom-1/3 h-[300px] w-[300px] rounded-full bg-cyan-500/5 blur-[80px]" />
      </div>

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 2xl:max-w-[1600px]">
        {/* 标题 */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={springConfig}
          className="mb-12 text-center"
        >
          <span className="mb-4 inline-flex items-center gap-2 rounded-full border border-purple-500/30 bg-purple-500/10 px-4 py-1.5 text-sm font-medium text-purple-300">
            <Archive className="h-4 w-4" />
            智能归档
          </span>
          <h2 className="mb-4 text-3xl font-bold text-white md:text-4xl lg:text-5xl">
            案件全流程管理与
            <span className="bg-gradient-to-r from-purple-400 to-cyan-400 bg-clip-text text-transparent">
              智能文书生成
            </span>
          </h2>
          <p className="mx-auto max-w-2xl text-gray-400">
            一次录入、全局复用，文件夹自动生成，文书自动归档到指定位置
          </p>
        </motion.div>

        {/* 演示区域 */}
        <div className="grid gap-6 lg:grid-cols-2 items-stretch">
          {/* 左侧：上传和识别 */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={springConfig}
            className="flex flex-col space-y-4"
          >
            {/* 上传区域 */}
            <div
              className={cn(
                'rounded-2xl border p-6 transition-all duration-500',
                stage === 'upload'
                  ? 'border-cyan-500/50 bg-cyan-500/5'
                  : 'border-gray-800 bg-gray-900/50'
              )}
            >
              <div className="flex flex-col items-center gap-3 text-center">
                <div
                  className={cn(
                    'flex h-16 w-16 items-center justify-center rounded-2xl transition-colors',
                    stage === 'upload' ? 'bg-cyan-500/20' : 'bg-gray-800'
                  )}
                >
                  <Upload
                    className={cn(
                      'h-8 w-8',
                      stage === 'upload' ? 'text-cyan-400' : 'text-gray-500'
                    )}
                  />
                </div>
                <div>
                  <h3 className="font-semibold text-white">上传案件材料</h3>
                  <p className="text-sm text-gray-500">身份证、营业执照、合同等</p>
                </div>
              </div>
            </div>

            {/* AI 识别结果 */}
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{
                opacity: stage !== 'upload' ? 1 : 0,
                height: stage !== 'upload' ? 'auto' : 0,
              }}
              className="overflow-hidden rounded-2xl border border-purple-500/30 bg-purple-500/5"
            >
              <div className="p-4">
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-purple-400" />
                  <span className="font-semibold text-white">AI 识别结果</span>
                  {stage === 'recognizing' && (
                    <Loader2 className="ml-auto h-4 w-4 animate-spin text-purple-400" />
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: '案由', value: AI_RECOGNITION_DATA.caseType },
                    { label: '原告', value: AI_RECOGNITION_DATA.plaintiff },
                    { label: '被告', value: AI_RECOGNITION_DATA.defendant },
                    { label: '标的', value: AI_RECOGNITION_DATA.amount },
                  ].map((item, index) => (
                    <motion.div
                      key={item.label}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: stage !== 'upload' ? 1 : 0 }}
                      transition={{ delay: index * 0.15 }}
                      className="rounded-lg bg-gray-800/50 p-3"
                    >
                      <div className="text-xs text-gray-500">{item.label}</div>
                      <div className="font-medium text-white">
                        {stage === 'recognizing' && index > 1 ? '—' : item.value}
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </motion.div>

            {/* 生成状态 */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: stage === 'generating' || stage === 'completed' ? 1 : 0 }}
              className="rounded-2xl border border-gray-800 bg-gray-900/50 p-4 flex-1"
            >
              <div className="space-y-3">
                {[
                  { icon: FolderOpen, label: '文件夹结构', status: folderStatus },
                  { icon: FileText, label: '文书生成', status: docsStatus },
                  { icon: Archive, label: '自动归档', status: archiveStatus },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center gap-3 rounded-lg bg-gray-800/30 p-3"
                  >
                    <item.icon className="h-5 w-5 text-gray-400" />
                    <span className="flex-1 text-sm text-gray-300">{item.label}</span>
                    {getStatusIcon(item.status)}
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>

          {/* 右侧：文件夹树 */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={springConfig}
            className="rounded-2xl border border-gray-800 bg-gray-900/50 overflow-hidden flex flex-col"
          >
            {/* 标题栏 */}
            <div className="flex items-center gap-3 border-b border-gray-800 bg-gray-900/80 px-4 py-3">
              <FolderOpen className="h-5 w-5 text-yellow-400" />
              <span className="font-semibold text-white">{FOLDER_TREE.name}</span>
              <span
                className={cn(
                  'ml-auto rounded-full px-2 py-0.5 text-xs font-medium',
                  stage === 'completed'
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-cyan-500/20 text-cyan-400'
                )}
              >
                {stage === 'completed' ? '已完成' : '生成中...'}
              </span>
            </div>

            {/* 文件夹内容 */}
            <div className="p-4 flex-1">
              {FOLDER_TREE.children.map((child, index) => (
                <FolderNode
                  key={child.name}
                  node={child}
                  level={0}
                  isVisible={showTree}
                  delay={index * 0.1}
                />
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
