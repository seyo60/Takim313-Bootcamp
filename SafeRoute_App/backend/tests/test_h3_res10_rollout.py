"""Kontrollü H3 res-10 geçişinin saf fonksiyon ve motor regresyon testleri."""

from datetime import datetime, timezone

import h3
import numpy as np
import pytest

from chicago_311_lighting_etl import process_lighting_records
from chicago_crime_etl import process_crime_records
from h3_policy import (
    calibrated_child_risk,
    polyline_h3_cells,
    resolve_hierarchical_risk,
)
from routing_engine import CompactCSREngine


CHICAGO_LAT = 41.8781
CHICAGO_LNG = -87.6298


def _two_res10_children() -> tuple[str, str, str]:
    parent = h3.latlng_to_cell(CHICAGO_LAT, CHICAGO_LNG, 9)
    children = sorted(h3.cell_to_children(parent, 10))
    return parent, children[0], children[-1]


def test_res9_default_crime_score_is_backward_compatible():
    ref = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    result = process_crime_records(
        [
            {
                "id": "1",
                "date": ref.isoformat(),
                "primary_type": "BATTERY",
                "latitude": str(CHICAGO_LAT),
                "longitude": str(CHICAGO_LNG),
            }
        ],
        reference_date=ref,
    )

    cell = next(iter(result.values()))
    assert cell["h3_resolution"] == 9
    assert cell["risk_crime"] == pytest.approx(0.1)
    assert h3.get_resolution(next(iter(result))) == 9


def test_res10_crime_is_bounded_and_parent_shrunk():
    parent, child_a, child_b = _two_res10_children()
    lat_a, lng_a = h3.cell_to_latlng(child_a)
    lat_b, lng_b = h3.cell_to_latlng(child_b)
    ref = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)

    result = process_crime_records(
        [
            {
                "id": "a",
                "date": ref.isoformat(),
                "primary_type": "BATTERY",
                "latitude": str(lat_a),
                "longitude": str(lng_a),
            },
            {
                "id": "b",
                "date": ref.isoformat(),
                "primary_type": "THEFT",
                "latitude": str(lat_b),
                "longitude": str(lng_b),
            },
        ],
        reference_date=ref,
        h3_resolution=10,
        parent_resolution=9,
    )

    assert len(result) == 2
    assert all(h3.get_resolution(key) == 10 for key in result)
    assert all(value["parent_h3_index"] == parent for value in result.values())
    assert all(0.0 <= value["risk_crime"] <= 1.0 for value in result.values())
    assert all(
        value["risk_crime"] != value["local_density_risk_crime"]
        for value in result.values()
    )


def test_res10_lighting_is_bounded_and_keeps_resolution_metadata():
    _parent, child_a, child_b = _two_res10_children()
    lat_a, lng_a = h3.cell_to_latlng(child_a)
    lat_b, lng_b = h3.cell_to_latlng(child_b)
    ref = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    result, metadata = process_lighting_records(
        [
            {
                "sr_number": "SR_A",
                "created_date": ref.isoformat(),
                "sr_type": "Street Light - All Out Complaint",
                "status": "Open",
                "latitude": str(lat_a),
                "longitude": str(lng_a),
            },
            {
                "sr_number": "SR_B",
                "created_date": ref.isoformat(),
                "sr_type": "Street Light Out Complaint",
                "status": "Open",
                "latitude": str(lat_b),
                "longitude": str(lng_b),
            },
        ],
        reference_date=ref,
        h3_resolution=10,
        parent_resolution=9,
    )

    assert metadata["open_records_count"] == 2
    assert len(result) == 2
    assert all(value["h3_resolution"] == 10 for value in result.values())
    assert all(0.0 <= value["risk_lighting"] <= 1.0 for value in result.values())


