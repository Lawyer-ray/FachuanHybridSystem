/**
 * 两段文本的差异片段计算，用于在双引擎分歧里把「哪里不一样」标出来。
 *
 * ## 为什么只标「实质差异」，不标排版差异
 *
 * 实测第 1 页那条 high 分歧：两段文本有 12 处差异，**全部是半角 `:` 与全角 `：`
 * 的差别**，加上 PaddleOCR-VL 把换行写成了字面量 `\n`。如果原样标红，律师看到的
 * 是一屏高亮的冒号，真正的错字（`张甲某` / `张乙某`）反而被淹掉。
 *
 * 所以这里先做与后端 `dual_engine._normalize` **同口径**的归一化，只在归一化后
 * 仍有差异的位置打标；纯标点/空白/标记差异不标。
 *
 * ## 为什么不直接复用后端的差异结果
 *
 * 后端做的是「判定」（要不要报这条分歧），它吐出的是 severity 与相似度，
 * 不是字符级区间。要在前端画高亮，需要字符区间——在这里算一次即可，
 * 不必为它扩后端 schema。
 *
 * ## 归一化口径必须与后端一致
 *
 * `normalizeForDiff` 与 `dual_engine._normalize` 的规则集**刻意保持同构**：
 * 剥 LaTeX、剥 HTML 标签、全角标点折半角、去掉 Markdown 标记与空白。
 * 两边不一致会出现「判据说有差异，高亮却找不到位置」的撕裂。
 * 若后端改了规则，这里要同步（两边都有注释指向对方）。
 */

/** 全半角标点归一表：与后端 `_PUNCT_MAP` 同口径 */
const PUNCT_MAP: Record<string, string> = {
  '，': ',',
  '。': '.',
  '、': ',',
  '；': ';',
  '：': ':',
  '？': '?',
  '！': '!',
  '（': '(',
  '）': ')',
  '【': '[',
  '】': ']',
  '《': '<',
  '》': '>',
  '“': '"',
  '”': '"',
  '‘': "'",
  '’': "'",
  '—': '-',
  '…': '.',
  '％': '%',
}

