"""证件号码校验位验证（纯函数）。"""

from __future__ import annotations

# 身份证号校验位（ISO 7064 MOD 11-2）
_ID_CARD_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CARD_CHECK_CODES = "10X98765432"

# 统一社会信用代码校验字符集（GB 32100）
_CREDIT_CODE_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"  # pragma: allowlist secret
_CREDIT_CODE_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)  # pragma: allowlist secret


def _validate_id_number(id_number: str | None) -> bool:
    """身份证号校验位验证（ISO 7064 MOD 11-2）。"""
    if not id_number or len(id_number) != 18:
        return False
    if not id_number[:17].isdigit():
        return False
    checksum = sum(int(c) * w for c, w in zip(id_number[:17], _ID_CARD_WEIGHTS))
    return _ID_CARD_CHECK_CODES[checksum % 11] == id_number[17].upper()


def _validate_credit_code(code: str | None) -> bool:
    """统一社会信用代码校验（GB 32100）。"""
    if not code or len(code) != 18:
        return False
    if any(ch not in _CREDIT_CODE_CHARS for ch in code):
        return False
    values = [_CREDIT_CODE_CHARS.index(ch) for ch in code[:17]]
    checksum = sum(v * w for v, w in zip(values, _CREDIT_CODE_WEIGHTS)) % 31
    return _CREDIT_CODE_CHARS[(31 - checksum) % 31] == code[17]
