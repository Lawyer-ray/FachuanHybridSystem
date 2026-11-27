import { useQuery } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'

import { getContract } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { ProjectEditForm } from './ProjectEditForm'

/**
 * 项目编辑页（`/projects/:id/edit`）。
 *
 * 只用合同本身：详情页那套 `useDealDetail` 会顺带拉律师、案件、逐案提醒（编辑页
 * 一个都用不上），这里直接读 `workbenchKeys.contract(id)` —— 与详情页同一个缓存键，
 * 所以「详情 → 编辑 → 返回」全程不会出现空白重取。
 *
 * 数据到手后交给 `ProjectEditForm`（用 `key` 收口初值：仓库惯例，见 RenamePackDialog
 * ——用 effect 回填会先闪一帧空表单）。
 */
export function ProjectEditPage() {
  const { id } = useParams<{ id: string }>()
  const contractId = Number(id)
  // Number('12abc') 给 NaN、Number('') 给 0：非正整数一律当非法 id，别静默打开别的项目
  const valid = Number.isInteger(contractId) && contractId > 0

  const q = useQuery({
    queryKey: workbenchKeys.contract(contractId),
    queryFn: () => getContract(contractId),
    enabled: valid,
  })

  if (!valid) return <Navigate to="/projects" replace />
  if (q.isPending) return <LoadingBlock text="正在加载项目…" className="py-[90px]" />
  if (q.error || !q.data) {
    return (
      <div className="mx-auto max-w-[720px] px-6 py-10">
        <ErrorBlock
          error={q.error ?? '项目不存在'}
          onRetry={() => void q.refetch()}
          retryText="重试"
          className="text-sm"
        />
      </div>
    )
  }

  return <ProjectEditForm key={q.data.id} contract={q.data} />
}
