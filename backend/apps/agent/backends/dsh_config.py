"""把 Django 的 ``LLMProvider`` 映射成 DeepSeek Harness 的 ``DeepSeekHarnessConfig``。

## 为什么单独一个模块

``dsh_backend`` 负责「跑一轮」，本模块只负责「这一轮用什么 provider / key /
模型 / 目录」。拆开的理由和 pi 侧 ``model_config`` 一样：provider 解析要读同步
ORM，而 block 模型在事件循环里跑，两者的线程模型完全不同（见 ``build_config``
的 ``provider`` 参数说明）。

## 哪些是实测确认的

- dsh 认 ``DEEPSEEK_BASE_URL`` + ``DEEPSEEK_API_KEY`` 两个环境变量；
  ``DeepSeekHarnessConfig.base_url`` / ``api_key`` 会把它们写进子进程 env
  （``api.py`` 的 ``__init__`` 可见）。所以本模块只需填这两个字段。
- ``dsh_home`` **必须显式给**，SDK 绝不隐式用 ``~/.dsh``（``client.py`` 的
  ``_default_launch_args`` 会抛 ``ValueError``）。目录还存在内容生命周期问题
  （profile 里要装插件），所以必须是**稳定目录**而不是 ``mkdtemp`` 一次性目录。

## 为什么 provider 解析复用 pi 的函数

``_load_provider`` / ``_provider_keys_and_models`` / ``_provider_models`` 已经
处理了本仓库的全部配置细节（``api_keys`` 的 ``key|model1,model2`` 格式、
``extra_models`` 的逗号/分号/换行混写、key 轮转）。再写一套等于让两边的
「哪个平台算可用」口径分叉——Admin 里改一个 provider，pi 能跑、dsh 跑不了
（或反过来）是最难查的一类配置故障。

## 读库走缓存，key 轮转不走缓存

每轮现查 ``LLMProvider`` 要付一条 ``sync_to_async`` + ORM 的固定开销（实测
占首字延迟里约 1.3s 量级）。:func:`build_config` 不传 ``provider`` 时改走
``gateway_cache.get_gateway_settings``（30s TTL + provider 保存信号失效）。
缓存只存平台静态配置，**key 轮转仍然每轮现算**——否则轮转会被冻结，
所有会话压在同一把 key 上（见 ``gateway_cache`` 模块 docstring）。
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from ..pi.model_config import _next_key
from .gateway_cache import get_gateway_settings, model_supports_thinking, settings_from_provider

logger = logging.getLogger(__name__)

#: dsh home 根目录的环境变量。与 pi 的 ``FACHUAN_AGENT_HOME`` 并列而不是复用：
#: dsh home 里有 profile 与 node_modules（插件），和 pi 的 ``models.json`` 目录
#: 完全不同的生命周期。混用会让「删掉 pi 配置目录」连带把 dsh 的插件装到
#: 一半的 profile 一起删掉。
DSH_HOME_ENV = "FACHUAN_DSH_HOME"
#: 缺省根目录（用户级，避免误入 git）。
DEFAULT_ROOT_NAME = ".fachuan-dsh"

#: 官方 MCP 插件版本。它落后于 runtime（0.2.2-rc.2），必须显式豁免才能装；
#: 升级 runtime 时这里也要跟着确认（见 docs 里的 dsh 接入说明）。
MCP_CLIENT_VERSION = "0.0.1-rc.1"

#: dsh 的 provider 名。**2026-11-18 真实网关实测后定为 ``fachuan``**。
#:
#: 走过的弯路（记录下来，避免以后再试一遍）：
#:
#: 1. ``deepseek-official`` + ``DEEPSEEK_BASE_URL`` 指向内网网关 → **502**。
#:    原因：该 provider 走 DeepSeek 原生 Messages 协议，而律所网关是
#:    LiteLLM（OpenAI 兼容）：``/v1/chat/completions`` 认，Messages 形态不认。
#: 2. 想在 ``llm-pi-ai`` 插件里声明 OpenAI 兼容路由 → 需同时给 ``api`` /
#:    ``baseURL`` / ``apiKeyEnv`` / ``models`` 四项，缺一个就报
#:    「resolves no models」或「no adapter registered for provider」。
#: 3. 配齐后仍 502 → **是系统代理劫持**（见 :func:`without_proxy_env`）。
#:
#: 所以这里用自己在 ``llm-pi-ai`` 里声明的 provider ``fachuan``，走
#: ``openai-completions`` 协议。该名字与 pi 侧 models.json 里的 provider key
#: 故意同名，排查日志时两侧不会各叫一个名字。
DEFAULT_PROVIDER = "fachuan"

#: 法穿在 dsh 侧使用的协议适配器（``llm-pi-ai`` 插件支持四种，
#: 见 ``dsh --dump-config-schema`` 的 ``llm-pi-ai`` 分支）。
#: 律所网关全是 LiteLLM / OpenAI 兼容，所以固定 completions；
#: 将来接 Anthropic 原生路由时要把它做成可配置。
DEFAULT_API = "openai-completions"


@dataclass(frozen=True)
class DshProviderConfig:
    """一次运行要用的 dsh 配置事实（不持有 SDK 类型）。

    为什么不直接返回 ``DeepSeekHarnessConfig``：本模块要在 **没有装 SDK** 的
    环境里被测试与 import（注册表延迟 import 的前提，见 ``builtin.py``）。
    返回 SDK 类型会把 ``import deepseek_harness`` 变成 import 本模块的副作用，
    没装 SDK 的部署（例如只跑 pi 的节点）会在 app 启动时崩。

    ``patches`` 是额外 profile 层文件路径（MCP 接入靠它，见
    ``docs/04-计划/活跃/dsh-python-sdk-integration.md`` §3.2）。空元组表示不加层。
    """

    dsh_home: str
    provider: str
    model: str
    base_url: str | None
    api_key: str | None
    patches: tuple[str, ...] = ()

    def sdk_kwargs(self) -> dict[str, Any]:
        """展开成 ``DeepSeekHarnessConfig(**kwargs)`` 的关键字参数。

        单独一个方法而不是在每个调用点手抄字段：dsh SDK 是 rc 版本（会改字段名），
        升级时只改这一处。
        """
        return {
            "dsh_home": self.dsh_home,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "patches": self.patches,
            # 注意：代理变量的剔除**不能**靠这里——SDK 是用
            # ``os.environ.copy()`` 叠加 env，加得进、删不掉。
            # 真正的剔除在 ``without_proxy_env()``，由池层包住 start() 调用。
            # **必须显式给 cwd**（正式验收时踩到的真实故障）：
            #
            # dsh 启动时会读 cwd 下的 `.env`（layered env）。而它有一条自我
            # 保护规则：代理类变量（`HTTPS_PROXY` 等）只允许由**启动方环境**
            # 提供，不允许来自“随仓库走”的 `.env`——因为那些变量决定了进程
            # 去哪里取代码与网络。一旦命中，整个 runtime 直接退出：
            #
            #   Error: dsh: <cwd>/.env sets "HTTPS_PROXY", which only the
            #   launching environment may set ...
            #
            # 我们的 Django 进程 cwd 通常是 `backend/`，里面正有含代理配置的
            # `.env`，于是 dsh 一启就死（`TransportClosedError`）。
            #
            # 不能让 dsh 用仓库目录做 cwd：除了 `.env` 冲突，dsh 还会去读 cwd
            # 下的 `AGENTS.md`/技能目录（编码 agent 的默认行为），这些对法务
            # 场景全是多余且不可控的注入面。所以用 dsh home 自己下的子目录。
            "cwd": self.workspace_dir,
        }

    @property
    def workspace_dir(self) -> str:
        """dsh 运行用工作目录（位于该用户的 dsh home 下，不存在则建）。

        为什么不复用 dsh_home 本身：dsh 会在 cwd 写会话临时文件与工作产物，
        与 profile 目录（含 `node_modules`）混在一起会让「清工作区」和
        「清 profile」变成同一件事。

        它也不承载任何业务文件：法务附件一律以 base64 进 MCP 工具，dsh 不需要
        看到本机文件系统（与 pi 时不开放 read/bash 同一条红线）。
        """
        path = Path(self.dsh_home) / "workspace"
        path.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            path.chmod(0o700)
        return str(path)


#: 代理类变量。**必须从 dsh 子进程里剔除**，理由与 pi 侧
#: （`pi/rpc_client.py` 的 `_clean_env`）完全相同，但 dsh 没有这一步就会直接坏：
#:
#: 律所大模型网关是内网地址（如 `http://152.16.10.110:4000/v1`），而开发机的
#: `HTTP_PROXY`/`HTTPS_PROXY` 指向本地 Clash（`127.0.0.1:7897`），`NO_PROXY`
#: 通常只含 localhost。dsh 子进程继承后，请求会先被送到代理 → 代理无法回源
#: 内网地址 → 网关侧表现为 **502 with no body**，重试 5 次后返回空回复。
#:
#: 实测（正式验收）：同一条 key + base_url，直连 `chat/completions` 得到正常
#: 回答，走代理则 502。所以这不是“网络不通”，而是路由选错。
#:
#: 用环境变量剔除法而不是 `NO_PROXY=*`：clash / 企业代理对 `NO_PROXY` 通配的
#: 支持不一致（部分实现只认域名后缀），而 dsh 侧根本不需要出口代理——它只连
#: 内网网关、MCP 与本机。彻底不传最干净。
_PROXY_ENV_KEYS = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    }
)


@contextlib.contextmanager
def without_proxy_env() -> Iterator[None]:
    """临时从本进程环境里拿掉代理变量，退出时原样恢复。

    ## 为什么非得改本进程环境

    dsh SDK 启动子进程时是 ``env = os.environ.copy()`` 再叠加 ``config.env``
    （见 ``client.py`` 的 ``start()``）——**只能加、不能删**。所以我们无法从
    SDK 配置层把代理变量拿掉；只能在自己调用 ``start()`` 的瞬间把父进程环境
    里的这几个键临时删除，让 ``os.environ.copy()`` 拿到的就不含它们。

    ## 为什么是在这里而不是在池里

    删除窗口越短越好：本函数只覆盖一次 ``start()`` 调用（百毫秒量级，子进程
    已经把 env 拷走就不需要了）。放在池里整轮覆盖会让本进程的其他网络代码
    （比如同时跑的 httpx 请求）在窗口内失去代理，反而制造新问题。

    ## 并发安全

    ``os.environ`` 是**进程全局**的，两个并发 ``start()`` 会互相看到对方删的
    键——但由于两边都是“删同一批键、退出时恢复”，且恢复值是各自进入时的快照，
    实际效果是“期间代理变量缺席、之后恢复为最后一次快照”。对一个只用于
    “让子进程拷不到代理”的瞬时窗口而言这个语义足够；不引入锁是因为锁会把并发
    启动串行化，而子进程启动本来就是最慢的一步。

    真要彻底避免共享状态，只能绕开 SDK 自己 ``Popen``（等于放弃官方 SDK），
    不划算。
    """
    saved = {key: os.environ.pop(key) for key in list(_PROXY_ENV_KEYS) if key in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def proxy_env_keys() -> frozenset[str]:
    """需要从 dsh 子进程环境里剔除的变量名（供测试与诊断使用）。"""
    return _PROXY_ENV_KEYS


def _ensure_profile(home: Path) -> None:
    """让一个 dsh home 拥有可用的 ``sdk`` profile（含 mcp-client 插件）。

    ## 为什么需要这一步（真实缺口）

    每个 dsh home 首次启动时，dsh 会自己铺一份 shipped ``sdk`` profile——但**只有
    框架包，没有 ``@deepseek-ai/dsh-mcp-client``**。缺它的后果是：dsh 照常能对话，
    只是**没有任何法穿业务工具**（`mcp__fachuan__*` 一个都不注册），而且因为
    ``failOnStartupError`` 的语义，界面上不报错。律师会觉得「这个模型变笨了」。

    而装它要联网 pnpm 下载；按用户目录各装一份（几百 MB × N 人）既慢又浪费。

    ## 做法：共享一份，各 home 软链

    ``<root>/_shared_profile``：**唯一真实安装**，首次创建时装 mcp-client。
    各 home 的 ``profiles/sdk`` 指向它（symlink）。

    ## 为什么只链 ``profiles/sdk`` 而不链整个 home

    dsh home 下除了 profile 还有 ``sessions/``、``storages/``、``.credentials.yaml``
    等**按用户隔离**的东西（串号风险）。只共享「代码/依赖」这一层，数据层仍各管各的。

    ## 失败时的行为

    任何一步失败都只记 warning：dsh 仍能用 shipped profile 跑通对话，只是没有
    业务工具。把「工具面缺失」升级成「整轮对话失败」是错的取舍——模型本身能跑。
    运维可用 ``FACHUAN_DSH_AUTO_PROFILE=0`` 关掉自动引导（容器里依赖已预装时）。
    """
    if os.environ.get("FACHUAN_DSH_AUTO_PROFILE", "").strip() in {"0", "false", "False"}:
        return

    profile_dir = home / "profiles" / "sdk"
    # 已经是符号链接（之前链过）或已装好依赖 → 无需重复处理
    if profile_dir.is_symlink():
        return
    if (profile_dir / "node_modules" / "@deepseek-ai" / "dsh-mcp-client").is_dir():
        return

    shared = home.parent / "_shared_profile"
    try:
        if not shared.exists():
            _install_shared_profile(shared)
        # 目标 home 若已有 shipped profile（dsh 启动过一次），先挪走再链，
        # 否则 symlink 会失败（EEXIST）。挪走而不是删：里面可能有用户改过的 patch。
        if profile_dir.exists():
            legacy = home / "profiles" / "sdk.pre-shared"
            if not legacy.exists():
                profile_dir.rename(legacy)
            else:
                import shutil

                shutil.rmtree(profile_dir, ignore_errors=True)
        profile_dir.parent.mkdir(parents=True, exist_ok=True)
        # 指向 **shared 下的 profiles/sdk**，不是 shared 本身——
        # 链到 shared 根会让 dsh 把 `profiles/sdk` 解成 `shared/profiles/sdk`，
        # 而实际内容在 `shared/profiles/sdk/` 里，于是 node_modules 全找不到
        # （表现为「装了但工具面为空」）。实测踩到过。
        profile_dir.symlink_to(shared / "profiles" / "sdk", target_is_directory=True)
        logger.info("dsh profile 已链到共享安装：%s -> %s", profile_dir, shared)
    except Exception:  # 引导失败必须降级，不能拖垮对话
        # **刻意宽捕获**：这一步会调外部 `dsh` 子进程（网络装包），失败原因五花八门
        # ——CI 无网络（exit 127）、pnpm 权限、目标目录只读、subprocess 超时……
        # 设计约定是「工具面缺失」而**不是**「对话失败」（见函数 docstring）：
        # 模型本身能跑，把引导错误上抛会把「能用」变成「不能用」。
        #
        # 实测教训：原先只 catch OSError，而 subprocess.CalledProcessError 是
        # SubprocessError 子类**不是** OSError —— CI 里 8 个用例因此全红。
        logger.warning("dsh profile 引导失败（本会话无业务工具，但可对话）", exc_info=True)


def _install_shared_profile(shared: Path) -> None:
    """在共享目录里装出带 mcp-client 的 sdk profile（只跑一次）。

    先让 dsh 自己铺 shipped profile（它知道当前版本该用什么 bundle 组合），
    再补装 mcp-client。直接手写 package.json 会随 runtime 版本漂移。
    """
    import subprocess

    shared.mkdir(parents=True, exist_ok=True)
    dsh_bin = shutil_which("dsh")
    if dsh_bin is None:
        raise OSError("找不到 dsh 可执行文件（deepseek-harness-runtime-bin 未安装？）")

    # **必须设 dsh 认的那个变量名**（``DSH_HOME``），不是我们的 ``FACHUAN_DSH_HOME``。
    # 两者含义不同：前者是给 dsh 二进制的运行时约定，后者是我们自己的部署配置项
    # （dsh_home_for 读它来算根目录）。实测：只设 FACHUAN_DSH_HOME 时 dsh 报
    # 「requires an explicit DSH_HOME」并退出 2。
    env = {**os.environ, "DSH_HOME": str(shared)}
    # 让 dsh 把 shipped profile 铺到这个 home。
    # 用 `--help` 而不是 `--dump-config`：实测前者会初始化 profile 目录，
    # 后者只读组合树、缺 profile 时直接报错（不会替我们铺）。
    subprocess.run(
        [dsh_bin, "--profile", "sdk", "--help"],
        env=env,
        # cwd 必须是 dsh home 自己（不是仓库目录）：dsh 启动时读 cwd 下的 `.env`，
        # 而 `backend/.env` 含 HTTPS_PROXY —— 它会以「代理只允许由启动方环境提供」
        # 为由直接退出。同一坑在运行期由 workspace_dir 规避，引导期要单独处理。
        cwd=str(shared),
        check=True,
        capture_output=True,
        timeout=300,
    )
    profile = shared / "profiles" / "sdk"
    if not profile.is_dir():
        raise OSError(f"dsh 未铺出 profile：{profile}")

    # 装 mcp-client。版本需与 runtime 不兼容 → 必须显式豁免（否则 install 被拒）。
    version = _runtime_version()
    steps: list[list[str]] = []
    if version:
        steps.append(
            [
                dsh_bin,
                "plugin",
                "--profile",
                "sdk",
                "allow-version",
                f"@deepseek-ai/dsh-mcp-client@{MCP_CLIENT_VERSION}",
                "--dsh-version",
                version,
                "--accept-risk",
            ]
        )
    steps.append([dsh_bin, "plugin", "--profile", "sdk", "add", "@deepseek-ai/dsh-mcp-client"])
    for step in steps:
        subprocess.run(step, env=env, cwd=str(shared), check=True, capture_output=True, timeout=600)

    installed = profile / "node_modules" / "@deepseek-ai" / "dsh-mcp-client"
    if not installed.is_dir():
        raise OSError("mcp-client 安装后仍不存在")


def shutil_which(name: str) -> str | None:
    """找出与**当前 Python 环境配对**的 dsh 可执行文件。

    ## 为什么不能直接用 ``shutil.which``

    实测：开发机 `PATH` 上的 `dsh` 是全局 npm 版 **0.2.2-rc.1**，而本项目
    `deepseek-harness-sdk==0.2.2rc2` 配对的是 venv 里的 **0.2.2-rc.2**。
    用错版本会报 `dsh: ... returned non-zero exit status 1`，而错误信息完全不提
    「版本不匹配」——排查方向被彻底带偏（我实际踩过，花了一轮才定位）。

    ## 优先级

    1. 与当前解释器同目录的 `dsh`（venv 的 `bin/dsh`）—— 唯一保证配对的那个
    2. ``PATH`` 上的 `dsh`（容器里通常已对齐版本）
    """
    import shutil
    import sys

    sibling = Path(sys.executable).parent / name
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)
    return shutil.which(name)


def _runtime_version() -> str:
    """当前 dsh runtime 版本（用于 allow-version 豁免）。取不到返回空串。"""
    import subprocess

    dsh_bin = shutil_which("dsh")
    if dsh_bin is None:
        return ""
    try:
        # dsh 的 Python 包装器要求 ``DSH_HOME`` 显式给出（不给就退出、stdout 为空）。
        # 这里用临时目录：只为问版本，不该碰真实 home 的 profile。
        with tempfile.TemporaryDirectory(prefix="dsh-ver-") as tmp:
            out = subprocess.run(
                [dsh_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
                env={**os.environ, "DSH_HOME": tmp},
                cwd=tmp,
            )
        return out.stdout.strip().lstrip("v")
    except (OSError, subprocess.SubprocessError):
        return ""


def dsh_home_for(user_id: int | None) -> str:
    """该用户的稳定 dsh home 目录（不存在就建）。

    按 ``user_id`` 隔离而不是全局一个目录：dsh home 里既有 profile（含
    ``node_modules``，几百 MB 且装一次要联网）也有会话历史与凭据缓存。多个律师
    共用一个目录会让 A 的 ``.credentials.yaml`` 被 B 的请求命中——串号比慢更糟。

    无用户身份（测试 / 后台任务）落在 ``_shared`` 子目录：不能回退到「谁先来算
    谁的」，否则并发测试之间会互相删目录。

    目录权限设 0700：里面会落凭据文件（与 ``pi.session_store.agent_home`` 同口径）。
    """
    configured = os.environ.get(DSH_HOME_ENV, "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / DEFAULT_ROOT_NAME
    path = root / (str(user_id) if user_id is not None else "_shared")
    path.mkdir(parents=True, exist_ok=True)
    _ensure_profile(path)
    try:
        os.chmod(path, 0o700)
    except OSError:
        # 权限收紧失败不是致命错误（容器里可能已是受限用户），但不能静默：
        # 这个目录里有 API key 与凭据缓存。
        logger.warning("无法收紧 dsh home 权限 %s（忽略）", path, exc_info=True)
    return str(path)


#: dsh 默认是「给程序员用的编码 agent」，默认开着一整套 shell / 文件 / 技能 /
#: 联网能力。法务场景要的是「律师助理」，这些能力必须显式关掉——它们的共同
#: 后果是「提示注入 → 读写宿主文件 / 执行命令 / 向任意地址外发」。
#:
#: 这里用 **禁用插件** 而不是限制参数：dsh 的插件一旦挂上就会往工具面向模型
#: 暴露工具声明，即使调不出来也会占上下文与被诱导的可能。直接 `disabled: true`
#: 才是真的不提供。
#:
#: 每条都写了关它的具体理由，避免以后有人「为了方便调试」顺手打开。
_DSH_LOCKDOWN_PATCH = """
# 法穿安全收紧层（默认加载，优先于用户 patch）
- id: tool-bash
  disabled: true
