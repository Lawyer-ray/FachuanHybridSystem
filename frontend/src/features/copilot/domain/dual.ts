/**
 * 多答（multi-agent answers）的分流与展示口径。
 *
 * 「双答」是本功能最早的名字（一轮里 pi + dsh 并排），现在扩到最多
 * {@link MAX_ANSWERS} 栏。后端把各 agent 的事件**按到达顺序交错**推给前端，每个
 * 事件带 `agent`（谁产的）与 `run_id`（哪一轮的哪一栏）。本模块只做纯变换：
 *
 * 1. **分流键归一**：事件 → 该追加到哪条 assistant 消息（见 {@link agentOf}）；
 * 2. **展示标签**：kind → 中文名（见 {@link agentLabel}）；
 * 3. **转录分组**：相邻的若干条 assistant 合成一轮多答（见 {@link groupAnswerRuns}）。
 *
 * 为什么放在 domain 而不是组件里：分流的正确性（同一轮各栏各归各家）必须能在
 * node 环境直接单测，不能只靠渲染 DOM 去间接验——DOM 断言失败时看不清是
 * 「分错了栏」还是「样式没出来」。
 */

import type { ChatMessage } from '../types'
import { mergeCitations } from './knowledge'

/** 一轮里最多几栏。必须与后端 `services/chat/multi.MAX_ANSWERS` 同值（规格 2.3：超过直接 400）。
 *
 * 这个值不是技术上限：成本随栏数线性涨，栏数再多，侧边栏面板里每栏的宽度就不够读了；
 * 当前取值对应已注册的 agent 运行时个数。 */
export const MAX_ANSWERS = 5

/** 转录项：一条消息，或一轮里连续的若干条 assistant（多答时 2~{@link MAX_ANSWERS} 条） */
export interface AnswerGroup {
  answers: ChatMessage[]
}

/** 空串 / 未标注一律当 pi：引入多答之前本系统只有 pi 在跑（见后端字段注释） */
export const DEFAULT_AGENT_KIND = 'pi'

/**
 * 综合结论在会话转录里的 `agent_kind`。
 *
 * **必须与后端 `apps/agent/services/synthesis/kinds.SYNTHESIS_AGENT_KIND` 同值**（后端
 * 那一处是唯一定义，前端只有这一处镜像）。它不是任何一栏 AI 的回答：不进栏清单、
 * 不占栏位，正文由 ReviewPanel 下的 SynthesisCard 渲染。
 */
export const SYNTHESIS_AGENT_KIND = 'synthesis'

/**
 * 事件该归到哪个 agent。
 *
 * 绝大多数事件带 `agent`；缺失时（旧后端 / 早于本字段的事件）回落到会话级口径
 * pi——**不能**回落到「当前主后端」，否则多答里主后端的事件会被同时写进两条。
 */
export function agentOf(event: object): string {
  // 事件类型是判别联合，多数成员没有 `agent` 字段（delta / thinking / usage…）。
  // 这里用属性探测而不是要求每个成员都声明它：契约里 `agent` 是「转发方补齐」的
  // 可选字段，让联合成员逐个声明只会变出两份定义。
  const agent = (event as { agent?: string }).agent
  return agent || DEFAULT_AGENT_KIND
}

/** 事件里的 `run_id`（缺省空串）；前端只做透传与日志，不解析它的内部结构 */
export function runIdOf(event: object): string {
  return (event as { run_id?: string }).run_id ?? ''
}

/**
 * kind → 栏头显示名。
 *
 * **只放「给人看的品牌名」，不放后端标识**：没登记的 kind 原样显示（`agentLabel`
 * 的兜底），所以新后端上线时漏加一行不会崩，只是栏头出现英文标识。
 *
 * 五个后端的顺序不代表优先级（顺序由后端 `GET /agent/backends` 给）。
 */
const AGENT_LABELS: Record<string, string> = {
  pi: 'Pi',
  dsh: 'DeepSeek Harness',
  'openai-agents': 'OpenAI Agents',
  antigravity: 'Antigravity',
  'claude-agent': 'Claude Agent',
  // 综合结论在转录里也是一条 assistant（见 SYNTHESIS_AGENT_KIND）。它不是某一栏的
  // 回答，distinctAgentKinds / mergeAgentAnswers 都会把它排掉；这里只给它一个可读名字。
  [SYNTHESIS_AGENT_KIND]: '综合结论',
}

export function agentLabel(kind: string): string {
  return AGENT_LABELS[kind] ?? kind
}

