"""
Steering 条件加载器

Requirements: 8.1
"""

import fnmatch
import threading
from pathlib import Path

from ._configs import SteeringConfigProvider

__all__ = ["SteeringConditionalLoader"]


class SteeringConditionalLoader:
    """Steering 条件加载器"""

    _SPEC_PATTERN_MAP: dict[str, list[str]] = {
        "api-layer": ["**/api/**/*.py", "**/apis/**/*.py"],
        "service-layer": ["**/services/**/*.py", "**/service/**/*.py"],
        "admin-layer": ["**/admin/**/*.py", "**/admins/**/*.py"],
        "model-layer": ["**/models.py", "**/model/**/*.py"],
        "client-module": ["**/client/**/*.py", "**/clients/**/*.py"],
        "cases-module": ["**/cases/**/*.py", "**/case/**/*.py"],
        "contracts-module": ["**/contracts/**/*.py", "**/contract/**/*.py"],
        "organization-module": ["**/organization/**/*.py", "**/org/**/*.py"],
        "automation-module": ["**/automation/**/*.py", "**/auto/**/*.py"],
        "sms-module": ["**/sms/**/*.py"],
    }

    def __init__(self, config_provider: SteeringConfigProvider):
        self.config_provider = config_provider
        self._file_pattern_cache: dict[str, list[str]] = {}
        self._lock = threading.RLock()

    def should_load_specification(self, spec_file_path: str, target_file_path: str) -> bool:
        """判断是否应该加载指定的规范文件"""
        rules = self.config_provider.get_loading_rules()

        for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
            if self._matches_pattern(spec_file_path, rule.pattern):
                if rule.condition == "always":
                    return True
                elif rule.condition == "fileMatch":
                    return self._matches_file_pattern(target_file_path, rule.pattern)
                elif rule.condition == "manual":
                    return False

        return False

    def get_applicable_specifications(self, target_file_path: str) -> list[str]:
        """获取适用于目标文件的规范文件列表"""
        applicable_specs: list[str] = []
        self.config_provider.get_loading_rules()

        steering_root = Path(".kiro/steering")
        if not steering_root.exists():
            return applicable_specs

        for spec_file in steering_root.rglob("*.md"):
            rel_path = spec_file.relative_to(steering_root)
            spec_path = str(rel_path)

            if self.should_load_specification(spec_path, target_file_path):
                applicable_specs.append(spec_path)

        return applicable_specs

    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """检查文件路径是否匹配模式"""
        return fnmatch.fnmatch(file_path, pattern)

    def _matches_file_pattern(self, target_file_path: str, spec_pattern: str) -> bool:
        """检查目标文件是否匹配规范的文件模式"""
        file_patterns = self._get_file_patterns_for_spec(spec_pattern)

        for pattern in file_patterns:
            if fnmatch.fnmatch(target_file_path, pattern):
                return True

        return False

    def _get_file_patterns_for_spec(self, spec_pattern: str) -> list[str]:
        """根据规范模式获取对应的文件模式"""
        with self._lock:
            if spec_pattern in self._file_pattern_cache:
                return self._file_pattern_cache[spec_pattern]

            patterns = self._resolve_file_patterns(spec_pattern)
            self._file_pattern_cache[spec_pattern] = patterns
            return patterns

    def _resolve_file_patterns(self, spec_pattern: str) -> list[str]:
        """根据规范模式解析文件模式"""
        for key, patterns in self._SPEC_PATTERN_MAP.items():
            if key in spec_pattern:
                return patterns
        return ["**/*.py"]
