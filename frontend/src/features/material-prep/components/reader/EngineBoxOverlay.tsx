import type { EngineBlockRect, EngineName, EngineVariant, RectPrecision, RotDeg } from '../../types'
import { rectPrecisionOf } from '../../types'
import { engineShortLabel, rotateNormRect } from '../../draft'

/**
 * 双框对照的配色与画法（契约【视觉规则】的硬要求）。
 *
 * - 主引擎 MinerU = **实线** `#16a34a`（绿）
 * - 副引擎 VL = **虚线** `#f59e0b`（琥珀），`5 3` 划线样式
 * - 半透明填充 `fillOpacity 0.12`：两框大面积重叠时仍能两框的边都看见
 *   （不透明填充会把先画的那个完全盖住，正是要避免的情形）
 * - `approx`（整页近似框，坐标不可信）统一用更淡的描边：不给假精度
 */
const ENGINE_BOX_COLORS: Record<string, string> = {
  mineru: '#16a34a',
  paddleocr_vl: '#f59e0b',
  textin: '#6366f1',
}
const ENGINE_BOX_DEFAULT_COLOR = '#71717a'
/** 主引擎：实线。其余走虚线——契约只点名 MinerU 是主引擎 */
const PRIMARY_ENGINE: EngineName = 'mineru'
/** 虚线间隔（契约写死 5 3） */
const ENGINE_BOX_DASH = '5 3'
/** 描边宽度用 px 且不随 viewBox 缩放：页面图宽上千像素，按比例算会细成一条看不见的线 */
const ENGINE_BOX_STROKE = 2

const VIEWBOX = 1000

/** 一个引擎在某页上的框 + 该引擎这一处的文本（框旁标注要说清「这个框说的是什么」） */
export interface EngineBoxGroup {
  variant: EngineVariant
  blocks: EngineBlockRect[]
}

/**
 * 双引擎对照框（SVG 覆盖层，与页图同尺寸、绝对定位铺满）。
 *
 * ## 坐标口径
 *
 * 复用既有约定：`rect` 是**相对页面图像**归一化的 0-1（`PositionedBlock.rect` 同口径，
 * 见外层 `boxRef` 容器的注释）。这里把 0-1 乘上 viewBox 边长再交给 SVG，
 * 而不是另建一套像素换算——页卡宽度随缩放/列数变化，用 px 画会在每次缩放后失准。
 * `preserveAspectRatio="none"` 让 viewBox 直接拉满容器，于是 `x*100%` 与 `x*VIEWBOX`
 * 是同一个点，两套口径不会漂移。
 *
 * ## 为什么叠在一个 `<svg>` 里而不是每框一个 div
 *
 * 两框大面积重叠时，两个独立绝对定位元素的填充会互相遮挡，谁在后谁看得见。
 * 统一用 `fillOpacity: 0.12` 的半透明填充 + 描边，重叠处颜色自然叠深，
 * 而两条边都完整可见——这正是「两框重叠时都可见」的实现方式。
 *
 * ## 退化情形
 *
 * 某引擎这一页一个框都没给（后端没传 block bbox / 该引擎降级失败）时，它那一组
 * 渲染不出任何 rect，页面上只有另一个引擎的框。这是刻意的：**不伪造一个假框去凑
 * 成一对**，缺坐标就如实缺着——假框会让律师对着一个不存在的差异下结论。
 * 坐标不可信（`approx`）的框描边更淡并在小字前加「≈」：宁可看着不确定，也不给假精度。
 */
export function EngineBoxOverlay({
  groups,
  rotation = 0,
}: {
  groups: EngineBoxGroup[]
  /** 页旋转角度：页转了框必须跟着转，否则框会指到隔壁（比没有框更糟） */
  rotation?: RotDeg
}) {
  // 一条分歧通常只对应一个块，所以按整组判断「本引擎坐标是否可信」。
  // 一组里混着精确框与近似框时，只要有一个精确框就按精确处理（有精确信息就别放弃它）。
  const entries = groups.map((g) => {
    const color = ENGINE_BOX_COLORS[g.variant.engine] ?? ENGINE_BOX_DEFAULT_COLOR
    const dashed = g.variant.engine !== PRIMARY_ENGINE
    // 坐标可信度按「最差的那个块」算：一组里只要有一个块是推算的，
    // 这组框就不能对外声称精确（混合时若按最好算，会给出假精度）。
    const precisions = g.blocks.map((b) => (b as { precision?: RectPrecision }).precision ?? rectPrecisionOf(b))
    const approx = precisions.some((p) => p !== 'exact')
    const veryApprox = precisions.length > 0 && precisions.every((p) => p === 'page')
    return { group: g, color, dashed, approx, veryApprox }
  })

  return (
    <div className="pointer-events-none absolute inset-0">
      <svg
        data-engine-box-overlay
        className="absolute inset-0 h-full w-full"
        viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
        preserveAspectRatio="none"
        aria-hidden
      >
        {entries.flatMap(({ group, color, dashed, approx, veryApprox }) =>
          group.blocks.map((b, i) => {
            // 引擎给的是**未旋转**页面的坐标；页面转了就把 rect 一起转过去
            const rect = rotateNormRect(b.rect, rotation)
            // 三档透明度：精确 1.0 / 推算 0.55 / 整页近似 0.28
            const stroke = !approx ? 1 : veryApprox ? 0.28 : 0.55
            return (
              <g key={`${group.variant.engine}:${i}`} data-engine-box={group.variant.engine}>
                <rect
                  x={rect.x * VIEWBOX}
                  y={rect.y * VIEWBOX}
                  width={rect.w * VIEWBOX}
                  height={rect.h * VIEWBOX}
                  fill={color}
                  fillOpacity={0.12}
                  stroke={color}
                  strokeOpacity={stroke}
                  strokeWidth={ENGINE_BOX_STROKE}
                  strokeDasharray={dashed ? ENGINE_BOX_DASH : undefined}
                  rx={2}
                />
                {/* 框旁标注：引擎短名 + 这个框对应的文本，律师一眼对上「哪个框是哪个引擎的哪个字」 */}
                <text
                  x={rect.x * VIEWBOX}
                  y={rect.y * VIEWBOX - 3}
                  fill={color}
                  fillOpacity={approx ? 0.7 : 1}
                  stroke="white"
                  strokeWidth={2.5}
                  paintOrder="stroke"
                  fontSize={11}
                >
                  {labelOf(group.variant.engine, b.text, approx)}
                </text>
              </g>
            )
          }),
        )}
      </svg>
    </div>
  )
}

/** 框旁小字：`MinerU 张三丰`；文本过长截断，`approx` 补一个「≈」表示坐标不可信 */
function labelOf(engine: EngineName, text: string, approx: boolean): string {
  const body = text.trim().slice(0, 18)
  const name = engineShortLabel(engine)
  return `${approx ? '≈' : ''}${name}${body ? ` ${body}` : ''}`
}
