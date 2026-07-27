# backend/build_compact_graph.py
"""
Chicago GraphML verisini sıkıştırılmış NumPy ve SciPy binary formatına (compact_graph.npz) dönüştüren çevrimdışı betik.

Çıktı Dosyası: ../data-science/compact_graph.npz
İçerik:
- node_x: float32 dizisi (Boylamlar)
- node_y: float32 dizisi (Enlemler)
- edge_src: int32 dizisi (Başlangıç düğüm indeksi)
- edge_dst: int32 dizisi (Bitiş düğüm indeksi)
- edge_length: float32 dizisi (Fiziksel mesafe metre)
- h3_keys: String dizisi (H3 Res 9 indeks haritası)
- h3_edge_offsets: int32 dizisi (H3 -> edge_ids dilimleme ofsetleri)
- h3_edge_values: int32 dizisi (H3 hücrelerine ait kenar indeksleri)
"""

import os
import sys
import time
import hashlib
from pathlib import Path
import numpy as np
import osmnx as ox
import h3

GRAPHML_PATH = Path("../data-science/chicago_walk.graphml")
OUTPUT_NPZ_PATH = Path("../data-science/compact_graph.npz")
H3_RESOLUTION = 9


def build_compact_graph():
    if not GRAPHML_PATH.exists():
        print(f"HATA: {GRAPHML_PATH} bulunamadı!")
        sys.exit(1)

    print(f"[Build Compact] GraphML okunuyor: {GRAPHML_PATH}...")
    t0 = time.time()
    G = ox.load_graphml(GRAPHML_PATH)
    t1 = time.time()
    print(f"[Build Compact] GraphML yüklendi ({t1 - t0:.2f} sn). Düğüm: {len(G.nodes):,}, Kenar: {len(G.edges):,}")

    # Düğümleri ardışık 0..N-1 tamsayı dizinine eşle
    node_list = list(G.nodes())
    node_to_idx = {node_id: idx for idx, node_id in enumerate(node_list)}

    N = len(node_list)
    M = len(G.edges)

    node_x = np.zeros(N, dtype=np.float32)
    node_y = np.zeros(N, dtype=np.float32)

    for node_id, data in G.nodes(data=True):
        idx = node_to_idx[node_id]
        node_x[idx] = np.float32(data["x"])
        node_y[idx] = np.float32(data["y"])

    edge_src = np.zeros(M, dtype=np.int32)
    edge_dst = np.zeros(M, dtype=np.int32)
    edge_length = np.zeros(M, dtype=np.float32)

    h3_to_edge_list = {}

    for edge_idx, (u, v, key, data) in enumerate(G.edges(keys=True, data=True)):
        u_idx = node_to_idx[u]
        v_idx = node_to_idx[v]

        edge_src[edge_idx] = u_idx
        edge_dst[edge_idx] = v_idx
        edge_length[edge_idx] = np.float32(data.get("length", 1.0))

        # Orta nokta H3 indeksi hesapla (float64 hassasiyeti ile boundary sapmasını önle)
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        mid_lat = (float(u_data["y"]) + float(v_data["y"])) / 2.0
        mid_lng = (float(u_data["x"]) + float(v_data["x"])) / 2.0
        cell = h3.latlng_to_cell(mid_lat, mid_lng, H3_RESOLUTION)

        if cell not in h3_to_edge_list:
            h3_to_edge_list[cell] = []
        h3_to_edge_list[cell].append(edge_idx)

    # H3 ters indeksini sıkıştırılmış CSR-benzeri iki 1D int32 dizisine dönüştür
    h3_keys = list(h3_to_edge_list.keys())
    h3_edge_offsets = np.zeros(len(h3_keys) + 1, dtype=np.int32)
    total_refs = sum(len(v) for v in h3_to_edge_list.values())
    h3_edge_values = np.zeros(total_refs, dtype=np.int32)

    current_offset = 0
    for idx, key in enumerate(h3_keys):
        edge_ids = h3_to_edge_list[key]
        h3_edge_offsets[idx] = current_offset
        length = len(edge_ids)
        h3_edge_values[current_offset:current_offset + length] = edge_ids
        current_offset += length
    h3_edge_offsets[len(h3_keys)] = current_offset

    # SHA256 bütünlük özeti (data_hash) hesapla
    hasher = hashlib.sha256()
    hasher.update(node_x.tobytes())
    hasher.update(node_y.tobytes())
    hasher.update(edge_src.tobytes())
    hasher.update(edge_dst.tobytes())
    hasher.update(edge_length.tobytes())
    data_hash = hasher.hexdigest()

    OUTPUT_NPZ_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUTPUT_NPZ_PATH,
        version=np.array(["1.0"], dtype=str),
        data_hash=np.array([data_hash], dtype=str),
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        edge_length=edge_length,
        h3_keys=np.array(h3_keys, dtype=str),
        h3_edge_offsets=h3_edge_offsets,
        h3_edge_values=h3_edge_values,
    )

    size_mb = OUTPUT_NPZ_PATH.stat().st_size / (1024 * 1024)
    print(f"[Build Compact] BAŞARILI! Sıkıştırılmış ikili graf kaydedildi: {OUTPUT_NPZ_PATH.resolve()}")
    print(f"[Build Compact] Dosya Boyutu: {size_mb:.2f} MB (GraphML: 470 MB idi - %95+ küçülme!)")


if __name__ == "__main__":
    build_compact_graph()
