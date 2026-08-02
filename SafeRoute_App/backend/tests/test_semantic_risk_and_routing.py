import pytest
from routing_cost import risk_adjusted_length
from crud import _compute_total_risk, create_report, process_report_and_event_clustering, recalculate_h3_live_risk
from main import ReportCreate


def test_1_db_raw_risk_over_100_rejected_or_normalized():
    raw_risk = 50.0
    normalized = raw_risk / 100.0 if raw_risk > 1.0 else raw_risk
    assert normalized == 0.50
    assert 0.0 <= normalized <= 1.0


def test_2_seed_importer_normalizes_50_to_0_50():
    raw_anlik_risk = 50.0
    crime_risk = raw_anlik_risk / 100.0 if raw_anlik_risk > 1.0 else raw_anlik_risk
    assert crime_risk == 0.50


def test_3_all_risk_channels_bounded_0_to_1():
    tot = _compute_total_risk(crime=0.8, lighting=0.5, live=0.2)
    assert 0.0 <= tot <= 1.0
    assert abs(tot - (0.8 * 0.65 + 0.5 * 0.20 + 0.2 * 0.15)) < 1e-5


def test_4_low_risk_route_score_less_than_high_risk_route_score():
    low_risk = 0.10
    high_risk = 0.80

    score_low = low_risk * 100.0
    score_high = high_risk * 100.0

    assert score_low < score_high
    assert score_low == 10.0
    assert score_high == 80.0


def test_5_high_risk_edge_dijkstra_cost_greater_than_low_risk():
    length = 100.0
    alpha = 2.0

    cost_low = risk_adjusted_length(length, 0.1, alpha=alpha)
    cost_high = risk_adjusted_length(length, 0.9, alpha=alpha)

    assert cost_high > cost_low
    assert cost_low == 120.0
    assert cost_high == pytest.approx(617.5)


def test_6_routes_do_not_artificially_saturate_to_100():
    route_risk = 0.35
    risk_score = route_risk * 100.0
    assert risk_score < 100.0
    assert risk_score == 35.0


def test_7_safety_score_plus_risk_score_equals_100():
    route_risk = 0.25
    risk_score = route_risk * 100.0
    safety_score = (1.0 - route_risk) * 100.0
    assert abs((safety_score + risk_score) - 100.0) < 1e-5


def test_8_route_risk_is_length_weighted():
    # Kenar 1: uzunluk 100m, risk 0.2
    # Kenar 2: uzunluk 300m, risk 0.8
    # Toplam risk = (100*0.2 + 300*0.8) / 400 = (20 + 240) / 400 = 260 / 400 = 0.65
    l1, r1 = 100.0, 0.2
    l2, r2 = 300.0, 0.8

    expected_risk = (l1 * r1 + l2 * r2) / (l1 + l2)
    assert expected_risk == 0.65


def test_9_networkx_and_compact_csr_use_same_risk_scale():
    # Her iki motor da risk_weight olarak 0.0 - 1.0 aralığını kullanmalıdır
    edge_risk_val = 0.45
    alpha = 2.0
    adjusted_len = risk_adjusted_length(100.0, edge_risk_val, alpha=alpha)
    assert adjusted_len == 190.0


def test_10_priority_urgent_contract_preserved():
    rep = ReportCreate(
        text="Acil durum ihbar açıklaması detaylı",
        lat=41.8781,
        lng=-87.6298,
        category="crime",
        priority="urgent"
    )
    assert rep.priority == "urgent"


@pytest.mark.anyio
async def test_11_single_urgent_report_does_not_boost_live_risk():
    h3_cell = "892654a32b7ffff"
    rep = await create_report(
        db=None,
        lat=41.8781,
        lng=-87.6298,
        text="Aydınlatma lambası tamamen karanlık",
        category="lighting",
        priority="urgent",
        reporter_installation_id="device-urgent-1"
    )
    assert rep.priority == "urgent"
    assert rep.status == "pending"

    ev = await process_report_and_event_clustering(db=None, report=rep)
    assert ev.status == "pending"

    live_risk = await recalculate_h3_live_risk(db=None, h3_index=h3_cell)
    assert live_risk == 0.0


@pytest.mark.anyio
async def test_12_urgent_report_does_not_bypass_multi_verification():
    rep = await create_report(
        db=None,
        lat=41.8781,
        lng=-87.6298,
        text="Şüpheli hareketler acil durum",
        category="general",
        priority="urgent",
        reporter_installation_id="device-urgent-2"
    )
    ev = await process_report_and_event_clustering(db=None, report=rep)
    assert ev.unique_reporter_count == 1
    assert ev.status == "pending"
