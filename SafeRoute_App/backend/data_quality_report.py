"""Read-only aggregate data-quality report; never emits reports or coordinates."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import text

from main import AsyncSessionLocal


QUERY = text(
    """
    SELECT
      h3_resolution,
      COUNT(*) AS cells,
      COUNT(*) FILTER (WHERE total_risk > 0) AS cells_with_signal,
      COUNT(*) FILTER (
        WHERE COALESCE(extra_features, '{}'::jsonb)
          ?| ARRAY['open_311_lighting_count', 'completed_311_lighting_count']
      ) AS cells_with_lighting_observation,
      COUNT(*) FILTER (
        WHERE COALESCE(extra_features, '{}'::jsonb)
          ?| ARRAY['open_311_lighting_count', 'completed_311_lighting_count']
          AND COALESCE(risk_lighting, 0.0) = 0.0
      ) AS observed_lighting_zero_risk_cells,
      COUNT(*) FILTER (
        WHERE risk_crime NOT BETWEEN 0 AND 1
           OR risk_lighting NOT BETWEEN 0 AND 1
           OR risk_live NOT BETWEEN 0 AND 1
           OR total_risk NOT BETWEEN 0 AND 1
      ) AS invalid_risk_cells,
      COUNT(*) FILTER (WHERE location IS NULL) AS null_location_cells,
      COUNT(*) FILTER (
        WHERE ABS(
          total_risk - LEAST(
            1.0,
            GREATEST(
              0.0,
              0.65 * COALESCE(risk_crime, 0.0)
              + 0.20 * COALESCE(risk_lighting, 0.0)
              + 0.15 * COALESCE(risk_live, 0.0)
            )
          )
        ) > 0.0001
      ) AS formula_mismatch_cells,
      MIN(updated_at) AS oldest_cell_update,
      MAX(updated_at) AS newest_cell_update
    FROM h3_heatmap
    GROUP BY h3_resolution
    ORDER BY h3_resolution
    """
)


async def collect() -> dict:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(QUERY)).mappings().all()
        duplicate_cells = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM ("
                    "SELECT h3_resolution, h3_index FROM h3_heatmap "
                    "GROUP BY h3_resolution, h3_index HAVING COUNT(*) > 1"
                    ") AS duplicate_groups"
                )
            )
        ).scalar_one()
        etl_rows = (
            await session.execute(
                text(
                    "SELECT etl_name, last_successful_run, records_processed, status "
                    "FROM etl_runs ORDER BY etl_name"
                )
            )
        ).mappings().all()
    def serialize(value):
        return value.isoformat() if hasattr(value, "isoformat") else value
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cells": [{key: serialize(value) for key, value in row.items()} for row in rows],
        "duplicate_cell_groups": duplicate_cells,
        "etl": [{key: serialize(value) for key, value in row.items()} for row in etl_rows],
        "zero_semantics": {
            "lighting": "A zero is a computed low/expired signal only when the cell has lighting observation keys; otherwise it means no lighting-source observation for that cell.",
        },
    }


def main() -> int:
    print(json.dumps(asyncio.run(collect()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