- id: bash-sandbox
  disabled: true
- id: tool-pwsh
  disabled: true
- id: pwsh-sandbox
  disabled: true
- id: tool-jobs
  disabled: true
- id: shell-env
  disabled: true
- id: tool-fs
  disabled: true
- id: tool-fs-search
  disabled: true
- id: fs-observation-policy
  disabled: true
- id: tool-plugin-manager
  disabled: true
- id: plugin-manager
  disabled: true
- id: skill
  disabled: true
- id: skill-filesystem
  disabled: true
- id: tool-skill
  disabled: true
- id: agent-instructions
  disabled: true
- id: goal
  disabled: true
- id: goal-round-driver
  disabled: true
- id: command-goal
  disabled: true
# 子 agent / 工作流 / 定时任务：法务场景无此需求，且都是「可再起一个模型循环」
# 的入口——多一层循环就多一处不受主会话审批约束的工具调用面。
- id: subagent
  disabled: true
- id: subagent-spawn-in-process
  disabled: true
- id: subagent-fork-in-process
  disabled: true
- id: tool-subagent
  disabled: true
- id: tool-subagent-fork
  disabled: true
- id: tool-subagent-control
  disabled: true
- id: tool-agent-team
  disabled: true
- id: workflow-ptc
  disabled: true
