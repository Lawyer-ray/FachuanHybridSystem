import type { CaseListItem } from '../types'
import { casesApi } from './client'

/**
 * 在既有项目下新建一个程序案件（项目页「＋ 新建X案件」）。
 *
 * 走 `POST /cases/cases/full` 而不是精简版 `/cases`：法院在案件上不是标量字段，
 * 而是 `supervising_authorities` 子表（详情页 `c.auth` 取的就是它第一行），
 * 只有 full 版能在建案的同一次请求里把法院一起落下来；分两次建会出现
 * 「案卡先没有法院、刷新后才有」的空窗。
 *
 * **`contract_id` 是这条链路的命门**：后端 `CaseCommandService.create_case`
 * 拿它校验合同、并按合同勾选的代理阶段校验 `current_stage`。本仓库的
 * `CaseIn` 原本没声明这个字段（ModelSchema 白名单里没有 FK），已补上；
 * 少了它建出来的案件会挂空合同，项目页直接看不见。
 *
 * 另外两条实测口径：
 * - 合同必须 `status=active`，否则后端回「合同未激活」（未盖章项目要先在编辑页改状态）；
 * - `current_stage` 必须属于该合同的 `representation_stages`，否则回「当前阶段必须属于代理阶段集合」。
 *   所以这里只发调用方给的那个阶段（项目页给的是「合同勾选、尚未立案」的下一程序）。
 */
export async function createCaseUnderContract(input: {
  contractId: number
  name: string
  /** 阶段代码（first_trial / second_trial / enforcement …） */
  stage: string
  /** 合同类型代码；与合同一致时阶段校验才过得去 */
  caseType?: string | null
  cause?: string
  targetAmount?: number | null
  /** 主管机关（法院 / 仲裁委）名称；空则不建子表记录 */
  court?: string
  /** 建档后后端会自动补建档编号 */
  isFiled?: boolean
}): Promise<CaseListItem> {
  return casesApi
    .post('cases/full', {
      json: {
        case: {
          name: input.name,
          contract_id: input.contractId,
          status: 'active',
          current_stage: input.stage,
          ...(input.caseType ? { case_type: input.caseType } : {}),
          ...(input.cause ? { cause_of_action: input.cause } : {}),
          ...(input.targetAmount != null ? { target_amount: input.targetAmount } : {}),
          ...(input.isFiled ? { is_filed: true } : {}),
        },
        ...(input.court ? { supervising_authorities: [{ name: input.court }] } : {}),
      },
    })
    .json<CaseListItem>()
}
