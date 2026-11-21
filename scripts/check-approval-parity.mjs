#!/usr/bin/env node
/**
 * 审批分级跨语言一致性（approval parity）。
 *
 * ## 解决的问题
 *
 * 审批分级在两侧各有一份实现：权威源是服务端
 * `backend/apps/agent/services/approval/risk.py`，pi extension 侧是
 * `backend/apps/agent/pi/approval-rules.ts`。此前的一致性检查只是用正则从 TS
 * 源码里抠出数组字面量比文本（`test_agent_risk_tiers.py` 的 `_ts_list`）——
 * **TS 侧的判定函数其实从未被执行过**。文本相等不等于判定相等：注解缺失的
 * 缺省语义、短名归一的口径都在「表一致」的表象下各自漂过。
 *
 * 本脚本用 Node 原生类型剥离（`node --experimental-strip-types`，Node ≥22.6；
 * ≥22.18/23 默认开启）**直接加载并执行** `approval-rules.ts`，拿与 Python 测试
 * 同一份向量 `backend/tests/ci/fixtures/approval_vectors.json` 逐条比对期望值。
 * 向量里的期望值 = 服务端的判定（权威），所以这里是「TS 实现 vs Python 语义」
 * 的真执行对账，而不是源码文本比对。
 *
 * ## 失败姿态
 *
 * 任何一条不一致 → 非零退出。
 * Node 不支持类型剥离 / 无法 import 该 TS 文件 / 向量文件缺失或为空 → 同样
 * **非零退出并说明原因**，绝不在没跑成的情况下打印通过（静默 pass 比没有
 * 这道门更糟）。
 *
 * ## 用法
 *
 *   node scripts/check-approval-parity.mjs
 *   make approval-parity
 */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL, fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RULES_PATH = path.join(repoRoot, "backend", "apps", "agent", "pi", "approval-rules.ts");
const VECTORS_PATH = path.join(repoRoot, "backend", "tests", "ci", "fixtures", "approval_vectors.json");

/** 向量条数下限：太少就守不住规则表（一次重构删掉大半也能全绿）。 */
const MIN_VECTORS = 40;

const RISK_LEVELS = new Set(["low", "medium", "high", "critical"]);

function die(message) {
  console.error(`approval-parity: ${message}`);
  process.exit(1);
}

/**
 * 确保当前 Node 能直接 import `.ts`。
 *
 * Node ≥22.18/23 默认开启类型剥离（`process.features.typescript === "strip"`）；
 * 22.6–22.17 需要显式 `--experimental-strip-types`。两种情况都接受：
 * 需要 flag 且当前没有 → 用 flag 重跑自己一次。重跑仍失败（或 flag 不被支持）
 * 就如实非零退出，不假装通过。
 */
function ensureTypeStripping() {
  const tsSupport = process.features?.typescript;
  if (tsSupport) {
    return;
  }
  if (process.env.APPROVAL_PARITY_REEXEC === "1") {
    die(
      "当前 Node 不支持直接加载 TypeScript（类型剥离不可用），无法执行 approval-rules.ts。" +
        ` 当前版本 ${process.version}；请用 Node ≥22.6（推荐 ≥22.18，默认开启）。`,
    );
  }
  const child = spawnSync(
    process.execPath,
    ["--experimental-strip-types", ...process.execArgv, fileURLToPath(import.meta.url), ...process.argv.slice(2)],
    { stdio: "inherit", env: { ...process.env, APPROVAL_PARITY_REEXEC: "1" } },
  );
  if (child.error) {
    die(`带 --experimental-strip-types 重跑失败: ${child.error.message}`);
  }
  if (child.status !== 0) {
    die(
      `当前 Node（${process.version}）无法启用类型剥离（退出码 ${child.status}）。` +
        " 本检查需要 Node ≥22.6（推荐 ≥22.18）。",
    );
  }
  process.exit(0);
}