- id: tool-workflow
  disabled: true
- id: schedule
  disabled: true
- id: tool-schedule
  disabled: true
- id: tool-todo
  disabled: true
- id: present
  disabled: true
# 联网：法务检索必须走法穿自己的 web_search MCP 工具（可审计、可配内部代理、
# 可按律师权限限流）。dsh 自带的这四件会绕过全部这些约束。
- id: web
  disabled: true
- id: tool-web
  disabled: true
- id: web-search-deepseek
  disabled: true
- id: web-deepseek-api
  disabled: true
- id: web-fetch-http
  disabled: true
"""


def _provider_patch_path(dsh_home: str, *, base_url: str, models: list[str], thinking: bool = False) -> str:
    """把「本网关走 OpenAI 兼容协议」写成 patch 文件，返回路径。

    ## 为什么这件事必须落成 patch

    dsh 的模型路由由 ``llm-pi-ai`` 插件的 ``providers`` 配置决定，而 plate 里
    默认只有 ``deepseek-official``（DeepSeek 原生 Messages 协议）。律所网关是
    LiteLLM（OpenAI 兼容），必须显式声明 ``api: openai-completions``。

    ## 三个字段缺一不可（实测报错对照）

    - 缺 ``api`` → ``no adapter registered for provider "fachuan"``
    - 缺 ``models`` → ``provider "fachuan" resolves no models``
    - ``models`` 写成字典/字符串列表 → ``expected array`` / ``expected object``
      （正确形态是「对象数组」，每项至少 ``id``）

    ## 为什么内容要按网关动态生成

    ``baseURL`` 与可用模型都来自 ``LLMProvider``（Admin 里改），写死会让
    「换了网关但 dsh 还打旧地址」变成静默故障。所以每次启动按当前配置重写。
    """

    def _q(value: str) -> str:
        """YAML 双引号字符串转义（只处理会破坏结构的字符）。"""
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = [
        "# 由 apps.agent.backends.dsh_config 生成——不要手改",
        "# 作用：把律所 LLMProvider（OpenAI 兼容网关）声明成 dsh 的一个 provider",
        "- id: llm-pi-ai",
        "  config:",
        "    providers:",
        f"      {DEFAULT_PROVIDER}:",
        f"        api: {DEFAULT_API}",
        f"        baseURL: {_q(base_url)}",
        "        apiKeyEnv: DEEPSEEK_API_KEY",
        "        displayName: 律所网关",
        "        models:",
    ]
    for name in models:
        lines.append(f"          - id: {_q(name)}")
        lines.append(f"            name: {_q(name)}")
        # ── 思考模式（与 pi 的 models.json 同款兼容层）──────────────────────
        #
        # **为什么必须有这一段**（真实反馈：「dsh 没有开启思考强度」）：
        #
        # 律所网关是 LiteLLM，它把思考开关放在 ``chat_template_kwargs.thinking``
        # （布尔），而 dsh 的 openai-completions 适配器默认探测会误判 →
        # 不发思考参数 → 网关不返回 reasoning_content →
        # 表现为「模型支持思考、平台也开了，但 dsh 永远不思考」。
        #
        # pi 侧早就踩过并解决了（``model_config._model_entry`` 的 compat），
        # dsh 侧此前完全没写，所以同一个网关在两边行为不同。
        #
        # 三件事缺一不可：
        #   1. reasoningEfforts 声明「这个模型能用哪些思考档位」——不声明时
        #      dsh 认为它不支持推理，连 ``reasoning_effort`` 都不会下发。
        #   2. thinkingFormat=chat-template：走 chat_template_kwargs 通道。
        #   3. chatTemplateKwargs.thinking：告诉 dsh 往该通道写什么（布尔）。
        #      写法是字面量 ``true``，而不是 pi 的 ``$var: thinking.enabled``
        #      ——dsh 的模型条目里没有 pi 那套变量求值语义。
        if thinking:
            lines.append("            reasoningEfforts:")
            # off 必须列上：律师关掉思考时 dsh 要能真的关（否则只能整模型禁用）。
            #
            # 档位集合受**服务端白名单**约束，不是 pi/dsh 的七档全集。
            # 实测（2026-11-19）DeepSeek V4.1 走 vLLM 的原话：
            #   ``reasoning_effort must be low, high, xhigh, max, or an integer
            #   within [1, 100]``
            # 所以：
            # - ``medium`` **不能列**：发出去直接 400，选中即整轮对话失败；
            #   以前这里列了它，等于在 UI 上埋了一个必炸档位。
            # - ``minimal`` 不列：服务端会静默降成 low，不如直接不给。
            # - 补上 ``xhigh`` / ``max``：律师要的就是能调到最高。
            for effort in ("off", "low", "high", "xhigh", "max"):
                # key 必须加引号：YAML 1.1 把裸的 ``off`` / ``on`` / ``yes`` / ``no``
                # 解析成**布尔**，于是 ``off: "off"`` 会变成 ``False: 'off'``，
                # dsh 找不到名为 off 的档位 → 用户无法关闭思考，且不报错。
                lines.append(f"              {_q(effort)}: {_q(effort)}")
            lines.append("            compat:")
            lines.append("              thinkingFormat: chat-template")
            # True：网关实测接受 reasoning_effort（见 pi/model_config.py 同款注释）。
            # thinking 开关管「要不要想」，effort 管「想多深」，两者互补。
            lines.append("              supportsReasoningEffort: true")
            lines.append("              maxTokensField: max_tokens")
            lines.append("              chatTemplateKwargs:")
            lines.append("                thinking: true")
    path = Path(dsh_home) / "fachuan-provider.patch.yml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _lockdown_patch_path(dsh_home: str) -> str:
    """把安全收紧层写成一个稳定的 patch 文件，返回路径。

    为什么落盘而不是内联：``DeepSeekHarnessConfig.patches`` 收的是**文件路径**
    （它会被拼成 `--patch <path>` 命令行参数），没有「直接传 YAML 文本」的入口。

    写在 dsh home 下而不是临时目录：这个文件是每次启动都要用的稳定配置，
    不是一次性产物；放临时目录会被清掉后导致下一次启动失去收紧层——
    而这种失效是静默的（dsh 不会报「你没关 bash」）。

    内容固定，只在缺失时写一次，避免每次启动都改文件 mtime（dsh 可能对
    profile 层做变更检测）。
    """
    path = Path(dsh_home) / "fachuan-lockdown.patch.yml"
    if not path.is_file():
        path.write_text(_DSH_LOCKDOWN_PATCH, encoding="utf-8")
    return str(path)


def dsh_patches(
    dsh_home: str | None = None,
    *,
    base_url: str = "",
    models: list[str] | None = None,
    thinking: bool = False,
) -> tuple[str, ...]:
    """额外 profile 层（安全收紧 + MCP 接入）路径。

    顺序有意义：**收紧层在前**，用户/部署提供的 MCP patch 在后。dsh 按顺序
    叠加 patch 层，后写的同 id 条目覆盖先写的——所以把收紧层放前面，能保证
    不会因为某个 MCP patch 里顺手写了 `tool-bash: enabled` 而把红线打开。
    反过来则做不到（收紧层会盖掉用户真实需要的 MCP 配置，那会变成功能故障）。

    ``FACHUAN_DSH_PATCHES``：``os.pathsep`` 分隔（Linux/macOS 是 ``:``）。
    用环境变量而不是硬编码，因为 patch 文件里含 MCP 的 Authorization 头
    （真实用户 token），必须由部署侧生成到运行目录，不能进 git。

    格式：``os.pathsep`` 分隔（Linux/macOS 是 ``:``）。用环境变量而不是硬编码，
    因为 patch 文件里含 MCP 的 Authorization 头（真实用户 token），必须由部署侧
    生成到运行目录，不能进 git。

    不存在的路径直接剔除并 warning：dsh 拿到不存在的 patch 会启动失败，
    而「MCP 没接上」的报错会落在 ``initialize`` 超时上，排查方向完全被带偏。
    """
    paths: list[str] = []
    if dsh_home:
        # 1) 安全收紧（永远第一）
        with contextlib.suppress(OSError):
            paths.append(_lockdown_patch_path(dsh_home))
        # 2) 网关路由（有 base_url 才有意义）
        if base_url:
            with contextlib.suppress(OSError):
                paths.append(
                    _provider_patch_path(dsh_home, base_url=base_url, models=list(models or []), thinking=thinking)
                )

    raw = os.environ.get("FACHUAN_DSH_PATCHES", "").strip()
    if not raw:
        return tuple(paths)
    for part in raw.split(os.pathsep):
        candidate = part.strip()
        if not candidate:
            continue
        if not Path(candidate).is_file():
            logger.warning("dsh patch 文件不存在，已忽略: %s", candidate)
            continue
        paths.append(candidate)
    return tuple(paths)


def dsh_mcp_patch(dsh_home: str, *, user_token: str, session_id: str = "") -> str | None:
    """生成「法穿业务工具」那一层 patch，返回路径（无 token 时 ``None``）。

    单独一个函数而不是在 :func:`build_config` 里内联：本函数会**同步拉起共享
    MCP**（阻塞，冷启动可达数秒），把它圈成一个有名有姓的步骤，比藏在一个
    70 行的配置映射函数中间更容易在读日志时定位（``dsh MCP patch 已写入``）。

    ``dsh_mcp`` 用**模块内延迟 import**：它 import ``pi.shared_mcp``，而后者会
    连带拉起 ``mcp_server`` 包的路径假设。dsh 是可选后端，配置模块不该在
    「只是映射一个 provider」时就把工具面的依赖树拉进来。
    """
    from . import dsh_mcp

    return dsh_mcp.ensure_mcp_patch(dsh_home, user_token=user_token, session_id=session_id)


def _insert_before_env_patches(mcp_patch: str | None, patches: tuple[str, ...]) -> tuple[str, ...]:
    """把 MCP 层插在内置层之后、``FACHUAN_DSH_PATCHES`` 之前。

    为什么不能直接 ``append``：:func:`dsh_patches` 的返回值里「内置层」与
    「部署侧环境变量提供的层」是混在一起的，而 dsh 对同 id 条目是**后写胜出**。
    部署方要能用自己的 patch 覆盖 MCP（例如换 endpoint、加 ``toolCallTimeoutMs``），
    所以 MCP 必须排在环境变量那批**之前**。这里按「文件是否在环境变量清单里」
    重新切一刀，而不是让 :func:`dsh_patches` 返回结构体——那会把一个公开的、
    已被测试与调用方依赖的返回值形状改掉，为一段插入逻辑付不必要的代价。
    """
    if mcp_patch is None:
        return patches
    env_paths = {part.strip() for part in os.environ.get("FACHUAN_DSH_PATCHES", "").split(os.pathsep) if part.strip()}
    builtin = tuple(path for path in patches if path not in env_paths)
    deployment = tuple(path for path in patches if path in env_paths)
    return (*builtin, mcp_patch, *deployment)


def build_config(
    *,
    user_id: int | None,
    model_hint: str | None = None,
    provider: Any | None = None,
    user_token: str = "",
    session_id: str = "",
    api_key: str | None = None,
) -> DshProviderConfig | None:
    """把当前启用的 ``LLMProvider`` 映射成 dsh 配置；不可用时返回 ``None``。

    Args:
        user_id: 决定 dsh home 目录归属（见 :func:`dsh_home_for`）。
        model_hint: 本轮指定模型（``RunContext.model``）；为空则用 provider 的
            ``default_model``。指定但不在 provider 白名单里时仍然照用——用户的
            显式选择优先，provider 白名单只是「有哪些可选」，不是硬闸门。
        provider: 已查好的 ``LLMProvider``。**调用方在 async 上下文里必须自己用
            ``sync_to_async`` 查好再传**：本函数不会读库，否则在事件循环里调用
            会抛 ``SynchronousOnlyOperation``；传 ``None`` 时本函数会走同步查询
            （带 30s TTL 缓存，见 ``gateway_cache``），只适用于已在同步上下文
            （线程 / 后台任务）里的调用方。
        user_token: 律师本人的 access token（``RunContext.user_token``，**不是**
            provider key）。``user_id`` 只决定「谁的 home 目录」，拿不到这个请求
            的身份——所以业务工具的 MCP patch 只能由调用方把 token 传进来（见
            :func:`dsh_mcp_patch`）。空串表示本轮无身份，接不上业务工具。
        api_key: 本轮编排层指定的网关 key（``RunContext.api_key``）。有值时照用，
            **不再走** ``_next_key`` 轮转——网关限每把 key 的并发（实测 3），
            同轮多个 agent 必须拿不同的 key（见 ``key_scheduler``）。``None`` /
            空串保持原口径（每轮现算轮转），与引入本参数前逐字一致。

    Returns:
        可用的 dsh 配置；**没有任何可用 provider（或缺 base_url / api_key）时
        返回 ``None``**。调用方必须据此报友好错误——静默用 dsh 自己的默认
        provider 会让请求打到 ``deepseek-official`` 官方端点，用错的 key、
        记错的账，且用户完全看不出发生了什么。
    """
    # ``provider`` 传了就用它（同步上下文，已查好）；没传就走缓存路径：命中时
    # 完全不碰数据库（命中后省掉 sync_to_async 那条固定开销，实测首字延迟里
    # 约 1.3s 的量级）。TTL 与 ``LLMProvider`` 的 save/delete 信号失效见
    # ``gateway_cache`` 模块 docstring。
    settings = settings_from_provider(provider) if provider is not None else get_gateway_settings(model_hint)
    if settings is None:
        logger.warning("没有启用的 LLMProvider，dsh 无法启动")
        return None

    base_url = settings.base_url
    keys = list(settings.api_keys)
    if not base_url or not keys:
        logger.warning("LLMProvider 缺少 base_url 或 api_key，dsh 无法启动")
        return None

    models = list(settings.models)
    model = (model_hint or "").strip() or settings.default_model or (models[0] if models else "")
    if not model:
        logger.warning("LLMProvider 未配置任何模型，dsh 无法启动")
        return None

    home = dsh_home_for(user_id)
    # 模型列表必须包含本轮要用的 model，否则 dsh 报
    # 「provider resolves no models」——它只会从声明的 models 里挑。
    declared = list(models)
    if model not in declared:
        declared.insert(0, model)

    # 顺序：安全收紧 → 网关路由 → 业务工具（MCP）→ 部署侧额外 patch。
    # 收紧在前保证「不会被后面的 patch 重新打开 bash」；网关路由在中是因为它
    # 描述「本机怎么连模型」，比工具面更基础；MCP 层在部署侧之前，让部署方仍能
    # 用 ``FACHUAN_DSH_PATCHES`` 覆盖/补充 MCP 配置（后写的同 id 条目胜出）。
    # 思考模式：与 pi 同口径——**平台总开关 + 该模型确实是推理模型**两个条件都满足
    # 才声明。只按平台开关不看模型会给普通模型错报能力（网关直接 400，见 pi 侧
    # `_model_entry` 的同款注释）；只按模型不看开关则等于绕过律师/Amon 的配置。
    # 模型能力由 ``gateway_cache.model_supports_thinking`` 统一判：它先问
    # provider 的 ``supports_thinking``（同步上下文传了 provider 时），走缓存路径
    # 时用与 ``LLMProvider`` 同一份特征表——同一个模型在两条路径上不会判出两种结果。
    thinking_capable = bool(settings.enable_thinking and model_supports_thinking(model, provider))
    extra = dsh_patches(home, base_url=base_url, models=declared, thinking=thinking_capable)
    mcp_patch = dsh_mcp_patch(home, user_token=user_token, session_id=session_id)
    return DshProviderConfig(
        dsh_home=home,
        provider=DEFAULT_PROVIDER,
        model=model,
        base_url=base_url,
        # 编排层指定了本轮的 key 就用它；为空才回落到与会话间 key 轮转同源的口径
        # （pi 的 models.json 也走这个），避免所有 dsh 会话压在同一把 key 上触发限流。
        # **轮转每轮现算**：缓存里存的是全部 key，不是「这一轮选哪把」
        # （见 ``gateway_cache`` 的红线二）。
        api_key=(api_key or "").strip() or _next_key(keys),
        patches=_insert_before_env_patches(mcp_patch, extra),
    )
