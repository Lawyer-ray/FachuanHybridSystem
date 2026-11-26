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
                '未决项批注的署名（Word/OnlyOffice 审阅面板里显示的"人"）。缺省 Lawyer；按这一份文书的要求填，不要写死'
            )
        ),
    ] = "",
    assess_first: Annotated[
        bool,
        Field(
            description=(
                "起草前先判断材料够不够（默认 true，多一次模型调用约 20~40 秒）。"
                "材料明显不全时它会直接返回 created=false 与缺口清单——那是律师要的答案，"
                "不要把 created=false 当成故障"
            )
        ),
    ] = True,
    force: Annotated[
        bool,
        Field(description="材料缺口已到 blocking 时仍要草稿；缺口会写成 <待填写：x> 并挂批注"),
    ] = False,
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
        assess_first: 起草前先判断材料够不够（默认开）。
        force: 缺口是 blocking 时仍出草稿。

    Returns:
        `{created, doc_type, name, subpath, file_url, filled, pending, slot_fill_rate,
        review_run_id, warnings, reason, readiness}`；`file_url` 可直接交给画布打开。
        `readiness.verdict=blocked` 时 `reason` 里就是「缺哪几项」，把原话回给律师。
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
            "assess_first": assess_first,
            "force": force,
        },
    )
    return result


def assess_draft_readiness(
    case_id: Annotated[int | None, Field(description="案件 ID（与 contract_id 二选一）", ge=1)] = None,
    contract_id: Annotated[int | None, Field(description="合同 ID（与 case_id 二选一）", ge=1)] = None,
    cause_of_action: Annotated[
        str,
        Field(
            description=(
                "案由；留空取案件上的字段。它决定用哪份要件档案，"
                "例如「土地租赁合同纠纷」会问到解除权与履约保证金，「合同纠纷」只会问通用付款要件"
            )
        ),
    ] = "",
    facts: Annotated[
        dict[str, str] | None,
        Field(description="律师已知的事实（如「被告已付 3 个月租金」），会直接改变缺口清单"),
    ] = None,
    instruction: Annotated[str, Field(description="律师的补充说明（可选）")] = "",
) -> dict[str, Any]:
    """判断「这个案子现在的材料够不够出这份文书」——**只读，不生成任何文件**。

    律师问「还缺什么」「能不能直接起诉」时先用这个工具，不要直接起草再让律师自己发现
    材料不全。返回四块：要件事实矩阵（每个要件在本案对应什么事实、出处在哪、缺不缺）、
    补充材料清单（要什么 / 为什么 / 向谁要 / 什么形式）、需要核实的问题清单、以及结论
    `verdict`。

    `verdict` 三个正常值：
    - `ready`：材料齐，可以直接起草；
    - `draftable_with_gaps`：能起草，但有非关键缺口，成稿里会出现 `<待填写：x>`；
    - `blocked`：关键材料没到位，起草会被闸门挡住（除非显式 `force`）。

    把 `missing_materials` 与 `questions` **原样转给律师**：那是他要去要材料、要去问客户的清单。
    不要替律师补全这些事实，也不要因为 `blocked` 就自己换一种文书或另造格式。

    Args:
        case_id / contract_id: 二选一，判断哪个项目。
        cause_of_action: 案由（可选，留空取案件字段）。
        facts: 律师已知的事实（可选）。
        instruction: 补充说明（可选）。

    Returns:
        `{verdict, profile_key, matrix, missing_materials, questions, blocking, warnings}`。
    """
    if (case_id is None) == (contract_id is None):
        raise ValueError("case_id 与 contract_id 必须二选一：两个都不给就不知道判断哪个项目")
    result: dict[str, Any] = client.post(
        "/doc-workspace/draft/assess",
        json={
            "case_id": case_id,
            "contract_id": contract_id,
            "cause_of_action": cause_of_action,
            "facts": facts or {},
            "instruction": instruction,
        },
    )
    return result


__all__ = ["assess_draft_readiness", "draft_document"]
