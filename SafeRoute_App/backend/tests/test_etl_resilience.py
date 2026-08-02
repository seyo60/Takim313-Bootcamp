import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import requests

from chicago_crime_etl import fetch_chicago_crimes, run_crime_etl, ETLFetchError as CrimeETLFetchError
from chicago_311_lighting_etl import fetch_chicago_311_lighting, run_lighting_etl, ETLFetchError as LightingETLFetchError


@patch("requests.get")
def test_1_lighting_5000_records_makes_5_requests_with_limit_1000(mock_get, tmp_checkpoint_mgr):
    """Lighting ETL max_records=5000 ile tek devasa istek yerine 5 adet 1000 limitli sayfalama isteği yapar."""
    call_counter = 0
    def side_effect(*args, **kwargs):
        nonlocal call_counter
        resp = MagicMock()
        resp.status_code = 200
        call_counter += 1
        resp.json.return_value = [
            {
                "sr_number": f"SR_{call_counter}_{i}",
                "created_date": f"2026-07-{(28 - call_counter):02d}T12:00:00.000",
                "sr_type": "Street Light Out Complaint",
                "status": "Open",
                "latitude": "41.8781",
                "longitude": "-87.6298"
            } for i in range(1000)
        ]
        return resp

    mock_get.side_effect = side_effect

    records = fetch_chicago_311_lighting(max_records=5000, checkpoint_mgr=tmp_checkpoint_mgr)

    assert len(records) == 5000
    assert mock_get.call_count == 5
    for call_args in mock_get.call_args_list:
        params = call_args[1]["params"]
        assert params["$limit"] <= 1000


@patch("requests.get")
def test_2_crime_page_limit_capped_at_5000(mock_get):
    """Crime ETL sayfa limiti en fazla 5000 olacak şekilde kapsüllenir."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "id": f"{i}",
            "date": "2026-07-28T12:00:00.000",
            "primary_type": "BATTERY",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        } for i in range(5000)
    ]
    mock_get.return_value = mock_resp

    records = fetch_chicago_crimes(limit=50000, max_records=5000)

    assert len(records) == 5000
    params = mock_get.call_args[1]["params"]
    assert params["$limit"] == 5000


@patch("time.sleep")
@patch("requests.get")
def test_3_http_429_respects_retry_after(mock_get, mock_sleep):
    """429 Too Many Requests durumunda Retry-After başlığına uyulur ve tekrar denenir."""
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "2.5"}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = [
        {
            "id": "100",
            "date": "2026-07-28T12:00:00.000",
            "primary_type": "BATTERY",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        }
    ]

    mock_get.side_effect = [resp_429, resp_200]

    records = fetch_chicago_crimes(max_records=1)

    assert len(records) == 1
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(2.5)


@patch("time.sleep")
@patch("requests.get")
def test_4_http_502_503_timeout_retries_with_exponential_backoff(mock_get, mock_sleep, tmp_checkpoint_mgr):
    """502/503 ve timeout hatalarında katlanarak artan gecikme (backoff) uygulanır."""
    resp_502 = MagicMock()
    resp_502.status_code = 502
    resp_502.headers = {}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = [
        {
            "sr_number": "SR1",
            "created_date": "2026-07-28T12:00:00.000",
            "sr_type": "Street Light Out Complaint",
            "status": "Open",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        }
    ]

    mock_get.side_effect = [requests.Timeout("Connection timed out"), resp_502, resp_200]

    records = fetch_chicago_311_lighting(max_records=1, checkpoint_mgr=tmp_checkpoint_mgr)

    assert len(records) == 1
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert 1.0 <= delays[0] <= 2.0
    assert 2.0 <= delays[1] <= 3.5


@pytest.mark.anyio
@patch("requests.get")
@patch("crud.upsert_crime_data", new_callable=AsyncMock)
@patch("crud.record_etl_run", new_callable=AsyncMock)
async def test_5_persistent_api_error_raises_etl_fetch_error_and_zero_db_calls(mock_etl_run, mock_upsert, mock_get):
    """Kalıcı API hatasında (3 deneme başarısız) ETLFetchError fırlatılır ve DB'ye HİÇBİR ŞEY yazılmaz."""
    resp_500 = MagicMock()
    resp_500.status_code = 500
    resp_500.headers = {}
    mock_get.return_value = resp_500

    with pytest.raises(CrimeETLFetchError) as exc_info:
        await run_crime_etl(max_records=100, dry_run=False)

    assert "deneme sonrasında başarısız" in str(exc_info.value)
    assert not mock_upsert.called
    assert not mock_etl_run.called


