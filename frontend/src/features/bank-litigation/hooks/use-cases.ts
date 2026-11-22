/**
 * 本 feature 读取 hook 的**转口**（barrel）。
 *
 * ═══ 为什么拆 ═══
 * 这个文件曾把「异步读取骨架 + 案件 hook + OA hook」装在一起（126 行），
 * 名字 `use-cases` 与实际职责不符：找 `useOAConfigs` / `useLoad` 的人不会想到进这里。
 * 现在真实定义按关注点落在三个文件，本文件只 re-export，调用方 import 路径不用改：
 *
 *   use-async-load.ts  useLoad + AsyncState —— 全体读取 hook 的三态骨架
 *   use-case.ts        useCases / useCase / useMaterialStatus / useReadiness /
 *                      useCaseFilingInfo
 *   use-oa.ts          useOAConfigs / useConflictCheck
 *
 * 新代码请直接从上面三个文件 import，不要再往本文件加东西。
 */
export type { AsyncState } from './use-async-load'
export { useCase, useCaseFilingInfo, useCases, useMaterialStatus, useReadiness } from './use-case'
export { useConflictCheck, useOAConfigs } from './use-oa'
