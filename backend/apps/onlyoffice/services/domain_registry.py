"""OnlyOffice 业务域注册表：一份文档属于哪个业务、怎么取、谁能看。

**为什么要这层**：`EditorSession.task_type` 早就预留了「未来接入其它业务域」，
但实现里三处写死了 `"contract_review"`——保存回写、取文件代理、内容版本。
于是起诉状 / 答辩状 / 和解协议这些同属「AI 出一批修订、律师逐条决策」的文书
没法复用复审台：加一个业务域要改三个分散的位置，且每处都要重复一遍权限口径。

注册表把「业务域 = 一组钩子」固化下来：

```
OODomain(
    key="contract_review",                  # 与 EditorSession.task_type 对应
    path_pattern=r"/api/v1/contract-review/(uuid)/(download|download-original)",
    get_owner_id=lambda task: task.user_id,
    resolve_file=lambda svc, task_id, which: svc.get_result_file(...) / svc.get_original_file(...),
    adopt_edited=lambda task_id, data, version_tag: svc.adopt_edited_output(...),
)
```

新增业务域（例如起诉状）只要在 `_registry` 里加一条，三处调用点自动支持，
权限判定也统一走 `is_owner_or_admin`。

**没有做过度抽象**：钩子只覆盖实际用到的四件事，不做通用「文档适配器」——
`Revision` 怎么定位、怎么写入是各业务自己的事，不塞进注册表。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# 下载路径里的两种取法
WHICH_RESULT = "download"
WHICH_ORIGINAL = "download-original"


@dataclass(frozen=True)
class OODomain:
    """一个业务域的 OnlyOffice 接入钩子。"""

    key: str
    """与 EditorSession.task_type 对应的业务标识。"""

    path_pattern: str
    """DS 取文件代理放行的路径正则；第 1 组是 task_id，第 2 组是 download / download-original。"""

    get_owner_id: Callable[[Any], Any]
    """任务对象 → 属主 user id（权限判定用）。"""

    resolve_file: Callable[[Any, Any, str], Any]
    """(service, owner_id, which) → 产物文件 Path。"""

    adopt_edited: Callable[..., Any]
    """(session, data, version_tag) → 落库目标。

    统一收 session 而不是 owner_id：folder 域要从 `session.source_path`
    反解 subpath，只给 id 不够；review 域从 `session.task_id` 取即可。"""

    cast_id: Callable[[str], Any] = UUID
    """路径里第 1 组 → 业务主键。默认转 UUID（contract_review 是 UUID 主键）；
    contract / case 这类自增 int 主键需显式传 int。"""

    resolve_for_proxy: Callable[[Any, Any, str], Any] | None = None
    """更灵活的取文件钩子：(user, owner_id, rest) → Path。

    传了它就不走 `resolve_file` + `get_review_service`——有些业务域（如
    contract_folder）根本不是 review task，拿不到 review service，且需要
    从 query string 拼出 subpath。返回 None 表示无权/不存在。
    """

    def parse_path(self, path: str) -> tuple[Any, str] | None:
        m = re.match(self.path_pattern, path)
        if not m:
            return None
        return self.cast_id(m.group(1)), (m.group(2) or "")


def _adopt_review(task_id: Any, data: bytes, version_tag: int) -> str:
    """审查产物落盘：交给 contract_review 的 service（它自己管版本命名与留档）。"""
    from apps.contract_review.services.wiring import get_review_service

    return get_review_service().adopt_edited_output(task_id, data, version_tag=version_tag)


def _contract_review_domain() -> OODomain:
    return OODomain(
        key="contract_review",
        # 分支顺序不能反：正则从左到右匹配，`download` 在前会把
        # `download-original` 截成 `download`（取错文件：拿到修订版而不是原稿）。
        # 不能用 `$` 锚定：真实下载路径带 `?fn=合同.docx` 查询串，
        # 锚定后整条路径都不匹配，代理会 404。
        path_pattern=r"^/api/v1/contract-review/([0-9a-f-]{36})/(download-original|download)(?:\?|$)",
        get_owner_id=lambda task: getattr(task, "user_id", None),
        resolve_file=lambda svc, task_id, which: (
            svc.get_result_file(task_id) if which == WHICH_RESULT else svc.get_original_file(task_id)
        ),
        adopt_edited=lambda session, data, version_tag: _adopt_review(session.task_id, data, version_tag),
    )


def _contract_folder_domain() -> OODomain:
    """合同绑定文件夹里的单个文件（客户来件、发票、监督卡…）。

    **为什么要它**：以前文件夹里的 docx 只能下载——浏览器没有 docx 渲染器，
    `window.open` 结果必然落到本地磁盘。要让律师直接看到内容（甚至就地改、
    跟 AI 对话），就得让 DS 能拉这个文件，而 DS 容器带不上 Authorization，
    只能走 `/onlyoffice/file?src=&sig=` 代理。代理只放行注册表里的路径。

    **保存回写**：决定「原地改、原地存」后，DS 的 status=2/6 回调必须真的
    写回磁盘。会话里记了 `source_path`（即 `/api/v1/contracts/{id}/folder-file
    ?subpath=...`），从这里解出 subpath 再覆写——不回写就等于编辑器假保存。
    """

    def _resolve(_svc: Any, owner_id: Any, which: str) -> Any:
        # which 就是 subpath 原文（URL 里已 urlencode，Django 已解码）
        raise RuntimeError(f"contract_folder 取文件必须走 subpath：{which}")

    def _adopt_edited(session: Any, data: bytes, version_tag: int) -> Any:
        """DS 保存回写：把编辑产物覆写回原文件（原地保存，不留备份）。

        从 `session.source_path` 反解 contract_id + subpath，而不是另外存字段：
        落盘目标必须与「当初打开的是哪一份」严格一致，多存一份副本就可能
        指向别处。解析失败就报错让 DS 重试，绝不猜。
        """
        from urllib.parse import unquote

        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        parsed = domain_for_path(session.source_path or "")
        if parsed is None or parsed[0].key != "contract_folder":
            raise RuntimeError(f"无法从会话反解文件夹路径: {session.source_path}")
        contract_id = parsed[1]
        subpath = unquote(parsed[2])

        owner = getattr(session, "user", None)
        ContractFolderBrowseService().save_file_content(
            owner_id=contract_id,
            subpath=subpath,
            data=data,
            # 回写不校验 mtime：这次保存就是当前会话产生的，校验只会
            # 在「编辑器开着时文件被外部改动」这种少见场景下误报
            expect_mtime=None,
            user=owner,
            org_access=getattr(owner, "org_access", None),
            perm_open_access=False,
        )
        logger.info("文件夹文件已回写: contract=%s subpath=%s v%d", contract_id, subpath, version_tag)
        return f"{contract_id}:{subpath}"

    def _resolve_proxy(user: Any, contract_id: int, subpath: str) -> Any:
        """按签名用户身份解析文件夹里的文件（权限口径与 REST 端点一致）。

        不自己判 ACL：直接调 folder_browse_service.resolve_file，它内部走
        ContractAccessPolicy——代理绝不能比 REST 端点宽松。

        **subpath 要手动解码**：它经过了两层 URL 编码——前端
        `folderFileUrl` 先 encodeURIComponent 一次，`/onlyoffice/file` 的
        `src` 参数又包了一层。DS 只解开外层，所以后端拿到的仍是
        `%E5%90%88...` 这种字面百分号串，直接拿去拼路径必然 404
        （表现为编辑器报「文档打开失败」）。这里解一次还原成真实文件名。
        """
        from urllib.parse import unquote

        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        real_subpath = unquote(subpath)
        try:
            return ContractFolderBrowseService().resolve_file(
                owner_id=contract_id,
                user=user,
                org_access=getattr(user, "org_access", None),
                perm_open_access=False,
                subpath=real_subpath,
            )
        except Exception:
            logger.warning(
                "OnlyOffice 代理取文件夹文件失败: contract=%s subpath=%s", contract_id, subpath, exc_info=True
            )
            return None

    return OODomain(
        key="contract_folder",
        # 第 2 组捕获 subpath 原文（Django 已在解析 query 时解码一次）
        path_pattern=r"^/api/v1/contracts/(\d+)/folder-file\?(?:.*?&)?subpath=([^&]*)",
        cast_id=int,
        get_owner_id=lambda contract: getattr(contract, "owner_id", None),
        resolve_file=_resolve,
        adopt_edited=_adopt_edited,
        resolve_for_proxy=_resolve_proxy,
    )


_registry: dict[str, OODomain] = {}


def register_domain(domain: OODomain) -> None:
    _registry[domain.key] = domain


def get_domain(key: str) -> OODomain | None:
    return _registry.get(key)


def all_domains() -> list[OODomain]:
    return list(_registry.values())


def domain_for_path(path: str) -> tuple[OODomain, Any, str] | None:
    """按站内路径反查业务域。"""
    for domain in _registry.values():
        parsed = domain.parse_path(path)
        if parsed is not None:
            return domain, parsed[0], parsed[1]
    return None


def is_owner_or_admin(user: Any, owner_id: Any) -> bool:
    """统一的文档权限口径：属主或超管。各业务不再各写一遍。"""
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return owner_id is not None and owner_id == getattr(user, "pk", None)


def _bootstrap() -> None:
    """内置业务域。新业务域在这里注册（或在自己的 apps.ready 里 register_domain）。"""
    register_domain(_contract_review_domain())
    register_domain(_contract_folder_domain())


_bootstrap()
