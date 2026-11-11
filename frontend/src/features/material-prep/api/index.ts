/**
 * 材料预处理的后端对接出口。
 *
 * 按**后端域**拆为 inbox-packs / cache / ocr / pdf-split / client / contracts /
 * cases / office / upload-links 九个模块，本文件只做 barrel re-export：消费方
 * 继续 `from '../api'` / `from './api'` 不变（原 api.ts 拆成 api/ 目录，解析
 * 结果同一份模块图）。
 *
 * 2026-11 拆分缘起：单文件 api.ts 到 588 行越过 frontend/CLAUDE.md 的 450 行
 * 硬红线，且七个后端域（inbox 材料包、附件字节、OCR、PDF 拆分、当事人、合同、
 * cases 归案、Office 取字、上传链接）混在一处。拆分点是「一个后端域一个文件」，
 * 不是机械切行——归案（assignPack）整条链路仍在同一文件内，行为与拆分前逐字一致。
 *
 * 注意：**不要**把这里改成只 re-export 一个子集。子模块之间存在共享的客户端
 * 实例（inboxApi / clientApi / contractsApi），它们是既有「每个 prefix 一个
 * client」约定的延续，直接整组导出。
 */

export * from './inbox-packs'
export * from './cache'
export * from './ocr'
export * from './pdf-split'
export * from './client'
export * from './contracts'
export * from './cases'
export * from './office'
export * from './upload-links'
