"""Finance API integration tests."""

from __future__ import annotations

import json

import pytest

from apps.finance.models import LPRRate

# ===================================================================
# LPR Rates
# ===================================================================


@pytest.fixture(autouse=True)
def _no_lpr_auto_sync(monkeypatch):
    """禁止 LPR 计算接口触发真实浏览器同步（本文件只测 API 契约，不测抓取）。

    背景（CI 偶发红）：`/api/v1/lpr/calculate` 在 rate_mode="lpr" 时会先调
    `LPRSyncService().sync_if_needed()`，数据“过期”时会启动 CloakBrowser 去
    下载浏览器二进制并抓官网。本文件造的 2024 年利率相对“今天”必然过期，
    于是每次跑都会走真实下载——CI 上下载源超时（The read operation timed out）
    就会把用例卡到 pytest-timeout 60s 自杀，并连带 idle-in-transaction 报错。

    实测同一 PR 连续 3 次绿、第 4 次红，根因是外部网络，不是业务逻辑。
    抓取链路由 tests/ci/unit/finance/ 下的服务层用例覆盖，这里应该 hermetic。
    """
    from apps.finance.services.lpr import LPRSyncService

    def _skip_sync(self):
        return {"synced": False, "sync_result": None, "error": None}

    monkeypatch.setattr(LPRSyncService, "sync_if_needed", _skip_sync, raising=True)


@pytest.mark.django_db
def test_list_lpr_rates(authenticated_client):
    LPRRate.objects.create(
        effective_date="2024-01-01",
        rate_1y=3.45,
        rate_5y=3.95,
        source="manual",
        is_auto_synced=False,
    )
    resp = authenticated_client.get("/api/v1/lpr/rates")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1


@pytest.mark.django_db
def test_list_lpr_rates_with_date_filter(authenticated_client):
    LPRRate.objects.create(effective_date="2024-01-01", rate_1y=3.45, rate_5y=3.95, source="manual")
    LPRRate.objects.create(effective_date="2024-06-01", rate_1y=3.35, rate_5y=3.85, source="manual")
    resp = authenticated_client.get("/api/v1/lpr/rates", {"start_date": "2024-03-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1


@pytest.mark.django_db
def test_get_latest_lpr_rate(authenticated_client):
    LPRRate.objects.create(effective_date="2024-07-01", rate_1y=3.35, rate_5y=3.85, source="manual")
    resp = authenticated_client.get("/api/v1/lpr/rates/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rate_1y"] is not None


@pytest.mark.django_db
def test_get_latest_lpr_rate_not_found(authenticated_client):
    # Clear all rates
    LPRRate.objects.all().delete()
    resp = authenticated_client.get("/api/v1/lpr/rates/latest")
    # May return 404 or 200 with error depending on implementation
    assert resp.status_code in (404, 200, 500)
    # 无数据时服务抛 NotFoundError → 404 错误信封
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "LPR_RATE_NOT_FOUND"
    assert body["message"] == "暂无LPR利率数据"
    assert "rate_1y" not in body  # 错误响应不得夹带利率数据


@pytest.mark.django_db
def test_get_sync_status(authenticated_client):
    LPRRate.objects.create(effective_date="2024-01-01", rate_1y=3.45, rate_5y=3.95, source="manual")
    resp = authenticated_client.get("/api/v1/lpr/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_records" in data


@pytest.mark.django_db
def test_calculate_interest(authenticated_client):
    LPRRate.objects.create(effective_date="2020-01-01", rate_1y=4.15, rate_5y=4.80, source="manual")
    LPRRate.objects.create(effective_date="2024-07-01", rate_1y=3.35, rate_5y=3.85, source="manual")
    resp = authenticated_client.post(
        "/api/v1/lpr/calculate",
        data=json.dumps(
            {
                "start_date": "2024-01-01",
                "end_date": "2024-06-30",
                "principal": 100000,
                "rate_mode": "lpr",
                "rate_type": "1y",
                "year_days": 365,
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "total_interest" in data
    assert "periods" in data


@pytest.mark.django_db
def test_calculate_interest_missing_fields(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/lpr/calculate",
        data=json.dumps(
            {
                "rate_mode": "lpr",
                "rate_type": "1y",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "MISSING_REQUIRED_FIELDS" in data.get("code", "")
