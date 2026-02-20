import logging
import re

from apps.core.models import SystemConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


_SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|bearer|cookie|session|private)",
    re.IGNORECASE,
)
_LIKELY_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-\.=]{24,}$")


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(key or ""))


def _safe_preview(key: str, value: str | None, *, max_len: int = 30) -> str:
    if value is None:
        return "(空)"
    if not isinstance(value, str):
        value = str(value)
    if _is_sensitive_key(key) or _LIKELY_TOKEN_RE.match(value):
        return f"<redacted len={len(value)}>"
    if len(value) <= max_len:
        return value
    return f"{value[:max_len]}..."


def _print_section(title: str) -> None:
    logger.info("=" * 60)
    logger.info(title)
    logger.info("=" * 60)


_print_section("数据库中的 SILICON 相关配置：")
silicon_configs = SystemConfig.objects.filter(key__icontains="SILICON")
logger.info(f"共 {silicon_configs.count()} 条\n")
for config in silicon_configs:
    logger.info(f"  {config.key} = {_safe_preview(config.key, config.value)}")

logger.info("")
_print_section("数据库中的 LLM 相关配置：")
llm_configs = SystemConfig.objects.filter(key__icontains="LLM")
logger.info(f"共 {llm_configs.count()} 条\n")
for config in llm_configs:
    logger.info(f"  {config.key} = {_safe_preview(config.key, config.value)}")

logger.info("")
_print_section("测试 SystemConfigService：")
from apps.core.services import SystemConfigService

service = SystemConfigService()
test_keys = ["SILICONFLOW_API_KEY", "SILICONFLOW.API_KEY", "siliconflow_api_key"]
for key in test_keys:
    value = service.get_config(key) # type: ignore
    if value:
        logger.info(f"  ✓ {key} = {_safe_preview(key, value, max_len=10)}") # type: ignore
    else:
        logger.info(f"  ✗ {key} (未找到)")

logger.info("")
_print_section("测试 LLMConfig：")
from apps.core.llm.config import LLMConfig

api_key = LLMConfig.get_api_key()
api_key_len = len(api_key) if api_key else 0
logger.info(f"  API Key: {_safe_preview('api_key', api_key, max_len=10)} (长度: {api_key_len})")
logger.info(f"  Base URL: {LLMConfig.get_base_url()}")
logger.info(f"  Model: {LLMConfig.get_default_model()}")
