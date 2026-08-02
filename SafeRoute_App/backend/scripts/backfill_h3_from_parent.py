"""Eksik graf H3 hücrelerini ebeveyn/kardeş ortalaması ile doldurur.

Varsayılan dry-run. Gerçek yazma için --execute kullanın.

Kullanım:
    .\.venv\Scripts\python.exe scripts/backfill_h3_from_parent.py
    .\.venv\Scripts\python.exe scripts/backfill_h3_from_parent.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

import h3
from sqlalchemy.dialects.postgresql import insert as pg_insert

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings
from crud import _compute_total_risk
from h3_policy import LEGACY_H3_RESOLUTION, parent_cell, validate_h3_resolution
from main import AsyncSessionLocal
from models import H3HeatmapModel
from routing_engine import CompactCSREngine
from sqlalchemy import select


def infer_resolution(h3_index: str) -> int:
    try:
        return int(h3.get_resolution(str(h3_index)))
    except Exception:
        return LEGACY_H3_RESOLUTION


async def load_res10_cells(session) -> dict[str, H3HeatmapModel]:
    result = await session.execute(
        select(H3HeatmapModel).where(
            H3HeatmapModel.h3_resolution == validate_h3_resolution(settings.routing_h3_resolution)
        )
    )
    return {str(row.h3_index): row for row in result.scalars().all()}


def build_parent_aggregates(res10_rows: dict[str, H3HeatmapModel], parent_resolution: int) -> dict[str, dict]:
    buckets: dict[str, list[H3HeatmapModel]] = defaultdict(list)
    for h3_index, row in res10_rows.items():
        if infer_resolution(h3_index) != 10:
            continue
        buckets[parent_cell(h3_index, parent_resolution)].append(row)

    aggregates: dict[str, dict] = {}
    for parent, items in buckets.items():
        n = len(items)
        aggregates[parent] = {
            "risk_crime": sum(float(row.risk_crime or 0.0) for row in items) / n,
            "risk_lighting": sum(float(row.risk_lighting or 0.0) for row in items) / n,
            "risk_live": sum(float(row.risk_live or 0.0) for row in items) / n,
            "child_count": n,
        }
    return aggregates


def derive_payload(h3_index: str, source: dict, source_kind: str) -> dict:
    lat, lng = h3.cell_to_latlng(h3_index)
    risk_crime = float(source.get("risk_crime", 0.0))
    risk_lighting = float(source.get("risk_lighting", 0.0))
    risk_live = float(source.get("risk_live", 0.0))
    total_risk = _compute_total_risk(risk_crime, risk_lighting, risk_live)
    return {
        "h3_index": h3_index,
        "h3_resolution": validate_h3_resolution(settings.routing_h3_resolution),
        "lat": lat,
        "lng": lng,
        "location": f"SRID=4326;POINT({lng} {lat})",
        "risk_crime": risk_crime,
        "risk_lighting": risk_lighting,
        "risk_live": risk_live,
        "total_risk": total_risk,
        "extra_features": {
            "backfill_source": source_kind,
            "backfill_child_count": source.get("child_count"),
        },
    }


async def run(execute: bool, batch_size: int) -> None:
    parent_resolution = validate_h3_resolution(settings.h3_parent_resolution)
    engine = CompactCSREngine()
    engine.load_graph(settings.compact_graph_path)
    graph_cells = set(engine.h3_keys_map.keys())

    async with AsyncSessionLocal() as session:
        res10_rows = await load_res10_cells(session)
        res9_result = await session.execute(
            select(H3HeatmapModel).where(H3HeatmapModel.h3_resolution == parent_resolution)
        )
        res9_rows = {str(row.h3_index): row for row in res9_result.scalars().all()}
        parent_aggs = build_parent_aggregates(res10_rows, parent_resolution)

        missing = sorted(graph_cells - set(res10_rows.keys()))
        to_insert: list[dict] = []
        for cell in missing:
            parent = parent_cell(cell, parent_resolution)
            if parent in res9_rows:
                row = res9_rows[parent]
                source = {
                    "risk_crime": float(row.risk_crime or 0.0),
                    "risk_lighting": float(row.risk_lighting or 0.0),
                    "risk_live": float(row.risk_live or 0.0),
                    "child_count": None,
                }
                to_insert.append(derive_payload(cell, source, "res9_row"))
            elif parent in parent_aggs:
                to_insert.append(derive_payload(cell, parent_aggs[parent], "parent_child_mean"))

        print(f"Graf hücreleri: {len(graph_cells):,}")
        print(f"Mevcut res-10 satırları: {len(res10_rows):,}")
        print(f"Backfill adayı: {len(to_insert):,}")
        print(f"Backfill sonrası kapsam: {len(res10_rows) + len(to_insert):,} ({100*(len(res10_rows)+len(to_insert))/len(graph_cells):.1f}%)")
        print(f"Hâlâ verisiz kalacak: {len(missing) - len(to_insert):,}")

        if not execute:
            print("\nDry-run — yazma yapılmadı. Uygulamak için --execute ekleyin.")
            return

        inserted = 0
        for start in range(0, len(to_insert), batch_size):
            batch = to_insert[start : start + batch_size]
            stmt = pg_insert(H3HeatmapModel).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["h3_resolution", "h3_index"],
            )
            result = await session.execute(stmt)
            inserted += result.rowcount or 0
        await session.commit()
        print(f"\nYazıldı: {inserted:,} yeni h3_heatmap satırı")
        print("Backend'i yeniden başlatın ki risk belleğe yansısın.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eksik H3 hücrelerini ebeveyn ortalaması ile doldurur.")
    parser.add_argument("--execute", action="store_true", help="Gerçekten veritabanına yaz")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(run(execute=args.execute, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
