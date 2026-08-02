import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import h3

from chicago_crime_etl import fetch_chicago_crimes, process_crime_records, run_crime_etl
from chicago_311_lighting_etl import (
    fetch_chicago_311_lighting,
    process_lighting_records,
    run_lighting_etl,
    compute_lighting_ticket_risk
)


@patch("requests.get")
def test_1_crime_etl_order_desc_and_batch_limit(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": f"{i}",
            "date": "2026-07-28T12:00:00.000",
            "primary_type": "BATTERY",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        } for i in range(100)
    ]
    mock_get.return_value = mock_resp

    records = fetch_chicago_crimes(max_records=100)

    assert len(records) == 100
    assert mock_get.called
    kwargs = mock_get.call_args[1]
    params = kwargs["params"]
    assert params["$order"] == "date DESC, id ASC"
    assert params["$limit"] == 100


@patch("requests.get")
def test_2_lighting_etl_order_desc_and_batch_limit(mock_get, tmp_checkpoint_mgr):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "sr_number": f"SR{i}",
            "created_date": "2026-07-28T12:00:00.000",
            "sr_type": "Street Light Out Complaint",
            "status": "Open",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        } for i in range(50)
    ]
    mock_get.return_value = mock_resp

    records = fetch_chicago_311_lighting(max_records=50, checkpoint_mgr=tmp_checkpoint_mgr)

    assert len(records) == 50
    assert mock_get.called
    kwargs = mock_get.call_args[1]
    params = kwargs["params"]
    assert params["$order"] == "created_date DESC, sr_number ASC"
    assert params["$limit"] == 50


def test_3_crime_recent_records_aggregation_and_counters():
    ref_dt = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    recent_records = [
        {
            "id": "1",
            "date": (ref_dt - timedelta(days=2)).isoformat(),
            "primary_type": "BATTERY",
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "id": "2",
            "date": (ref_dt - timedelta(days=20)).isoformat(),
            "primary_type": "THEFT",
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
        {
            "id": "3",
            "date": (ref_dt - timedelta(days=50)).isoformat(),
            "primary_type": "BURGLARY",
            "latitude": "41.8781",
            "longitude": "-87.6298",
        },
    ]

    h3_res = process_crime_records(recent_records, reference_date=ref_dt)
    cell = h3_res[h3.latlng_to_cell(41.8781, -87.6298, 9)]

    assert cell["crime_7d"] == 1
    assert cell["crime_30d"] == 2
    assert cell["crime_90d"] == 3
    assert 0.0 < cell["risk_crime"] <= 1.0


def test_4_lighting_open_vs_completed_risk():
    ref_dt = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    created_dt = ref_dt - timedelta(days=5)

    open_risk, status_factor_open, _ = compute_lighting_ticket_risk("Open", created_dt, ref_dt, 0.80)
    assert status_factor_open == 1.0
    assert open_risk > 0.0

    closed_risk, status_factor_closed, _ = compute_lighting_ticket_risk("Completed", created_dt, ref_dt, 0.80)
    assert status_factor_closed == 0.0
    assert closed_risk == 0.0


@pytest.mark.anyio
@patch("requests.get")
@patch("crud.upsert_crime_data")
@patch("crud.record_etl_run")
async def test_5_crime_dry_run_does_not_call_db_writes(mock_etl_run, mock_upsert, mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": "1",
            "date": "2026-07-28T12:00:00.000",
            "primary_type": "BATTERY",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        }
    ]
    mock_get.return_value = mock_resp

    res = await run_crime_etl(max_records=10, dry_run=True)

    assert len(res) > 0
    assert not mock_upsert.called
    assert not mock_etl_run.called


@pytest.mark.anyio
@patch("requests.get")
@patch("crud.upsert_lighting_data")
@patch("crud.record_etl_run")
async def test_6_lighting_dry_run_does_not_call_db_writes(mock_etl_run, mock_upsert, mock_get, tmp_checkpoint_mgr):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "sr_number": "SR123",
            "created_date": "2026-07-28T12:00:00.000",
            "sr_type": "Street Light Out Complaint",
            "status": "Open",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        }
    ]
    mock_get.return_value = mock_resp

    res = await run_lighting_etl(max_records=10, dry_run=True, checkpoint_mgr=tmp_checkpoint_mgr)

    assert len(res) > 0
    assert not mock_upsert.called
    assert not mock_etl_run.called


def test_7_risk_values_strictly_bounded():
    ref_dt = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    records_crime = [
        {
            "id": f"{i}",
            "date": ref_dt.isoformat(),
            "primary_type": "HOMICIDE",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        } for i in range(100)
    ]
    crime_res = process_crime_records(records_crime, reference_date=ref_dt)
    for data in crime_res.values():
        assert 0.0 <= data["risk_crime"] <= 1.0

    records_lighting = [
        {
            "sr_number": f"SR{i}",
            "created_date": ref_dt.isoformat(),
            "sr_type": "Viaduct Light Out Complaint",
            "status": "Open",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        } for i in range(100)
    ]
    lighting_res, _ = process_lighting_records(records_lighting, reference_date=ref_dt)
    for data in lighting_res.values():
        assert 0.0 <= data["risk_lighting"] <= 1.0
