/** 收件箱 feature 出口（跨域只允许从这里取） */
export { InboxPage } from './components/InboxPage'
export { INBOX_LIST_KEY, listInbox, getInboxMessage, setReadState, convertToPack } from './api'
export { INBOX_SOURCE_TABS, SOURCE_LABEL } from './constants'
export { groupByTime, countUnread, filterRows } from './domain'
export type { InboxRow, InboxDetail, InboxAttachment, InboxSourceFilter } from './types'
export { packIdOf, canConvert, isPackSource } from './types'
