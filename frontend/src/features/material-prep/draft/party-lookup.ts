import { lookupClients } from '../api'
import type { DraftState } from '../types'
import { detectPartyCandidates, joinPartyNames, type DetectedParties } from './detect-parties'

/**
 * 用**客户库**给文本识别出来的当事人「定身份」。
 *
 * ═══ 为什么光靠标签不够 ═══
 * 标签只说明「这一行是什么字段」，不说明「我们代表谁」。同一叠纸里
 * 「申请人」可以同时指委托单位（复议申请人）和职工（工伤认定申请人）——
 * 见 detect-parties.ts 的 AMBIGUOUS_OUR_LABELS，该材料包 就是把两造拼成了一个委托人。
 * 词频、优先级、白名单都救不了这种**语义对立**，只能换一个信息源。
 *
 * ═══ 为什么客户库是那个信息源 ═══
 * `is_our_client` 是律师自己维护过的既成事实：归案建当事人（api/cases.ts 的
 * ensureClient）、办案主页建项目（features/workbench/templates.ts）都会把当事人
 * 以「我方委托人 / 对方当事人」写进客户库。所以**已经有过项目的材料**尤其准 ——
 * 那个项目早就把这叠纸里的人分好两侧了，这里只是把结论读回来。
 *
 * ═══ 失败口径 ═══
 * 查不到 / 请求失败 / 客户库里没有这个人 → 一律退回标签判定（detectParties 的老行为），
 * 绝不因为网络问题让「自动识别当事人」整体失效。
 */

/** 一次最多查几个名字：候选是「我方 → 对方 → 职工」顺序，截断只丢最不可能的那些 */
const MAX_LOOKUPS = 6

/** 客户库检索的最小形状（真实实现是 api/client 的 lookupClients，单测可注入假实现） */
export type PartySearcher = (keyword: string) => Promise<SearcherHit[]>

export interface SearcherHit {
  name: string
  is_our_client: boolean
}

/** 一个候选名在客户库里的落点 */
export interface KnownParty {
  /** 材料里识别出来的写法 */
  text: string
  /** 客户库里登记的全称（建案/建合同要用它，否则会另建一个重复客户） */
  canonical: string
  isOurClient: boolean
}

/**
 * 从检索命中里挑出与 `name` 指同一个主体的那一条。
 *
 * 服务端按 `name__icontains` 检索，命中项有两类：真名的超集（材料里写的是简称 /
 * 带职务尾巴），以及手机号/证件号撞上的无关项。只认前一类，且要求候选名够长
 * （≥4 字）—— 认错主体比不填更糟，律师根本不会去核对一个「看起来对」的委托人。
 */
export function pickSameParty(name: string, hits: readonly SearcherHit[]): SearcherHit | null {
  const exact = hits.find((h) => h.name === name)
  if (exact) return exact
  return hits.find((h) => h.name.includes(name) && name.length >= 4) ?? null
}

/** 候选名 → 客户库落点（并发查、单个失败不影响其余） */
export async function lookupKnownParties(
  names: readonly string[],
  search: PartySearcher,
): Promise<KnownParty[]> {
  const targets = [...new Set(names.map((n) => n.trim()).filter(Boolean))].slice(0, MAX_LOOKUPS)
  if (targets.length === 0) return []
  const settled = await Promise.allSettled(targets.map((name) => search(name)))
  const found: KnownParty[] = []
  targets.forEach((text, i) => {
    const r = settled[i]
    if (!r || r.status !== 'fulfilled') return
    const hit = pickSameParty(text, r.value)
    if (!hit) return
    found.push({ text, canonical: hit.name, isOurClient: hit.is_our_client })
  })
  return found
}

/** 把客户库结论与标签判定合成最终结果（纯函数，便于单测） */
export function mergeKnownParties(
  detected: DetectedParties,
  known: readonly KnownParty[],
): DetectedParties {
  if (known.length === 0) return detected
  const knownOur = known.filter((k) => k.isOurClient)
  const knownTheir = known.filter((k) => !k.isOurClient)
  // 客户库认得的那一侧以库为准；库给不出答案的一侧才用标签判定兜底。
  // 兜底时要把「已知属于对面」的名字剔掉 —— 否则又把两造拼进同一个字段。
  const textOurs = detected.our
    .split('、')
    .filter((n) => n && !knownTheir.some((k) => k.text === n))
  const textTheirs = detected.their
    .split('、')
    .filter((n) => n && !knownOur.some((k) => k.text === n))
  return {
    our: knownOur.length > 0 ? joinPartyNames([...new Set(knownOur.map((k) => k.canonical))]) : joinPartyNames(textOurs),
    their:
      knownTheir.length > 0
        ? joinPartyNames([...new Set(knownTheir.map((k) => k.canonical))])
        : joinPartyNames(textTheirs),
  }
}

/** 订阅点：真实调用方用它（自动分段完成时 / 「重新识别当事人」按钮） */
export const searchClientLibrary: PartySearcher = (keyword) => lookupClients(keyword)

/** 识别当事人总入口：文本候选 → 客户库对账 → 合并（客户库不可用时等价于 detectParties） */
export async function resolveParties(
  draft: DraftState,
  search: PartySearcher = searchClientLibrary,
): Promise<DetectedParties> {
  const cand = detectPartyCandidates(draft)
  const text: DetectedParties = {
    our: joinPartyNames(cand.ours),
    their: joinPartyNames(cand.theirs),
  }
  if (cand.names.length === 0) return text
  try {
    return mergeKnownParties(text, await lookupKnownParties(cand.names, search))
  } catch {
    // 客户库只是「更准的旁证」，挂了不能拖垮识别本身
    return text
  }
}
