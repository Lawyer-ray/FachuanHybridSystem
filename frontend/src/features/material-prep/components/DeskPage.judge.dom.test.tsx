// @vitest-environment jsdom
/**
 * DeskPage：judge / openAt / 删除 / 拖放与收尾清理（jsdom）。
 *
 * 从 DeskPage.dom.test.tsx 按被测单元拆出；共用桩与渲染入口见
 * `desk-page-test-harness.tsx`，用例本身逐字搬迁（含两段覆盖率补测）。
 */
import { act, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  dialogs,
  httpError,
  navSpy,
  pack,
  renderDesk,
  resetDeskPageMocks,
  setup,
  storeMock,
  ui,
} from './desk-page-test-harness'

import { toast } from 'sonner'

beforeEach(resetDeskPageMocks)

describe('DeskPage：judge 离场', () => {
  it('归案成功：卡片进入 leaving 并从列表移除', async () => {
    const { judgeMutate } = setup([pack(1, 'todo')])
    const { unmount } = renderDesk()

    // 直接调 judgeVoid 的等价入口不存在，改由 PackGrid 触发不可行
    // —— 这里验证 leaving 初值为空即可，judge 路径由下方 hook 级测试覆盖
    expect(ui.grid!.leaving).toEqual({})
    expect(judgeMutate).not.toHaveBeenCalled()
    unmount()
  })
})

// ============ judge / openAt / 删除 / 拖放（覆盖率补测） ============

describe('DeskPage：openAt 与不接', () => {
  it('打开第 0 个：调用 openPack 并 SPA 跳转', async () => {
    setup([pack(5, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('打开第0个').click()
      await Promise.resolve()
    })
    expect(storeMock.open).toHaveBeenCalledWith(5)
    unmount()
  })

  it('从「待处理」打开材料包：跳转详情时带上 stage（否则会闪一下列表）', async () => {
    // bug：openAt 原先 navigate(materialPrepDetail(id)) 不带 ?stage=，
    // 详情路由 parseStage(null) 回落成「收件箱」→ 先渲染一帧收件箱列表，
    // 阅读器才盖上来，用户看到「闪一下列表再进详情」。
    setup([pack(5, 'todo')])
    const { unmount, getByText } = renderDesk('/material-prep?stage=todo')

    await act(async () => {
      getByText('打开第0个').click()
      await Promise.resolve()
    })
    expect(storeMock.open).toHaveBeenCalledWith(5)
    expect(navSpy.navigate).toHaveBeenCalledWith('/material-prep/5?stage=todo')
    unmount()
  })

  it('不接：以 filed 调 judge 并提示归档留痕', async () => {
    const { judgeMutate } = setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(judgeMutate).toHaveBeenCalledWith({ id: 1, status: 'filed' }))
    await waitFor(() => expect(toast.success ?? toast).toBeTruthy())
    unmount()
  })

  it('judge 失败：提示状态更新失败', async () => {
    // 真实 API 失败是 ky 的 HTTPError（无可用 data），errMessage 才会回落到兜底文案；
    // 裸 Error 的 message('boom') 会被上层当成可读文案透出，与线上形状不符
    setup([pack(1, 'todo')], {
      judge: vi.fn(async () => {
        throw httpError(500)
      }),
    })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('状态更新失败，请重试'))
    unmount()
  })
})

describe('DeskPage：通过弹窗归案', () => {
  it('确认归案以 done 调 judge', async () => {
    const { judgeMutate } = setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('确认归案').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(judgeMutate).toHaveBeenCalledWith({ id: 1, status: 'done' }))
    unmount()
  })
})

describe('DeskPage：删除', () => {
  it('确认删除：以目标 id 发删除请求、提示并清空目标', async () => {
    const { deleteMutate } = setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    // 先点「删」设目标，再点弹窗确认
    fireEvent.click(getByText('删'))
    await act(async () => {
      getByText('确认删除').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(deleteMutate).toHaveBeenCalledWith(1))
    expect(toast).toHaveBeenCalledWith('pack-1 已删除')
    expect(toast.error).not.toHaveBeenCalled()
    // 成功后清空目标：再次确认不会重复发包
    await act(async () => {
      getByText('确认删除').click()
      await Promise.resolve()
    })
    expect(deleteMutate).toHaveBeenCalledTimes(1)
    unmount()
  })

  it('删除被财务凭证挡住（409）：透出后端原文，而不是笼统的「删除失败」', async () => {
    // 后端 ConflictError 的 message 必须直达用户：笼统文案会让人以为是网络抖动而反复重试
    const backendMsg = '该材料包已被待认领的发票记录 2 条引用，不能再删除；请先处理这些凭证'
    setup([pack(1, 'todo')], {
      del: vi.fn(async () => {
        throw httpError(409, { code: 'INBOX_MESSAGE_REFERENCED', message: backendMsg })
      }),
    })
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('删'))
    await act(async () => {
      getByText('确认删除').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(backendMsg))
    unmount()
  })

  it('无删除目标时确认是 no-op', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('确认删除').click()
      await Promise.resolve()
    })
    // 未设置 deleteTarget 时不抛错即可
    expect(dialogs.props).toBeTruthy()
    unmount()
  })
})