/**
 * 把转录切成「渲染项」：**一段连续的非 user 消息 = 一轮**，user 消息各自成组。
 *
 * ## 为什么不是「连续的 assistant 合成一组」（这条曾经就是这么写的，踩过两次）
 *
 * 早先按「连续 assistant」分组，理由是「同一轮各栏的回答相邻写入」。**这个前提
 * 是错的**：工具调用（`role: 'tool'`）也落在同一段里，而多 agent 的工具是**交错**
 * 落库的。实测真实会话（session 268）的顺序长这样：
 *
 *     tool(openai-agents) ×N
 *     assistant(pi)
 *     tool(openai-agents) ×N
 *     assistant(dsh)
 *     ...
 *
 * 按「连续 assistant」切会得到两个后果，都是用户报的 bug：
 *
 * 1. **工具消息各自成组** → 每组只有 1 条 → 调用方走「单条」分支 → 渲染成全宽
 *    `ToolRow` 堆在对话底部，分不清哪个 agent 查的、还占满屏幕；
 * 2. **同一轮的 assistant 被工具隔开** → 三个 agent 被切成多组 → 刷新后从
 *    3 栏变成 2 栏 + 1 条掉到下面（用户截图）。
 *
 * 轮次语义对这两件事都免疫：user 消息天然是轮次边界（每条 user 开启新一轮），
 * 一轮里 assistant / tool 无论怎么交错都在同一组，组内再按 `agentKind` 分栏。
 * 判据也不依赖后端新增字段（消息表没有 turn_id），历史数据同样成立。
 *
 * 单条也返回长度为 1 的组：调用方用一个形状处理，不必分两条路径。
 *
 * 综合结论消息（{@link SYNTHESIS_AGENT_KIND}）**不进任何组**：它的正文由该轮
 * ReviewPanel 下的 SynthesisCard 按轮次回读渲染。而且它是律师点按钮那一刻才写入的，
 * 按落库顺序会排在**当时最新一轮**的末尾（未必是它所属的那一轮），留在转录流里
 * 会挂错轮次。
 */
export function groupAnswerRuns(messages: ChatMessage[]): AnswerGroup[] {
  const groups: AnswerGroup[] = []
  for (const message of messages) {
    if (message.agentKind === SYNTHESIS_AGENT_KIND) continue
    const last = groups[groups.length - 1]
    // user 一定是新组的开头；非 user 只要上一组也不是 user 就并入（= 同一轮）
    const mergeable = message.role !== 'user' && last !== undefined && last.answers[0]?.role !== 'user'
    if (mergeable) last.answers.push(message)
    else groups.push({ answers: [message] })
  }
  return groups
}

/**
 * 一组里实际出现过的 agent kind（按首次出现顺序；不含空 kind）。
 *
 * ## 栏序以 **assistant** 为准，工具只在「这家从没出过正文」时补位
 *
 * 多 agent 的工具是**交错**落库的，而且往往先于正文（模型先查再答）。若把工具
 * 也算进栏序，刷新后栏的左右顺序会跟着「谁的工具先落库」整排换位——实时视图
 * 里是 pi→dsh→openai-agents，刷新完变成 openai-agents→pi→dsh，同一个人换了
 * 位置，读起来像换了答案（真实反馈：刷新后 agent 个数和顺序都乱）。
 *
 * ## 只看 assistant，**不从工具回退补位**
 *
 * 「整轮中断 / 全部失败」时一组里可能只有工具、没有正文。若让工具参与栏清单，
 * 这一组就会被判成「多栏」→ 渲染出若干空白栏 + 栏头，而律师真正想看的工具行
 * 反而被吞掉（实测见过 `sm:grid-cols-4` 的空栅）。没有正文就没有栏可谈，
 * 此时应当逐条平铺工具行。
 */
export function distinctAgentKinds(answers: readonly ChatMessage[]): string[] {
  const seen: string[] = []
  for (const answer of answers) {
    const kind = answer.agentKind
    // 综合结论不是某一栏 AI 的回答：算进栏清单会让多答布局凭空多出一栏，
    // 而它已经由 SynthesisCard 渲染。
    if (answer.role === 'assistant' && kind && kind !== SYNTHESIS_AGENT_KIND && !seen.includes(kind)) seen.push(kind)
  }
  return seen
}

/**
 * 把一轮里「同一栏的多条 assistant」并为一条（就地渲染用）。
 *
 * 后端在**每个** agent 的每轮各发一次 done（见 streaming.ts 的 onDone 契约），
 * 但单后端轮次里同一个 agent 也可能产出多段 assistant 消息（工具调用被拆段、
 * 停止后重发等）。多栏渲染要求「一栏一个气泡」，否则同一个人会说两遍话、
 * 栏头重复出现。
 *
 * 判据是本轮的**栏清单**（store 开流时就知道），不是「有没有 agentKind」：
 * - 栏清单里有的 kind：同 kind 的多条合成一条（内容按到达顺序拼接）；
 * - 栏清单外的 kind：原样各自一条——后端降级时才会出现，前端不该擅自合并
 *   不相干的回答（那会把两轮回答拼成一段看似连贯的话）。
 *
 * 首条的位置即该栏的位置：栏的左右顺序 = 清单顺序（见 store 的 rounds 记账）。
 *
 * 例外：综合结论（{@link SYNTHESIS_AGENT_KIND}）**不输出**。它同样不在栏清单里，
 * 但不是「降级时的不相干回答」——它由 ReviewPanel 下的 SynthesisCard 渲染；按上面
 * 「原样各自一条」处理会多出一栏「综合结论」，与卡片重复。`groupAnswerRuns` 已先把
 * 它排掉，这里再守一道，给直接传入整段转录的调用方。
 */
