"""文档工作面的工具面：审查、读清单、读/写已有修订、写批注、新建文件。

## 与 `folder_rewrite` / `write_patch` 的分工

| 工具 | 用途 |
|---|---|
| `rewrite_folder_file` | 律师框选一段、说「改成这样」——单段直改 |
| `propose_write_patch` / `apply_file_write_patches` | 多栏并答时先出草案，再由人裁决 |
| **`review_folder_file`** | 一次性按标准库审全篇，产出**挂在文件上**的清单 |
| **`list_document_findings`** | 读回清单（含上次审查的结论与状态） |
| **`list_document_revisions`** | 读文档里**已有的**修订，避免重复提同一件事 |
| **`apply_document_revisions`** | 把清单/整段改写一次落多条（全或无） |
| **`add_document_comments`** | 不改正文的意见（商业判断、缺失项、PDF） |
| **`create_folder_file`** | 在文件夹里新建一份 docx |

## 两条硬约束

1. **不带 task_id**：全部以「项目文件夹里的那一份文件」为坐标（`contract_id` 或
   `case_id` 二选一 + `subpath`）。旧的 `/contract-review/*` 端点随 app 一起消失。
2. **写工具必须能被审批层拦到**：它们的名字要出现在
   `apps/agent/services/approval/policy.py` 的 `MULTI_LANE_WRITE_TOOLS` 里，
   否则多栏并答时会互相覆盖。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client


def _owner(contract_id: int | None, case_id: int | None) -> tuple[str, int]:
    """`contract_id` / `case_id` 二选一 → `(kind, owner_id)`。

    都不给没法定位文件；都给说明引用块读串了——猜一个就是写错文件。
    """
    if (contract_id is None) == (case_id is None):
        raise ValueError("contract_id 与 case_id 必须二选一（来自 [已引用文件：…] 引用里的 id 键）")
    if case_id is not None:
        if isinstance(case_id, bool) or case_id <= 0:
            raise ValueError(f"case_id 应为正整数，收到：{case_id!r}")
        return "case", int(case_id)
    assert contract_id is not None
    if isinstance(contract_id, bool) or contract_id <= 0:
        raise ValueError(f"contract_id 应为正整数，收到：{contract_id!r}")
    return "contract", int(contract_id)


def review_folder_file(
    subpath: Annotated[str, Field(description="绑定根下的相对路径(posix)，如 1-律师资料/1-合同/专项合同.docx")],
    contract_id: Annotated[int | None, Field(description="合同 ID（文件在合同绑定文件夹）", ge=1)] = None,
    case_id: Annotated[int | None, Field(description="案件 ID（文件在案件绑定文件夹）", ge=1)] = None,
    stance: Annotated[
        str, Field(description="我方立场：party_a（代表甲方）/ party_b（代表乙方）/ neutral（中立复核）")
    ] = "neutral",
    contract_type: Annotated[str, Field(description="合同类型（买卖/租赁/服务/劳动…）；留空用通用标准")] = "",
) -> dict[str, Any]:
    """按标准条款库审查一份合同，结论**挂在原文件上**（不产生第二份 docx）。

    审查在后台跑，本工具立刻返回 `run_id`。几秒后用 `list_document_findings`
    取清单；律师在右栏逐条采纳/驳回。

    Args:
        subpath: 文件在绑定文件夹里的相对路径。
        contract_id / case_id: 二选一。
        stance: 立场。同一份合同代表甲/乙方，结论方向相反，**必须问清楚**。
        contract_type: 决定用哪套标准库。

    Returns:
        `{"run_id": 12, "status": "queued"}`；跑完用 `list_document_findings` 取结果。
    """
    kind, owner_id = _owner(contract_id, case_id)
    result: dict[str, Any] = client.post(
        "/doc-workspace/review/runs",
        json={"kind": kind, "owner_id": owner_id, "subpath": subpath.strip(), "stance": stance, "contract_type": contract_type},
    )
    return result


def list_document_findings(
    contract_id: Annotated[int | None, Field(description="合同 ID", ge=1)] = None,
    case_id: Annotated[int | None, Field(description="案件 ID", ge=1)] = None,
    subpath: Annotated[str, Field(description="相对路径；与 run_id 二选一")] = "",
    run_id: Annotated[int | None, Field(description="指定轮次；不给则取该文件最近一轮", ge=1)] = None,
) -> dict[str, Any]:
    """读审查清单（含每条的状态、严重度、载体与建议）。

    律师的决策也会体现在 `status` 里：`proposed` 待决 / `accepted` 已采纳 /
    `rejected` 已驳回（带理由码）/ `stale` 锚点失效 / `moot` 已被消解。
    """
    if run_id is not None:
        by_run: dict[str, Any] = client.get(f"/doc-workspace/review/runs/{run_id}")
        return by_run
    kind, owner_id = _owner(contract_id, case_id)
    if not (subpath or "").strip():
        raise ValueError("subpath 不能为空（或改用 run_id）")
    result: dict[str, Any] = client.get(
        "/doc-workspace/review/runs/latest",
        params={"kind": kind, "owner_id": owner_id, "subpath": subpath.strip()},
    )
    return result


def list_document_revisions(
    subpath: Annotated[str, Field(description="绑定根下的相对路径(posix)")],
    contract_id: Annotated[int | None, Field(description="合同 ID", ge=1)] = None,
    case_id: Annotated[int | None, Field(description="案件 ID", ge=1)] = None,
) -> dict[str, Any]:
    """列出文档里**已有的**修订痕迹（谁改的、删了什么、插了什么）。

    改之前先看它：否则容易把已经改过的句子再提一次，或者把已被接受的修改
    当成现行文本去改。
    """
    kind, owner_id = _owner(contract_id, case_id)
    result: dict[str, Any] = client.get(
        "/doc-workspace/revisions", params={"kind": kind, "owner_id": owner_id, "subpath": subpath.strip()}
    )
    return result


def apply_document_revisions(
    subpath: Annotated[str, Field(description="绑定根下的相对路径(posix)")],
    patches: Annotated[
        list[dict[str, str]],
        Field(description='要落的修订列表：[{"selection": 原文, "suggested": 改写}]，**全或无**'),
    ],
    contract_id: Annotated[int | None, Field(description="合同 ID", ge=1)] = None,
    case_id: Annotated[int | None, Field(description="案件 ID", ge=1)] = None,
    base_mtime: Annotated[float | None, Field(description="打开文件时的 mtime（建议传，做乐观锁）")] = None,
) -> dict[str, Any]:
    """一次落多条修订，**全或无**：任何一条定位不到就一个字都不写。

    半改过的文件既不是原稿也不是审完稿，律师无法判断哪几条生效了。
    返回 `applied=false` + `failed_index` 时，把那一条的 `selection` 加长到唯一再重试。
    """
    kind, owner_id = _owner(contract_id, case_id)
    result: dict[str, Any] = client.post(
        "/doc-workspace/apply-batch",
        json={
            "kind": kind,
            "owner_id": owner_id,
            "subpath": subpath.strip(),
            "patches": patches,
            "base_mtime": base_mtime,
        },
    )
    return result


def add_document_comments(
    subpath: Annotated[str, Field(description="绑定根下的相对路径(posix)")],
    comments: Annotated[
        list[dict[str, str]],
        Field(description='批注列表：[{"selection": 对应的原文, "text": 批注内容}]'),
    ],
    contract_id: Annotated[int | None, Field(description="合同 ID", ge=1)] = None,
    case_id: Annotated[int | None, Field(description="案件 ID", ge=1)] = None,
    base_mtime: Annotated[float | None, Field(description="打开文件时的 mtime（建议传）")] = None,
) -> dict[str, Any]:
    """给若干段挂 Word 原生批注（**不改正文**）。

    什么时候用它而不是修订：只有风险提示、需要律师做商业判断的（「违约金无上限，
    是否接受取决于谈判地位」），或根本锚不到具体文字的缺失项。硬给一个「改法」
    等于替律师做商业决定。
    """
    kind, owner_id = _owner(contract_id, case_id)
    result: dict[str, Any] = client.post(
        "/doc-workspace/comments",
        json={
            "kind": kind,
            "owner_id": owner_id,
            "subpath": subpath.strip(),
            "comments": comments,
            "base_mtime": base_mtime,
        },
    )
    return result


def create_folder_file(
    name: Annotated[str, Field(description="文件名；不以 .docx 结尾会自动补上")],
    contract_id: Annotated[int | None, Field(description="合同 ID", ge=1)] = None,
    case_id: Annotated[int | None, Field(description="案件 ID", ge=1)] = None,
    subpath_dir: Annotated[str, Field(description="目标目录（绑定根下的相对路径）；留空 = 根目录")] = "",
    paragraphs: Annotated[list[str] | None, Field(description="正文段落（按顺序成段）")] = None,
    markdown: Annotated[str, Field(description="或给 markdown：# 开头成标题，空行分段")] = "",
) -> dict[str, Any]:
    """在项目文件夹里新建一份 docx。

    **同名不覆盖**：已存在同名文件时会自动加序号。返回的 `file_url` 可以直接
    交给画布打开（前端据此跳进编辑）。

    Returns:
        `{"created": true, "name": "…", "subpath": "…", "file_url": "…"}`。
    """
    kind, owner_id = _owner(contract_id, case_id)
    result: dict[str, Any] = client.post(
        "/doc-workspace/files",
        json={
            "kind": kind,
            "owner_id": owner_id,
            "subpath_dir": subpath_dir.strip(),
            "name": name.strip(),
            "paragraphs": paragraphs or [],
            "markdown": markdown,
        },
    )
    return result


__all__ = [
    "add_document_comments",
    "apply_document_revisions",
    "create_folder_file",
    "list_document_findings",
    "list_document_revisions",
    "review_folder_file",
]
