"""GraphML verisini çözünürlük etiketli Compact CSR NPZ biçimine dönüştürür.

Format 2.0 ile her yol kenarı yalnızca orta noktasına değil, gerçek geometrisi
boyunca varsayılan 30 metre aralıklarla birden fazla H3 hücresine bağlanır.
Bu, küçük res-10 hücrelerinin yanından geçen uzun/virajlı bir kenarın yanlış
tek bir risk hücresine atanmasını önler.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import h3
import numpy as np
import osmnx as ox

from h3_policy import (
    DEFAULT_EDGE_SAMPLE_SPACING_M,
    LEGACY_H3_RESOLUTION,
    edge_lat_lng_points,
    polyline_h3_cells,
    validate_h3_resolution,
)


DEFAULT_GRAPHML_PATH = Path("../data-science/chicago_walk.graphml")


def default_output_path(h3_resolution: int) -> Path:
    """Res-9 mevcut dosya adını korur; res-10 ayrı artefakt üretir."""
    resolution = validate_h3_resolution(h3_resolution)
    if resolution == LEGACY_H3_RESOLUTION:
        return Path("../data-science/compact_graph.npz")
    return Path(f"../data-science/compact_graph_res{resolution}.npz")


def build_compact_graph(
    graphml_path: str | Path = DEFAULT_GRAPHML_PATH,
    output_path: str | Path | None = None,
    *,
    h3_resolution: int = LEGACY_H3_RESOLUTION,
    sample_spacing_m: float = DEFAULT_EDGE_SAMPLE_SPACING_M,
) -> Path:
    """Compact grafı üretir ve oluşturulan NPZ yolunu döndürür."""
    resolution = validate_h3_resolution(h3_resolution)
    graphml_path = Path(graphml_path)
    output_path = (
        Path(output_path)
        if output_path is not None
        else default_output_path(resolution)
    )
    if sample_spacing_m <= 0:
        raise ValueError("sample_spacing_m sıfırdan büyük olmalıdır.")
    if not graphml_path.exists():
        raise FileNotFoundError(f"GraphML bulunamadı: {graphml_path.resolve()}")

    print(f"[Build Compact] GraphML okunuyor: {graphml_path}...")
    t0 = time.time()
    graph = ox.load_graphml(graphml_path)
    t1 = time.time()
    print(
        f"[Build Compact] GraphML yüklendi ({t1 - t0:.2f} sn). "
        f"Düğüm: {len(graph.nodes):,}, Kenar: {len(graph.edges):,}"
    )
    print(
        f"[Build Compact] H3 Res-{resolution}, çok-noktalı örnekleme "
        f"aralığı={sample_spacing_m:g} m"
    )

    node_list = list(graph.nodes())
    node_to_idx = {node_id: idx for idx, node_id in enumerate(node_list)}
    node_count = len(node_list)
    edge_count = len(graph.edges)

    node_x = np.zeros(node_count, dtype=np.float32)
    node_y = np.zeros(node_count, dtype=np.float32)
    for node_id, data in graph.nodes(data=True):
        idx = node_to_idx[node_id]
        node_x[idx] = np.float32(data["x"])
        node_y[idx] = np.float32(data["y"])

    edge_src = np.zeros(edge_count, dtype=np.int32)
    edge_dst = np.zeros(edge_count, dtype=np.int32)
    edge_length = np.zeros(edge_count, dtype=np.float32)
    h3_to_edge_list: dict[str, list[int]] = {}

    for edge_idx, (u, v, _key, data) in enumerate(
        graph.edges(keys=True, data=True)
    ):
        edge_src[edge_idx] = node_to_idx[u]
        edge_dst[edge_idx] = node_to_idx[v]
        edge_length[edge_idx] = np.float32(data.get("length", 1.0))

        points = edge_lat_lng_points(graph, u, v, data)
        cells = polyline_h3_cells(
            points,
            resolution=resolution,
            spacing_m=sample_spacing_m,
        )
        if not cells:
            mid_lat = (
                float(graph.nodes[u]["y"]) + float(graph.nodes[v]["y"])
            ) / 2.0
            mid_lng = (
                float(graph.nodes[u]["x"]) + float(graph.nodes[v]["x"])
            ) / 2.0
            cells = [str(h3.latlng_to_cell(mid_lat, mid_lng, resolution))]

        for cell in cells:
            h3_to_edge_list.setdefault(cell, []).append(edge_idx)

    h3_keys = list(h3_to_edge_list)
    h3_edge_offsets = np.zeros(len(h3_keys) + 1, dtype=np.int64)
    total_references = sum(len(edge_ids) for edge_ids in h3_to_edge_list.values())
    h3_edge_values = np.zeros(total_references, dtype=np.int32)

    current_offset = 0
    for idx, key in enumerate(h3_keys):
        edge_ids = h3_to_edge_list[key]
        h3_edge_offsets[idx] = current_offset
        next_offset = current_offset + len(edge_ids)
        h3_edge_values[current_offset:next_offset] = edge_ids
        current_offset = next_offset
    h3_edge_offsets[len(h3_keys)] = current_offset

    hasher = hashlib.sha256()
    for array in (node_x, node_y, edge_src, edge_dst, edge_length):
        hasher.update(array.tobytes())
    hasher.update(str(resolution).encode("ascii"))
    hasher.update(str(float(sample_spacing_m)).encode("ascii"))
    data_hash = hasher.hexdigest()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        version=np.array(["2.0"], dtype=str),
        data_hash=np.array([data_hash], dtype=str),
        h3_resolution=np.array([resolution], dtype=np.int16),
        edge_sample_spacing_m=np.array([sample_spacing_m], dtype=np.float32),
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        edge_length=edge_length,
        h3_keys=np.array(h3_keys, dtype=str),
        h3_edge_offsets=h3_edge_offsets,
        h3_edge_values=h3_edge_values,
    )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    mean_cells_per_edge = (
        total_references / edge_count if edge_count else 0.0
    )
    print(f"[Build Compact] BAŞARILI: {output_path.resolve()}")
    print(
        f"[Build Compact] Boyut={size_mb:.2f} MB, "
        f"H3 hücresi={len(h3_keys):,}, "
        f"ortalama hücre/kenar={mean_cells_per_edge:.2f}"
    )
    return output_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SafeRoute çözünürlük etiketli Compact CSR graf üreticisi"
    )
    parser.add_argument(
        "--graph",
        default=str(DEFAULT_GRAPHML_PATH),
        help="Kaynak GraphML dosyası",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Çıktı NPZ dosyası (res-10 varsayılanı compact_graph_res10.npz)",
    )
    parser.add_argument(
        "--h3-resolution",
        type=int,
        choices=(9, 10),
        default=LEGACY_H3_RESOLUTION,
    )
    parser.add_argument(
        "--sample-spacing-m",
        type=float,
        default=DEFAULT_EDGE_SAMPLE_SPACING_M,
        help="Kenar geometrisi örnekleme aralığı (metre)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = _parse_args()
    try:
        build_compact_graph(
            cli_args.graph,
            cli_args.output,
            h3_resolution=cli_args.h3_resolution,
            sample_spacing_m=cli_args.sample_spacing_m,
        )
    except Exception as exc:
        print(f"[Build Compact HATA] {exc}", file=sys.stderr)
        sys.exit(1)
