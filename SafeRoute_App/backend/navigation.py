"""Deterministic navigation contract with honest metadata fallbacks."""

from __future__ import annotations

import hashlib
import math
from typing import Sequence


WALKING_SPEED_MPS = 1.2


def _distance_m(a: Sequence[float], b: Sequence[float]) -> float:
    lng1, lat1 = map(math.radians, a)
    lng2, lat2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    hav = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6_371_000.0 * 2.0 * math.atan2(math.sqrt(hav), math.sqrt(max(0.0, 1.0 - hav)))


def _bearing(a: Sequence[float], b: Sequence[float]) -> float:
    lng1, lat1 = map(math.radians, a)
    lng2, lat2 = map(math.radians, b)
    y = math.sin(lng2 - lng1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lng2 - lng1)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _turn_delta(before: float, after: float) -> float:
    return (after - before + 540.0) % 360.0 - 180.0


def _maneuver(delta: float) -> tuple[str, str]:
    magnitude = abs(delta)
    if magnitude < 30.0:
        return "continue", "Düz devam edin."
    if magnitude < 100.0:
        return ("turn_right", "Sağa dönün.") if delta > 0 else ("turn_left", "Sola dönün.")
    return ("sharp_right", "Keskin sağa dönün.") if delta > 0 else ("sharp_left", "Keskin sola dönün.")


def _edge_id(graph_version: str, start_node: str, end_node: str) -> str:
    raw = f"{graph_version}:{start_node}>{end_node}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _instruction_with_street(
    maneuver: str,
    instruction: str,
    street_name: str | None,
    way_type: str | None,
) -> str:
    way_value = (way_type or "").lower()
    way_context = None
    if "steps" in way_value:
        way_context = "Merdivenlerde"
    elif any(
        value in way_value
        for value in ("footway", "path", "pedestrian", "corridor")
    ):
        way_context = "Yaya yolunda"
    elif "crossing" in way_value:
        way_context = "Yaya geçidinde"
    elif "service" in way_value:
        way_context = "Servis yolunda"

    if not street_name and not way_context:
        return instruction
    if not street_name:
        if maneuver == "depart":
            return f"{way_context} rotaya başlayın."
        if maneuver == "continue":
            return f"{way_context} düz devam edin."
        return f"{way_context} {instruction[0].lower()}{instruction[1:]}"
    if maneuver == "depart":
        return f"{street_name} üzerinde rotaya başlayın."
    if maneuver == "continue":
        return f"{street_name} üzerinde düz devam edin."
    direction = {
        "turn_right": "sağa",
        "turn_left": "sola",
        "sharp_right": "keskin sağa",
        "sharp_left": "keskin sola",
    }.get(maneuver)
    return (
        f"{street_name} yönüne {direction} dönün."
        if direction
        else instruction
    )


def build_navigation_contract(
    coordinates: list[list[float]],
    path_signature: Sequence[str],
    graph_version: str,
    profile: str,
    risk_snapshot_at: str,
    edge_signature: Sequence[str] = (),
    street_names: Sequence[str | None] = (),
    way_types: Sequence[str | None] = (),
) -> tuple[str, list[str], list[dict]]:
    if len(coordinates) < 2 or len(path_signature) != len(coordinates):
        raise ValueError("Navigation contract requires aligned path nodes and coordinates")

    segment_count = len(path_signature) - 1
    if edge_signature and len(edge_signature) != segment_count:
        raise ValueError("Navigation edge identity must align with route segments")
    if street_names and len(street_names) != segment_count:
        raise ValueError("Navigation street names must align with route segments")
    if way_types and len(way_types) != segment_count:
        raise ValueError("Navigation way types must align with route segments")
    normalized_names = (
        list(street_names) if street_names else [None] * segment_count
    )
    normalized_way_types = (
        list(way_types) if way_types else [None] * segment_count
    )
    edge_ids = [
        _edge_id(
            graph_version,
            str(edge_signature[i]) if edge_signature else str(path_signature[i]),
            "" if edge_signature else str(path_signature[i + 1]),
        )
        for i in range(segment_count)
    ]
    route_raw = (
        f"{graph_version}|{risk_snapshot_at}|{profile}|{'/'.join(edge_ids)}"
    ).encode("utf-8")
    route_id = hashlib.sha256(route_raw).hexdigest()[:32]

    segment_distances = [
        _distance_m(coordinates[i], coordinates[i + 1])
        for i in range(len(coordinates) - 1)
    ]
    bearings = [
        _bearing(coordinates[i], coordinates[i + 1])
        for i in range(len(coordinates) - 1)
    ]

    boundaries = [0]
    for segment_idx in range(1, len(bearings)):
        street_changed = (
            normalized_names[segment_idx]
            and normalized_names[segment_idx]
            != normalized_names[segment_idx - 1]
        )
        way_type_changed = (
            normalized_way_types[segment_idx]
            and normalized_way_types[segment_idx]
            != normalized_way_types[segment_idx - 1]
        )
        if (
            abs(_turn_delta(bearings[segment_idx - 1], bearings[segment_idx]))
            >= 30.0
            or street_changed
            or way_type_changed
        ):
            boundaries.append(segment_idx)
    boundaries.append(len(segment_distances))

    steps: list[dict] = []
    for step_index in range(len(boundaries) - 1):
        start_segment = boundaries[step_index]
        end_segment = boundaries[step_index + 1]
        distance = sum(segment_distances[start_segment:end_segment])
        if step_index == 0:
            maneuver_type, instruction = "depart", "Rotaya başlayın."
        else:
            delta = _turn_delta(bearings[start_segment - 1], bearings[start_segment])
            maneuver_type, instruction = _maneuver(delta)
        street_name = next(
            (
                name
                for name in normalized_names[start_segment:end_segment]
                if name
            ),
            None,
        )
        way_type = next(
            (
                value
                for value in normalized_way_types[start_segment:end_segment]
                if value
            ),
            None,
        )
        instruction = _instruction_with_street(
            maneuver_type,
            instruction,
            street_name,
            way_type,
        )
        step_edges = edge_ids[start_segment:end_segment]
        step_id = hashlib.sha256(
            f"{route_id}:{step_index}:{','.join(step_edges)}".encode("utf-8")
        ).hexdigest()[:24]
        steps.append(
            {
                "step_id": step_id,
                "maneuver": maneuver_type,
                "instruction": instruction,
                "street_name": street_name,
                "way_type": way_type,
                "distance_m": round(distance, 1),
                "duration_s": round(distance / WALKING_SPEED_MPS, 1),
                "bearing_before": round(bearings[start_segment], 1),
                "bearing_after": round(bearings[end_segment - 1], 1),
                "location": coordinates[start_segment],
                "edge_ids": step_edges,
            }
        )

    steps.append(
        {
            "step_id": hashlib.sha256(f"{route_id}:arrive".encode("utf-8")).hexdigest()[:24],
            "maneuver": "arrive",
            "instruction": "Varış noktanıza ulaştınız.",
            "street_name": None,
            "way_type": None,
            "distance_m": 0.0,
            "duration_s": 0.0,
            "bearing_before": round(bearings[-1], 1),
            "bearing_after": round(bearings[-1], 1),
            "location": coordinates[-1],
            "edge_ids": [],
        }
    )
    return route_id, edge_ids, steps
