/**
 * 首页 · 今日工作台的后端对接出口。
 *
 * 全部路径已按 frontend/CLAUDE.md「对接后端接口纪律」核对过后端 OpenAPI
 * （http://127.0.0.1:8002/api/v1/openapi.json）与真实返回：
 *   - 日历视图        = GET  /reminders/calendar     （合并/统计都在后端算好）
 *   - 快速记一笔解析 = POST /reminders/parse       （仅能识别"绝对日期"文本）
 *   - 新建安排       = POST /reminders/create
 *   - 待处理流入     = GET  /inbox/messages        （收件箱，按收到时间倒序）
 *   - 收法院短信     = POST /automation/court-sms
 *   - 要素式转换     = POST /doc-convert/convert   （multipart：file + mbid）
 *     模板列表       = GET  /doc-convert/mbid-list
 *   - DOC 转 DOCX   = POST /doc-converter/jobs     （multipart：files[]）
 *   - 文档解析      = POST /document-parsing/parse  （multipart：file + 表单字段）
 *     查任务        = GET  /document-parsing/task/{task_id}
 *
 * 按资源拆为 reminders / inbox / tools / document-parsing 四个子模块，本文件只做
 * barrel re-export，消费方继续 `from '../api'` / `from '../../api'` 不变。
 */

export { remindersApi, fetchCalendarMonth, setRemindersCompleted, calendarKeys, REMINDER_TYPES_KEY, searchTargetOptions, listReminderTypes, parseReminder, createReminder } from './reminders'
export type { CalendarEvent, CalendarStats, CalendarMonth, TargetType, TargetOption, ReminderTypeOption, ParsedReminder, CreateReminderIn } from './reminders'

export { inboxApi, listInbox, formatRelative } from './inbox'
export type { InboxMessageOut } from './inbox'

export { automationApi, docConvertApi, docConverterApi } from './tools'
export { submitCourtSms, listConvertTemplates, convertDocument, createConverterJob, getConverterJob, converterDownloadUrl, DOC_CONVERT_TIMEOUT_MS, CONVERT_TEMPLATES_KEY } from './tools'
export { HOME_INBOX_KEY } from './inbox'
export type { ConvertTemplateGroup, ConvertResult, ConverterJob } from './tools'

export {
  getCourtSmsDetail,
  assignCourtSmsCase,
  retryCourtSms,
  deleteCourtSms,
  courtSmsDocDownloadUrl,
  courtSmsDownloadAllUrl,
  copyCourtSmsDocsToClipboard,
  searchCasesForAssign,
} from './court-sms'
export type { CourtSmsDetail, CaseSearchItem } from './court-sms'
export { withAuthToken, triggerDownload } from './download'

export {
  documentParsingApi,
  parseDocument,
  getParseTaskTask,
  PARSE_BACKENDS,
  DOC_PARSE_TIMEOUT_MS,
  DOC_PARSE_POLL_MS,
  DOC_PARSE_MAX_POLLS,
} from './document-parsing'
export type { ParseBackend, ParseDocumentIn, ParseSubmit, ParseTaskStatus, ParseOutcome } from './document-parsing'
