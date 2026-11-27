// @vitest-environment jsdom
/**
 * 新建下一程序案件：钉的是**发给后端的东西**，因为这条链路的三个坑都在请求里：
 * - `contract_id` 必须带（不带就挂空合同，项目页看不见，且不报错）；
 * - `current_stage` 必须属于合同的代理阶段（后端按合同校验，不在集合里 400）；
 * - 法院不是案件上的标量，要走 `supervising_authorities` 子表才有 `c.auth`。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ createCaseUnderContract: vi.fn() }))
vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  ...api,
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { AddCaseDialog } from './AddCaseDialog'

// 虚构主体：这里只验证「默认值怎么回填、怎么发出去」，不依赖任何真实当事人
const DEFAULTS = {
  name: '张某诉某公司买卖合同纠纷',
  cause: '买卖合同纠纷',
  amount: '161762',
  court: '某某人民法院',
}

function setup(over: Partial<Parameters<typeof AddCaseDialog>[0]> = {}) {
  const onSaved = vi.fn()
  const onClose = vi.fn()
  render(
    <AddCaseDialog
      open
      contractId={448}
      stage="执行"
      stageCode="enforcement"
      caseType="civil"
      defaults={DEFAULTS}
      onClose={onClose}
      onSaved={onSaved}
      {...over}
    />,
  )
  return { onSaved, onClose }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.createCaseUnderContract.mockResolvedValue({ id: 99, name: DEFAULTS.name })
})

describe('AddCaseDialog', () => {
  it('默认值来自上一个程序，律师确认即可提交', () => {
    setup()
    expect((screen.getByLabelText('案件名称') as HTMLInputElement).value).toBe(DEFAULTS.name)
    expect((screen.getByLabelText('案由') as HTMLInputElement).value).toBe(DEFAULTS.cause)
    expect((screen.getByLabelText('标的额') as HTMLInputElement).value).toBe('161762')
    expect((screen.getByLabelText('主管机关') as HTMLInputElement).value).toBe(DEFAULTS.court)
  })

  it('提交带上 contract_id / 阶段 / 案型 / 金额 / 法院，成功后把新案件 id 交回页面', async () => {
    const { onSaved, onClose } = setup()
    fireEvent.click(screen.getByRole('button', { name: '新建案件' }))

    await waitFor(() => expect(api.createCaseUnderContract).toHaveBeenCalledTimes(1))
    expect(api.createCaseUnderContract).toHaveBeenCalledWith({
      contractId: 448,
      name: DEFAULTS.name,
      stage: 'enforcement',
      caseType: 'civil',
      cause: DEFAULTS.cause,
      targetAmount: 161762,
      court: DEFAULTS.court,
      isFiled: false,
    })
    expect(onSaved).toHaveBeenCalledWith(99)
    expect(onClose).toHaveBeenCalled()
  })

  it('名称为空时不可提交（不发请求）', () => {
    setup({ defaults: { ...DEFAULTS, name: '  ' } })
    expect((screen.getByRole('button', { name: '新建案件' }) as HTMLButtonElement).disabled).toBe(true)
    expect(api.createCaseUnderContract).not.toHaveBeenCalled()
  })

  it('后端拒绝（如「合同未激活」）原样展示，且停在弹窗里不清空输入', async () => {
    api.createCaseUnderContract.mockRejectedValueOnce(new Error('合同未激活'))
    setup()
    fireEvent.click(screen.getByRole('button', { name: '新建案件' }))

    expect(await screen.findByText(/合同未激活/)).toBeTruthy()
    expect((screen.getByLabelText('案件名称') as HTMLInputElement).value).toBe(DEFAULTS.name)
  })
})
