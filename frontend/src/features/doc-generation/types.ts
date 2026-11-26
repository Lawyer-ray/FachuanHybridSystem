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
