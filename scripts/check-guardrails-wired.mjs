#!/usr/bin/env node
/**
 * 护栏通电自检（Guardrail Wiring Check）
 *
 * 解决的问题（见 docs/harness/pitfalls.md PIT-001 / PIT-005）：
 *   写了一个检查脚本，但从没挂进 CI / pre-commit / Makefile。
 *   它存在、能跑、看起来是护栏，实际上从不执行 —— 「没人执行的护栏等于没有护栏，
 *   而且还多一份维护税」。
 *
 * 判据：scripts/ 下的每个检查脚本，必须在至少一条「必经链」上被引用：
 *   - .github/workflows/*.yml        （CI）
 *   - Makefile                        （本地一键）
 *   - backend/.pre-commit-config.yaml （提交前）
 *   - scripts/ci-local.sh             （本地 CI）
 *   - package.json 的 scripts         （前端/根）
 *
 * 不在必经链上的脚本必须显式登记到 ALLOWED_UNWIRED，并写明理由（一次性工具、
 * 只能手动跑的诊断脚本、依赖真实凭据等）。这样「有人跑」与「故意不跑」是
 * 两件被显式区分的事，而不是一片混沌。
 *
 * 退出码：0 = 全部通电或已豁免；1 = 发现未通电且未豁免的脚本。
 *
 * 用法：
 *   node scripts/check-guardrails-wired.mjs
 *   node scripts/check-guardrails-wired.mjs --json     # 机器可读
 *   node scripts/check-guardrails-wired.mjs --list     # 只列当前视图
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/**
 * 必经链清单。key 是给人看的名字，value 是相对 repoRoot 的文件/目录。
 * 目录会递归读取其中所有 .yml / .yaml。
 */
const CHAIN_SOURCES = {
  "GitHub Actions": ".github/workflows",
  Makefile: "Makefile",
  "pre-commit": "backend/.pre-commit-config.yaml",
  "本地 CI": "scripts/ci-local.sh",
  "package.json": ["package.json", "frontend/package.json"],
};

/**
 * 检查脚本的识别规则：文件名以 check- / verify- / assert- / audit- 开头，
 * 或位于 scripts/ 且扩展名为 .mjs/.py/.sh 且名字含 guard/scan。
 * 纯粹的一次性工具（如 issue-license-code）不算检查脚本。
 */
const isCheckScript = (name) => {
  if (!/\.(mjs|js|py|sh)$/.test(name)) return false;
  return /^(check|verify|assert|audit)[-_]/.test(name) || /(^|[-_])(guard|scan)([-_.]|$)/.test(name);
};

/**
 * 显式豁免：这些脚本故意不挂进必经链。每条都必须写理由，
 * 否则半年后没人知道它为什么在这儿。
 */
const ALLOWED_UNWIRED = new Map([
  // 示例格式（当前无条目，新增时照此写）：
  // ["scripts/check-foo.mjs", "依赖真实生产凭据，只能在发版机上手工跑"],
  [
    "scripts/verify_dsh_mcp.py",
    "端到端验收：需本机 node runtime + dsh home 里装好的 @deepseek-ai/dsh-mcp-client + 真启 dsh 子进程（冷启动数秒），CI 容器不具备且耗时远超单测。" +
      "它不是「没人跑」——依赖它的静态护栏 tests/ci/unit/agent/test_dsh_verify_assertion_sources.py 在 CI 里跑（守护脚本的断言来源不被生产静默）。" +
      "本脚本在接入 dsh 工具面变更时手工跑一次，输出贴进验收报告。",
  ],
]);

function readIfExists(relPath) {
  const abs = path.join(repoRoot, relPath);
  try {
    return readFileSync(abs, "utf8");
  } catch {
    return null;
  }
}

/** 递归收集目录下所有 yml/yaml 文本 */
function readYamlDir(relDir) {
  const abs = path.join(repoRoot, relDir);
  const out = [];
  let entries;
  try {
    entries = readdirSync(abs);
  } catch {
    return "";
  }
  for (const name of entries) {
    const rel = path.join(relDir, name);
    const full = path.join(repoRoot, rel);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) {
      out.push(readYamlDir(rel));
    } else if (/\.ya?ml$/.test(name)) {
      const text = readIfExists(rel);
      if (text) out.push(text);
    }
  }
  return out.join("\n");
}

