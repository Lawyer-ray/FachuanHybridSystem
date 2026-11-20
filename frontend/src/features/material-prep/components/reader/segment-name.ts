/**
 * 左栏段名的「可截断头部 / 必须保留尾部」拆分。
 *
 * ## 为什么需要它
 *
 * 段名里真正区分两份材料的往往是**尾部**：「授权委托书某甲-P20.pdf」与
 * 「授权委托书某甲-P22.pdf」只有页号不同。而 CSS `truncate` 裁的正是尾部。
 *
 * 以前的做法是 `midEllipsis()` 先按字数把中间挖掉（保留首尾），再交给 CSS 截断。
 * 但它的字数上限（16）远大于左栏真正放得下的宽度（232px 栏里段名只剩四五个字），
 * 于是 CSS 又把尾巴连同省略号一起裁掉——中部省略等于从来没生效过。
 *
 * 现在改成结构性拆分的依据：**头部 flex-1 + truncate 吃剩余宽度，尾部 flex-none
 * 永远完整**。这样一来栏宽可拖、下载按钮收进浮层等宽度变化都不需要重算字数。
 */

/**
 * 尾部 = 扩展名（含紧邻的页号标记，如 `-P20.pdf` / `P3-9.md`）。
 * 拆完头部不足 6 个字符时不拆：整段本来就放得下，硬拆只会多一层 DOM。
 */
export function splitNameTail(name: string): { head: string; tail: string } {
  const m = name.match(/(?:[-_ ]?P\d+(?:[-–—]\d+)?)?\.[A-Za-z0-9]{1,6}$/)
  if (!m) return { head: name, tail: '' }
  const tail = m[0]
  if (name.length - tail.length < 6) return { head: name, tail: '' }
  return { head: name.slice(0, -tail.length), tail }
}
