#!/usr/bin/env node
/**
 * worktree 生命周期护栏（Worktree Lifecycle Check）
 *
 * ## 解决的问题（2026-11-21 实测：一次查出 18 个 worktree / 1.9G）
 *
 * 「火力全开」模式下每个 writer 独占一个 worktree 是**硬要求**（两个 writer 同一
 * cwd 必然互相覆盖）。但规范此前只写了「开」，没写「收」，于是出现三种残留：
 *
 * 1. **分支没人合回来**：writer commit 到 `lane/x` 就「完成」了，而 `commit` 到
 *    自己的分支并不会让内容进主线——squash 合并后 patch-id 全变，`git branch
 *    --merged` 永远说「未合并」，人不敢删 → 永久堆积。
 * 2. **目录在仓库外，`git status` 看不见**：`../_wt/` 这类布局让所有本地检查
 *    （pr-ready / guardrails / pre-commit）都碰不到它。
 * 3. **浅克隆让「已合并」难以判定**：`.git/shallow` 下 `--merged` / `git cherry`
 *    给出的是假结论（实测被它骗过一次：报告「151 条补丁未进 main」，实际内容
 *    98% 已在 main）。但有一条**不信历史也能用**的判据：
 *    `git merge-base --is-ancestor <branch> HEAD` —— 真 merge（非 squash）进来的分支
 *    是 HEAD 的祖先，这个判定在浅克隆里同样成立。squash 合并的分支则判不出来，
 *    仍按「目录在不在 / 脏不脏 / 推没推」处理（要精确判定得 `git fetch --unshallow`）。
 *
 * ## 判据（FAIL 会让 `make guardrails` 非零退出）
 *
 * | 情况 | 判定 | 理由 |
 * |:-|:-|:-|
 * | 工作目录已不存在（只剩 git 元数据） | FAIL（提示 prune） | 纯垃圾，`git worktree prune` 即可清 |
 * | 有未提交改动 且 分支未推送 | FAIL | 改动**只存在于这台机器上的这个目录**，误删即丢 |
 * | 有分支但从未推送 且 最后提交超过 N 天 | FAIL | 最典型的「合并债」：内容可能已在主线，但无人能确认 |
 * | detached（不属于任何分支）且超过 N 天 | FAIL | 临时手段忘了收（本仓库允许 detached + patch 交付，但必须当场收掉） |
 * | 分支已是本分支/主线的**祖先**（`merge-base --is-ancestor`） | 可回收 | 真 merge（非 squash）进来的，内容与提交都在主线里 |
 * | 分支已推送 且 空闲超过 2N 天 | WARN | 内容在远端有备份，可安全回收 |
 * | 浅克隆 | WARN（一次性） | 提示 `git fetch --unshallow`，否则永远无法确认合并状态 |
 *
 * ## 用法
 *
 * ```bash
 * node scripts/check_worktrees.mjs            # 检查（FAIL 非零退出）
 * node scripts/check_worktrees.mjs --json     # 机器可读
 * FACHUAN_WORKTREE_MAX_AGE_DAYS=14 node scripts/check_worktrees.mjs
 * ```
 *
 * 回收前先归档（把「删」变成「挪到备份」，人才敢删）：
 * ```bash
 * git bundle create ../_wt/archive-$(date +%Y%m%d).bundle --branches
 * git bundle verify ../_wt/archive-$(date +%Y%m%d).bundle
 * ```
 *
 * 退出码：0 = 无 FAIL；1 = 有 FAIL。
 */

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** 允许的最大空闲天数（可按环境变量覆盖）。超过即认为是「忘了收」。 */
const MAX_AGE_DAYS = Number(process.env.FACHUAN_WORKTREE_MAX_AGE_DAYS || 7);
/** 「内容在远端有备份」的 worktree 允许更久，但超过这个倍数仍要提醒。 */
const PUSHED_GRACE_FACTOR = 2;
const DAY_MS = 86400_000;

