import os
from pathlib import Path
import osmnx as ox
import networkx as nx
import routing

GRAPH_PATH = Path("../data-science/chicago_walk.graphml")

print("=== 1. DOSYA BOYUTU KONTROLÜ ===")
if GRAPH_PATH.exists():
    size_bytes = GRAPH_PATH.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"Dosya Yolu: {GRAPH_PATH.resolve()}")
    print(f"Dosya Boyutu: {size_mb:.2f} MB ({size_bytes:,} bayt)")
else:
    print(f"HATA: Dosya bulunamadı: {GRAPH_PATH}")
    exit(1)

print("\n=== GRAF YÜKLENİYOR ===")
G = ox.load_graphml(GRAPH_PATH)

print("\n=== 2. NODE VE EDGE SAYISI KONTROLÜ ===")
nodes, edges = ox.graph_to_gdfs(G)
print(f"Node (Düğüm) Sayısı: {len(G.nodes):,}")
print(f"Edge (Kenar) Sayısı: {len(G.edges):,}")

print("\n=== 3. COĞRAFİ SINIRLAR VE CRS KONTROLÜ ===")
bounds = nodes.total_bounds  # [minx, miny, maxx, maxy] -> [min_lng, min_lat, max_lng, max_lat]
print(f"CRS: {G.graph.get('crs')}")
print(f"Min Longitude (Boylam): {bounds[0]:.6f}")
print(f"Min Latitude (Enlem):   {bounds[1]:.6f}")
print(f"Max Longitude (Boylam): {bounds[2]:.6f}")
print(f"Max Latitude (Enlem):   {bounds[3]:.6f}")

print("\n=== 4. BÖLGE VE SNAP MESAFESİ TESTLERİ ===")
test_regions = {
    "Chicago Loop": (41.8781, -87.6298),
    "Kuzeybatı Chicago": (41.9742, -87.8200),
    "Rogers Park": (42.0106, -87.6696),
    "South Chicago": (41.7397, -87.5544),
    "Hegewisch": (41.6548, -87.5451),
    "Austin": (41.8885, -87.7660),
    "Englewood": (41.7753, -87.6416),
}

valid_nodes = {}
MAX_SNAP_DISTANCE_M = 250.0

for name, (lat, lng) in test_regions.items():
    res = ox.nearest_nodes(G, X=lng, Y=lat, return_dist=True)
    if isinstance(res, tuple):
        node_id, dist = res
    else:
        node_id, dist = res, 0.0

    valid_nodes[name] = (node_id, lat, lng)
    status = "OK (<= 250m)" if dist <= MAX_SNAP_DISTANCE_M else "EXCEEDED (> 250m)"
    print(f"• {name:15s} | Lat: {lat:.4f}, Lng: {lng:.4f} | En Yakın Düğüm: {node_id} | Snap Mesafesi: {dist:.1f} m -> {status}")

print("\n=== 5. ÇAPRAZ BÖLGE ROTA HESAPLAMA TESTLERİ ===")
# Test 1: Chicago Loop -> Austin
start_lat, start_lng = test_regions["Chicago Loop"]
end_lat, end_lng = test_regions["Austin"]
print(f"\n[Rota 1] Chicago Loop -> Austin:")
coords_safe, dist_safe, safety_score, route_risk = routing.compute_safe_route(G, start_lat, start_lng, end_lat, end_lng)
coords_short, dist_short, safety_short, risk_short = routing.compute_shortest_route(G, start_lat, start_lng, end_lat, end_lng)
print(f"  Güvenli Rota: {dist_safe/1000:.2f} km, {len(coords_safe)} nokta, Güvenlik Skoru: {safety_score:.1f}/100, Rota Riski: {route_risk:.4f}")
print(f"  En Kısa Rota: {dist_short/1000:.2f} km, {len(coords_short)} nokta, Güvenlik Skoru: {safety_short:.1f}/100, Rota Riski: {risk_short:.4f}")

# Test 2: Rogers Park -> Hegewisch (Kuzeyden Güneye Tüm Şehir Rotalama)
start_lat, start_lng = test_regions["Rogers Park"]
end_lat, end_lng = test_regions["Hegewisch"]
print(f"\n[Rota 2] Rogers Park -> Hegewisch (Kuzey-Güney Çapraz Rota):")
coords_safe, dist_safe, safety_score, route_risk = routing.compute_safe_route(G, start_lat, start_lng, end_lat, end_lng)
print(f"  Güvenli Rota: {dist_safe/1000:.2f} km, {len(coords_safe)} nokta, Güvenlik Skoru: {safety_score:.1f}/100, Rota Riski: {route_risk:.4f}")

# Test 3: Kuzeybatı Chicago -> South Chicago (Kuzeybatı - Güneydoğu Çapraz Rota)
start_lat, start_lng = test_regions["Kuzeybatı Chicago"]
end_lat, end_lng = test_regions["South Chicago"]
print(f"\n[Rota 3] Kuzeybatı Chicago -> South Chicago (Kuzeybatı-Güneydoğu Çapraz Rota):")
coords_safe, dist_safe, safety_score, route_risk = routing.compute_safe_route(G, start_lat, start_lng, end_lat, end_lng)
print(f"  Güvenli Rota: {dist_safe/1000:.2f} km, {len(coords_safe)} nokta, Güvenlik Skoru: {safety_score:.1f}/100, Rota Riski: {route_risk:.4f}")

print("\n=== TÜM KONTROLLER BAŞARIYLA TAMAMLANTI ===")
