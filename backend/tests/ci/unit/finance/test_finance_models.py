"""finance app Model 单元测试

覆盖 LPRRate 的 property、__str__。
"""

import pytest
from decimal import Decimal
from datetime import date

from apps.finance.models.lpr_rate import LPRRate


# ============================================================
# LPRRate
# ============================================================


@pytest.mark.django_db
class TestLPRRate:
    def test_str(self):
        rate = LPRRate.objects.create(
            effective_date=date(2025, 1, 20),
            rate_1y=Decimal("3.10"),
            rate_5y=Decimal("3.60"),
        )
        result = str(rate)
        assert "2025-01-20" in result
        assert "3.10" in result
        assert "3.60" in result

    def test_rate_1y_decimal(self):
        rate = LPRRate(rate_1y=Decimal("3.45"))
        assert rate.rate_1y_decimal == Decimal("0.0345")

    def test_rate_5y_decimal(self):
        rate = LPRRate(rate_5y=Decimal("3.95"))
        assert rate.rate_5y_decimal == Decimal("0.0395")

    def test_rate_1y_decimal_exact(self):
        rate = LPRRate(rate_1y=Decimal("3.00"))
        assert rate.rate_1y_decimal == Decimal("0.03")

    def test_rate_5y_decimal_exact(self):
        rate = LPRRate(rate_5y=Decimal("4.20"))
        assert rate.rate_5y_decimal == Decimal("0.0420")

    def test_effective_date_unique(self):
        LPRRate.objects.create(
            effective_date=date(2025, 6, 20),
            rate_1y=Decimal("3.00"),
            rate_5y=Decimal("3.50"),
        )
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            LPRRate.objects.create(
                effective_date=date(2025, 6, 20),
                rate_1y=Decimal("3.10"),
                rate_5y=Decimal("3.60"),
            )

    def test_source_field(self):
        rate = LPRRate.objects.create(
            effective_date=date(2025, 7, 20),
            rate_1y=Decimal("3.00"),
            rate_5y=Decimal("3.50"),
            source="中国人民银行官网",
        )
        assert rate.source == "中国人民银行官网"

    def test_is_auto_synced_default(self):
        rate = LPRRate.objects.create(
            effective_date=date(2025, 8, 20),
            rate_1y=Decimal("3.00"),
            rate_5y=Decimal("3.50"),
        )
        assert rate.is_auto_synced is False
