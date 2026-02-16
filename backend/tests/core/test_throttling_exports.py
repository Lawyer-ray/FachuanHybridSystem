def test_core_throttling_delegates_to_infrastructure_throttling():
    from apps.core import throttling
    from apps.core.infrastructure import throttling as infra_throttling

    assert throttling.RateLimiter is infra_throttling.RateLimiter
    assert throttling.rate_limit is infra_throttling.rate_limit
    assert throttling.rate_limit_from_settings is infra_throttling.rate_limit_from_settings
