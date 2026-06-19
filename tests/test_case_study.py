import pytest
from decimal import Decimal
from datetime import date
from src.analytics.case_study import calculate_case_study, CaseStudyRequest, CaseStudyCashflow, ReturnMethod
from src.services.case_study_service import CaseStudyService

def test_calculate_case_study_basic():
    # Product gains 5%, USD/CNY stable at 7.2
    req = CaseStudyRequest(
        opening_value_usd=Decimal("10000"),
        closing_value_usd=Decimal("10500"),
        opening_fx=Decimal("7.2"),
        closing_fx=Decimal("7.2"),
        fee_usd=Decimal("0"),
        cny_benchmark_return=Decimal("0.03")
    )
    res = calculate_case_study(req)

    assert res.usd_product_return == Decimal("0.05")
    assert res.total_change_cny == Decimal("3600") # (10500*7.2 - 10000*7.2)
    assert res.local_pnl_cny == Decimal("3600")
    assert res.fx_effect_cny == Decimal("0")
    assert res.interaction_cny == Decimal("0")
    assert res.relative_alpha_cny == Decimal("1440") # 3600 - (10000*7.2*0.03)

def test_calculate_case_study_fx_loss():
    # Product gains 5%, USD/CNY drops from 7.2 to 7.0
    req = CaseStudyRequest(
        opening_value_usd=Decimal("10000"),
        closing_value_usd=Decimal("10500"),
        opening_fx=Decimal("7.2"),
        closing_fx=Decimal("7.0"),
        fee_usd=Decimal("0"),
        cny_benchmark_return=Decimal("0.03")
    )
    res = calculate_case_study(req)

    # op_cny = 72000, cl_cny = 73500, total_change = 1500
    assert res.total_change_cny == Decimal("1500")

    # Bridge:
    # local_pnl = 500 * 7.2 = 3600
    # fx_effect = 10000 * (7.0 - 7.2) = -2000
    # interaction = 500 * (7.0 - 7.2) = -100
    # 3600 - 2000 - 100 = 1500 (Matches!)

    assert res.local_pnl_cny == Decimal("3600")
    assert res.fx_effect_cny == Decimal("-2000")
    assert res.interaction_cny == Decimal("-100")
    assert res.unclassified_cny == Decimal("0")

def test_calculate_case_study_with_fees():
    req = CaseStudyRequest(
        opening_value_usd=Decimal("10000"),
        closing_value_usd=Decimal("10500"),
        opening_fx=Decimal("7.2"),
        closing_fx=Decimal("7.2"),
        fee_usd=Decimal("50")
    )
    res = calculate_case_study(req)

    # Gross local pnl = 10500 - 10000 + 50 = 550
    # usd_ret = 550 / 10000 = 5.5%
    assert res.usd_product_return == Decimal("0.055")
    # fees_friction_cny = -50 * 7.2 = -360
    assert res.fees_friction_cny == Decimal("-360")

def test_case_study_service_analyze():
    svc = CaseStudyService()
    payload = {
        "opening_value_usd": 10000,
        "closing_value_usd": 10500,
        "opening_fx": 7.2,
        "closing_fx": 7.1,
        "fee_usd": 50,
        "cny_benchmark_return": 0.03,
        "include_scenarios": True
    }
    resp = svc.analyze(payload)
    assert resp["success"] is True
    data = resp["data"]
    assert "analysis" in data
    assert "scenarios" in data
    assert "journal_draft" in data

    # Check scenario matrix size (5x5)
    assert len(data["scenarios"]) == 5
    assert len(data["scenarios"][0]) == 5

    # Check journal draft fields
    journal = data["journal_draft"]
    assert "thesis" in journal
    assert "baseline" in journal
    assert "invalidation_conditions" in journal

def test_case_study_bridge_identity():
    # More complex case to verify bridge
    req = CaseStudyRequest(
        opening_value_usd=Decimal("10000"),
        closing_value_usd=Decimal("9800"),
        opening_fx=Decimal("7.2"),
        closing_fx=Decimal("7.5"),
        fee_usd=Decimal("100"),
        cny_benchmark_return=Decimal("0.02")
    )
    res = calculate_case_study(req)

    # total_change_cny = 9800*7.5 - 10000*7.2 = 73500 - 72000 = 1500
    # explained = local_pnl + fx_effect + interaction + fees
    # gross_local_usd = 9800 - 10000 + 100 = -100
    # local_pnl_cny = -100 * 7.2 = -720
    # fx_effect_cny = 10000 * (7.5 - 7.2) = 3000
    # interaction_cny = -100 * (7.5 - 7.2) = -30
    # fees_cny = -100 * 7.5 = -750
    # explained = -720 + 3000 - 30 - 750 = 1500

    assert res.total_change_cny == Decimal("1500")
    assert res.unclassified_cny == Decimal("0")
    assert res.local_pnl_cny == Decimal("-720")
    assert res.fx_effect_cny == Decimal("3000")
    assert res.interaction_cny == Decimal("-30")
    assert res.fees_friction_cny == Decimal("-750")
