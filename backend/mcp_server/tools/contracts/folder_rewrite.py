"""合同/案件绑定文件夹的**改写落盘** —— 让 AI 能把改好的文字写回原文件。

## 为什么必须有这个工具

在此之前，MCP 工具面里只有 `read_folder_file`（读），没有任何写入通道：
律师框选一段、说「改成这样」，模型只能把改写结果**贴在聊天里**，他必须自己
复制回 Word。这正是「AI 助手没有修改成功」的直接原因——不是模型不会改，
而是它没有落笔的手。

## 与审查流水线的分工

- `contract_review` 的流水线：一次性审全篇，产物是**另一份** docx（不改原稿）；
- 本工具：改**指定的这一段**，直接写回**原文件**，以 Word 修订痕迹留痕。

两者都要留痕，但落点不同：审查要保住客户原稿，划词直改就是要改那份合同本身。

## 为什么以 `original` 定位而不是给段落序号

段落序号会因任何一次改动而漂移（前文增删一句，后面全错位）。模型看得见原文，
用原文定位才稳——和 `DocxRevisionTool` 的 `Search → apply_revision` 是同一套口径。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client


def rewrite_folder_file(
    subpath: Annotated[
        str, Field(description="绑定根下的相对路径(posix),如 1-律师资料/1-合同/专项合同.docx;来自 [已引用文件：…] 引用")
    ],
    original: Annotated[
        str, Field(description="要替换的**原文片段**,必须与文档中逐字一致(可从 read_folder_file 取到的正文里复制)")
    ],
    replacement: Annotated[str, Field(description="改写后的完整替换文本。保留法律文书语体;只给这一段正文,不要带解释")],
    contract_id: Annotated[
        int | None, Field(description="合同 ID(合同绑定文件夹);来自 [已引用文件：…] 引用里的 contract_id", ge=1)
    ] = None,
    case_id: Annotated[
        int | None,
        Field(
            description="案件 ID;**暂不支持**——落盘端点当前只认合同绑定文件夹,传了会直接报错,保留参数位是为了案件域接入",
            ge=1,
        ),
    ] = None,
) -> dict[str, Any]:
    """把文档里的一段原文替换为改写文本，**以 Word 修订痕迹写回原文件**。

    律师在编辑器里框选一段、提出修改要求后，用它落笔。替换以 `<w:del>`/`<w:ins>`
    修订痕迹写入，律师在 Word/WPS 的「审阅」里可逐条接受或拒绝——不会被静默改成
    定稿文本。

    Args:
        subpath: 绑定根下的相对路径（posix），来自消息里的 `[已引用文件：…]`。
        original: 要替换的原文片段，必须逐字一致（含标点）。跨段落的原文会失败，
            请缩小到段内。
        replacement: 改写后的完整文本。只给这一段正文，不要夹带「改写如下」之类的说明。
        contract_id: 合同 ID（合同绑定文件夹）。
        case_id: 案件绑定文件夹**暂不支持**划词直改，传了会直接报错。

    Returns:
        `{"applied": true, "contract_id": ..., "subpath": ..., "name": ...}` 表示已写入
        （前端据此刷新打开中的编辑器画布）；
        `{"applied": false, "reason": "..."}` 表示定位失败（原文已变/跨段），
        此时**文件未被修改**，可按 reason 提示律师重新框选。

    Raises:
        ValueError: contract_id 未给或非正整数、传了 case_id（暂不支持），或
            original/replacement 为空。
    """
    # 案件域必须显式拒绝：落盘端点只认 contract_id，若把 case_id 当
    # contract_id 发出去，会写进**同编号的另一份合同**——错绑定的静默写坏
    if case_id is not None:
        raise ValueError("划词直改暂不支持案件绑定文件夹（case_id），只支持合同（contract_id）")
    if contract_id is None:
        raise ValueError("必须提供 contract_id（来自消息里的 [已引用文件：…] 引用）")
    if isinstance(contract_id, bool) or not isinstance(contract_id, int) or contract_id <= 0:
        raise ValueError(f"contract_id 应为正整数（来自消息里的文件夹引用），收到：{contract_id!r}")
    if not (subpath or "").strip():
        raise ValueError("subpath 不能为空（来自消息里的文件夹引用）")
    if not (original or "").strip():
        raise ValueError("original 不能为空：它是定位锚点，必须与文档原文逐字一致")
    if not (replacement or "").strip():
        raise ValueError("replacement 不能为空")

    # 落盘由后端做（复用 DocxRevisionTool + 合同行级 ACL）。MCP 进程不该自己
    # 解析文件夹路径、也不该自己拼 docx——单一写入口。
    result: dict[str, Any] = client.post(
        "/contract-review/direct-edit/apply",
        json={
            "contract_id": contract_id,
            "subpath": subpath.strip(),
            "selection": original,
            "suggested": replacement,
        },
    )
    return result


__all__ = ["rewrite_folder_file"]