const jsonMode = process.argv.includes("--json");

/** 跑一条 git 命令，失败返回空串（护栏不该因为 git 报错而崩）。 */
function git(args, cwd = repoRoot) {
  try {
    return execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

/** 当前仓库是否浅克隆（浅克隆下「是否已合并」不可判定，必须显式提示）。 */
function isShallow() {
  return git(["rev-parse", "--is-shallow-repository"]) === "true";
}

/**
 * 解析 `git worktree list --porcelain`。
 *
 * 逐块读 `worktree` / `HEAD` / `branch` / `detached`：porcelain 是逐行 key，
 * 空行分隔，比解析人类可读表格稳（表格会对齐、会截断路径）。
 */
function listWorktrees() {
  const out = git(["worktree", "list", "--porcelain"]);
  const entries = [];
  let current = null;
  for (const line of out.split("\n")) {
    if (line.startsWith("worktree ")) {
      if (current) entries.push(current);
      current = { path: line.slice("worktree ".length), head: "", branch: "", detached: false };
      continue;
    }
    if (!current) continue;
    if (line.startsWith("HEAD ")) current.head = line.slice(5);
    else if (line.startsWith("branch ")) current.branch = line.slice("branch ".length).replace("refs/heads/", "");
    else if (line === "detached") current.detached = true;
  }
  if (current) entries.push(current);
  return entries;
}

/**
 * 未提交状态拆成两类。
 *
 * **只有未跟踪文件（`??`）不算「有改动丢了」**：那是构建产物 / 本地 docs / 临时
 * 稿件，回收 worktree 时本来就要丢。真正的风险是「已跟踪文件的改动」，所以两类
 * 分开报：`changed` 才是 FAIL 依据，`untracked` 只提示。
 */
function workingState(dir) {
  const out = git(["-C", dir, "status", "--porcelain"]);
  const lines = out ? out.split("\n").filter(Boolean) : [];
  const untracked = lines.filter((l) => l.startsWith("??")).length;
  return { changed: lines.length - untracked, untracked };
}

/**
 * 该 worktree 是否正被进程使用（cwd 在目录内）。
 *
 * 为什么必须查它：另一个会话/另一个 AI 可能正在这个目录里跑测试，此时任何
 * 「回收」建议都是误导（`git worktree remove --force` 会把它正在跑的东西抽掉）。
 * 用 ``lsof -a -d cwd``（macOS/Linux 都有）；命令不存在或超时一律当作「没在用」，
 * 护栏不该因缺工具而崩。
 */
function inUse(dir) {
  try {
    const out = execFileSync("lsof", ["-a", "-d", "cwd", dir], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 3000,
    });
    return out.split("\n").filter(Boolean).length > 1; // 首行是表头
  } catch {
    return false;
  }
}

/**
 * 空闲天数 = min(最后提交距今, worktree 管理目录 mtime 距今)。
 *
 * 为什么不能用「最后提交时间」单独判：detached worktree 是挂在**某个提交**上的，
 * 那个提交可能很老（今天刚 checkout 也一样）——只用提交时间会把「今天刚建的临时
 * worktree」误判成「放了很久」。反过来只用目录 mtime 又会把「只改了文件没提交」
 * 当成活跃。取两者较小值 = 「这里最后一次有任何动作」。
 */
function idleDays(dir, entryPath) {
  const commitAge = (() => {
    const ts = Number(git(["-C", dir, "log", "-1", "--format=%ct"]));
    return Number.isFinite(ts) && ts > 0 ? (Date.now() - ts * 1000) / DAY_MS : Number.POSITIVE_INFINITY;
  })();
  const adminAge = (() => {
    try {
      const base = path.join(repoRoot, ".git", "worktrees");
      for (const id of readdirSync(base)) {
        const gitdirFile = path.join(base, id, "gitdir");
        if (!existsSync(gitdirFile)) continue;
        const target = readFileSync(gitdirFile, "utf8").trim();
        if (path.resolve(path.dirname(target)) !== path.resolve(entryPath)) continue;
        return (Date.now() - statSync(path.join(base, id)).mtimeMs) / DAY_MS;
      }
    } catch {
      // 拿不到管理目录（裸仓库 / 权限）就退回提交时间
    }
    return Number.POSITIVE_INFINITY;
  })();
  return Math.min(commitAge, adminAge);
}

/**
 * 该分支是否已经是本分支的祖先（= 真 merge 进来过，内容与提交都在主线里）。
 *
 * `merge-base --is-ancestor` 不依赖完整历史——只要提交链在本地存在就能判，
 * 浅克隆下也成立（`--merged` / `git cherry` 则会被 graft 边界骗）。
 */
function isMergedIntoHead(sha) {
  if (!sha) return false;
  try {
    execFileSync("git", ["merge-base", "--is-ancestor", sha, "HEAD"], { cwd: repoRoot, stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** 该提交是否已存在于任何远端分支（= 内容有远端备份）。 */
function isPushed(sha) {
  if (!sha) return false;
  return git(["branch", "-r", "--contains", sha]) !== "";
}

/** 目录是否还存在（worktree 被手工 rm -rf 后 git 元数据仍在，需要 prune）。 */
function exists(p) {
  try {
    execFileSync("test", ["-d", p]);
    return true;
  } catch {
    return false;
  }
}

function inspect(entry) {
  const main = path.resolve(entry.path) === path.resolve(repoRoot);
  if (main) return null; // 主工作区不参与检查（`git status` 已由别的护栏覆盖）

  const row = {
    path: entry.path,
    branch: entry.detached ? "(detached)" : entry.branch || "(unknown)",
    head: entry.head.slice(0, 8),
    exists: exists(entry.path),
    dirty: 0,
    pushed: false,
    ageDays: null,
    verdict: "OK",
    reasons: [],
  };
  if (!row.exists) {
    row.verdict = "FAIL";
    row.reasons.push("目录已不存在（只剩 git 元数据）→ `git worktree prune`");
    return row;
  }

  if (inUse(entry.path)) {
    // 使用中的 worktree 一律不判 FAIL：它可能就是另一个会话正在干活的地方
    row.verdict = "WARN";
    row.reasons.push("有进程正在这个目录里工作（不判定、不建议回收）");
    row.ageDays = null;
    return row;
  }

  const state = workingState(entry.path);
  row.dirty = state.changed;
  row.untracked = state.untracked;
  row.pushed = isPushed(entry.head);
  row.merged = isMergedIntoHead(entry.head);
  const idle = idleDays(entry.path, entry.path);
  row.ageDays = Number.isFinite(idle) ? Math.floor(idle) : null;

  const tooOld = row.ageDays === null || row.ageDays > MAX_AGE_DAYS;

  if (row.merged) {
    // 真 merge 进来的分支：内容与提交都在主线里，唯一风险是这里还有未提交的新改动
    if (row.dirty > 0) {
      row.verdict = "FAIL";
      row.reasons.push(`分支已合并进当前分支，但这里有 ${row.dirty} 个已跟踪文件的未提交改动（确认是要留的新东西还是残留）`);
    } else {
      row.verdict = "WARN";
      row.reasons.push("分支已合并进当前分支（merge-base --is-ancestor 成立），worktree 可回收");
    }
    return row;
  }

  if (row.dirty > 0 && !row.pushed) {
    row.verdict = "FAIL";
    row.reasons.push(`${row.dirty} 个**已跟踪文件**的未提交改动且分支未推送（改动只存在于这台机器）`);
  } else if (row.untracked > 0) {
    row.verdict = row.verdict === "FAIL" ? "FAIL" : "WARN";
    row.reasons.push(`${row.untracked} 个未跟踪文件（构建产物/本地 docs，回收时本来就会丢；确认无需保留）`);
  }
  if (!row.pushed && tooOld) {
    row.verdict = "FAIL";
    row.reasons.push(
      `分支从未推送且最后提交在 ${row.ageDays ?? "未知"} 天前（> ${MAX_AGE_DAYS} 天）→ 先归档再回收`,
    );
  }
  if (entry.detached && tooOld) {
    row.verdict = "FAIL";
    row.reasons.push(
      `detached worktree 已存在 ${row.ageDays ?? "未知"} 天（detached 只能用于「当场交付 patch」，` +
        `交付完必须 \`git worktree remove\`）`,
    );
  }
  if (row.verdict === "OK" && row.pushed && row.ageDays !== null && row.ageDays > MAX_AGE_DAYS * PUSHED_GRACE_FACTOR) {
    row.verdict = "WARN";
    row.reasons.push(`已推送但空闲 ${row.ageDays} 天，可安全回收（内容在远端）`);
  }
  return row;
}

function main() {
  const shallow = isShallow();
  const rows = listWorktrees()
    .map(inspect)
    .filter(Boolean);

  const fails = rows.filter((r) => r.verdict === "FAIL");
  const warns = rows.filter((r) => r.verdict === "WARN");

  if (jsonMode) {
    console.log(JSON.stringify({ shallow, maxAgeDays: MAX_AGE_DAYS, worktrees: rows }, null, 2));
    return fails.length ? 1 : 0;
  }

  console.log(`worktree 生命周期检查（主工作区除外，共 ${rows.length} 个；阈值 ${MAX_AGE_DAYS} 天）`);
  if (shallow) {
    console.log(
      "  ⚠ 当前是**浅克隆**（git rev-parse --is-shallow-repository=true）：\n" +
        "     `git branch --merged` / `git cherry` 在浅克隆下会给出**假结论**（实测被它骗过），\n" +
        "     所以本脚本不判定「是否已合并」，只判定「目录在不在 / 脏不脏 / 推没推」。\n" +
        "     要精确判定合并状态：git fetch --unshallow（只补历史，不动工作树）。",
    );
  }
  console.log("");
  for (const r of rows) {
    const mark = r.verdict === "FAIL" ? "✗ FAIL" : r.verdict === "WARN" ? "⚠ WARN" : "· ok  ";
    const age = r.ageDays === null ? "  ?" : String(r.ageDays).padStart(3);
    const push = r.merged ? "已合并" : r.pushed ? "已推送" : "仅本地";
    const extra = r.untracked ? `+${r.untracked}?` : "";
    console.log(`  ${mark}  ${r.branch.padEnd(26)} ${age}天  changed=${r.dirty}${extra}  ${push}  ${r.path}`);
    for (const reason of r.reasons) console.log(`            └ ${reason}`);
  }

  // 只对「该回收的」打命令：WARN 里因为「有未跟踪文件」而警告、但其实刚刚还在动
  // 的 worktree（idle 很新）不在其列——打印 `git worktree remove --force` 会诱导
  // 把那正在用的目录抽掉。
  const recyclable = [...fails, ...warns.filter((r) => r.ageDays !== null && r.ageDays > MAX_AGE_DAYS)];
  if (recyclable.length) {
    console.log("\n回收步骤（先归档，让「删」变成「挪到备份」）：");
    console.log("  git bundle create ../_wt/archive-$(date +%Y%m%d).bundle --branches");
    console.log("  git bundle verify ../_wt/archive-$(date +%Y%m%d).bundle");
    for (const r of recyclable) {
      console.log(`  git worktree remove --force ${r.path}`);
      if (!r.branch.startsWith("(")) console.log(`  git branch -D ${r.branch}`);
    }
    console.log("  git worktree prune");
  }

  console.log("");
  if (fails.length) {
    console.log(`✗ ${fails.length} 个 worktree 有未收尾的改动或未归档的分支（见上）。`);
    return 1;
  }
  console.log("✅ 无 FAIL（WARN 项可择期回收）。");
  return 0;
}

process.exit(main());