@pytest.mark.anyio
@patch("requests.get")
@patch("crud.upsert_lighting_data", new_callable=AsyncMock)
@patch("crud.record_etl_run", new_callable=AsyncMock)
async def test_6_page_2_failure_prevents_partial_db_writes(mock_etl_run, mock_upsert, mock_get, tmp_checkpoint_mgr):
    """İkinci sayfada hata oluştuğunda birinci sayfanın kısmi verisi DB'ye ASLA yazılmaz."""
    resp_page1 = MagicMock()
    resp_page1.status_code = 200
    resp_page1.json.return_value = [
        {
            "sr_number": f"SR_{i}",
            "created_date": "2026-07-28T12:00:00.000",
            "sr_type": "Street Light Out Complaint",
            "status": "Open",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        } for i in range(1000)
    ]

    resp_page2_503 = MagicMock()
    resp_page2_503.status_code = 503
    resp_page2_503.headers = {}

    # 1. Sayfa başarılı, 2. Sayfa 503 hatası fırlatır (Adaptif sayfa küçültmeler dahil tüm retries 503 alır)
    mock_get.side_effect = [resp_page1] + [resp_page2_503] * 50

    with patch("time.sleep"):
        with pytest.raises(LightingETLFetchError):
            await run_lighting_etl(max_records=2000, dry_run=False, checkpoint_mgr=tmp_checkpoint_mgr)

    assert not mock_upsert.called
    assert not mock_etl_run.called


@pytest.mark.anyio
@patch("requests.get")
@patch("crud.upsert_crime_data", new_callable=AsyncMock)
@patch("crud.record_etl_run", new_callable=AsyncMock)
async def test_7_successful_empty_api_response_in_production_raises_error(mock_etl_run, mock_upsert, mock_get):
    """Üretim modunda (non-dry-run) API 0 kayıt döndürürse güvenlik nedeniyle ETLFetchError üretilir ve DB korunur."""
    resp_empty = MagicMock()
    resp_empty.status_code = 200
    resp_empty.json.return_value = []
    mock_get.return_value = resp_empty

    with pytest.raises(CrimeETLFetchError) as exc_info:
        await run_crime_etl(max_records=100, dry_run=False)

    assert "0 kayıt döndürdü" in str(exc_info.value)
    assert not mock_upsert.called
    assert not mock_etl_run.called


@pytest.mark.anyio
@patch("requests.get")
@patch("crud.upsert_lighting_data", new_callable=AsyncMock)
@patch("crud.record_etl_run", new_callable=AsyncMock)
async def test_8_dry_run_mode_never_writes_to_db(mock_etl_run, mock_upsert, mock_get, tmp_checkpoint_mgr):
    """--dry-run modunda veritabanı yazma fonksiyonları çağrılmaz."""
    resp_valid = MagicMock()
    resp_valid.status_code = 200
    resp_valid.json.return_value = [
        {
            "sr_number": "SR1",
            "created_date": "2026-07-28T12:00:00.000",
            "sr_type": "Street Light Out Complaint",
            "status": "Open",
            "latitude": "41.8781",
            "longitude": "-87.6298"
        }
    ]
    mock_get.return_value = resp_valid

    res = await run_lighting_etl(max_records=10, dry_run=True, checkpoint_mgr=tmp_checkpoint_mgr)

    assert len(res) > 0
    assert not mock_upsert.called
    assert not mock_etl_run.called
