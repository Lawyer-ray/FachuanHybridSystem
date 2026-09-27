/**
 * 社交登录的展示格式化。
 *
 * 后端下发的 `display_name` 可能是中文（飞书 / 微信）也可能是拉丁（Google），
 * 与中文模板拼接时的留白规则不同。这类规则集中在这里，便于单测覆盖，
 * 组件只负责调用。
 */

/**
 * 中文模板与品牌名拼接，按品牌名语种决定是否补空格。
 *
 * - 中文品牌紧贴才自然：「使用飞书登录」
 * - 拉丁品牌必须留白：「使用 Google 登录」
 *
 * 判据取品牌名首字符是否为 ASCII 字母数字——后端 `display_name` 由我们自己在
 * `PROVIDER_SPECS` 里配置，不存在「中文名首字符是英文」的情况。
 */
export function spacedBrand(prefix: string, brand: string, suffix: string): string {
  return /^[A-Za-z0-9]/.test(brand) ? `${prefix} ${brand} ${suffix}` : `${prefix}${brand}${suffix}`
}
