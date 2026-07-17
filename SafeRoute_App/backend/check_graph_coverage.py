# backend/check_graph_coverage.py
"""
Mehmet Ali'nin verdigi graf dosyasinin (chicago.graphml) hangi alani
kapsadigini, kac node/edge icerdigini ve dosya boyutunu raporlar.
"""
import osmnx as ox
import os

GRAPH_PATH = "../data-science/chicago.graphml"  # yolu kendi klasor yapina gore ayarla

print(f"Graf yukleniyor: {GRAPH_PATH}")
G = ox.load_graphml(GRAPH_PATH)

# Dosya boyutu
file_size_mb = os.path.getsize(GRAPH_PATH) / (1024 * 1024)

# Node/edge sayisi
node_count = len(G.nodes)
edge_count = len(G.edges)

# Kapsadigi cografi alan (bounding box)
lats = [data["y"] for _, data in G.nodes(data=True)]
lngs = [data["x"] for _, data in G.nodes(data=True)]

min_lat, max_lat = min(lats), max(lats)
min_lng, max_lng = min(lngs), max(lngs)

print("\n--- GRAF RAPORU ---")
print(f"Dosya boyutu: {file_size_mb:.2f} MB")
print(f"Kavşak (node) sayısı: {node_count}")
print(f"Sokak parçası (edge) sayısı: {edge_count}")
print(f"\nKapsadığı alan (bounding box):")
print(f"  Enlem (lat): {min_lat:.4f} - {max_lat:.4f}")
print(f"  Boylam (lng): {min_lng:.4f} - {max_lng:.4f}")
print(f"\nBu koordinatları Google Maps'te aratarak alanı görsel olarak kontrol edebilirsin:")
print(f"  Sol alt köşe: {min_lat:.4f}, {min_lng:.4f}")
print(f"  Sağ üst köşe: {max_lat:.4f}, {max_lng:.4f}")