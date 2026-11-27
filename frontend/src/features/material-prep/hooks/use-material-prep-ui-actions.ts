/**
 * 材料预处理页接 UI 动作的**全部接线**，一行进 `DeskPage`：
 *
 * 1. 声明「AI 能读的那部分页面状态」（阶段 / 选中包 / 各阶段条数），以及没选中包时**判不了**
 *    （`blockedActions`：模型据此决定是问人还是换路，而不是自己编一个 `packId`）；
 * 2. 监听执行器的广播事件 → 重拉列表 + toast（执行器可能在 copilot 那侧跑，见
 *    `ui-actions.ts` 的 `PACK_STATUS_CHANGED_EVENT`）；
 * 3. 消费「先跳过来、再由本页继续做」的挂起队列。
 *
 * 为什么合成一个 hook 而不是散在 DeskPage 里：三件事共用同一个 QueryClient 与同一句文案，
 * 而 DeskPage 已接近拆分阈值（350 行软红线）。hook 里没有业务判断，只有接线。
 */

import { useCallback, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router'
import { toast } from 'sonner'

import { ROUTES } from '@/app/paths'
import { useUiPageState, useUiPendingAction } from '@/features/copilot/ui-tools/contract'
import type { BlockedAction, UiActionRequest } from '@/features/copilot/ui-tools/contract'

import type { PrepStage } from '../stages'
import {
  judgeMaterialPack,
  PACK_JUDGE_LABEL,
  PACK_STATUS_CHANGED_EVENT,
} from '../ui-actions'
import type { PackStatusChangedDetail } from '../ui-actions'
import { PACKS_KEY } from './use-material-packs'

/** 页面声明的页名（与 `useUiPageState` 的注册键同一个字符串） */
const PAGE_NAME = 'material-prep'

export function useMaterialPrepUiActions({
  stage,
  selected,
  counts,
}: {
  /** 当前筛选阶段（页签所在的那一段漏斗） */
  stage: PrepStage
  /** 选中材料包的 **id**（不是下标：模型只能拿 id 去调动作） */
  selected: number | null
  /** 各阶段条数（角标上的那几个数字） */
  counts: Record<PrepStage, number>
}): void {
  const queryClient = useQueryClient()
  const location = useLocation()

  // 页面状态快照：**只放判断下一步真正要用的字段**（整页状态进模型上下文既贵又容易过期）。
  // 后端 `UiSnapshotIn` 的 `state` 上限 2000 字且超限**直接拒收**（不截断，截断会造出
  // 「页面上没有这个字段」的假事实）：这里四个字段全是小标量（阶段名 / 包 id / 四个计数），
  // 天然在限内；往这里加字段前先估一下序列化长度。
  // 没选中材料包时，「判材料包」这条动作**有但此刻不可用**：模型不被告知就会自己编一个
  // `packId` 硬调（它看到 judge 在 available_actions 里）。理由必须点名「先选一条」——
  // 模型据此才能决定是问人（问律师指的是哪一个）还是换一条路，而不是猜一个 id。
  const blockedActions: BlockedAction[] =
    selected === null
      ? [
          {
            name: 'ui_material_prep_judge',
            reason: '当前没有选中材料包：先让律师选一条，或问他指的是哪一个',
          },
        ]
      : []
  useUiPageState(
    PAGE_NAME,
    {
      page: PAGE_NAME,
      route: location.pathname + location.search,
      stage,
      selected,
      counts,
    },
    { blockedActions },
  )

  const refreshPacks = useCallback(
    () => queryClient.invalidateQueries({ queryKey: PACKS_KEY }),
    [queryClient],
  )

  // 执行器那边已经写完库了，这边只负责「让律师看见它真的变了」：重拉 + 一句 toast。
  useEffect(() => {
    const onStatusChanged = (event: Event): void => {
      const detail = (event as CustomEvent<PackStatusChangedDetail | undefined>).detail
      void refreshPacks()
      toast(detail ? `材料包 ${detail.packId} 已判为${PACK_JUDGE_LABEL[detail.status]}` : '材料包状态已更新')
    }
    window.addEventListener(PACK_STATUS_CHANGED_EVENT, onStatusChanged)
    return () => window.removeEventListener(PACK_STATUS_CHANGED_EVENT, onStatusChanged)
  }, [refreshPacks])

  const handlePending = useCallback(
    (request: UiActionRequest) => {
      // 队列键是 `spec.route`，同一页将来若有第二条动作，这里是唯一能发现「本页没实现它」
      // 的地方（静默 return 会让模型以为执行过了、页面却一动不动）
      if (request.action !== 'ui_material_prep_judge') {
        console.warn(`材料预处理页收到不属于自己的待执行动作 ${request.action}，已忽略`)
        return
      }
      void (async () => {
        const outcome = await judgeMaterialPack(request.args)
        if (!outcome.ok) {
          toast.error(outcome.message)
          return
        }
        // 这条路径上执行器没跑（是页面替它跑的），所以广播不会来：自己刷 + 自己说
        await refreshPacks()
        toast(outcome.detail ?? '材料包状态已更新')
      })()
    },
    [refreshPacks],
  )

  // 队列键必须与清单里这条动作的 `route` **逐字相同**，所以从 `@/app/paths` 取同一个值，
  // 不手写一遍字面量（门禁：`ui-tools/manifest-route.node.test.ts`）。
  // 拼错一个字母的表现是「AI 说判好了、页面一动不动」——整条链路上最难查的静默失效。
  useUiPendingAction(ROUTES.materialPrep, handlePending)
}
