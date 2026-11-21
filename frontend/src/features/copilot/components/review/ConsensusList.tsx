/**
 * 共识 / 分歧：这几份答案里谁和谁是同一个立场（双向蕴含成团）。
 *
 * ## 三态不许折叠
 *
 * - `clustersError` 非空 = **没跑成团**（判等超时/超份/异常）：只显示「未成团：<原因>」。
 *   绝不能显示成「三份全异」——「判等失败」与「三份真的不一样」对律师是两条完全
 *   不同的信息，后者会让人以为分歧已经查清；
 * - `clusters` 为空且无错误 = 没跑成团（旧数据/单栏）：整块不渲染，不臆造结论；
 * - 有簇 = 照后端顺序显示每一簇的成员（多于一栏 = 共识，单栏 = 单独立场）。
 *
 * ## tie 时不加任何高亮
 *
 * `tie === true` 表示没有可判定的代表（全异或最大簇并列）。后端保证此时所有簇
 * `tie=true`、`representative_id=""`，`toClusterViews` 也已把 `emphasized` 全部置
 * false、代表清空——本组件只认 `emphasized` 这一位，**不**自己找「最大簇」或
 * 「第一条」来突出（那正是 tie 语义要禁止的事）。
 */

import { agentLabel } from '../../domain'
import type { ClusterView } from '../../domain/fusion'

export function ConsensusList({ clusters, clustersError }: { clusters: ClusterView[]; clustersError: string }) {
  if (clustersError) {
    return (
      <div className="mt-2" data-testid="review-clusters">
        <div className="text-[11px] font-medium text-muted-foreground">共识 / 分歧</div>
        {/* 失败只是一个原因，不是一种「三份全异」的结论 */}
        <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-500" data-testid="clusters-error">
          未成团：{clustersError}
        </p>
      </div>
    )
  }
  // 没跑成团（旧数据/单栏）：不显示空区块，更不显示任何「立场」结论
  if (clusters.length === 0) return null

  const tied = clusters.some((cluster) => cluster.tie)
  return (
    <div className="mt-2" data-testid="review-clusters">
      <div className="text-[11px] font-medium text-muted-foreground">共识 / 分歧（同一立场的栏归为一簇）</div>
      <ul className="mt-1 space-y-1">
        {clusters.map((cluster, index) => {
          const members = cluster.memberIds.map(agentLabel).join('、')
          const shared = cluster.memberIds.length > 1
          return (
            <li
              key={index}
              data-testid={`cluster-${index}`}
              data-emphasized={cluster.emphasized ? 'true' : undefined}
              className={`rounded-[6px] border px-1.5 py-1 ${
                cluster.emphasized ? 'border-foreground/30 bg-background/60' : 'border-border bg-background/30'
              }`}
            >
              <div className="flex flex-wrap items-baseline gap-x-1.5">
                <span className="text-[11px]">
                  {shared ? '共识' : '单独立场'}：{members}
                </span>
                {/* 代表只在「多栏共识且可判定」时出现：单栏的代表就是它自己，说了也是噪声；
                    tie 时 representativeId 已被清空 */}
                {shared && cluster.emphasized && cluster.representativeId && (
                  <span className="text-[10px] text-muted-foreground">代表 {agentLabel(cluster.representativeId)}</span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {tied && (
        <p className="mt-1 text-[11px] text-muted-foreground" data-testid="clusters-tie">
          没有可判定的代表（各簇并列，未做推荐）
        </p>
      )}
    </div>
  )
}