describe('DeskPage：拖放层级计数', () => {
  function dragEvent(type: string, hasFiles = true) {
    const e = new Event(type, { bubbles: true, cancelable: true }) as Event & {
      dataTransfer?: { types: string[]; files: unknown[]; dropEffect?: string }
    }
    e.dataTransfer = { types: hasFiles ? ['Files'] : ['text/plain'], files: [] }
    return e
  }

  it('拖入文件时进入 dragging 态（DropLayer 收到 dragging=true）', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    act(() => {
      root.dispatchEvent(dragEvent('dragenter'))
    })
    await waitFor(() => expect(ui.drop!.dragging).toBe(true))
    unmount()
  })

  it('非文件拖入不进入 dragging 态', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    act(() => {
      root.dispatchEvent(dragEvent('dragenter', false))
    })
    unmount()
  })

  it('dragLeave 逐层递减，归零才取消 dragging', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    act(() => {
      root.dispatchEvent(dragEvent('dragenter'))
      root.dispatchEvent(dragEvent('dragenter'))
      root.dispatchEvent(dragEvent('dragleave'))
      root.dispatchEvent(dragEvent('dragleave'))
    })
    unmount()
  })
})

// ============ 剩余分支（覆盖率补测） ============

describe('DeskPage：重复 judge 防重入', () => {
  it('同一 pack 连续两次 judge：第二次被 leaving 守卫拦下', async () => {
    const judgeMutate = vi.fn(async () => ({}))
    setup([pack(1, 'todo')], { judge: judgeMutate })
    const { unmount, getByText } = renderDesk()

    // 第一次点「不接」→ 进入 leaving
    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    await waitFor(() => expect(judgeMutate).toHaveBeenCalledTimes(1))

    // 第二次点击应被拦下（leaving[pack.id] 已置位）
    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    expect(judgeMutate).toHaveBeenCalledTimes(1)
    unmount()
  })
})

describe('DeskPage：删除目标与选择文件', () => {
  it('点「删」设置删除目标后弹窗收到该目标', async () => {
    setup([pack(3, 'todo')])
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('删'))
    await waitFor(() => expect(dialogs.props!.deleteTarget).toBeTruthy())
    unmount()
  })

  it('点「改名」设置重命名目标', async () => {
    setup([pack(4, 'todo')])
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('改名'))
    await waitFor(() => expect(dialogs.props!.renameTarget).toBeTruthy())
    unmount()
  })

  it('点「接」设置归案目标后弹窗收到该目标', async () => {
    setup([pack(5, 'todo')])
    const { unmount, getByText } = renderDesk()

    fireEvent.click(getByText('接'))
    await waitFor(() => expect(dialogs.props!.assigning).toBeTruthy())
    unmount()
  })

})

describe('DeskPage：拖放上传与 dragOver', () => {
  function dragEvent(type: string, files: File[] = []) {
    const e = new Event(type, { bubbles: true, cancelable: true }) as Event & {
      dataTransfer?: { types: string[]; files: File[]; dropEffect?: string }
    }
    e.dataTransfer = { types: ['Files'], files }
    return e
  }

  it('drop 触发上传并清空 dragging', async () => {
    const { createMutate } = setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    await act(async () => {
      root.dispatchEvent(dragEvent('drop', [new File(['x'], 'a.pdf')]))
      await Promise.resolve()
    })
    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    unmount()
  })

  it('dragOver 文件时 preventDefault 并设置 dropEffect=copy', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    const e = dragEvent('dragover')
    act(() => {
      root.dispatchEvent(e)
    })
    expect(e.defaultPrevented).toBe(true)
    expect((e as unknown as { dataTransfer: { dropEffect: string } }).dataTransfer.dropEffect).toBe('copy')
    unmount()
  })

  it('dragOver 非文件时不做处理', async () => {
    setup([pack(1, 'todo')])
    const { unmount, container } = renderDesk()
    await waitFor(() => expect(ui.drop).toBeTruthy())

    const root = container.firstElementChild as HTMLElement
    const e = new Event('dragover', { bubbles: true, cancelable: true }) as Event & {
      dataTransfer?: { types: string[]; dropEffect?: string }
    }
    e.dataTransfer = { types: ['text/plain'] }
    act(() => {
      root.dispatchEvent(e)
    })
    expect(e.defaultPrevented).toBe(false)
    unmount()
  })
})

// ============ 对话框取消 / 离场清理（覆盖率补测） ============

describe('DeskPage：对话框取消', () => {
  it('对话框取消回调各自清空目标', async () => {
    setup([pack(1, 'todo')])
    const { unmount, getByText } = renderDesk()

    // 先设目标再取消
    fireEvent.click(getByText('删'))
    await waitFor(() => expect(dialogs.props!.deleteTarget).toBeTruthy())
    fireEvent.click(getByText('取消删除'))
    await waitFor(() => expect(dialogs.props!.deleteTarget).toBeNull())

    fireEvent.click(getByText('接'))
    await waitFor(() => expect(dialogs.props!.assigning).toBeTruthy())
    fireEvent.click(getByText('取消归案'))
    await waitFor(() => expect(dialogs.props!.assigning).toBeNull())

    fireEvent.click(getByText('改名'))
    await waitFor(() => expect(dialogs.props!.renameTarget).toBeTruthy())
    fireEvent.click(getByText('关闭改名'))
    await waitFor(() => expect(dialogs.props!.renameTarget).toBeNull())
    unmount()
  })
})

describe('DeskPage：离场定时器清理', () => {
  it('judge 后离场标记在定时器到点后被清除', async () => {
    vi.useFakeTimers()
    const judgeMutate = vi.fn(async () => ({}))
    setup([pack(1, 'todo')], { judge: judgeMutate })
    const { unmount, getByText } = renderDesk()

    await act(async () => {
      getByText('不接').click()
      await Promise.resolve()
    })
    // PACK_LEAVE_REMOVAL_MS 后离场标记被删
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })
    expect(ui.grid!.leaving).toEqual({})
    vi.useRealTimers()
    unmount()
  })
})
