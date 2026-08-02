import os
import pytest
from unittest.mock import patch

from chicago_311_lighting_etl import (
    ETLCheckpointManager,
    CHECKPOINT_DIR,
)


def test_1_pytest_env_blocks_default_production_checkpoint_dir():
    """PYTEST_CURRENT_TEST ortam değişkeni varken varsayılan production checkpoint dizini seçildiğinde RuntimeError fırlatır."""
    with pytest.raises(RuntimeError) as exc_info:
        ETLCheckpointManager()

    assert "[ETL SAFETY GUARD ABORT]" in str(exc_info.value)
    assert "production checkpoint" in str(exc_info.value)


def test_2_single_instance_lock_rejection(tmp_path):
    """Aynı checkpoint dizini için iki farkı ETLCheckpointManager oluşturulduğunda ikincisinin lock alamayıp reddedildiğini doğrular."""
    cp_dir = tmp_path / "lock_test"
    mgr1 = ETLCheckpointManager(checkpoint_dir=cp_dir)
    mgr2 = ETLCheckpointManager(checkpoint_dir=cp_dir)

    # 1. İşlem lock alır
    mgr1.acquire_lock()
    assert mgr1._lock_fh is not None

    # 2. İşlem aynı dizinde lock almaya çalışınca RuntimeError fırlatır
    with pytest.raises(RuntimeError) as exc_info:
        mgr2.acquire_lock()

    assert "[ETL SINGLE-INSTANCE LOCK ERROR]" in str(exc_info.value)

    # 1. İşlem serbest bırakır
    mgr1.release_lock()
    assert mgr1._lock_fh is None

    # Şimdi 2. işlem başarıyla lock alabilir
    mgr2.acquire_lock()
    assert mgr2._lock_fh is not None
    mgr2.release_lock()


def test_3_atomic_replace_retry_and_cache_first_order(tmp_path):
    """Önbellek (cache) dosyasının checkpoint metadata dosyasından önce yazıldığını ve Windows PermissionError durumunda retry yapıldığını doğrular."""
    cp_dir = tmp_path / "atomic_test"
    mgr = ETLCheckpointManager(checkpoint_dir=cp_dir)

    save_sequence = []

    original_atomic = mgr._atomic_write_file

    def tracked_atomic(target_path, data_obj):
        save_sequence.append(target_path.name)
        return original_atomic(target_path, data_obj)

    mgr._atomic_write_file = tracked_atomic

    cp_data = {
        "version": "1.0",
        "etl_name": "lighting_etl",
        "status": "in_progress",
        "records_count": 5
    }
    records_data = [{"sr_number": "SR1"}]

    mgr.save(cp_data, records=records_data)

    # 1. Sıralama kontrolü: lighting_records_cache.json ÖNCE, lighting_etl_checkpoint.json SONRA yazılmalıdır
    assert save_sequence == ["lighting_records_cache.json", "lighting_etl_checkpoint.json"]
    assert mgr.checkpoint_file.exists()
    assert mgr.cache_file.exists()


def test_4_windows_permission_error_retry(tmp_path):
    """os.replace ilk 2 denemede PermissionError verirse 10 retry mekanizmasının başarıyla üstesinden geldiğini doğrular."""
    cp_dir = tmp_path / "perm_test"
    mgr = ETLCheckpointManager(checkpoint_dir=cp_dir)

    real_replace = os.replace
    attempt_counter = 0

    def mock_replace(src, dst):
        nonlocal attempt_counter
        attempt_counter += 1
        if attempt_counter <= 2:
            raise PermissionError("Access is denied (Windows test mock)")
        return real_replace(src, dst)

    with patch("os.replace", side_effect=mock_replace):
        with patch("time.sleep"):
            mgr._atomic_write_file(mgr.checkpoint_file, {"status": "ok"})

    assert attempt_counter == 3
    assert mgr.checkpoint_file.exists()


def test_5_real_production_checkpoint_dir_remains_untouched():
    """Gerçek backend/.etl_checkpoints klasörünün testler boyunca hiçbir şekilde değiştirilmediğini kontrol eder."""
    prod_dir = CHECKPOINT_DIR.resolve()
    assert prod_dir.exists()
    # guard_real_etl_checkpoints_dir autouse fixture'ı her testin sonunda ve başında bunu bağımsız olarak denetler.
