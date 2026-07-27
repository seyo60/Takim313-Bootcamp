# backend/tests/test_etl.py
"""
Chicago Crime & 311 Lighting ETL Boru Hattı ve Çok Etkenli Risk Formülü Birim Testleri.
"""

from datetime import datetime, timezone, timedelta
import pytest
import h3

import crud
from chicago_crime_etl import get_crime_severity, process_crime_records
from chicago_311_lighting_etl import (
    get_lighting_severity,
    compute_lighting_ticket_risk,
    process_lighting_records,
)


def test_crime_severity_categorization():
    assert get_crime_severity("HOMICIDE") == 1.0
    assert get_crime_severity("BATTERY") == 1.0
    assert get_crime_severity("ASSAULT") == 1.0
    assert get_crime_severity("BURGLARY") == 0.6
    assert get_crime_severity("THEFT") == 0.6
    assert get_crime_severity("NARCOTICS") == 0.3
    assert get_crime_severity("OTHER OFFENSE") == 0.3


def test_process_crime_records_h3_aggregation():
    ref_dt = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)

    raw_records = [
        {
            "id": "1",
            "date": (ref_dt - timedelta(days=2)).isoformat(),
            "primary_type": "BATTERY",
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "id": "2",
            "date": (ref_dt - timedelta(days=15)).isoformat(),
            "primary_type": "THEFT",
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "id": "3",
            "date": (ref_dt - timedelta(days=60)).isoformat(),
            "primary_type": "BURGLARY",
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
    ]

    h3_results = process_crime_records(raw_records, reference_date=ref_dt)
    expected_h3 = h3.latlng_to_cell(41.8781, -87.6298, 9)

    assert expected_h3 in h3_results
    cell_data = h3_results[expected_h3]

    assert cell_data["crime_7d"] == 1
    assert cell_data["crime_30d"] == 2
    assert cell_data["crime_90d"] == 3
    assert cell_data["violent_crime_30d"] == 1
    assert 0.0 <= cell_data["risk_crime"] <= 1.0


def test_lighting_severity_categorization():
    assert get_lighting_severity("Street Light Out Complaint") == 0.35
    assert get_lighting_severity("Street Light - All Out Complaint") == 0.80
    assert get_lighting_severity("Viaduct Light Out Complaint") == 0.85
    assert get_lighting_severity("Traffic Signal Out Complaint") == 0.75


def test_compute_lighting_ticket_risk_status_and_decay():
    ref_dt = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    recent_open_dt = ref_dt - timedelta(days=10)

    # 1. Açık ve yeni arıza -> status_factor=1.0, yüksek risk
    risk_open, status_factor, time_factor = compute_lighting_ticket_risk(
        status="Open",
        created_dt=recent_open_dt,
        reference_dt=ref_dt,
        severity=0.85
    )
    assert status_factor == 1.0
    assert time_factor > 0.9
    assert risk_open > 0.7

    # 2. Tamamlanan arıza -> status_factor=0.0, aktif risk 0
    risk_completed, status_completed, _ = compute_lighting_ticket_risk(
        status="Completed",
        created_dt=recent_open_dt,
        reference_dt=ref_dt,
        severity=0.85
    )
    assert status_completed == 0.0
    assert risk_completed == 0.0


def test_process_lighting_records_aggregation():
    ref_dt = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)

    raw_lighting = [
        {
            "sr_type": "Street Light - All Out Complaint",
            "status": "Open",
            "created_date": (ref_dt - timedelta(days=5)).isoformat(),
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "sr_type": "Viaduct Light Out Complaint",
            "status": "In Progress",
            "created_date": (ref_dt - timedelta(days=12)).isoformat(),
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "sr_type": "Street Light - One Out Complaint",
            "status": "Completed",
            "created_date": (ref_dt - timedelta(days=30)).isoformat(),
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
    ]

    h3_results = process_lighting_records(raw_lighting, reference_date=ref_dt)
    expected_h3 = h3.latlng_to_cell(41.8781, -87.6298, 9)

    assert expected_h3 in h3_results
    cell_data = h3_results[expected_h3]

    assert cell_data["open_311_lighting_count"] == 2
    assert cell_data["completed_311_lighting_count"] == 1
    assert 0.0 < cell_data["risk_lighting"] <= 1.0


def test_multi_factor_risk_formula():
    # R_total = 0.65*crime + 0.20*lighting + 0.15*live
    crime = 0.8
    lighting = 0.5
    live = 0.2

    expected_total = (0.8 * 0.65) + (0.5 * 0.20) + (0.2 * 0.15)  # 0.52 + 0.10 + 0.03 = 0.65
    calc_total = crud._compute_total_risk(crime=crime, lighting=lighting, live=live)

    assert abs(calc_total - expected_total) < 1e-6


def test_lighting_deduplication():
    ref_dt = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    raw_lighting = [
        {
            "sr_number": "SR12345",
            "sr_type": "Street Light - All Out Complaint",
            "status": "Open",
            "created_date": ref_dt.isoformat(),
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "sr_number": "SR12345",  # Duplicate SR number
            "sr_type": "Street Light - All Out Complaint",
            "status": "Open",
            "created_date": ref_dt.isoformat(),
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "sr_number": "SR99999",
            "sr_type": "Street Light - All Out Complaint",
            "status": "Open - DUP",  # Duplicate status
            "created_date": ref_dt.isoformat(),
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
    ]

    h3_results = process_lighting_records(raw_lighting, reference_date=ref_dt)
    expected_h3 = h3.latlng_to_cell(41.8781, -87.6298, 9)

    assert expected_h3 in h3_results
    cell_data = h3_results[expected_h3]
    # Only 1 unique ticket should be processed
    assert cell_data["open_311_lighting_count"] == 1