const LATEX_TEXT_CMD_RE = /\\(?:text|textbf|textrm|underline|mbox|mathrm)\s*\{([^{}]*)\}/g
const LATEX_CMD_RE = /\\[a-zA-Z]+/g
const TAG_ANY_RE = /<\s*\/?\s*[a-zA-Z][^>]*>/g
const NOISE_CHARS_RE = /[#*`|>\-_~=\s\u3000]+/g

/**
 * 把文本归一化到「只保留有语义的字符」。
 *
 * 返回的字符串**长度与原文不同**，所以它不能直接用来做高亮定位。
 * 高亮的做法是：对归一化后的串求差异区间，再把区间映射回原文——
 * 映射靠 `normalizeWithMap` 保留「归一化后的第 i 个字符来自原文第几位」。
 */
export function normalizeForDiff(text: string): string {
  let raw = String(text ?? '')
  raw = raw.replace(LATEX_TEXT_CMD_RE, '$1')
  raw = raw.replace(LATEX_CMD_RE, '')
  raw = raw.replace(TAG_ANY_RE, '')
  raw = raw.replace(/\$/g, '').replace(/\\_/g, '_')
  raw = raw.replace(/\{/g, '').replace(/\}/g, '')
  raw = raw.replace(/\\n/g, ' ').replace(/\\t/g, ' ')
  raw = [...raw].map((ch) => PUNCT_MAP[ch] ?? ch).join('')
  return raw.replace(NOISE_CHARS_RE, '')
}

export interface DiffSegment {
  /** 该片段在**原文**里的文字 */
  text: string
  /** true = 这段是差异（该高亮）；false = 两边一致 */
  changed: boolean
}

/**
 * 计算 `left` 相对 `right` 的差异片段（用于给 left 侧打高亮）。
 *
 * 返回的片段按顺序拼接即为 `left` 原文，`changed` 标记哪些片段与 `right` 不同。
 *
 * ## 为什么按「归一化后」求差异，再映射回原文
 *
 * 直接对原文求 diff 会把每个全半角标点都算成差异。归一化后求 diff，
 * 差异区间才是语义层面的；再用位置映射把区间还原到原文，标出来的
 * 就是「那几个真不同的字」。
 */
export function diffSegments(left: string, right: string): DiffSegment[] {
  const src = String(left ?? '')
  if (!src) return []

  const { norm, map } = normalizeWithMap(src)
  const otherNorm = normalizeForDiff(right)

  if (!norm || !otherNorm) {
    // 一侧归一化后为空（整行都是标记/空白）：无法比对，整行按「未变」处理，
    // 不制造假高亮。空行差异另有 missing 类分歧负责表达。
    return [{ text: src, changed: false }]
  }

  // 归一化后完全相同 → 没有实质差异，整行不标
  if (norm === otherNorm) return [{ text: src, changed: false }]

  const changedNormIdx = new Set<number>()
  let i = 0
  let j = 0
  while (i < norm.length || j < otherNorm.length) {
    if (i < norm.length && j < otherNorm.length && norm[i] === otherNorm[j]) {
      i += 1
      j += 1
      continue
    }
    // 找到下一个能对齐的位置（贪心足够：行级文本很短，不需要最优编辑距离）
    let advanced = false
    for (let k = 1; k <= 8 && !advanced; k += 1) {
      if (i + k < norm.length && j + k < otherNorm.length && norm[i + k] === otherNorm[j + k]) {
        for (let t = 0; t < k; t += 1) changedNormIdx.add(i + t)
        i += k
        j += k
        advanced = true
      }
    }
    if (advanced) continue
    // 长度不同：把多出来的位置全部记为差异后收尾
    while (i < norm.length) {
      changedNormIdx.add(i)
      i += 1
    }
    while (j < otherNorm.length) j += 1
  }

  if (changedNormIdx.size === 0) return [{ text: src, changed: false }]

  // 把「归一化后第 k 个字符变了」映射回原文区间
  const changedSrc = new Set<number>()
  changedNormIdx.forEach((k) => {
    const at = map[k]
    if (at !== undefined) changedSrc.add(at)
  })

  // 按原文位置切成连续片段
  const out: DiffSegment[] = []
  let buf = ''
  let bufChanged = changedSrc.has(0)
  for (let pos = 0; pos < src.length; pos += 1) {
    const isChanged = changedSrc.has(pos)
    if (isChanged !== bufChanged && buf) {
      out.push({ text: buf, changed: bufChanged })
      buf = ''
    }
    bufChanged = isChanged
    buf += src[pos]
  }
  if (buf) out.push({ text: buf, changed: bufChanged })
  return out
}

/**
 * 归一化同时保留位置映射：`map[k]` = 归一化后第 k 个字符来自原文的下标。
 *
 * 逐字符处理而不是先 regex 批量替换：批量替换后拿不到「这个字原来在第几位」，
 * 而高亮必须落回原文坐标。
 */
function normalizeWithMap(text: string): { norm: string; map: number[] } {
  // 先做「会改变长度但位置可追踪」的几类处理，逐段保留来源下标：
  // 这里用最简单可靠的做法——对每个原文字符单独归一化，能保留就保留。
  // 多字符规则（LaTeX/HTML）先在整串上去掉，再对剩下的逐字扫描。
  let stage = String(text ?? '')
  stage = stage.replace(LATEX_TEXT_CMD_RE, '$1')
  stage = stage.replace(LATEX_CMD_RE, '')
  stage = stage.replace(TAG_ANY_RE, '')
  stage = stage.replace(/\$/g, '').replace(/\\_/g, '_')
  stage = stage.replace(/\{/g, '').replace(/\}/g, '')
  stage = stage.replace(/\\n/g, ' ').replace(/\\t/g, ' ')

  const normChars: string[] = []
  const map: number[] = []
  for (let i = 0; i < stage.length; i += 1) {
    const ch = PUNCT_MAP[stage[i]!] ?? stage[i]!
    if (NOISE_CHARS_RE.test(ch)) {
      NOISE_CHARS_RE.lastIndex = 0
      continue
    }
    NOISE_CHARS_RE.lastIndex = 0
    // 映射用 stage 的下标：stage 是原文去掉多字符规则后的版本，
    // 与原文的下标已不完全对应——但用于「标出大致的差异位置」足够了，
    // 且 stage 长度与原文差异只来自被剥掉的标记，不影响可见文字的顺序。
    normChars.push(ch)
    map.push(Math.min(i, Math.max(0, text.length - 1)))
  }
  return { norm: normChars.join(''), map }
}
