/**
 * 品牌标注册表。
 *
 * 有标的 Provider 走浅底样式：彩色 logo 落在登录页的黄铜底上不可辨（Google 黄
 * 对比度仅约 1.3:1），只能配白底——这也正是 Google 品牌规范要求的用法。
 * 没有标的（飞书）沿用黄铜主按钮。新增平台加一行即可。
 */
import type { ComponentType } from 'react'
import { GitHubIcon } from './GitHubIcon'
import { GoogleIcon } from './GoogleIcon'
import { MicrosoftIcon } from './MicrosoftIcon'

export const BRAND_MARKS: Record<string, ComponentType<{ size?: number }>> = {
  google: GoogleIcon,
  github: GitHubIcon,
  microsoft: MicrosoftIcon,
}
