/**
 * 收件箱子域出口。
 *
 * 收件箱是 material-prep 域内部的**一个视图**（流水线第一段），不再是独立
 * feature：它与材料包共享预处理的页面外壳、上传动作与拖放层。跨 feature 只应
 * 从 `@/features/material-prep` 取需要的东西，不穿透到本目录。
 */
export { InboxView } from './components/InboxView'
export { INBOX_LIST_KEY, listInbox, getInboxMessage, setReadState, convertToPack } from './api'
export { INBOX_SOURCE_TABS, SOURCE_LABEL } from './constants'
export { groupByTime, countUnread, filterRows } from './domain'
export type { InboxRow, InboxDetail, InboxAttachment, InboxSourceFilter } from './types'
export { packIdOf, canConvert, isPackSource } from './types'
