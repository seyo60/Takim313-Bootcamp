# backend/generate_test_graph.py
"""
Mehmet Ali'nin asıl Chicago graf dosyası gelene kadar,
routing algoritmasını test etmek için küçük bir bölgenin
yaya (walk) graf ağını indirip diske kaydeder.
"""
import osmnx as ox

# Küçük bir test bölgesi - Chicago Loop (downtown), hızlı iner
# Mehmet Ali'nin dosyası gelince bu satırı onun verdiği bölge/dosya ile değiştireceğiz
PLACE_NAME = "Loop, Chicago, Illinois, USA"
OUTPUT_PATH = "test_network.graphml"

print(f"'{PLACE_NAME}' bölgesi için yaya graf ağı indiriliyor...")
G = ox.graph_from_place(PLACE_NAME, network_type="walk")

print(f"Graf indirildi: {len(G.nodes)} kavşak (node), {len(G.edges)} sokak parçası (edge)")

ox.save_graphml(G, filepath=OUTPUT_PATH)
print(f"Graf '{OUTPUT_PATH}' dosyasına kaydedildi.")