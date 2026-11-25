"""输出侧页旋转：把「人工转正」的顺时针增量烧进要交出去的 PDF。

## 这个模块解决什么

律师扫描卡纸时会把整叠纸倒着（180°）送进扫描仪，扫出来每页都是倒的。阅读器里
人工点「转正」只是**屏幕上的事**：角度记在前端草稿里，PDF 文件本身一个字节都没变。
于是「我看着正了」与「发给客户的 PDF 还是倒的」会同时成立，而且没人会再回来看
第二眼。所以每一个把 PDF 交给下一站的出口（切页归案、归档进卷宗、单段下载、整包
下载）都必须先按人工角度改页对象自身的 ``/Rotate``，**再去切页**——``insert_pdf``
复制的是页对象，/Rotate 跟着走；切完再改已经来不及。

## 角度约定：顺时针增量，叠加在页自身 /Rotate 之上

- 入参是 HTTP 那一份编码：``"页码:角度,页码:角度"``。页码 = **源 PDF 的绝对页号**
  （1 起，不是段内第几页）；角度只有 0/90/180/270，按**顺时针**度量；
- 语义是「在页自身 /Rotate 之上再顺时针转多少」：``page.set_rotation((page.rotation +
  deg) % 360)``。所以源 PDF 本来就是 90° 扫描件（/Rotate=90）时，再转 90 读回
  **180**，不是 90——叠加与覆盖是两种结果，写错就会把一页正常纸转倒。

### 与 ``page_rotation.py`` 是两套约定，禁止互相传值

同层还有一个 ``page_rotation.py``，处理的是**另一件事**：PaddleOCR 开整页方向分类
后，服务端先把页面转正再识别，返回的坐标全在「转正帧」，那里的 θ 是**逆时针为正**
的**回写**角度（``normalize_theta`` / ``derotate_point`` / ``derotate_rect`` …），
用途是把识别框搬回原页帧，一个字都不写进 PDF。

一句话分界：那边是**读**（逆时针、反变换、只动坐标），这边是**写**（顺时针、增量、
动 /Rotate）。本模块的 deg 不许传给 ``normalize_theta`` / ``derotate_point`` /
``derotate_rect``，反之亦然：两个 90 恰好互相抵消，方向搞反时肉眼极难发现，等到
「客户收到的 PDF 是倒的」才发现就已经发出去了。

## 非法输入为什么只告警、不 400

旋转是「让人看正」的辅助信息，与页区间、文件大小不是一类东西：一个 ``"3:45"`` 或
越界页号不该让律师丢掉一份已经切好的卷宗。所以脏 token 一律忽略 + ``logger.warning``
（日志里带原 token 与原因，事后能查到调用方发错了什么）；页区间本身的校验仍按原样
400，由 API 层负责。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger("apps.pdf_splitting")

#: 允许的顺时针增量（直角，整数度）。0 合法且有意义：它把同一页更早给的增量撤销掉。
ROTATION_STEPS: tuple[int, ...] = (0, 90, 180, 270)


def parse_page_rotations(raw: str) -> dict[int, int]:
    """``"页码:角度,页码:角度"`` → ``{页码: 顺时针增量}``；空串/None → 空表。

    同页重复时**后值覆盖前值**（``"1:90,1:270"`` → ``{1: 270}``）：那是"最后一个
    说法算数"的直读语义，跨段合并（``merge_page_rotations``）也走这条。重复本身不
    告警——它没有歧义；有歧义的是「同一个绝对页被两段各给一个角度」，那条在合并里
    留痕。
    """
    # 非 str 一律当「没转」：端点里 `rotations: str = Form("")` 的直接调用方
    # （单测、内部调用）省略该参数时拿到的是 Form 对象而不是空串；真实请求经过
    # Ninja 永远是 str。这里统一收敛，别让「省了个参数」变成 500。
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return {}
    rotations: dict[int, int] = {}
    for token in text.split(","):
        page_no, deg = _parse_token(token)
        if page_no is None:
            continue
        rotations[page_no] = deg
    return rotations


def _parse_token(token: str) -> tuple[int | None, int]:
    """单个 token → ``(页码, 角度)``；脏 token 归 ``(None, 0)`` 并告警。"""
    text = token.strip()
    page_text, separator, deg_text = text.partition(":")
    page_text, deg_text = page_text.strip(), deg_text.strip()
    if not separator or not page_text or not deg_text:
        _warn_ignored(text, "not_page_colon_angle")
        return None, 0
    # 只认 ASCII 数字：``int()`` 会接受 ``"１"`` 这类全角数字，而调用方写全角几乎
    # 总是输入法事故；``"3.0"`` / ``"-3"`` 也不该被悄悄收下。
    if not (page_text.isascii() and page_text.isdigit()):
        _warn_ignored(text, "page_not_positive_int")
        return None, 0
    if not (deg_text.isascii() and deg_text.isdigit()):
        _warn_ignored(text, "angle_not_right_angle")
        return None, 0
    page_no, deg = int(page_text), int(deg_text)
    if page_no < 1:
        _warn_ignored(text, "page_below_one")
        return None, 0
    if deg not in ROTATION_STEPS:
        _warn_ignored(text, "angle_not_right_angle")
        return None, 0
    return page_no, deg


def _warn_ignored(token: str, reason: str) -> None:
    logger.warning("pdf_split_page_rotation_ignored", extra={"token": token, "reason": reason})


def merge_page_rotations(raws: Iterable[str]) -> dict[int, int]:
    """多段各自的 ``rotations`` → 一张 ``{页码: 角度}``（归档端点只 apply 一次）。

    为什么归档必须先合并再 apply：一份 ``source_doc`` 被所有段复用，页指纹也是在同一
    份文档上算（``page_signature`` 走 ``get_pixmap``，**会**吃 /Rotate）。逐段 apply 的
    话，先切出的段与后算的指纹方向不一致，副本判定就会把同一份材料判成两份不同的；
    而 ``insert_pdf`` 之后文档已经变了，回头再补转更是错上加错。

    同页冲突（正常拆分下同一绝对页只属于一个段，两段叠页说明调用方页区间算错了）→
    **payload 顺序后者覆盖前者** + ``logger.warning`` 带页号与两个角度：静默取一个值
    会让这种 bug 永远查不到，而它是「卷宗里有两份互相矛盾的同一页」的前兆。
    """
    merged: dict[int, int] = {}
    for raw in raws:
        for page_no, deg in parse_page_rotations(raw).items():
            previous = merged.get(page_no)
            if previous is not None and previous != deg:
                logger.warning(
                    "pdf_split_page_rotation_conflict",
                    extra={"page": page_no, "previous_deg": previous, "deg": deg},
                )
            merged[page_no] = deg
    return merged


def apply_page_rotations(doc: Any, rotations: Mapping[int, int] | None) -> int:
    """把 ``{页码: 顺时针增量}`` 烧进 ``doc``，返回**真正改过**的页数。

    ``doc`` 是 pymupdf 的 ``Document``，这里按 ``Any`` 收：本模块顶层不 import fitz，
    纯编码/合并逻辑的单测不必加载那个二进制（延迟到调用方那边，见各出口的 import）。

    两条忽略规则与解析侧同口径（告警、不抛）：
    - 越界页号：``doc.page_count`` 只有这里知道，解析侧无从判断；
    - 非直角增量：``set_rotation`` 对任意整数都照写，写进一份合同 PDF 是无法解释的。
    增量 0 不计入返回页数——它是"撤销"，不是"转过"。
    """
    if not rotations:
        return 0
    page_count = int(doc.page_count)
    applied = 0
    for page_no in sorted(rotations):
        deg = int(rotations[page_no])
        if deg == 0:
            continue
        if deg not in ROTATION_STEPS:
            logger.warning(
                "pdf_split_page_rotation_ignored",
                extra={"page": page_no, "deg": deg, "reason": "angle_not_right_angle"},
            )
            continue
        if page_no < 1 or page_no > page_count:
            logger.warning(
                "pdf_split_page_rotation_ignored",
                extra={"page": page_no, "deg": deg, "reason": "page_out_of_range", "total_pages": page_count},
            )
            continue
        page = doc.load_page(page_no - 1)
        page.set_rotation((int(page.rotation) + deg) % 360)
        applied += 1
    return applied


__all__ = [
    "ROTATION_STEPS",
    "apply_page_rotations",
    "merge_page_rotations",
    "parse_page_rotations",
]
