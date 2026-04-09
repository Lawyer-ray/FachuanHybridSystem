/**
 * useFlowAnimation - SMS 流程动画控制 Hook
 * @module features/home/hooks/use-flow-animation
 *
 * 管理 SMS 流程演示的动画状态和序列控制
 * 实现播放、重置功能和步骤计时
 *
 * Requirements: 4.3, 4.7, 4.8
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import type { SMSFlowState, NodeStatus } from '../types'
import { SMS_PROCESS_NODES, SMS_RESULT_CARDS } from '../constants'

// ============================================================================
// 常量定义
// ============================================================================

/** 每个步骤的默认持续时间（毫秒） */
const DEFAULT_STEP_DURATION = 800

/** 总步骤数 */
const TOTAL_STEPS = 13

// ============================================================================
// 初始状态
// ============================================================================

const initialState: SMSFlowState = {
  currentStep: 0,
  phoneVisible: false,
  smsVisible: false,
  forwardVisible: false,
  arrowActive: false,
  nodeStatuses: SMS_PROCESS_NODES.reduce(
    (acc, node) => ({ ...acc, [node.id]: 'idle' as NodeStatus }),
    {} as Record<string, NodeStatus>
  ),
  resultCardsVisible: SMS_RESULT_CARDS.map(() => false),
  isPlaying: false,
}

// ============================================================================
// Hook 返回类型
// ============================================================================

interface UseFlowAnimationReturn {
  /** 当前动画状态 */
  state: SMSFlowState
  /** 当前步骤（1-based，用于显示） */
  currentStep: number
  /** 是否正在播放 */
  isPlaying: boolean
  /** 开始播放动画 */
  play: () => void
  /** 重置动画状态 */
  reset: () => void
  /** 总步骤数 */
  totalSteps: number
}

// ============================================================================
// 步骤执行函数
// ============================================================================

/**
 * 根据步骤索引更新状态
 *
 * 动画序列：
 * - Step 1: 显示手机和短信通知
 * - Step 2: 显示转发卡片和激活箭头
 * - Steps 3-9: 依次激活每个处理节点（receive → parse → download → match → rename → analyze → notify）
 * - Steps 10-13: 依次显示结果卡片
 */
function getStateForStep(step: number, prevState: SMSFlowState): Partial<SMSFlowState> {
  const nodeIds = SMS_PROCESS_NODES.map((n) => n.id)

  switch (step) {
    // Step 1: 显示手机和短信通知
    case 1:
      return {
        phoneVisible: true,
        smsVisible: true,
      }

    // Step 2: 显示转发卡片和激活箭头
    case 2:
      return {
        forwardVisible: true,
        arrowActive: true,
      }

    // Steps 3-9: 处理节点动画
    case 3:
    case 4:
    case 5:
    case 6:
    case 7:
    case 8:
    case 9: {
      const nodeIndex = step - 3 // 0-6
      const currentNodeId = nodeIds[nodeIndex]
      const prevNodeId = nodeIndex > 0 ? nodeIds[nodeIndex - 1] : null

      const newNodeStatuses = { ...prevState.nodeStatuses }

      // 将前一个节点设为完成状态
      if (prevNodeId) {
        newNodeStatuses[prevNodeId] = 'completed'
      }

      // 将当前节点设为处理中状态
      newNodeStatuses[currentNodeId] = 'processing'

      return { nodeStatuses: newNodeStatuses }
    }

    // Step 10: 完成最后一个节点，显示第一个结果卡片
    case 10: {
      const lastNodeId = nodeIds[nodeIds.length - 1]
      const newNodeStatuses = { ...prevState.nodeStatuses }
      newNodeStatuses[lastNodeId] = 'completed'

      const newResultCards = [...prevState.resultCardsVisible]
      newResultCards[0] = true

      return {
        nodeStatuses: newNodeStatuses,
        resultCardsVisible: newResultCards,
      }
    }

    // Steps 11-13: 显示剩余结果卡片
    case 11:
    case 12:
    case 13: {
      const cardIndex = step - 10 // 1, 2, 3
      const newResultCards = [...prevState.resultCardsVisible]
      newResultCards[cardIndex] = true

      return { resultCardsVisible: newResultCards }
    }

    default:
      return {}
  }
}

// ============================================================================
// Hook 实现
// ============================================================================

/**
 * SMS 流程动画控制 Hook
 *
 * @param stepDuration - 每个步骤的持续时间（毫秒），默认 800ms
 * @returns 动画状态和控制函数
 *
 * @example
 * ```tsx
 * function SMSFlowDemo() {
 *   const { state, currentStep, isPlaying, play, reset, totalSteps } = useFlowAnimation()
 *
 *   return (
 *     <div>
 *       <FlowControls
 *         isPlaying={isPlaying}
 *         currentStep={currentStep}
 *         totalSteps={totalSteps}
 *         onPlay={play}
 *         onReset={reset}
 *       />
 *       <PhoneMockup smsVisible={state.smsVisible} />
 *       <ProcessNodes nodeStatuses={state.nodeStatuses} />
 *       <ResultCards visibleCards={state.resultCardsVisible} />
 *     </div>
 *   )
 * }
 * ```
 */
export function useFlowAnimation(
  stepDuration: number = DEFAULT_STEP_DURATION
): UseFlowAnimationReturn {
  const [state, setState] = useState<SMSFlowState>(initialState)
  const [internalStep, setInternalStep] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /**
   * 清除定时器
   */
  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  /**
   * 开始播放动画
   */
  const play = useCallback(() => {
    // 如果已经在播放，不做任何操作
    if (isPlaying) return

    // 重置状态并开始播放
    setState(initialState)
    setInternalStep(1)
    setIsPlaying(true)
  }, [isPlaying])

  /**
   * 重置动画状态
   */
  const reset = useCallback(() => {
    clearTimer()
    setState(initialState)
    setInternalStep(0)
    setIsPlaying(false)
  }, [clearTimer])

  /**
   * 动画步骤执行效果
   */
  useEffect(() => {
    if (!isPlaying || internalStep === 0) return

    // 执行当前步骤的状态更新
    setState((prev) => ({
      ...prev,
      ...getStateForStep(internalStep, prev),
      currentStep: internalStep,
    }))

    // 如果还有下一步，设置定时器
    if (internalStep < TOTAL_STEPS) {
      timerRef.current = setTimeout(() => {
        setInternalStep((prev) => prev + 1)
      }, stepDuration)
    } else {
      // 动画完成
      setIsPlaying(false)
    }

    return () => {
      clearTimer()
    }
  }, [isPlaying, internalStep, stepDuration, clearTimer])

  /**
   * 组件卸载时清理
   */
  useEffect(() => {
    return () => {
      clearTimer()
    }
  }, [clearTimer])

  return {
    state,
    currentStep: internalStep,
    isPlaying,
    play,
    reset,
    totalSteps: TOTAL_STEPS,
  }
}
