import json


def test_openapi_v1_schema_invariants():
    from apiSystem.api import api_v1

    schema = api_v1.get_openapi_schema()
    assert schema.get("openapi") == "3.1.0"

    info = schema.get("info") or {}
    assert info.get("title") == "法穿AI案件管理系统 API"
    assert info.get("version") == "1.0.0"

    paths = schema.get("paths") or {}
    assert "/api/v1/" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/token/pair" in paths
    assert all(isinstance(p, str) and p.startswith("/api/v1/") for p in paths.keys())

    components = schema.get("components") or {}
    security_schemes = (components.get("securitySchemes") or {}).get("JWTOrSessionAuth") or {}
    assert security_schemes.get("type") == "http"
    assert security_schemes.get("scheme") == "bearer"

    health_detail = (paths.get("/api/v1/health/detail") or {}).get("get") or {}
    raw = json.dumps(health_detail, ensure_ascii=False, sort_keys=True, default=str)
    assert "JWTOrSessionAuth" in raw
