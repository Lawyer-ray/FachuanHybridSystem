"""关键词规范化与 tuning config 单元测试。"""
from __future__ import annotations

import pytest

from apps.legal_research.services.keywords import normalize_keyword_query
from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig


# ── normalize_keyword_query ────────────────────────────────────────────────

def test_normalize_basic() -> None:
    """基本规范化。"""
    assert normalize_keyword_query("买卖 合同") == "买卖 合同"


def test_normalize_comma_separated() -> None:
    """逗号分隔。"""
    result = normalize_keyword_query("买卖,合同,纠纷")
    assert result == "买卖 合同 纠纷"


def test_normalize_chinese_comma() -> None:
    """中文逗号分隔。"""
    result = normalize_keyword_query("买卖，合同，纠纷")
    assert result == "买卖 合同 纠纷"


def test_normalize_semicolon() -> None:
    """分号分隔。"""
    result = normalize_keyword_query("买卖;合同;纠纷")
    assert result == "买卖 合同 纠纷"


def test_normalize_chinese_semicolon() -> None:
    """中文分号分隔。"""
    result = normalize_keyword_query("买卖；合同；纠纷")
    assert result == "买卖 合同 纠纷"


def test_normalize_dunhao() -> None:
    """顿号分隔。"""
    result = normalize_keyword_query("买卖、合同、纠纷")
    assert result == "买卖 合同 纠纷"


def test_normalize_newline() -> None:
    """换行分隔。"""
    result = normalize_keyword_query("买卖\n合同\n纠纷")
    assert result == "买卖 合同 纠纷"


def test_normalize_deduplication() -> None:
    """去重。"""
    result = normalize_keyword_query("买卖 买卖 合同")
    assert result == "买卖 合同"


def test_normalize_empty() -> None:
    """空字符串返回空。"""
    assert normalize_keyword_query("") == ""


def test_normalize_whitespace_only() -> None:
    """纯空格返回空。"""
    assert normalize_keyword_query("   ") == ""


def test_normalize_none() -> None:
    """None 返回空。"""
    assert normalize_keyword_query(None) == ""


def test_normalize_mixed_separators() -> None:
    """混合分隔符。"""
    result = normalize_keyword_query("买卖，合同;纠纷 违约")
    assert result == "买卖 合同 纠纷 违约"


# ── LegalResearchTuningConfig ──────────────────────────────────────────────

def test_config_default_values() -> None:
    """默认值正确。"""
    config = LegalResearchTuningConfig()
    assert config.recall_weight_keyword == 0.18
    assert config.passage_top_k == 5
    assert config.reranker_enabled is False


def test_config_normalized_recall_weights_sum_to_one() -> None:
    """默认权重归一化后和为 1。"""
    config = LegalResearchTuningConfig()
    weights = config.normalized_recall_weights
    assert abs(sum(weights) - 1.0) < 0.001


def test_config_normalized_recall_weights_custom() -> None:
    """自定义权重归一化。"""
    config = LegalResearchTuningConfig(
        recall_weight_keyword=1.0,
        recall_weight_summary=1.0,
        recall_weight_bm25=1.0,
        recall_weight_vector=1.0,
        recall_weight_passage=1.0,
        recall_weight_metadata=1.0,
    )
    weights = config.normalized_recall_weights
    assert abs(sum(weights) - 1.0) < 0.001
    # 所有权重应相等
    for w in weights:
        assert abs(w - 1 / 6) < 0.001


def test_config_normalized_recall_weights_all_zero() -> None:
    """全零权重使用默认值归一化。"""
    config = LegalResearchTuningConfig(
        recall_weight_keyword=0.0,
        recall_weight_summary=0.0,
        recall_weight_bm25=0.0,
        recall_weight_vector=0.0,
        recall_weight_passage=0.0,
        recall_weight_metadata=0.0,
    )
    weights = config.normalized_recall_weights
    assert abs(sum(weights) - 1.0) < 0.001


def test_config_get_int_valid() -> None:
    """_get_int 正常解析。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "5")
    assert LegalResearchTuningConfig._get_int(mock_config, "KEY", 1, 1, 10) == 5


def test_config_get_int_invalid() -> None:
    """_get_int 无效值返回默认值。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "abc")
    assert LegalResearchTuningConfig._get_int(mock_config, "KEY", 3, 1, 10) == 3


def test_config_get_int_clamp_min() -> None:
    """_get_int 下限钳制。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "0")
    assert LegalResearchTuningConfig._get_int(mock_config, "KEY", 5, 1, 10) == 1


def test_config_get_int_clamp_max() -> None:
    """_get_int 上限钳制。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "100")
    assert LegalResearchTuningConfig._get_int(mock_config, "KEY", 5, 1, 10) == 10


def test_config_get_float_valid() -> None:
    """_get_float 正常解析。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "0.5")
    assert LegalResearchTuningConfig._get_float(mock_config, "KEY", 0.0, 0.0, 1.0) == 0.5


def test_config_get_float_clamp() -> None:
    """_get_float 钳制。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "1.5")
    assert LegalResearchTuningConfig._get_float(mock_config, "KEY", 0.5, 0.0, 1.0) == 1.0


def test_config_get_bool_true_values() -> None:
    """_get_bool 各种 true 值。"""
    from types import SimpleNamespace
    for val in ["1", "true", "yes", "on", "y", "True", "YES"]:
        mock_config = SimpleNamespace(get_value=lambda key, default="", v=val: v)
        assert LegalResearchTuningConfig._get_bool(mock_config, "KEY", False) is True


def test_config_get_bool_false_values() -> None:
    """_get_bool 各种 false 值。"""
    from types import SimpleNamespace
    for val in ["0", "false", "no", "off", "n", "False", "NO"]:
        mock_config = SimpleNamespace(get_value=lambda key, default="", v=val: v)
        assert LegalResearchTuningConfig._get_bool(mock_config, "KEY", True) is False


def test_config_get_bool_invalid_returns_default() -> None:
    """_get_bool 无效值返回默认。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "maybe")
    assert LegalResearchTuningConfig._get_bool(mock_config, "KEY", True) is True
    assert LegalResearchTuningConfig._get_bool(mock_config, "KEY", False) is False


def test_config_get_text_truncate() -> None:
    """_get_text 超长截断。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "a" * 200)
    result = LegalResearchTuningConfig._get_text(mock_config, "KEY", "default", max_len=50)
    assert len(result) == 50


def test_config_get_text_empty_returns_default() -> None:
    """_get_text 空值返回默认。"""
    from types import SimpleNamespace
    mock_config = SimpleNamespace(get_value=lambda key, default="": "")
    assert LegalResearchTuningConfig._get_text(mock_config, "KEY", "default", max_len=50) == "default"
