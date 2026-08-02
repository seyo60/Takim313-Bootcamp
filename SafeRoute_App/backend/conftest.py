import os
import sys
from pathlib import Path
import pytest

os.environ.setdefault("APP_ENVIRONMENT", "test")
os.environ.setdefault("REPORTER_HASH_SECRET", "test-only-reporter-hash-secret-0001")
os.environ.setdefault("ROUTING_H3_RESOLUTION", "10")

# Chicago 311 Lighting ETL import for safety guard testing fixture
sys.path.insert(0, str(Path(__file__).parent))
from chicago_311_lighting_etl import ETLCheckpointManager, CHECKPOINT_DIR




@pytest.fixture(autouse=True)
def guard_real_etl_checkpoints_dir():
    """
    Tüm testlerin gerçek backend/.etl_checkpoints klasörüne dokunmasını engeller
    ve test başlangıcı ile bitişi arasında gerçek klasörün değişmediğini doğrular.
    """
    real_checkpoints_dir = CHECKPOINT_DIR.resolve()
    if not real_checkpoints_dir.exists():
        real_checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_dir():
        files_state = {}
        for p in real_checkpoints_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(real_checkpoints_dir)
                try:
                    stat = p.stat()
                    files_state[str(rel)] = (stat.st_size, stat.st_mtime)
                except Exception:
                    pass
        return files_state

    initial_snapshot = _snapshot_dir()

    yield

    final_snapshot = _snapshot_dir()

    if initial_snapshot != final_snapshot:
        added = set(final_snapshot.keys()) - set(initial_snapshot.keys())
        removed = set(initial_snapshot.keys()) - set(final_snapshot.keys())
        modified = {k for k in initial_snapshot.keys() & final_snapshot.keys() if initial_snapshot[k] != final_snapshot[k]}
        raise RuntimeError(
            f"[CRITICAL REGRESSION DETECTED] Test execution mutated real production checkpoint directory at {real_checkpoints_dir}!\n"
            f"Added files: {added}\n"
            f"Removed files: {removed}\n"
            f"Modified files: {modified}"
        )


@pytest.fixture
def tmp_checkpoint_mgr(tmp_path):
    """Her test için izole pytest tmp_path tabanlı ETLCheckpointManager üretir."""
    cp_dir = tmp_path / "checkpoints"
    return ETLCheckpointManager(checkpoint_dir=cp_dir)
