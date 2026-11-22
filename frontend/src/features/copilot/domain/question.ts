/**
 * 结构化问答（`question_request`）的纯领域逻辑：归一化、草稿变换、答案批次。
 *
 * 为什么单独一个模块：后端把 `questions` 声明成自由形状（`Array<Record<string,
 * unknown>>`，见 sse_types.py），模型给什么形状都可能——字符串数组、缺 id、
 * options 写成字符串。归一化只认**已知字段**、绝不猜结构，坏项丢弃而不是抛错：
 * 一条坏题不该让整轮对话卡住（提问本身无副作用）。
 *
 * 与审批的区别（后端 question.py 的设计前提）：审批是闸门（超时=拒绝），
 * 提问是求助（超时=模型按假设继续）。所以这里没有 fail-closed，只有
 * 「答了 / 跳过 / 已继续仍可补答」三种状态。
 *
 * 全部为纯函数（无 React、无 IO），vitest 直接覆盖。
 */

/** 选项：label 是答案回传的唯一键（后端按 label 对齐，没有 option id） */
export interface QuestionOption {
  label: string
  description: string
}

/** 归一化后的一道题（字段与 backend/apps/agent/services/question.py 的产出一一对齐） */
export interface QuestionItem {
  /** 答案按 id 回填，不按下标——避免「答的是第 2 题被当成第 1 题」 */
  id: string
  question: string
  /** 补充上下文（后端叫 context，法律场景常放条款原文） */
  context: string
  options: QuestionOption[]
  /** 允许自由文本作答（缺省 true，与后端同口径） */
  allowFreeform: boolean
  /** 允许多选（缺省 false） */
  allowMultiple: boolean
  /** 允许附加备注（缺省 false） */
  allowComment: boolean
}

/** 单题草稿（UI 状态，不是契约） */
export interface QuestionDraft {
  /** 已选选项 label（顺序 = 点击顺序） */
  selections: string[]
  /** 自由文本答案 */
  text: string
  /** 备注（allowComment 时才有输入框） */
  comment: string
}

/** 回传给后端的单题答案（字段名对齐 QuestionAnswerItem：selections/text/comment） */
export interface QuestionAnswerItem {
  id: string
  selections: string[]
  text: string
  comment: string
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function bool(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

/** options 宽容解析：字符串数组、对象数组、`{text}`/`{value}` 都收；空 label 丢弃 */
function normalizeOptions(raw: unknown): QuestionOption[] {
  if (!Array.isArray(raw)) return []
  const out: QuestionOption[] = []
  for (const opt of raw) {
    if (typeof opt === 'string') {
      const label = opt.trim()
      if (label) out.push({ label, description: '' })
      continue
    }
    if (!opt || typeof opt !== 'object') continue
    const rec = opt as Record<string, unknown>
    const label = str(rec.label ?? rec.text ?? rec.value).trim()
    if (!label) continue
    out.push({ label, description: str(rec.description).trim() })
  }
  return out
}

/**
 * 归一化模型提交的题面。**只认已知字段**：未知字段直接丢弃，
 * 缺 `question` 文本的题整条丢弃（没有题面就没有可答的东西）。
 *
 * `raw` 为 `undefined`/非数组时返回 `[]`，调用方据此决定是否渲染卡片。
 */
export function normalizeQuestions(raw: unknown): QuestionItem[] {
  if (!Array.isArray(raw)) return []
  const out: QuestionItem[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const rec = item as Record<string, unknown>
    const text = str(rec.question).trim()
    if (!text) continue
    out.push({
      // id 缺失时按序补位（后端一定会给，这里只做兜底，保证 key 稳定）
      id: str(rec.id).trim() || `q${out.length + 1}`,
      question: text,
      context: str(rec.context).trim(),
      options: normalizeOptions(rec.options),
      allowFreeform: bool(rec.allow_freeform, true),
      allowMultiple: bool(rec.allow_multiple, false),
      allowComment: bool(rec.allow_comment, false),
    })
  }
  return out
}

/** 空草稿 */
export function emptyDraft(): QuestionDraft {
  return { selections: [], text: '', comment: '' }
}

/**
 * 勾选/取消一个选项。
 *
 * 三条规则来自真实交互（多选题与自由文本共存）：
 * - 多选：切换该项，其余保留；
 * - 单选：替换为该项，并**清空自由文本**——单选语义下两者不能同时成立，
 *   留着文本会让用户以为「两个都算答了」；
 * - 再点已选项：取消（单选即清空，多选即移除）。
 */
export function toggleSelection(
  question: QuestionItem,
  draft: QuestionDraft,
  label: string,
): QuestionDraft {
  const has = draft.selections.includes(label)
  if (question.allowMultiple) {
    return {
      ...draft,
      selections: has ? draft.selections.filter((l) => l !== label) : [...draft.selections, label],
    }
  }
  return has ? { ...draft, selections: [] } : { ...draft, selections: [label], text: '' }
}

/**
 * 写入自由文本。
 *
 * 单选下输入文本会把已选选项**清空**（与 DSH 的答案编码一致：单选时
 * `selections` 与 `text` 互斥）；多选下两者共存——用户可能既要勾「需要
 * 补条款」又要写清楚补什么。
 */
export function setFreeform(
  question: QuestionItem,
  draft: QuestionDraft,
  text: string,
): QuestionDraft {
  if (question.allowMultiple) return { ...draft, text }
  return { ...draft, text, selections: text.trim() ? [] : draft.selections }
}

/** 这题算不算「已作答」（跳过是显式动作，不是未答） */
export function isAnswered(draft: QuestionDraft | undefined): boolean {
  if (!draft) return false
  return draft.selections.length > 0 || draft.text.trim().length > 0
}

/**
 * 组装回传体：**只带已作答的题**，未答的不出现在 `answers` 里
 * （后端会把缺项标成 `unanswered`，模型据此知道自己没得到答案）。
 */
export function buildAnswerBatch(
  questions: readonly QuestionItem[],
  drafts: Record<string, QuestionDraft>,
): QuestionAnswerItem[] {
  const out: QuestionAnswerItem[] = []
  for (const q of questions) {
    const draft = drafts[q.id]
    if (!isAnswered(draft)) continue
    out.push({
      id: q.id,
      selections: [...draft!.selections],
      text: q.allowFreeform ? draft!.text.trim() : '',
      comment: q.allowComment ? draft!.comment.trim() : '',
    })
  }
  return out
}

/** 倒计时文案（秒 → 「m:ss」；已到点返回空串，由 UI 换成「已继续」文案） */
export function formatCountdown(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds))
  if (safe <= 0) return ''
  const m = Math.floor(safe / 60)
  const s = safe % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
