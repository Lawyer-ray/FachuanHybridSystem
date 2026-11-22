import type { Inconsistency, Segment } from '../../types'
import { EngineDisagreementsInline } from './EngineDisagreementsInline'
import { SegmentPageHint, type DocHintPage } from './SegmentQualityHint'
import type { DisagreementBucket } from './segment-markdown-page-groups'

/**
 * 挂在正文某一页第一行之前的提示：该页的引擎分歧 + 证件页/图纸页提示。
 *
 * 两件事落点相同（「读到这一页就先知道这一页有什么问题」），所以合成一个组件，
 * 渲染顺序固定为「页提示 → 分歧」——一个负责「这页看不清」，一个负责「这页两个
 * 引擎读得不一样」，先讲缺内容再讲有争议。
 *
 * 分组本身是纯函数（`segment-markdown-page-groups.ts`），本文件只负责渲染，
 * 不重新计算任何页归属。
 */
export function PageAnchoredHints({
  page,
  bucket,
  docByPage,
  graphicPages,
  onGotoPage,
  seg,
  engineChecked,
  onJumpEngine,
  onToggleEngineChecked,
  onAdoptEngine,
  onEditEngine,
  inconsistencies,
}: {
  page: number
  /** 该页的分歧（没有就是 undefined：单画页提示） */
  bucket?: DisagreementBucket
  docByPage: Map<number, DocHintPage>
  graphicPages: Set<number>
  onGotoPage?: (page: number) => void
  seg: Segment
  engineChecked: string[]
  onJumpEngine?: (pageNo: number, key: string) => void
  onToggleEngineChecked?: (key: string, checked: boolean) => void
  onAdoptEngine?: (pageNo: number, text: string, disagreeKey?: string) => void
  onEditEngine?: (pageNo: number, text: string, disagreeKey?: string) => void
  inconsistencies?: Inconsistency[]
}) {
  const doc = docByPage.get(page)
  const graphic = graphicPages.has(page)
  return (
    <>
      {(doc || graphic) && (
        <SegmentPageHint page={page} doc={doc} graphic={graphic} onGotoPage={onGotoPage} />
      )}
      {bucket && (
        <EngineDisagreementsInline
          seg={seg}
          items={bucket.items}
          keys={bucket.keys}
          checked={engineChecked}
          onJump={onJumpEngine}
          onToggleChecked={onToggleEngineChecked}
          onAdopt={onAdoptEngine}
          onEdit={onEditEngine}
          inconsistencies={inconsistencies}
          heading={`P${page} 分歧`}
        />
      )}
    </>
  )
}
