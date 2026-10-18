"""Pre-commit / CI guardrails for sensitive patterns and diff-based checks."""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

SOURCE_DIR_PREFIXES = (
    "backend/apps/",
    "backend/apiSystem/",
    "backend/scripts/",
    "scripts/",
)
FORBIDDEN_BINARY_EXTENSIONS = (".onnx", ".mp4", ".zip")
FORBIDDEN_PRIVATE_PATH_PREFIXES = (
    "backend/plugins/weike_api_private/",
    "backend/apps/legal_research/services/sources/weike_api_private/",
    "backend/apps/legal_research/services/sources/weike/api_private/",
)
ALLOWLIST_MARKERS = (
    "pragma: allowlist secret",
    "allowlist secret",
    "# nosec",
    "privacy-allow",
)
PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(example|sample|dummy|placeholder|changeme|redacted|masked|测试|示例|演示|虚构|占位|\*\*\*|xxxx)"
)
# 隐私扫描跳过的文件（按文件名匹配，仓库根 / backend 子目录两种 cwd 都能命中）：
# 生成物内容由代码决定且会整体重生成，行级标记放不进去；案由种子是最高法公开词库，
# 「××诉××」是案由命名法不是真实案名
PRIVACY_SKIP_BASENAMES = ("openapi.json", "api-schema.d.ts", "seed_causes_of_action.json")
# 公开第三方（爬取目标 / SDK 厂商 / 自家律所），不是当事人隐私
ALLOWED_ENTITY_NAMES = ("小米科技", "腾讯科技", "阳光财产保险", "上海道律", "金诚同达")
CN_ID_PATTERN = re.compile(r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]\b")
CN_ID_BODY_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
CN_ID_CHECK_CHARS = "10X98765432"
CN_MOBILE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
CN_LANDLINE_PATTERN = re.compile(r"(?<!\d)0\d{2,3}-\d{7,8}(?!\d)")
# 统一社会信用代码（18 位，GB 32100）；首二位是登记管理部门/机构类别
USCC_PATTERN = re.compile(r"(?<![0-9A-Za-z])[159Y][1239][0-9A-HJ-NPQRTUWXY]{16}(?![0-9A-Za-z])")
USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"  # pragma: allowlist secret（GB 32100 字符集，非密钥）
USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
# 法院案号：（20XX）粤01民终NNN号
COURT_CASE_NO_PATTERN = re.compile(
    r"[（(]\s*20\d{2}\s*[）)][\u4e00-\u9fa5]{1,4}?\d{0,5}[\u4e00-\u9fa5]{1,8}[\u4e00-\u9fa5\d]{0,6}号"
)
# 内部案号 / OA 合同号：20XX + 2–4 位大写字母 + 3–5 位数字
INTERNAL_CASE_NO_PATTERN = re.compile(r"(?<![0-9A-Za-z])20\d{2}[A-Z]{2,4}\d{3,5}(?![0-9A-Za-z])")
# 案名（X诉Y… / X与Y…纠纷），两侧任一是「某」式脱敏即放行
CASE_NAME_VS_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{2,24})诉([\u4e00-\u9fa5（）()·、，,]{2,60}?)(?:一案|纠纷|之诉|仲裁|执行)"
)
CASE_NAME_WITH_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{2,24})与([\u4e00-\u9fa5（）()·、，,]{2,60}?)(?:纠纷|仲裁|之诉)"
)
ANON_NAME_PATTERN = re.compile(r"某|张三|李四|王五|赵六|[甲乙丙丁]方|[A-Za-z]某")
# 公司 / 机构名：甲方运动用品有限公司 放行，佛山市某某有限公司 看是否含「某」
COMPANY_PATTERN = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{2,24})(?:股份有限公司|有限责任公司|有限公司|集团有限公司|律师事务所|会计师事务所|合伙企业|经营部)"
)
# 解析代码里裸写的后缀字面量（"股份有限公司"）会退化成 body=「股份有限」；
# 文档里「机构名（有限公司 / …」这种枚举写法 body 以标点结尾——都不是公司名
COMPANY_SUFFIX_ARTIFACT_TAILS = ("有限", "公司", "股份", "集团", "责任", "（", "(", "、", "/", "：", ":")
# 完整地址链：省…市…区/县/镇/路/村…（只拦全链，单独提「广州市」不拦）
ADDRESS_PATTERN = re.compile(
    r"[\u4e00-\u9fa5]{1,8}(?:省|自治区)[\u4e00-\u9fa5]{1,8}市[\u4e00-\u9fa5]{1,14}(?:区|县|旗|镇|街道|路|村|大道)[\u4e00-\u9fa5\d]{0,25}"
)
SENSITIVE_LITERAL_ASSIGN_PATTERN = re.compile(
    r"(?i)\b(?:password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|api[_-]?key|secret(?:[_-]?key)?|authorization|cookie|sessionid)\b"
    r"\s*[:=]\s*['\"][^'\"]{4,}['\"]"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# ---- 大模型隐私复审：正则看不见的孤立人名 / 无后缀机构名 / 门牌级地址 ----
CJK_PATTERN = re.compile(r"[\u4e00-\u9fa5]")
# kimi 每把 key 限 3 并发；LLMProvider 表可配多把 key，槽位 = Σ(每 key 并发 × key 数)，
# 走后端进程级 KeyPool 轮转，无需自己记账
LLM_PRIVACY_CHUNK_LINES = 60
LLM_PRIVACY_MAX_LINES = 400
LLM_PRIVACY_MAX_CHARS = 24_000
LLM_PRIVACY_LINE_CHARS = 300
LLM_PRIVACY_TIMEOUT_S = 60
LLM_PRIVACY_MAX_SLOTS = 12
# 模型自己在理由里说「应放行 / 虚构 / 示例」的条目不算命中
LLM_REASON_PASS_PATTERN = re.compile(r"放行|虚构|示例")
LLM_PRIVACY_SYSTEM_PROMPT = """你是律所办案系统代码仓库的隐私合规审查员。仓库对外公开，任何真实当事人信息都不得入库。
下面是即将提交的新增文本行，格式「编号|内容」。请找出含有**真实隐私**的行：
A. 自然人姓名：未脱敏的中文全名或外文全名。放行：张某 / 李某某 / 某某式脱敏；张三、李四、王五等通用示例名；测试、示例、演示、虚构语境；公众人物与历史人物；代码标识符与拼音变量名。
B. 公司 / 机构名：未脱敏的具体企业、律师事务所、合作单位全称或可识别简称。放行：含「某」或甲方 / 乙方的虚构名；法院、检察院、仲裁委等公共机关；小米、腾讯、微信、支付宝等知名公开品牌与开源项目。
C. 地址：精确到街道门牌 / 楼栋楼层的地址。放行：只到省市区一级的地名。
D. 其他可直接识别特定个人或案件的信息：律师执业证号、银行卡号、车牌号、把具体当事人组合在一起的案件描述。
不要报告：电话号码、身份证号、法院案号（另有规则检查）；代码、URL、版本号、日期、日志、UI 文案里的功能名词。
只输出一个 JSON 数组，每项为 {"id": 编号整数, "kind": "姓名|机构|地址|其他", "evidence": "原文片段", "reason": "不超过 20 字"}；没有隐私输出 []。不要输出任何其他文字。"""


def _run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _parse_added_lines(diff_text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    current_line = 0
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_line = int(match.group(1)) - 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_line += 1
            lines.append((current_line, line[1:]))
            continue
        if line.startswith("-"):
            continue
        current_line += 1
    return lines


def _get_changed_files(mode: str, base: str | None, head: str) -> list[str]:
    if mode == "staged":
        output = _run_git(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    else:
        if not base:
            return []
        output = _run_git(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}..{head}"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _get_added_lines(filepath: str, mode: str, base: str | None, head: str) -> list[tuple[int, str]]:
    if mode == "all":
        try:
            content = Path(filepath).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        return [(i + 1, line) for i, line in enumerate(content.splitlines())]
    if mode == "staged":
        output = _run_git(["git", "diff", "--cached", "-U0", "--", filepath])
    else:
        if not base:
            return []
        output = _run_git(["git", "diff", f"{base}..{head}", "-U0", "--", filepath])
    return _parse_added_lines(output)


def _resolve_candidates(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    if files:
        return files
    if mode == "all":
        return [line.strip() for line in _run_git(["git", "ls-files"]).splitlines() if line.strip()]
    return _get_changed_files(mode, base, head)


def _check_todo(filepath: str, mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for lineno, content in _get_added_lines(filepath, mode, base, head):
        if "TODO" in content or "FIXME" in content:
            errors.append(f"{filepath}:{lineno}: 新增了 TODO/FIXME 标记")
    return errors


def _check_print(filepath: str, mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    try:
        source = Path(filepath).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, OSError, UnicodeDecodeError):
        return errors

    added_linenos = {ln for ln, _ in _get_added_lines(filepath, mode, base, head)}
    if not added_linenos:
        return errors

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ("print", "pprint") and node.lineno in added_linenos:
                errors.append(f"{filepath}:{node.lineno}: 新增了 {name}() 调用，请改用 logger")
    return errors


def _is_forbidden_binary_path(filepath: str) -> str | None:
    normalized = filepath.replace("\\", "/")
    if not any(normalized.startswith(prefix) for prefix in SOURCE_DIR_PREFIXES):
        return None
    lowered = normalized.lower()
    for ext in FORBIDDEN_BINARY_EXTENSIONS:
        if lowered.endswith(ext):
            return ext
    return None


def _check_binary_ext(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        ext = _is_forbidden_binary_path(filepath)
        if ext:
            errors.append(f"{filepath}: 禁止在源码目录提交 {ext} 文件，请改用制品仓/对象存储")
    return errors


def _check_private_paths(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        normalized = filepath.replace("\\", "/").lower()
        if any(normalized.startswith(prefix) for prefix in FORBIDDEN_PRIVATE_PATH_PREFIXES):
            errors.append(f"{filepath}: 禁止提交WK私有实现目录（weike_api_private/api_private）")
    return errors


def _has_allowlist_marker(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in ALLOWLIST_MARKERS)


def _valid_cn_id_checksum(number: str) -> bool:
    """GB 11643 校验位：真实证件号校验位必然合法，乱造的测试假数据基本过不了。"""
    body, check = number[:17], number[17].upper()
    total = sum(int(c) * w for c, w in zip(body, CN_ID_BODY_WEIGHTS))
    return CN_ID_CHECK_CHARS[total % 11] == check


def _valid_uscc_checksum(number: str) -> bool:
    """GB 32100 统一社会信用代码校验位（ISO 7064 MOD 31,3）。"""
    values = [USCC_CHARSET.index(c) for c in number[:17].upper()]
    total = sum(v * w for v, w in zip(values, USCC_WEIGHTS))
    return USCC_CHARSET[(31 - total % 31) % 31] == number[17].upper()


def _is_anonymized(name: str) -> bool:
    """当事人名是否已脱敏：张某 / 某公司 / 甲方 / 张三 这类放行。"""
    return bool(ANON_NAME_PATTERN.search(name)) or bool(PLACEHOLDER_PATTERN.search(name))


def _case_name_hit(content: str) -> str | None:
    """X诉Y… / X与Y…纠纷，两侧都不是脱敏名 → 疑似真实案名。"""
    for pattern in (CASE_NAME_VS_PATTERN, CASE_NAME_WITH_PATTERN):
        for match in pattern.finditer(content):
            plaintiff, defendant = match.group(1), match.group(2)
            # 「上诉」「起诉」「败诉」里的诉不是案名连接词
            if plaintiff.endswith(("上", "起", "败", "胜", "申")):
                continue
            defendant_head = re.split(r"[、，,]", defendant)[0]
            if not _is_anonymized(plaintiff) and not _is_anonymized(defendant_head):
                return f"疑似真实案名「{plaintiff}诉{defendant_head}…」，请改为「张某诉某公司」式脱敏"
    return None


def _privacy_hit(content: str) -> str | None:
    """单行隐私检测，返回给用户看的拒绝原因；None = 放行。"""
    for match in CN_ID_PATTERN.finditer(content):
        if _valid_cn_id_checksum(match.group(0)):
            return "检测到疑似真实身份证号（校验位合法），请脱敏或改为校验位不合法的假数据"
    if CN_MOBILE_PATTERN.search(content) and not PLACEHOLDER_PATTERN.search(content):
        return "检测到疑似手机号，请脱敏或改为占位符（如 138****1234），确属假数据可在行尾加 privacy-allow 标记"
    if CN_LANDLINE_PATTERN.search(content) and not PLACEHOLDER_PATTERN.search(content):
        return "检测到疑似座机号，请脱敏，确属假数据可在行尾加 privacy-allow 标记"
    if EMAIL_PATTERN.search(content) and not PLACEHOLDER_PATTERN.search(content):
        return "检测到疑似邮箱地址，请脱敏或改为占位符"
    for match in USCC_PATTERN.finditer(content):
        if _valid_uscc_checksum(match.group(0)):
            return "检测到疑似统一社会信用代码（校验位合法），请脱敏"
    if COURT_CASE_NO_PATTERN.search(content):
        return "检测到疑似法院案号，请脱敏（如（20XX）粤01民初某某号）"
    if INTERNAL_CASE_NO_PATTERN.search(content):
        return "检测到疑似内部案号/OA 合同号，请脱敏"
    case_hit = _case_name_hit(content)
    if case_hit:
        return case_hit
    for match in COMPANY_PATTERN.finditer(content):
        name = match.group(0)
        body = match.group(1)
        if body.endswith(COMPANY_SUFFIX_ARTIFACT_TAILS):
            continue
        if any(allowed in name for allowed in ALLOWED_ENTITY_NAMES):
            continue
        if not _is_anonymized(name):
            return f"疑似真实公司/机构名「{name}」，请改为「某公司 / 甲方公司」式虚构名"
    if ADDRESS_PATTERN.search(content) and not PLACEHOLDER_PATTERN.search(content):
        return "检测到疑似完整地址（省市区链），请脱敏"
    return None


def _check_sensitive(files: list[str], mode: str, base: str | None, head: str) -> list[str]:
    errors: list[str] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        normalized = filepath.replace("\\", "/")
        # 锁文件：自动生成、体量大，两种检查都跳过
        if normalized.endswith((".lock", "uv.lock", "poetry.lock", "Pipfile.lock")):
            continue
        in_source_dir = any(normalized.startswith(prefix) for prefix in SOURCE_DIR_PREFIXES)
        # 凭证类（Bearer / 密钥字面量）只盯运行时源码目录；全库凭证由 detect-secrets 兜底
        # 隐私类（姓名/案名/证件号/电话/案号/公司/地址）扫全部入库文件——
        # changelog、docs、前端、测试都泄漏过；存量行不阻塞，只拦新增行（棘轮式）
        skip_privacy = Path(normalized).name in PRIVACY_SKIP_BASENAMES
        for lineno, content in _get_added_lines(filepath, mode, base, head):
            if _has_allowlist_marker(content):
                continue
            if in_source_dir:
                if BEARER_PATTERN.search(content):
                    errors.append(f"{filepath}:{lineno}: 检测到 Bearer Token 字符串，请移除")
                    continue
                if SENSITIVE_LITERAL_ASSIGN_PATTERN.search(content) and not PLACEHOLDER_PATTERN.search(content):
                    errors.append(f"{filepath}:{lineno}: 检测到密码/Token 关键词字面量赋值，请改为环境变量或密钥管理")
                    continue
            if skip_privacy:
                continue
            hit = _privacy_hit(content)
            if hit:
                errors.append(f"{filepath}:{lineno}: {hit}")
    return errors


# ---- 大模型隐私复审 ----


def _collect_llm_privacy_lines(files: list[str], mode: str, base: str | None, head: str) -> list[tuple[str, int, str]]:
    """送审候选：有中文、未带豁免标记的新增行（纯代码 / URL / 数字行不含人名机构名，不送省 token）。"""
    out: list[tuple[str, int, str]] = []
    for filepath in _resolve_candidates(files, mode, base, head):
        normalized = filepath.replace("\\", "/")
        if normalized.endswith((".lock", "uv.lock", "poetry.lock", "Pipfile.lock")):
            continue
        if Path(normalized).name in PRIVACY_SKIP_BASENAMES:
            continue
        for lineno, content in _get_added_lines(filepath, mode, base, head):
            if _has_allowlist_marker(content) or not CJK_PATTERN.search(content):
                continue
            out.append((filepath, lineno, content.strip()[:LLM_PRIVACY_LINE_CHARS]))
    return out


def _bootstrap_django_for_llm() -> str | None:
    """让脚本能用后端的 LLMService（LLMProvider 表是模型配置唯一来源）。返回失败原因，None=成功。"""
    backend_dir = Path(__file__).resolve().parents[1]
    for path in (backend_dir, backend_dir / "apiSystem"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    # 应用启动 INFO 日志会刷屏；hook 以 verbose 运行时输出必须干净
    logging.disable(logging.INFO)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
    try:
        import django

        django.setup()
    except Exception as exc:  # 任何初始化失败都放行，不能让离线 / 环境缺失挡住提交
        return f"{exc.__class__.__name__}: {exc}"
    return None


def _llm_slot_capacity() -> int:
    """并发槽位 = Σ 启用平台的（每 key 并发 × key 数），上限兜底；取不到按单 key 3 并发。"""
    try:
        from apps.core.models.llm_provider import LLMProvider

        total = sum(
            max(1, p.concurrency_per_key) * max(1, len(p.parsed_api_keys()))
            for p in LLMProvider.objects.filter(enabled=True)
        )
    except Exception:
        return 3
    return max(1, min(total, LLM_PRIVACY_MAX_SLOTS))


def _parse_llm_json_array(text: str) -> list[dict] | None:
    """宽松取出模型输出里的 JSON 数组（容忍 ``` 围栏与前后废话）；解析不出返回 None。"""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else None


def _review_chunk(chunk: list[tuple[str, int, str]]) -> tuple[list[dict], str | None]:
    """审查一片候选行。返回 (命中列表, 错误原因)；错误时该片放行并由调用方提示。"""
    from apps.core.llm.service import get_llm_service

    prompt = "\n".join(f"{idx}|{content}" for idx, (_, _, content) in enumerate(chunk))
    try:
        response = get_llm_service().complete(
            prompt,
            system_prompt=LLM_PRIVACY_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=2000,
            caller="security_guard.llm_privacy",
        )
    except Exception as exc:
        return [], f"{exc.__class__.__name__}: {str(exc)[:120]}"
    items = _parse_llm_json_array(response.content or "")
    if items is None:
        return [], "模型输出不是 JSON 数组"
    findings: list[dict] = []
    for item in items:
        idx = item.get("id")
        if not isinstance(idx, int) or not 0 <= idx < len(chunk):
            continue
        evidence = str(item.get("evidence", ""))[:60]
        reason = str(item.get("reason", ""))[:40]
        # 确定性兜底：模型偶尔一边写「含甲方虚构名应放行」一边照样输出条目——
        # 证据本身符合脱敏规则（某 / 甲方 / 张三 / 测试…），或它自己的理由就说该放行，都不算命中
        if (evidence and _is_anonymized(evidence)) or LLM_REASON_PASS_PATTERN.search(reason):
            continue
        filepath, lineno, _ = chunk[idx]
        findings.append(
            {
                "file": filepath,
                "lineno": lineno,
                "kind": str(item.get("kind", "隐私"))[:8],
                "evidence": evidence,
                "reason": reason,
            }
        )
    return findings, None


def _run_llm_review(candidates: list[tuple[str, int, str]]) -> tuple[list[dict], list[str]]:
    """分片并发送审；槽位吃满多 key 配额。返回 (命中, 提示)。"""
    from concurrent.futures import ThreadPoolExecutor

    chunks = [candidates[i : i + LLM_PRIVACY_CHUNK_LINES] for i in range(0, len(candidates), LLM_PRIVACY_CHUNK_LINES)]
    workers = max(1, min(len(chunks), _llm_slot_capacity()))
    findings: list[dict] = []
    notices: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (chunk_findings, error) in enumerate(pool.map(_review_chunk, chunks), start=1):
            if error:
                notices.append(f"llm-privacy: 第 {index}/{len(chunks)} 片审查失败已放行（{error}）")
            findings.extend(chunk_findings)
    notices.insert(0, f"llm-privacy: 大模型复审 {len(candidates)} 行，{len(chunks)} 片 × {workers} 并发")
    return findings, notices


def _check_llm_privacy(files: list[str], mode: str, base: str | None, head: str) -> tuple[list[str], list[str]]:
    """大模型隐私复审入口。返回 (拦截项, 状态提示)；模型不可达一律放行并提示，不能挡住离线提交。"""
    if os.environ.get("FACHUAN_LLM_PRIVACY", "").strip().lower() in {"off", "0", "false"}:
        return [], ["llm-privacy: 已由 FACHUAN_LLM_PRIVACY=off 禁用"]
    candidates = _collect_llm_privacy_lines(files, mode, base, head)
    if not candidates:
        return [], ["llm-privacy: 没有需要复审的中文新增行"]
    truncated = False
    if len(candidates) > LLM_PRIVACY_MAX_LINES:
        candidates, truncated = candidates[:LLM_PRIVACY_MAX_LINES], True
    total_chars = 0
    for cut, (_, _, content) in enumerate(candidates):
        total_chars += len(content)
        if total_chars > LLM_PRIVACY_MAX_CHARS:
            candidates, truncated = candidates[:cut], True
            break
    failure = _bootstrap_django_for_llm()
    if failure:
        return [], [f"llm-privacy: 后端初始化失败，跳过大模型复审（{failure[:120]}）"]

    result: dict[str, tuple[list[dict], list[str]]] = {}

    def runner() -> None:
        result["value"] = _run_llm_review(candidates)

    worker = threading.Thread(target=runner, daemon=True)
    worker.start()
    worker.join(LLM_PRIVACY_TIMEOUT_S)
    if "value" not in result:
        return [], [f"llm-privacy: 超过 {LLM_PRIVACY_TIMEOUT_S}s 未返回，跳过大模型复审"]
    findings, notices = result["value"]
    if truncated:
        notices.append(f"llm-privacy: 新增行过多，只复审了前 {len(candidates)} 行")
    errors = [
        f"{f['file']}:{f['lineno']}: 大模型判定疑似{f['kind']}「{f['evidence']}」——{f['reason']}（确属虚构请在行尾加 privacy-allow 标记）"
        for f in findings
    ]
    if not errors:
        notices.append("llm-privacy: 大模型未发现隐私")
    return errors, notices


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        choices=["todo", "print", "binary-ext", "private-path", "sensitive", "llm-privacy"],
        required=True,
    )
    parser.add_argument("--mode", choices=["staged", "range", "all"], default="staged")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if args.mode == "range" and not args.base:
        print("--mode range 必须提供 --base", file=sys.stderr)
        sys.exit(2)

    all_errors: list[str] = []
    if args.check == "binary-ext":
        all_errors.extend(_check_binary_ext(args.files, args.mode, args.base, args.head))
    elif args.check == "private-path":
        all_errors.extend(_check_private_paths(args.files, args.mode, args.base, args.head))
    elif args.check == "sensitive":
        all_errors.extend(_check_sensitive(args.files, args.mode, args.base, args.head))
    elif args.check == "llm-privacy":
        errors, notices = _check_llm_privacy(args.files, args.mode, args.base, args.head)
        sys.stdout.write("".join(f"{notice}\n" for notice in notices))
        all_errors.extend(errors)
    else:
        for filepath in args.files:
            if args.check == "todo":
                all_errors.extend(_check_todo(filepath, args.mode, args.base, args.head))
            else:
                all_errors.extend(_check_print(filepath, args.mode, args.base, args.head))

    if all_errors:
        for err in all_errors:
            print(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
