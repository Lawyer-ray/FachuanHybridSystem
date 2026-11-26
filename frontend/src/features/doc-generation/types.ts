/**
 * 文书生成的域类型（对齐后端 `/api/v1/doc-workspace` 的 draft-by-type 出参）。
 *
 * 字段名直接用后端 snake_case，不做 camelCase 映射：出参来自 `DocDraftOut`，
 * 多一层重命名只会让「后端加了个字段、前端读不到」变成静默问题。
 */

/** 可起草的文书类型（后端 `DocumentSpec` 的对外投影，`GET doc-types`）。 */
export interface DocType {
  /** 稳定标识，如 `jurisdiction_objection`（下发给 draft-by-type） */
  doc_type: string
  /** 律师看到的类型名，如「管辖权异议申请书」 */
  display_name: string
  /** 骨架族（litigation_v1 / form_v1）：当前只有诉讼骨架，UI 不区分 */
  family: string
}

/** 起草入参。 */
export interface DraftRequest {
  doc_type: string
  case_id?: number
  /** 合同侧参数位：P0 只有案件文书，UI 不暴露（保留给合同文书接入） */
  contract_id?: number
  /** 「槽名 → 律师已确认的值」；P0 页面不给表单，留空交模型写 */
  facts: Record<string, string>
  auto_review: boolean
  instruction: string
  /**
   * 未决项批注的署名（Word/OnlyOffice 审阅面板里显示的「人」）。
   *
   * 随**本次起草**走，不进系统配置：同一个所里不同案子、不同客户对署名的要求都可能不同。
   * 留空由后端回落 `Lawyer`。
   */
  comment_author: string
  /**
   * 材料缺口已到 blocking 时仍要出草稿。
   *
   * 只在律师点了「仍然生成草稿（留空处会挂批注）」时为 true：缺口会写成
   * `<待填写：x>` 并挂批注，视图上不能伪装成材料齐全。
   */
  force?: boolean
}

/** 立案前判断的结论档（后端 `verdict`）。 */
export type ReadinessVerdict = 'ready' | 'draftable_with_gaps' | 'blocked' | 'unknown'

/** 缺口的严重度：不补无法立案 / 影响金额认定 / 影响抗辩。 */
export type MissingSeverity = 'blocking' | 'amount' | 'defense'

/** 要件事实矩阵的一行（后端 `matrix[i]`）：这条要件在本案对应什么事实、出处在哪。 */
export interface ReadinessRequirement {
  /** 要件稳定键（档案里的一行）；只用于排查，不展示给律师 */
  requirement_key?: string
  /** 要件名（「付款义务与到期日」）。后端按档案数据给，前端不再翻译 */
  requirement: string
  /** 为什么这条要件必须满足 */
  why?: string
  /** 本案对应的事实原文（材料里没有就是空串） */
  fact?: string
  /** 出处（「合同 三、2」） */
  source?: string
  /** met / partial / missing */
  status: string
}

/** 补充材料清单的一条（后端 `missing_materials[i]`）。 */
export interface ReadinessMissingItem {
  /** 要补什么，如「被告身份证复印件或户籍信息」 */
  item: string
  /** 为什么必须补 */
  why: string
  /** 向谁要（「委托人 / 律师调查」） */
  from_whom: string
  /** 要什么形式（「复印件 / 公安查询单」） */
  form: string
  severity: MissingSeverity
}

/** 需要核实的问题（后端 `questions[i]`）：材料回答不了、得去问人的那些。 */
export interface ReadinessQuestion {
  /** 问谁（「委托人经办人」） */
  to: string
  question: string
  why: string
}

/**
 * `POST draft/assess` 出参：结论 + 要件矩阵 + 补充材料清单 + 问题清单。
 *
 * 只读判断，不渲染、不落盘。字段名沿用后端 snake_case（与 `DraftResult` 同口径）。
 */
export interface DraftAssessResult {
  verdict: ReadinessVerdict
  /** 命中的要件档案（lease_arrears / contract_payment）；只用于排查，不展示给律师 */
  profile_key: string
  matrix: ReadinessRequirement[]
  missing_materials: ReadinessMissingItem[]
  questions: ReadinessQuestion[]
  /** 挡住起草的那几项缺口名（= severity=blocking 的 item） */
  blocking: string[]
  warnings: string[]
}

/** `POST draft/assess` 入参：项目坐标二选一 + 可选的案由 / 事实 / 补充说明。 */
export interface DraftAssessRequest {
  case_id?: number
  contract_id?: number
  /** 案由：留空由后端取案件上的字段，它决定命中哪份要件档案 */
  cause_of_action?: string
  /** 律师显式给出的事实，会直接改变缺口清单 */
  facts?: Record<string, string>
  instruction?: string
}

/**
 * `POST draft-by-type` 出参：`DocDraftOut` + 文书类型 / 落位归属 / 告警。
 *
 * `created=false` 是**业务失败**（`reason` 有原文），不是异常——失败原因
 * 必须在弹窗里原样给律师看，见 `DraftDialog`。
 */
export interface DraftResult {
  created: boolean
  doc_type: string
  /** 成稿落在哪一侧的文件夹（后端按 spec.folder_slot 解析，前端不许自己推断） */
  kind: 'case' | 'contract'
  owner_id: number
  name: string
  /** 文件夹内相对路径（`kind` + `owner_id` 绑定根之下）：打开画布就用它 */
  subpath: string
  file_url: string
  filled: Record<string, string>
  /** 既没素材、模型也没写出来的槽名（律师要手工补） */
  pending: string[]
  /** 槽位填充率 0~1 */
  slot_fill_rate: number
  review_run_id: number | null
  /** 非致命告警（如某个槽命中了下限、审查没排上） */
  warnings: string[]
  reason: string
}
