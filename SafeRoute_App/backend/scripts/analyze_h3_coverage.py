"""H3 risk kapsam analizi — graf vs veritabanı boşluk raporu.

Kullanım:
    cd SafeRoute_App/backend
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    .\.venv\Scripts\python.exe scripts/analyze_h3_coverage.py
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

import h3

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from h3_policy import LEGACY_H3_RESOLUTION, parent_cell, validate_h3_resolution
from main import AsyncSessionLocal
from routing_engine import CompactCSREngine
from sqlalchemy import text


async def load_db_cells() -> dict[str, dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT h3_index, h3_resolution, total_risk, risk_crime, risk_lighting, risk_live
                FROM h3_heatmap
                """
            )
        )
        rows = result.fetchall()
    return {
        str(row.h3_index): {
            "resolution": int(row.h3_resolution),
            "total_risk": float(row.total_risk or 0.0),
            "risk_crime": float(row.risk_crime or 0.0),
            "risk_lighting": float(row.risk_lighting or 0.0),
            "risk_live": float(row.risk_live or 0.0),
        }
        for row in rows
    }


def build_parent_aggregates(res10_cells: dict[str, dict], parent_resolution: int) -> dict[str, dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for h3_index, payload in res10_cells.items():
        if infer_resolution(h3_index) != 10:
            continue
        parent = parent_cell(h3_index, parent_resolution)
        buckets[parent].append(payload)

    aggregates: dict[str, dict] = {}
    for parent, items in buckets.items():
        n = len(items)
        aggregates[parent] = {
            "child_count": n,
            "total_risk": sum(item["total_risk"] for item in items) / n,
            "risk_crime": sum(item["risk_crime"] for item in items) / n,
            "risk_lighting": sum(item["risk_lighting"] for item in items) / n,
            "risk_live": sum(item["risk_live"] for item in items) / n,
        }
    return aggregates


def infer_resolution(h3_index: str) -> int:
    try:
        return int(h3.get_resolution(str(h3_index)))
    except Exception:
        return LEGACY_H3_RESOLUTION


async def main() -> None:
    routing_resolution = validate_h3_resolution(settings.routing_h3_resolution)
    parent_resolution = validate_h3_resolution(settings.h3_parent_resolution)

    engine = CompactCSREngine()
    engine.load_graph(settings.compact_graph_path)
    graph_cells = set(engine.h3_keys_map.keys())

    db_cells = await load_db_cells()
    res10_db = {k: v for k, v in db_cells.items() if v["resolution"] == routing_resolution}
    res9_db = {k: v for k, v in db_cells.items() if v["resolution"] == parent_resolution}

    missing = graph_cells - set(res10_db.keys())
    parent_aggs = build_parent_aggregates(res10_db, parent_resolution)

    fillable_from_parent = 0
    fillable_from_res9_row = 0
    still_orphan = 0
    for cell in missing:
        parent = parent_cell(cell, parent_resolution)
        if parent in res9_db:
            fillable_from_res9_row += 1
        elif parent in parent_aggs:
            fillable_from_parent += 1
        else:
            still_orphan += 1

    covered_now = len(graph_cells) - len(missing)
    covered_after_backfill = covered_now + fillable_from_parent + fillable_from_res9_row
    gap_pct = 100.0 * len(missing) / len(graph_cells)
    after_gap_pct = 100.0 * (len(graph_cells) - covered_after_backfill) / len(graph_cells)

    print("=== H3 Kapsam Analizi ===")
    print(f"Graf hücreleri (res-{routing_resolution}): {len(graph_cells):,}")
    print(f"DB res-{routing_resolution} satırları: {len(res10_db):,}")
    print(f"DB res-{parent_resolution} satırları: {len(res9_db):,}")
    print(f"Graf içinde DB'de eksik: {len(missing):,} ({gap_pct:.1f}%)")
    print()
    print("Eksik hücreler için doldurma potansiyeli:")
    print(f"  res-{parent_resolution} satırı zaten var: {fillable_from_res9_row:,}")
    print(f"  kardeş res-{routing_resolution} ortalamasından: {fillable_from_parent:,}")
    print(f"  hâlâ verisiz kalır: {still_orphan:,}")
    print()
    print(f"Backfill sonrası tahmini kapsam: {covered_after_backfill:,}/{len(graph_cells):,}")
    print(f"Backfill sonrası tahmini boşluk: {after_gap_pct:.1f}%")
    print(f"risk_cell_count (lookup, res10+res9): {len(res10_db) + len(res9_db):,}")


if __name__ == "__main__":
    asyncio.run(main())
