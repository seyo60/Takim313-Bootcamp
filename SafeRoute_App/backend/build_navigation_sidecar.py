"""Build a compact, deterministic navigation metadata sidecar from GraphML."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import osmnx as ox


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        values = [normalized_text(item) for item in value]
        return " / ".join(dict.fromkeys(item for item in values if item))
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def intern(value: str, table: list[str], lookup: dict[str, int]) -> int:
    existing = lookup.get(value)
    if existing is not None:
        return existing
    index = len(table)
    table.append(value)
    lookup[value] = index
    return index


def build_sidecar(graphml: Path, compact_graph: Path, output: Path) -> None:
    graphml = graphml.resolve()
    compact_graph = compact_graph.resolve()
    if not graphml.is_file() or not compact_graph.is_file():
        raise FileNotFoundError("GraphML and compact graph must both exist")

    print(f"[Navigation Sidecar] GraphML yükleniyor: {graphml}")
    graph = ox.load_graphml(graphml)
    compact = np.load(compact_graph, allow_pickle=False)
    node_x = compact["node_x"]
    node_y = compact["node_y"]
    edge_src = compact["edge_src"]
    edge_dst = compact["edge_dst"]

    node_list = list(graph.nodes())
    node_to_index = {node_id: index for index, node_id in enumerate(node_list)}
    if len(node_list) != len(node_x) or len(graph.edges) != len(edge_src):
        raise RuntimeError("GraphML and compact graph node/edge counts do not match")

    graph_x = np.fromiter(
        (float(graph.nodes[node]["x"]) for node in node_list),
        dtype=np.float64,
        count=len(node_list),
    )
    graph_y = np.fromiter(
        (float(graph.nodes[node]["y"]) for node in node_list),
        dtype=np.float64,
        count=len(node_list),
    )
    if not np.allclose(graph_x, node_x, atol=1e-6) or not np.allclose(
        graph_y,
        node_y,
        atol=1e-6,
    ):
        raise RuntimeError("GraphML node ordering/coordinates do not match compact graph")

    edge_count = len(edge_src)
    node_osm_id = np.asarray([int(str(node)) for node in node_list], dtype=np.int64)
    edge_key = np.zeros(edge_count, dtype=np.int32)
    name_ids = np.zeros(edge_count, dtype=np.int32)
    ref_ids = np.zeros(edge_count, dtype=np.int32)
    highway_ids = np.zeros(edge_count, dtype=np.int32)
    junction_ids = np.zeros(edge_count, dtype=np.int32)
    crossing = np.zeros(edge_count, dtype=np.bool_)
    out_degree = np.fromiter(
        (min(int(graph.out_degree(node)), 32767) for node in node_list),
        dtype=np.int16,
        count=len(node_list),
    )

    tables = {key: [""] for key in ("name", "ref", "highway", "junction")}
    lookups = {key: {"": 0} for key in tables}

    for edge_index, (source, target, key, data) in enumerate(
        graph.edges(keys=True, data=True)
    ):
        source_index = node_to_index[source]
        target_index = node_to_index[target]
        if (
            int(edge_src[edge_index]) != source_index
            or int(edge_dst[edge_index]) != target_index
        ):
            raise RuntimeError(
                f"Graph edge ordering mismatch at edge {edge_index}: "
                f"{source}->{target}"
            )
        edge_key[edge_index] = int(key)
        for field, destination in (
            ("name", name_ids),
            ("ref", ref_ids),
            ("highway", highway_ids),
            ("junction", junction_ids),
        ):
            value = normalized_text(data.get(field))
            destination[edge_index] = intern(
                value,
                tables[field],
                lookups[field],
            )
        target_data = graph.nodes[target]
        crossing[edge_index] = (
            normalized_text(target_data.get("highway")).lower() == "crossing"
            or bool(normalized_text(target_data.get("crossing")))
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        version=np.asarray(["1.0"], dtype=str),
        compact_graph_sha256=np.asarray([sha256_file(compact_graph)], dtype=str),
        graphml_sha256=np.asarray([sha256_file(graphml)], dtype=str),
        node_osm_id=node_osm_id,
        node_out_degree=out_degree,
        edge_key=edge_key,
        edge_name_id=name_ids,
        edge_ref_id=ref_ids,
        edge_highway_id=highway_ids,
        edge_junction_id=junction_ids,
        edge_crossing=crossing,
        street_names=np.asarray(tables["name"], dtype=str),
        street_refs=np.asarray(tables["ref"], dtype=str),
        highway_types=np.asarray(tables["highway"], dtype=str),
        junction_types=np.asarray(tables["junction"], dtype=str),
    )
    print(
        f"[Navigation Sidecar] OK: {output.resolve()} "
        f"({output.stat().st_size / 1024 / 1024:.2f} MiB, "
        f"{len(tables['name']) - 1:,} street names)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphml", type=Path, required=True)
    parser.add_argument("--compact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_sidecar(args.graphml, args.compact, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