/** 收集所有必经链的文本内容 */
function collectChainText() {
  const chunks = [];
  for (const [label, target] of Object.entries(CHAIN_SOURCES)) {
    const targets = Array.isArray(target) ? target : [target];
    for (const rel of targets) {
      const abs = path.join(repoRoot, rel);
      let st;
      try {
        st = statSync(abs);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        chunks.push(readYamlDir(rel));
      } else {
        const text = readIfExists(rel);
        if (text) chunks.push(text);
      }
    }
  }
  return chunks.join("\n");
}

/** 列 scripts/ 顶层的检查脚本（不含 fixtures/__pycache__） */
function listCheckScripts() {
  const abs = path.join(repoRoot, "scripts");
  let entries;
  try {
    entries = readdirSync(abs);
  } catch {
    return [];
  }
  return entries
    .filter((name) => {
      const full = path.join(abs, name);
      try {
        if (!statSync(full).isFile()) return false;
      } catch {
        return false;
      }
      return isCheckScript(name);
    })
    .sort();
}

/**
 * 判断脚本是否在链文本中被引用。
 * 同时接受三种写法：完整相对路径、文件名、去掉扩展名的名字
 * （因为 package.json 里常写 `node scripts/check-foo.mjs`，
 *   Makefile 里常写 `./scripts/check-foo.sh`）。
 */
function isReferenced(scriptName, chainText) {
  const stem = scriptName.replace(/\.(mjs|js|py|sh)$/, "");
  const needles = [`scripts/${scriptName}`, scriptName, stem];
  return needles.some((needle) => chainText.includes(needle));
}

function main() {
  const argv = process.argv.slice(2);
  const asJson = argv.includes("--json");
  const listOnly = argv.includes("--list");

  const chainText = collectChainText();
  const scripts = listCheckScripts();

  const wired = [];
  const unwired = [];
  const exempted = [];

  for (const name of scripts) {
    const rel = `scripts/${name}`;
    if (isReferenced(name, chainText)) {
      wired.push(rel);
    } else if (ALLOWED_UNWIRED.has(rel)) {
      exempted.push({ script: rel, reason: ALLOWED_UNWIRED.get(rel) });
    } else {
      unwired.push(rel);
    }
  }

  if (asJson) {
    process.stdout.write(
      `${JSON.stringify({ wired, unwired, exempted, total: scripts.length }, null, 2)}\n`,
    );
    process.exit(unwired.length === 0 ? 0 : 1);
  }

  console.log("护栏通电自检（PIT-001 / PIT-005）");
  console.log(`扫描 scripts/ 下的检查脚本：${scripts.length} 个`);
  console.log(`  已挂进必经链：${wired.length}`);
  console.log(`  显式豁免：${exempted.length}`);
  console.log(`  未通电：${unwired.length}`);
  console.log("");

  if (listOnly) {
    for (const rel of wired) console.log(`  [wired]    ${rel}`);
    for (const { script, reason } of exempted) console.log(`  [exempted] ${script} — ${reason}`);
    for (const rel of unwired) console.log(`  [UNWIRED]  ${rel}`);
    process.exit(unwired.length === 0 ? 0 : 1);
  }

  if (exempted.length > 0) {
    console.log("显式豁免：");
    for (const { script, reason } of exempted) console.log(`  - ${script}：${reason}`);
    console.log("");
  }

  if (unwired.length > 0) {
    console.error("以下检查脚本未挂进任何必经链：");
    for (const rel of unwired) console.error(`  - ${rel}`);
    console.error("");
    console.error("两种修法（二选一）：");
    console.error("  1) 挂进 CI / Makefile / pre-commit / ci-local.sh / package.json 的脚本链；");
    console.error(
      "  2) 如果它确实只能手工跑，在 scripts/check-guardrails-wired.mjs 的 ALLOWED_UNWIRED 里登记并写明理由。",
    );
    console.error("");
    console.error("背景：docs/harness/pitfalls.md PIT-005 —— 没人执行的护栏等于没有护栏。");
    process.exit(1);
  }

  console.log("全部检查脚本均已通电或已显式豁免。");
}

main();