export function mergeAgentAnswers(answers: ChatMessage[], agents: readonly string[]): ChatMessage[] {
  if (agents.length <= 0) return answers

  // 按栏收集：正文/思考累加，工具调用按到达顺序并列（不累加——它们各自是一条）。
  const byAgent = new Map<string, ChatMessage>()
  const toolsByAgent = new Map<string, ChatMessage[]>()
  for (const answer of answers) {
    const kind = answer.agentKind ?? DEFAULT_AGENT_KIND
    if (!agents.includes(kind)) continue

    // 工具调用归到**它自己那个 agent** 名下。多答时几个 agent 同时调工具，
    // 转录里交错相邻；只按时间平铺就分不清谁查了什么（真实反馈：一坨工具条
    // 堆在底部、占满整行）。
    if (answer.role === 'tool') {
      const list = toolsByAgent.get(kind)
      if (list) list.push(answer)
      else toolsByAgent.set(kind, [answer])
      continue
    }

    const prev = byAgent.get(kind)
    if (!prev) {
      byAgent.set(kind, answer)
      continue
    }
    // `...prev` 只保**前段**字段，后段的引用/截断/失败标记必须显式合并——
    // 漏掉时界面不报错，只是栏头徽标少算引用、停过的那段看不出被截断。
    // 引用按 `citeNo` 取并集（mergeCitations：同号后到为准、位置留在首次出现）；
    // truncated / failed 任一为真即真（任何一段被截/失败，整栏都要标）。
    const citations = mergeCitations(prev.citations, answer.citations ?? [])
    byAgent.set(kind, {
      ...prev,
      content: prev.content + answer.content,
      // 思考过程同理拼接；streaming 只要还有一段在流就仍算在流
      ...(answer.thinking ? { thinking: (prev.thinking ?? '') + answer.thinking } : {}),
      ...(prev.streaming || answer.streaming ? { streaming: true } : {}),
      // 两段都没有引用时不写空数组：`citations` 缺失 = 旧数据/没引，与 `[]` 不同义
      ...(citations.length > 0 ? { citations } : {}),
      ...(prev.truncated || answer.truncated ? { truncated: true } : {}),
      ...(prev.failed || answer.failed ? { failed: true } : {}),
    })
  }

  // 把工具挂回各自那一栏。挂在**合并后**的那条上（而不是每段 assistant 各挂），
  // 界面才是「一个人 → 他查过的东西 → 他的话」，而不是「话、工具、话、工具」。
  for (const [kind, tools] of toolsByAgent) {
    const answer = byAgent.get(kind)
    if (answer) answer.tools = tools
  }
  // 归位后的工具 id（下面过滤要用同一份判据，不能各算一遍）
  const attached = attachedToolIds([...byAgent.values()])

  const merged: ChatMessage[] = []
  const emitted = new Set<string>()
  for (const answer of answers) {
    const kind = answer.agentKind ?? DEFAULT_AGENT_KIND
    // 综合结论由 SynthesisCard 渲染，不占栏（见函数文档）
    if (kind === SYNTHESIS_AGENT_KIND) continue

    // **工具消息不参与栏的排序**，必须在循环最开头跳过。
    //
    // 原先这个判断写在 `if (!combined)` 里面，于是「栏已存在」的工具会一路走到
    // 下面的 `emitted.add / merged.push`，**抢在它自己那条 assistant 之前把整栏
    // 插进结果**。而多 agent 的工具总是先于正文落库（模型先查再答），结果就是
    // 刷新后栏序被工具的落库顺序带偏——实时视图 pi→dsh→oa，刷新完变成
    // oa→pi→dsh（实测踩过，用户报成「刷新后 agent 个数变少、顺序乱了」）。
    if (answer.role === 'tool' && toolsByAgent.has(kind)) continue

    const combined = byAgent.get(kind)
    if (!combined) {
      // 这一栏没有 assistant 正文（整轮失败 / 只有工具）：原样保留，不能凭空
      // 造一个空白栏。
      merged.push(answer)
      continue
    }
    if (emitted.has(kind)) continue
    emitted.add(kind)
    merged.push(combined)
  }

  // 挂到栏上的（含**未完成**的）工具不再当转录流里的独立行渲染：多栏时它们
  // 的位置是「本栏气泡里的活动行（正文未到）/ 本栏下方的 chip（正文已到）」。
  // 漏掉这一步，未完成的工具行会**同时**出现在气泡内和转录流里（重复两处）。
  return merged.filter((m) => m.role !== 'tool' || !attached.has(m.id))
}

/**
 * 已挂到某一栏 `tools` 上的工具消息 id（含**未完成**的那条）。
 *
 * 单栏不走 {@link mergeAgentAnswers}（那条路径的时间顺序本身就是对的，工具行
 * 照旧平铺），所以对单栏回答返回空集，行为与引入本函数前一致。
 */
export function attachedToolIds(merged: readonly ChatMessage[]): Set<string> {
  const ids = new Set<string>()
  for (const message of merged) for (const tool of message.tools ?? []) ids.add(tool.id)
  return ids
}
