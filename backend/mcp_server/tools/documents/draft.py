"""一句话起草：律师报一个文书类型，系统出成品并放进项目文件夹的对应位置。

## 为什么需要这个工具

模型此前「说不上这句话」：起草、渲染、落位、落盘、挂未决项批注这几件事全都已经在后端
拆好了，但工具面里没有入口，模型只能去拼 `create_folder_file` +
`add_document_comments` 这类零件，拼出来的路径和格式必然是猜的。

## 三条写进工具描述的边界

1. **不会自由排版**：格式来自 `DocumentSpec.skeleton_template`（律所已验证的模板），
   模型只能决定槽里的文字；
2. **会落盘**：成稿直接写进案件/合同的绑定文件夹，同名不覆盖（自动加序号）；
3. **会挂未决项批注**：没素材又没推出来的槽写成 `<待填写：x>` 并挂 Word 批注，
   律师打开就知道「这里为什么空着」。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from mcp_server.client import client


def draft_document(
    doc_type: Annotated[
        str,
        Field(
            description=(
                "文书类型，律师嘴里的那个词，如 管辖权异议申请书 / 起诉状 / 答辩状。"
                "必须是文书规格（DocumentSpec）里已配好的那一行；传一个库里没有的类型会返回 created=false"
            )
        ),
    ],
    case_id: Annotated[
        int | None, Field(description="案件 ID（与 contract_id 二选一），决定落到哪个案件文件夹", ge=1)
    ] = None,
    contract_id: Annotated[
        int | None, Field(description="合同 ID（与 case_id 二选一），决定落到哪个合同文件夹", ge=1)
    ] = None,
    facts: Annotated[
        dict[str, str] | None,
        Field(
            description=(
                "律师显式给出的事实，优先级最高（金额/日期/当事人这类绝不交模型猜）。"
                "键是骨架里的占位符名，值是最终要写进文书的文字"
            )
        ),
    ] = None,
    instruction: Annotated[str, Field(description="律师那句话里除文书类型外的补充要求（可选）")] = "",
    comment_author: Annotated[
        str,
        Field(
            description=(
                "未决项批注的署名（Word/OnlyOffice 审阅面板里显示的\"人\"）。"
                "缺省 Lawyer；按这一份文书的要求填，不要写死"
            )
        ),
    ] = "",
) -> dict[str, Any]:
    """按文书类型起草一份文书，**直接落进项目文件夹的指定位置**。

    律师说「出一份管辖权异议」时用这个工具，一次调用完成：
    找骨架 → 填槽 → 渲染 → 找位置 → 落盘 → （可选）自动排一轮初审。

    **不会自由排版**：格式来自已配好的骨架模板，模型只能返回值、不能改结构。
    **会落盘**：成稿写进案件/合同的绑定文件夹，同名不覆盖（自动加序号）。
    **缺素材的槽会写 `<待填写：x>` 并挂 Word 批注**，返回的 `pending` 里就是这些项——
    把 `pending` 转告律师去补，不要自己编一个金额或日期填上。

    返回 `created=false` 时先看 `reason`：多半是「这个文书还没有骨架」或「这个案件的文件夹里
    没有它的位置」。这两种情况都**不要自己造格式、也不要自己挑一条路径**，把 reason 原话回给
    律师，由人决定补规格还是补文件夹模板。

    Args:
        doc_type: 文书类型，如 管辖权异议申请书。
        case_id / contract_id: 二选一，决定落到哪个项目文件夹。
        facts: 律师显式给出的事实（可选，优先级最高）。
        instruction: 律师的补充要求（可选）。
        comment_author: 未决项批注的署名（可选，缺省 Lawyer）。

    Returns:
        `{created, doc_type, name, subpath, file_url, filled, pending, slot_fill_rate,
        review_run_id, warnings, reason}`；`file_url` 可直接交给画布打开。
    """
    if (case_id is None) == (contract_id is None):
        raise ValueError(
            "case_id 与 contract_id 必须二选一：文书要落进某个项目文件夹，两个都不给就没有落点，"
            "两个都给说明引用块读串了"
        )
    result: dict[str, Any] = client.post(
        "/doc-workspace/draft-by-type",
        json={
            "doc_type": doc_type.strip(),
            "case_id": case_id,
            "contract_id": contract_id,
            "facts": facts or {},
            "instruction": instruction,
            "comment_author": comment_author,
        },
    )
    return result


__all__ = ["draft_document"]
