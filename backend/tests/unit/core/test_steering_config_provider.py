def test_steering_config_provider_defaults():
    from apps.core.config.steering import SteeringConfigProvider  # type: ignore[attr-defined]

    class DummyConfigManager:
        def __init__(self):
            self._data = {}

        def get(self, key, default=None):
            return self._data.get(key, default)

    provider = SteeringConfigProvider(DummyConfigManager())
    rules = provider.get_loading_rules()

    assert rules
    assert any(r.condition == "always" for r in rules)
