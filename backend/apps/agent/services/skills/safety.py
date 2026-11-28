"""共享技能的两级内容闸门：PII / 凭证 / 案号 / 提示注入（纯函数，零 IO，零 ORM）。

契约见 ``docs/analysis/user-skills-copilot-2026-11-28/CONTRACT.md`` §7。个人技能只记录
不拦；共享技能（team / law_firm）在提审与批准时跑本闸门——它的正文会进全所/全团队的
提示词，一条客户身份证号泄漏就是保密义务问题。

## 为什么边界不用 ``\\b``

``re`` 默认走 Unicode 语义：汉字属于 ``\\w``，而 ``\\b`` 只在「``\\w`` 与非 ``\\w``」之间
成立。``"手机号" 后面紧贴 11 位数字`` 时，数字两侧都紧邻汉字、两端都不成边界，于是
``\\b1[3-9]\\d{9}\\b`` 对它返回 ``None``——这正是 ``memory/curation.py:scan_pii_risk`` 的
P0 漏报点（``"身份证310101199001011234"`` 同理）。本模块的数字规则一律写成
``(?<!\\d)…(?!\\d)``：只禁止「紧邻数字」，不禁「紧邻汉字」。额外加「紧邻拉丁字母也不认」
是为了不从 ``HT2024001234567890123`` 这种字母数字编号里截一段数字当卡号。数字类正则
统一加 ``re.ASCII``，让 ``\\d`` 只覆盖 0-9：全角数字不在闸门范围内，刻意规避由审批兜底。

## 为什么正则不是兜底防线

正则只能拦住**无心的照搬**（把客户身份证粘进共享技能），拦不住刻意规避（插空格、拆行、
全角、换写法）。真正的硬防线是三道非正则关卡：审批人逐条看 diff、服务端
``services/approval/risk.py`` 的四级判级 + 人工闸门、渲染层 ``render.py`` 的 frontmatter
白名单。本模块只负责把人的注意力引到位，不替代人。

## 为什么长数字串非要算校验位

``(?<!\\d)\\d{16,19}(?!\\d)`` 在法务正文里并不稀有（统一社会信用代码、合同编号、账号、
时间戳拼接）。不问校验位就大面积误杀，共享技能根本提交不了。身份证按 GB 11643 加权模
11，银行卡按 Luhn——两者都是**必要不充分**条件：过了才报 hard，没过就当普通数字放过
（零误杀优先于零漏报，漏掉的由审批兜底）。

## 脱敏

``Finding.excerpt`` 是唯一会进响应/日志的片段，因此就地脱敏：身份证/手机号/卡号只留
首尾各 2 位，邮箱只留首字符 + 域名，凭证只留前 4 字符，案号序号打码，主体名只留首字 +
组织形式。完整原文绝不外泄——闸门自己不能变成新的泄漏点。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

#: 硬拦截：拒绝提交/发布
HARD = "hard"
#: 软告警：标出命中、勾选确认、落审计
SOFT = "soft"
#: 扫描字段（顺序即 findings 输出顺序，同一输入永远同一结果）
FIELDS: tuple[str, ...] = ("title", "description", "body")

_Masker = Callable[[str], str]


@dataclass(frozen=True)
class Finding:
    """一条命中。冻结的：闸门结果是审计证据，不该在传递途中被就地改写。"""

    code: str  # id_card / phone / bank_card / court_case_no / email / secret
    #            / entity_name / injection / dangerous_tool
    level: str  # HARD / SOFT
    field: str  # title / description / body
    message: str
    excerpt: str  # 已脱敏，见模块注释「脱敏」


#: 身份证 GB 11643：前 17 位加权求和后模 11 查校验码
_ID_WEIGHTS: tuple[int, ...] = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_CODES = "10X98765432"
#: 16-19 位数字串是身份证与银行卡的共同候选池；20 位以上不切片、不误判
_DIGIT_RUN_RE = re.compile(r"(?<!\d)(?<![A-Za-z])\d{16,19}(?!\d)(?![A-Za-z])", re.ASCII)
#: 手机号：11 位、1 开头、次位是现行号段 [3-9]
_PHONE_RE = re.compile(r"(?<!\d)(?<![A-Za-z])1[3-9]\d{9}(?!\d)(?![A-Za-z])", re.ASCII)

#: 锤定的法院字号（长者在先：``执异``/``执复`` 必须先于 ``执``，``破申`` 先于 ``破``）
_CASE_TOKEN = "知民初|知民终|知民|民初|民终|民申|民再|刑初|刑终|行初|行终|执异|执复|执|破申|破|仲"
#: 必须「年份括注 + 法院代码 + 字号 + 序号 + 号」四段齐全才算案号。缺了字号那一段
#: （``（2024）第1号通知`` 这类红头文件文号）就不命中——正是 ``curation.py`` 用
#: 「年份括注 … 号」裸正则大面积误杀之处。
_COURT_CASE_NO_RE = re.compile(
    r"[（(]\s*(?:19|20)\d{2}\s*[）)]\s*[\u4e00-\u9fa5]{0,8}\d{0,4}\s*"
    rf"(?:{_CASE_TOKEN})\s*第?\s*\d{{1,6}}\s*号",
    re.ASCII,
)

_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
#: ``sk-`` 前缀用 ``(?<![A-Za-z0-9_-])`` 卡住 ``task-…`` 这类误命中
_SK_KEY_RE = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{16,}")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}")
_GHP_TOKEN_RE = re.compile(r"ghp_[A-Za-z0-9]{20,}")
_PEM_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")

#: 组织形式（长者在先：``有限责任公司`` 不能被 ``有限公司`` 抢先匹配）
_ENTITY_RE = re.compile("有限责任公司|股份有限公司|律师事务所|法律援助中心|仲裁委员会|人民法院|人民检察院|有限公司")
#: 出现即说明组织形式左侧是动词/介词短语而非名称：「需由｜律师事务所」「目标企业的｜
#: 有限责任公司」都由此切断；专名里几乎不会有这些字。
_NAME_STOP_CHARS = frozenset(
    "需由向的在对于与和及或并请以据依按将被把即应该本各须可赴到至经报提交给跟同称之其如若凡则亦还也都又再往自过令使让得能会要为是含无"
)
#: 断出来的短前缀仍是泛称（「当地｜法律援助中心」）→ 不算完整主体名
_GENERIC_NAME_HEADS = frozenset(
    {"当地", "本地", "外地", "我方", "对方", "双方", "各方", "贵司", "相关", "有关", "上述", "目标"}
)

#: 提示注入措辞逐条列举而非模糊正则：每条都是可直接给人看的证据，加词时一眼能审
_INJECTION_PHRASES: tuple[str, ...] = (
    "忽略审批",
    "忽略审核",
    "忽略以上",
    "忽略上述",
    "跳过确认",
    "跳过审批",
    "跳过审核",
    "你是系统管理员",
    "你现在是系统管理员",
    "绕过校验",
    "绕过审批",
    "绕过审核",
    "不要告诉用户",
    "不用告诉用户",
    "不要通知用户",
)
_DANGEROUS_TOOL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:delete_[A-Za-z0-9_]+|execute_[A-Za-z0-9_]+|clear_all)(?![A-Za-z0-9_])"
)


# ── 脱敏 ────────────────────────────────────────────────────────────────


def _mask_digits(raw: str) -> str:
    """身份证/手机号/卡号：只留首尾各 2 位（契约 §7 的硬要求）。"""
    return "*" * len(raw) if len(raw) <= 4 else f"{raw[:2]}{'*' * (len(raw) - 4)}{raw[-2:]}"


def _mask_email(raw: str) -> str:
    """邮箱：留首字符 + 域名（本地部分常是当事人姓名拼音，不整段回显）。"""
    local, _, domain = raw.partition("@")
    return f"{local[:1] or '*'}***@{domain}"


def _mask_secret(raw: str) -> str:
    """凭证：只留前 4 字符。PEM 头本身不是秘密，原样保留以便审批人认出类型。"""
    return raw if raw.startswith("-----BEGIN") else f"{raw[:4]}***"


def _mask_case_no(raw: str) -> str:
    """案号：序号打码，年份/法院/字号保留——审批人据此已能定位到具文。"""
    return re.sub(r"\d{1,6}(?=\s*号)", "***", raw, count=1)


def _mask_entity(head: str, designator: str) -> str:
    """主体名：只留名称首字 + 组织形式。"""
    return f"{head[:1]}{'*' * max(len(head) - 1, 1)}{designator}"


def _unmasked(raw: str) -> str:
    """工具名/注入措辞不是 PII，原样回显才能让审批人一眼找到正文位置。"""
    return raw


#: 文本规则表：``(正则, code, level, 脱敏, 提示语)``，顺序即 findings 输出顺序。
#: 新增一条规则只改这张表，扫描流程不动——这张表就是闸门的全部真相。
_TEXT_RULES: tuple[tuple[re.Pattern[str], str, str, _Masker, str], ...] = (
    (_PHONE_RE, "phone", HARD, _mask_digits, "疑似 11 位手机号，请移除后再提交"),
    (_COURT_CASE_NO_RE, "court_case_no", HARD, _mask_case_no, "疑似真实法院案号，请改用「某案」等指代"),
    (_EMAIL_RE, "email", HARD, _mask_email, "疑似邮箱地址，请改用「某邮箱」等指代"),
    (_SK_KEY_RE, "secret", HARD, _mask_secret, "疑似 API Key，共享技能里绝不能出现"),
    (_BEARER_RE, "secret", HARD, _mask_secret, "疑似 Bearer 令牌，共享技能里绝不能出现"),
    (_GHP_TOKEN_RE, "secret", HARD, _mask_secret, "疑似 GitHub 令牌，共享技能里绝不能出现"),
    (_PEM_KEY_RE, "secret", HARD, _mask_secret, "疑似私钥（PEM 头），共享技能里绝不能出现"),
    (_DANGEROUS_TOOL_RE, "dangerous_tool", SOFT, _unmasked, "正文提及高危工具名，请说明调用条件与权限边界"),
)


# ── 校验位 ──────────────────────────────────────────────────────────────


def _id_card_checksum_ok(value: str) -> bool:
    """GB 11643 校验位；``len != 18`` 或含非 ASCII 数字一律 False（末位 X 允许）。"""
    if len(value) != 18:
        return False
    body = value[:17]
    if not (body.isdigit() and body.isascii()):
        return False
    total = sum(int(char) * weight for char, weight in zip(body, _ID_WEIGHTS, strict=True))
    return value[17].upper() == _ID_CHECK_CODES[total % 11]


def _luhn_ok(value: str) -> bool:
    """银行卡 Luhn 校验（从右往左，偶数位双倍后按位加和，模 10 为 0）。"""
    total = 0
    for index, char in enumerate(reversed(value)):
        digit = int(char) * (2 if index % 2 else 1)
        total += digit - 9 if digit > 9 else digit
    return total % 10 == 0


# ── 各规则族 ────────────────────────────────────────────────────────────


def _scan_numeric_ids(field: str, text: str) -> list[Finding]:
    """候选数字串：先按身份证（18 位 + GB 11643），再按银行卡（Luhn）。

    同一段数字只报一次——18 位身份证碰巧过 Luhn 的概率约 1/10，但那不代表它是卡号。
    """
    findings: list[Finding] = []
    for match in _DIGIT_RUN_RE.finditer(text):
        raw = match.group(0)
        if _id_card_checksum_ok(raw):
            code, level = "id_card", HARD
            message = "疑似 18 位身份证号（GB 11643 校验位通过），请移除后再提交"
        elif _luhn_ok(raw):
            code, level = "bank_card", HARD
            message = f"疑似 {len(raw)} 位银行卡号（Luhn 校验通过），请移除后再提交"
        else:
            continue
        findings.append(Finding(code, level, field, message, _mask_digits(raw)))
    return findings


def _name_head(text: str, end: int) -> str | None:
    """取组织形式左侧的专名；泛称或句子成分（「需由」「目标企业的」）返回 ``None``。

    从右往左走，撞到断点字就停——比「先匹配最长中文串再过滤」可靠：后者会把
    ``"起草法律意见书需由律师事务所"`` 整段当专名（``curation.py`` 的误杀点）。  # privacy-allow
    """
    start = end
    while start > 0 and end - start < 20:
        char = text[start - 1]
        if not "\u4e00" <= char <= "\u9fa5" or char in _NAME_STOP_CHARS:
            break
        start -= 1
    head = text[start:end]
    return None if len(head) < 2 or head in _GENERIC_NAME_HEADS else head


def _scan_entities(field: str, text: str) -> list[Finding]:
    """完整主体名：组织形式前必须还有 ≥2 字专名，且不含动词/介词断点。"""
    findings: list[Finding] = []
    for match in _ENTITY_RE.finditer(text):
        head = _name_head(text, match.start())
        if head is None:
            continue
        designator = match.group(0)
        message = f"疑似完整主体名称（含「{designator}」），建议改成「某某公司」等匿名写法"
        findings.append(Finding("entity_name", SOFT, field, message, _mask_entity(head, designator)))
    return findings


def _scan_injection(field: str, text: str) -> list[Finding]:
    """提示注入措辞：命中即软告警，由审批人判断它是「技能规则」还是「越权指令」。"""
    message = "疑似提示注入/越权措辞，审批人需确认它在技能里到底起什么作用"
    return [Finding("injection", SOFT, field, message, phrase) for phrase in _INJECTION_PHRASES if phrase in text]


def _scan_field(field: str, text: str) -> list[Finding]:
    """单字段全量扫描：数字 → 文本规则表 → 主体名 → 注入措辞。"""
    findings = _scan_numeric_ids(field, text)
    for pattern, code, level, mask, message in _TEXT_RULES:
        findings.extend(Finding(code, level, field, message, mask(match.group(0))) for match in pattern.finditer(text))
    findings.extend(_scan_entities(field, text))
    findings.extend(_scan_injection(field, text))
    return findings


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """同一字段里重复出现的同一命中只留一条（正文里那串号码可能被引用多次）。"""
    seen: set[tuple[str, str, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.code, finding.field, finding.excerpt)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


# ── 唯一出口 ────────────────────────────────────────────────────────────


def scan_skill(*, title: str, description: str, body: str) -> list[Finding]:
    """扫描技能的三个字段，返回全部命中（空列表 = 通过）。

    纯函数：不碰 DB、不写日志、不抛异常。分级策略留在调用方——共享技能的
    ``review.submit/approve`` 遇 ``HARD`` 直接 422，遇 ``SOFT`` 要求勾选确认并把命中
    记进 ``AgentSkillRevision``；个人技能只记录不拦。
    """
    payload = {"title": title, "description": description, "body": body}
    findings: list[Finding] = []
    for field in FIELDS:
        findings.extend(_scan_field(field, payload[field] or ""))
    return _dedupe(findings)


def has_hard_block(findings: list[Finding]) -> bool:
    """是否含硬拦截项（CORE 在 submit/approve 前用它决定要不要 422）。"""
    return any(finding.level == HARD for finding in findings)
