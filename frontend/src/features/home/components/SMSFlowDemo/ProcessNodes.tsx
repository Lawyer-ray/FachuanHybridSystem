/**
 * ProcessNodes - 短信处理流程节点组件
 * @module features/home/components/SMSFlowDemo/ProcessNodes
 *
 * 实现 7 个处理节点（接收、解析、下载、匹配、重命名、分析、通知）
 * 支持三种状态样式（idle、processing、completed）
 * Requirements: 4.4, 4.5, 4.6
 */

import { motion } from 'framer-motion'
import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'
import { SMS_PROCESS_NODES } from '../../constants'
import type { NodeStatus, ProcessNodeData } from '../../types'

interface ProcessNodesProps {
  /** 每个节点的状态映射 */
  nodeStatuses: Record<string, NodeStatus>
  /** 自定义类名 */
  className?: string
}

interface ProcessNodeProps {
  /** 节点数据 */
  node: ProcessNodeData
  /** 节点状态 */
  status: NodeStatus
}

/**
 * 获取节点状态对应的样式类
 */
function getStatusStyles(status: NodeStatus, _colorScheme: string) {
  const baseStyles = cn(
    'relative flex flex-col items-center justify-center gap-2 rounded-xl p-4',
    'border-2 transition-all duration-300',
    'bg-gray-900/50 backdrop-blur-sm'
  )

  switch (status) {
    case 'idle':
      return cn(baseStyles, 'border-gray-700/50 opacity-40')

    case 'processing':
      return cn(
        baseStyles,
        'border-yellow-500 opacity-100',
        'shadow-lg shadow-yellow-500/20'
      )

    case 'completed':
      return cn(
        baseStyles,
        'border-green-500 opacity-100',
        'shadow-lg shadow-green-500/20'
      )

    default:
      return baseStyles
  }
}

/**
 * 获取图标容器的样式
 */
function getIconContainerStyles(status: NodeStatus, colorScheme: string) {
  const colorMap: Record<string, string> = {
    receive: 'from-blue-500 to-blue-600',
    parse: 'from-purple-500 to-purple-600',
    download: 'from-cyan-500 to-cyan-600',
    match: 'from-orange-500 to-orange-600',
    rename: 'from-pink-500 to-pink-600',
    analyze: 'from-violet-500 to-violet-600',
    notify: 'from-amber-500 to-amber-600',
  }

  const gradient = colorMap[colorScheme] || 'from-gray-500 to-gray-600'

  return cn(
    'flex h-10 w-10 items-center justify-center rounded-xl',
    'bg-gradient-to-br',
    gradient,
    status === 'idle' && 'grayscale'
  )
}

/**
 * 单个处理节点组件
 */
function ProcessNode({ node, status }: ProcessNodeProps) {
  const Icon = node.icon

  return (
    <motion.div
      className={getStatusStyles(status, node.colorScheme)}
      animate={
        status === 'processing'
          ? {
              scale: [1, 1.02, 1],
              borderColor: ['rgb(234 179 8)', 'rgb(250 204 21)', 'rgb(234 179 8)'],
            }
          : {}
      }
      transition={
        status === 'processing'
          ? {
              duration: 1.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }
          : {}
      }
    >
      {/* 图标容器 */}
      <div className={getIconContainerStyles(status, node.colorScheme)}>
        <Icon className="h-5 w-5 text-white" />
      </div>

      {/* 节点标题 */}
      <span
        className={cn(
          'text-xs font-medium',
          status === 'idle' ? 'text-gray-500' : 'text-white'
        )}
      >
        {node.title}
      </span>

      {/* 完成状态的勾选图标覆盖 */}
      {status === 'completed' && (
        <motion.div
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{
            type: 'spring',
            stiffness: 500,
            damping: 25,
          }}
          className={cn(
            'absolute -right-1.5 -top-1.5',
            'flex h-5 w-5 items-center justify-center rounded-full',
            'bg-green-500 shadow-md shadow-green-500/50'
          )}
          data-testid="check-icon"
        >
          <Check className="h-3 w-3 text-white" strokeWidth={3} />
        </motion.div>
      )}
    </motion.div>
  )
}

/**
 * 处理节点网格组件
 */
export function ProcessNodes({ nodeStatuses, className }: ProcessNodesProps) {
  return (
    <div
      className={cn(
        'grid grid-cols-2 gap-3',
        'sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-7',
        className
      )}
    >
      {SMS_PROCESS_NODES.map((node) => (
        <ProcessNode
          key={node.id}
          node={node}
          status={nodeStatuses[node.id] || 'idle'}
        />
      ))}
    </div>
  )
}
