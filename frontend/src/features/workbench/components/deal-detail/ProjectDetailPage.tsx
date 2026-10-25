import { useParams } from 'react-router'

import { useDealDetailPage } from './use-deal-detail-page'
import { DealDetailPage } from './DealDetailPage'
import { NonLitDetailPage } from './NonLitDetailPage'

/**
 * 项目详情的唯一入口：一条 URL（`/projects/:id`），按 `deal.lit` 分流。
 *
 * **为什么不拆成两条路由**：`nonlit` 是 non-litigation 的缩写，属实现分类而不是
 * 用户概念。旧实现把非诉挂在 `/projects/:id/nonlit`，还在 `DealDetailPage` 里
 * 偷偷把直达 `/projects/:id` 的非诉委托重定向过去——用户看到 URL 自己变了，
 * 却不知道为什么。现在两条路径都不再暴露分类词，刷新/分享/收藏都稳定。
 *
 * **分流依据**：`lit` 由合同 `case_type`（civil/criminal/advisor…）派生，与左栏
 * 内容严格对应。有法院程序 → 左栏案件程序链；无 → 左栏合同文件夹。
 *
 * 这里复用 `useDealDetailPage` 而不是让两个子页各自取一遍数据：分流发生在
 * 「已经知道 lit」之后，重复请求会白跑一次详情接口。
 */
export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { deal } = useDealDetailPage(id)

  // loading / error / 无效 id 由子页自己渲染（各自的骨架与错误态已就位），
  // 这里只做「知道 lit 之后选哪一页」。未知时按非诉渲染：未加载完成不闪案件链。
  if (deal?.lit) return <DealDetailPage />
  return <NonLitDetailPage />
}
