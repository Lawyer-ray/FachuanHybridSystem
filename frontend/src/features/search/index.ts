/**
 * 全局检索 feature 的对外出口。
 * 其它层（app / shared 组件）只应从这里引，不穿透内部目录。
 */

export { GlobalSearch } from './components/GlobalSearch'
export type { CategoryKey, Hit } from './types'
