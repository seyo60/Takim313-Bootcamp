import asyncio
import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import settings
import crud

async def main():
    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        points = await crud.get_all_heatmap_points(db)
        meta = await crud.get_latest_etl_runs(db)

    print("--- BACKEND HEATMAP PRE-VERIFICATION METRICS ---")
    total_cells = len(points)
    print(f"Total H3 cells: {total_cells}")

    if total_cells == 0:
        print("ERROR: Total H3 cells is 0! Database heatmap points are missing!")
        return

    total_risks = [p.total_risk for p in points if p.total_risk is not None]
    cells_with_risk = [r for r in total_risks if r > 0.0]
    print(f"Cells with risk > 0.0: {len(cells_with_risk)} ({len(cells_with_risk)/total_cells*100:.1f}%)")

    if total_risks:
        avg_risk = float(np.mean(total_risks))
        p50_risk = float(np.percentile(total_risks, 50))
        p95_risk = float(np.percentile(total_risks, 95))
        max_risk = float(np.max(total_risks))

        print(f"Average total_risk: {avg_risk:.4f}")
        print(f"P50 total_risk: {p50_risk:.4f}")
        print(f"P95 total_risk: {p95_risk:.4f}")
        print(f"Max total_risk: {max_risk:.4f}")

    print(f"risk_snapshot_at: {meta.get('risk_snapshot_at')}")
    print(f"crime_data_updated_at: {meta.get('crime_data_updated_at')}")
    print(f"lighting_data_updated_at: {meta.get('lighting_data_updated_at')}")

if __name__ == "__main__":
    asyncio.run(main())
