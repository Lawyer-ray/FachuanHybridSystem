"""回传件核对 MCP tools —— 「客户回传的那一份有没有被改」。

后端端点在 `/api/v1/doc-verify`（`apps/doc_verify/api/`），三个工具覆盖一条完整链路：

1. `list_unverified_returns`：先查「有没有还没裁决的回传件」（按案 / 跨案待办）；
2. `get_returned_document_check`：看某次核对的结论（发现项 + 覆盖度）；
3. `verify_returned_document`：客户刚回传、库里还没有记录时，主动提交一份跑核对。

裁决（accept/reject）刻意不在这里：那是律师的留痕动作，走网页/既有端点，
不给模型一个「自己批准自己」的入口。
"""

from __future__ import annotations

from typing import Any

from mcp_server.client import client
from mcp_server.tool_shaping import list_result


def list_unverified_returns(case_id: int | None = None, limit: int = 50) -> dict[str, Any]:
    """查「客户回传件还没核对完」的清单——客户把回签/修改后的材料发回来之后、立案或归档之前先调这个。

    问「这案有没有还没核对的回传件」传 ``case_id``；问「今天有什么回传件要处理」
    （不知道案号 / 想跨案看）不传，拿全局待办。两种口径都只含「要求核对 + 状态
    待裁决 + 还没有 accept/reject 记录」的运行，已裁决的不会重复出现。

    Args:
        case_id: 案件 ID。有它就只看该案（该案一条都没有时返回空 items，不代表没做过核对）。
        limit: 最多返回条数，默认 50；只用于不传 ``case_id`` 的全局待办口径。
    """
    if case_id is not None:
        return list_result(client.get("/doc-verify/unverified", params={"case_id": case_id}))
    return list_result(client.get("/doc-verify/pending", params={"limit": limit}), limit=limit)


def get_returned_document_check(run_id: int) -> dict[str, Any]:
    """看一次回传件核对的完整结论：状态（state / state_label）、发现项 findings、覆盖度 coverage。

    典型用法：`list_unverified_returns` 里拿到某条的 ``id`` 后调本工具，再向律师
    解释「差在哪一处、第几页、expected/actual 各是什么」。只读，不改状态、不裁决。

    Args:
        run_id: 核对运行 ID（清单里每条的 ``id``），不是出站基线 ID、也不是案件材料 ID。
    """
    return client.get(f"/doc-verify/runs/{run_id}")  # type: ignore[no-any-return]


def verify_returned_document(
    artifact_id: int,
    file_base64: str,
    file_name: str = "",
    tier: int | None = None,
) -> dict[str, Any]:
    """提交一份客户回传件跑核对（写操作：会落一条核对运行并返回它的结论）。

    什么时候调：客户把盖章/改过的文件发回来后，律师问「这份有没有被改动」，
    而 `list_unverified_returns` 里查不到对应记录时（这类回传件还没进过核对）。
    同一基线 + 同字节重复提交是幂等的，返回同一行，不会刷出一堆重复运行。

    ``file_base64`` 只放客户回传的那一份；**不要先把整本大 PDF（几十上百页）
    base64 再塞进来**——工具输出/入参都在会话上下文里，量级一大就是截断与超时。
    回传件通常只是一两页的回签页：优先读小件、单份、只含签字页的那个文件；
    整本大文件请让律师直接在前端上传核对。

    Args:
        artifact_id: 出站基线 ID——我们**发出去那一份**冻结下来的 id（`GET /doc-verify/artifacts?case_id=` 的 items），不是回传件自己的材料 ID。
        file_base64: 回传件字节的 base64（带 ``data:`` 前缀的 dataURL 也收）。
        file_name: 回传件文件名（带扩展名，用于日志与展示），可不传。
        tier: 核对层级。不传 = 自动（要求核对且是扫描件时升到 OCR 层）；显式传 0 = 只要免费层（字面比对）。
    """
    payload: dict[str, Any] = {"artifact_id": artifact_id, "file_base64": file_base64}
    if file_name:
        payload["file_name"] = file_name
    if tier is not None:
        payload["tier"] = tier
    return client.post("/doc-verify/runs", json=payload)  # type: ignore[no-any-return]


__all__ = [
    "list_unverified_returns",
    "get_returned_document_check",
    "verify_returned_document",
]