def test_calibration_uses_density_and_evidence_shrinkage():
    final, local, parent, weight = calibrated_child_risk(
        local_raw_score=1.0,
        parent_raw_score=2.0,
        base_saturation_score=10.0,
        evidence=1.0,
        child_resolution=10,
        parent_resolution=9,
        shrinkage_strength=2.0,
    )
    assert local == pytest.approx(0.7)
    assert parent == pytest.approx(0.2)
    assert weight == pytest.approx(1.0 / 3.0)
    assert final == pytest.approx((1.0 / 3.0) * 0.7 + (2.0 / 3.0) * 0.2)


def test_long_edge_crosses_multiple_res10_cells():
    cells = polyline_h3_cells(
        [
            (41.8781, -87.6320),
            (41.8781, -87.6260),
        ],
        resolution=10,
        spacing_m=30.0,
    )
    assert len(cells) >= 3
    assert len(cells) == len(set(cells))
    assert all(h3.get_resolution(cell) == 10 for cell in cells)


def test_hierarchical_lookup_prefers_child_then_parent_then_unknown():
    parent, child, _ = _two_res10_children()

    value, available, source = resolve_hierarchical_risk(
        child,
        {child: 0.7, parent: 0.4},
        unknown_risk=0.25,
    )
    assert value == pytest.approx(0.7)
    assert available is True
    assert source == child

    value, available, source = resolve_hierarchical_risk(
        child,
        {parent: 0.4},
        unknown_risk=0.25,
    )
    assert value == pytest.approx(0.4)
    assert available is True
    assert source == parent

    value, available, source = resolve_hierarchical_risk(
        child,
        {},
        unknown_risk=0.25,
    )
    assert value == pytest.approx(0.25)
    assert available is False
    assert source is None


def test_compact_engine_combines_all_cells_of_an_edge(monkeypatch):
    _parent, child_a, child_b = _two_res10_children()
    engine = CompactCSREngine()
    engine.node_x = np.array([-87.63, -87.62], dtype=np.float64)
    engine.node_y = np.array([41.87, 41.88], dtype=np.float64)
    engine.edge_src = np.array([0], dtype=np.int32)
    engine.edge_dst = np.array([1], dtype=np.int32)
    engine.edge_length = np.array([100.0], dtype=np.float64)
    engine.edge_risk = np.zeros(1, dtype=np.float32)
    engine.edge_has_data = np.zeros(1, dtype=np.bool_)
    engine.h3_keys_map = {
        child_a: np.array([0], dtype=np.int32),
        child_b: np.array([0], dtype=np.int32),
    }
    engine.N = 2
    engine.M = 1
    monkeypatch.setattr(
        "routing_engine.settings.routing_edge_max_risk_weight",
        0.65,
    )

    engine.apply_risk_weights({child_a: 0.9, child_b: 0.1})

    # 0.65*max(0.9) + 0.35*mean(0.5) = 0.76
    assert float(engine.edge_risk[0]) == pytest.approx(0.76, abs=1e-6)
    assert bool(engine.edge_has_data[0]) is True


def test_compact_engine_uses_res9_parent_for_res10_edge():
    parent, child, _ = _two_res10_children()
    engine = CompactCSREngine()
    engine.node_x = np.array([-87.63, -87.62], dtype=np.float64)
    engine.node_y = np.array([41.87, 41.88], dtype=np.float64)
    engine.edge_src = np.array([0], dtype=np.int32)
    engine.edge_dst = np.array([1], dtype=np.int32)
    engine.edge_length = np.array([100.0], dtype=np.float64)
    engine.edge_risk = np.zeros(1, dtype=np.float32)
    engine.edge_has_data = np.zeros(1, dtype=np.bool_)
    engine.h3_keys_map = {child: np.array([0], dtype=np.int32)}
    engine.N = 2
    engine.M = 1

    engine.apply_risk_weights({parent: 0.42})

    assert float(engine.edge_risk[0]) == pytest.approx(0.42, abs=1e-6)
    assert bool(engine.edge_has_data[0]) is True
