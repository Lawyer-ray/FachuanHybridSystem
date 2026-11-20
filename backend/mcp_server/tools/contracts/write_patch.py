"""多栏并答的**候选改写**（patch 草案区）——提出与单点应用。

## 为什么多栏时不能再直接改文件

三栏同时回答同一个问题时，每一栏手里的 `original` 都是"我读到的那一刻的原文"。
谁先落盘，后落盘的 `original` 就失效了：它要么失败（看起来像模型笨），要么在
别处撞上同一串字、改错位置。三套 `<w:ins>/<w:del>` 叠在同一段上，Word 的审阅
面板里就是一团乱麻，律师没法逐条接受/拒绝。

所以多栏模式下写类工具（`rewrite_folder_file` 等）被**从工具面摘掉**，改由本
工具出草案：`propose_write_patch` 只登记"把这段换成那段"，不碰文件；律师裁决后
再调 `apply_file_write_patches` 一次性落盘（服务端还会做冲突检测与 mtime 二次
校验）。单栏对话不受影响，仍然是 `rewrite_folder_file` 直接出修订痕迹。

## 审批

`apply_file_write_patches` 的名字命中审批高危前缀（`file_`），网关侧必然弹审批
卡——这是**有意的**：它是真正写文件的那一步。`propose_write_patch` 只写库里的
草案行、不碰文档字节，因此按只读工具处理（客户端会显示只读徽标）。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client
from mcp_server.identity import current_session_id


def propose_write_patch(
    subpath: Annotated[
        str, Field(description="绑定根下的相对路径(posix),如 1-合同/专项合同.docx;来自 [已引用文件：…] 引用")
    ],
    original: Annotated[
        str, Field(description="要替换的**原文片段**,必须与文档中逐字一致(从 read_folder_file 的正文里复制)")
    ],
    replacement: Annotated[str, Field(description="改写后的完整替换文本。保留法律文书语体;只给这一段正文,不要带解释")],
    contract_id: Annotated[
        int | None, Field(description="合同 ID(文件在合同绑定文件夹);与 case_id 二选一", ge=1)
    ] = None,
    case_id: Annotated[
        int | None, Field(description="案件 ID(文件在案件绑定文件夹);与 contract_id 二选一", ge=1)
    ] = None,
) -> dict[str, Any]:
    """把「原文 → 改写」登记为一条**候选改写（草案）**，不改动文件。

    多栏对比回答时用它代替直接改写：每一栏各提一条草案，律师看过差异后再决定
    采纳哪一条（或合并）。草案只是库里的记录，文件字节没有任何变化。

    Args:
        subpath: 绑定根下的相对路径（posix），来自消息里的 `[已引用文件：…]`。
        original: 要替换的原文片段，必须逐字一致（含标点）；跨段落的原文会失败，
            请缩小到段内。
        replacement: 改写后的完整文本；只给这一段正文，别夹带「改写如下」之类说明。
        contract_id: 合同 ID（文件在合同绑定文件夹）。
        case_id: 案件 ID（文件在案件绑定文件夹）。与 contract_id 二选一。

    Returns:
        `{"patch_id": "...", "status": "proposed", "subpath": ..., "base_mtime": ...}`。
        后续把这些 `patch_id` 交给 `apply_file_write_patches`（律师裁决后）。

    Raises:
        ValueError: contract_id / case_id 未给、都给或非正整数，或原文/改写为空。
    """
    if (contract_id is None) == (case_id is None):
        raise ValueError("contract_id 与 case_id 必须二选一（来自 [已引用文件：…] 引用里的 id 键）")
    if not (subpath or "").strip():
        raise ValueError("subpath 不能为空（来自消息里的文件夹引用）")
    if not (original or "").strip():
        raise ValueError("original 不能为空：它是定位锚点，必须与文档原文逐字一致")
    if not (replacement or "").strip():
        raise ValueError("replacement 不能为空")

    result: dict[str, Any] = client.post(
        "/contract-review/direct-edit/patch/propose",
        json={
            "subpath": subpath.strip(),
            "original": original,
            "replacement": replacement,
            # 会话标识由共享 MCP 从 X-Fachuan-Session 头带进来（pi 已注入）；
            # run_id / agent_kind 在 B1 阶段拿不到，留空由服务端兜底
            "session_id": current_session_id(),
            **({"contract_id": contract_id} if contract_id is not None else {"case_id": case_id}),
        },
    )
    return result


def apply_file_write_patches(
    patch_ids: Annotated[
        list[str], Field(description="要应用的 patch_id 列表（律师裁决后的选择，必须同属一份文件）")
    ],
    note: Annotated[str, Field(description="应用备注（留痕，如「采纳 A 的付款期限改法」）", max_length=200)] = "",
) -> dict[str, Any]:
    """把选中的候选改写**一次性**写进文档（以 Word 修订痕迹留痕）。

    律师裁决之后才调用。服务端会先做冲突检测（同一段原文两种改法 → 拒绝），再
    二次校验文件 mtime（提案后文件被改过 → 拒绝，避免把别人的修改盖掉），最后
    只写一次盘——三条都过了才会真正改动文件。

    Args:
        patch_ids: 要应用的 patch_id（来自 `propose_write_patch` 的返回）。
        note: 一句话留痕，说明这次应用的依据。

    Returns:
        `{"applied": [...], "merged": [...], "subpath": ..., "name": ...}`：
        `applied` 是真正写进文档的 patch，`merged` 是内容重复、已合并进前者的提案。

    Raises:
        ValueError: patch_ids 为空。
    """
    clean_ids = [str(pid).strip() for pid in patch_ids if str(pid).strip()]
    if not clean_ids:
        raise ValueError("patch_ids 不能为空：先调用 propose_write_patch 产出候选改写")
    result: dict[str, Any] = client.post(
        "/contract-review/direct-edit/patch/apply",
        json={"patch_ids": clean_ids, "note": note},
    )
    return result


__all__ = ["apply_file_write_patches", "propose_write_patch"]