function loadVectors() {
  let raw;
  try {
    raw = readFileSync(VECTORS_PATH, "utf8");
  } catch (error) {
    die(`读不到向量文件 ${path.relative(repoRoot, VECTORS_PATH)}: ${error.message}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    die(`向量文件不是合法 JSON: ${error.message}`);
  }
  if (!Array.isArray(parsed)) {
    die("向量文件的顶层必须是数组");
  }
  if (parsed.length < MIN_VECTORS) {
    die(`向量只有 ${parsed.length} 条，少于下限 ${MIN_VECTORS} 条（规则表会被删空了还全绿）`);
  }
  return parsed;
}

const REQUIRED_EXPORTS = ["classifyByName", "classifyByAnnotations", "isHardDenied", "shortName"];

async function loadRules() {
  let mod;
  try {
    mod = await import(pathToFileURL(RULES_PATH).href);
  } catch (error) {
    die(
      `无法加载 ${path.relative(repoRoot, RULES_PATH)}: ${error.message}\n` +
        "  （该模块必须是纯 TypeScript：不 import 任何 pi 扩展 API，否则 Node 跑不起来）",
    );
  }
  const missing = REQUIRED_EXPORTS.filter((name) => typeof mod[name] !== "function");
  if (missing.length > 0) {
    die(`approval-rules.ts 缺少导出: ${missing.join(", ")}`);
  }
  return mod;
}

/**
 * 与服务端 `classify_risk` 同构的组合：
 * 名字判定 → 有注解则与注解层取较大者 → 没有注解就退回名字判定。
 *
 * 这条「无注解不抬高」的口径 2026-11 才在 TS 侧对齐（此前是「至少 medium」），
 * 向量里 `annotations: null` 的读类样本就是钉它的。
 */
function classifyLikeServer(rules, vector) {
  const byName = rules.classifyByName(vector.name, vector.args ?? undefined);
  return rules.classifyByAnnotations(vector.annotations ?? undefined, byName);
}

async function main() {
  ensureTypeStripping();

  const vectors = loadVectors();
  const rules = await loadRules();

  console.log("审批分级跨语言一致性（Python 期望值 vs TS 纯函数真执行）");
  console.log(`  Node:   ${process.version}（typescript=${String(process.features?.typescript)}）`);
  console.log(`  规则:   ${path.relative(repoRoot, RULES_PATH)}`);
  console.log(`  向量:   ${path.relative(repoRoot, VECTORS_PATH)}（${vectors.length} 条）`);

  const failures = [];
  for (const [index, vector] of vectors.entries()) {
    const label = `#${String(index).padStart(2, "0")} ${vector.name}`;
    if (!RISK_LEVELS.has(vector.expected_level)) {
      failures.push(`${label}: 向量 expected_level 非法（${JSON.stringify(vector.expected_level)}）`);
      continue;
    }
    const actualLevel = classifyLikeServer(rules, vector);
    const actualHardDeny = rules.isHardDenied(vector.name) !== null;
    if (actualLevel !== vector.expected_level) {
      failures.push(`${label}: 分级不一致 — ts=${actualLevel} py=${vector.expected_level}（${vector.note ?? ""}）`);
    }
    if (actualHardDeny !== vector.expected_hard_deny) {
      failures.push(
        `${label}: 硬拒绝不一致 — ts=${actualHardDeny} py=${vector.expected_hard_deny}（${vector.note ?? ""}）`,
      );
    }
  }

  if (failures.length > 0) {
    console.error("");
    console.error(`以下 ${failures.length} 条与权威（Python）不一致：`);
    for (const failure of failures) {
      console.error(`  ✗ ${failure}`);
    }
    console.error("");
    console.error("改法：先改权威源 apps/agent/services/approval/risk.py → 更新向量 → 让 approval-rules.ts 跟上。");
    process.exit(1);
  }

  console.log(`OK ${vectors.length}/${vectors.length}`);
}

main().catch((error) => {
  die(`未预期的错误: ${error?.stack ?? String(error)}`);
});
