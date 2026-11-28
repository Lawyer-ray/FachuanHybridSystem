/**
 * 一条引擎分歧里**一侧正文**的渲染：差异高亮 + 长文本折叠。
 *
 * 从 `EngineDisagreementsInline.tsx` 拆出的原因：那个文件管的是「分歧清单与裁决」
 * （按本段页范围过滤、勾选已核对、采用/修改/跳原页），而这里管的是**一段文字的
 * 呈现口径**——哪些片段算改了（`data-diff-changed`）、折叠时截到第几个字
 * （`data-expand-fulltext` 的字节口径）。两者改动理由不同：调折叠阈值或高亮样式
 * 不该在清单编排里找，加一条裁决动作也不该重算截断量。
 */

/** `VariantBody` 的入参：差异切段来自 `diffSegments`，`total` 是**全文**字数
 *  （折叠时仍要说清「还有多少没看到」，不能拿段数判断）。 */
export interface VariantBodyProps {
  parts: { text: string; changed: boolean }[]
  collapsed: boolean
  onToggle: () => void
  total: number
}

/**
 * 一行的正文渲染：差异高亮 + 长文本折叠。
 *
 * ## 为什么要折叠
 *
 * 全文平均 200–300 字，一页 6 条分歧全部展开会把下面的正文推到看不见。
 * 但**不能直接截断**（那就是原来的问题）：截断后律师判断不了哪侧对。
 * 所以默认折叠、一键展开，折叠时也给字数，让人知道还有多少没看到。
 */
export function VariantBody({ parts, collapsed, onToggle, total }: VariantBodyProps) {
  // 折叠时只渲染前 160 字：分段数取决于差异分布（全文一致时只有 1 段），
  // 不能拿段数判断「还有多少没看到」。
  const LIMIT = 160
  let acc = 0
  const shown: { text: string; changed: boolean }[] = []
  for (const seg of parts) {
    if (!collapsed) {
      shown.push(seg)
      continue
    }
    if (acc >= LIMIT) break
    const room = LIMIT - acc
    shown.push(seg.text.length <= room ? seg : { text: seg.text.slice(0, room), changed: seg.changed })
    acc += Math.min(seg.text.length, room)
  }
  const truncated = collapsed && total > LIMIT
  return (
    <>
      {shown.map((seg, si) =>
        seg.changed ? (
          <mark
            key={si}
            data-diff-changed
            className="rounded bg-amber-200/80 px-0.5 font-medium text-amber-950"
          >
            {seg.text}
          </mark>
        ) : (
          <span key={si}>{seg.text}</span>
        ),
      )}
      {collapsed && (
        <button
          type="button"
          onClick={onToggle}
          data-expand-fulltext
          className="ml-1 rounded bg-secondary px-1 text-[10px] text-secondary-foreground hover:bg-zinc-200"
        >
          {truncated ? `展开全文（${total} 字）` : '展开'}
        </button>
      )}
      {!collapsed && (
        <button
          type="button"
          onClick={onToggle}
          data-collapse-fulltext
          className="ml-1 rounded bg-secondary px-1 text-[10px] text-secondary-foreground hover:bg-zinc-200"
        >
          收起
        </button>
      )}
    </>
  )
}
