import osmnx as ox
from pathlib import Path

# Graf dosyasinin kaydedilecegi konum: SafeRoute_App/data-science/chicago_walk.graphml
OUTPUT_PATH = Path("../data-science/chicago_walk.graphml")

# Yaya guvenligi icin gerekli ek OSM alanlari
extra_way_tags = [
    "lit",
    "sidewalk",
    "surface",
    "smoothness",
    "incline",
    "footway",
    "crossing",
    "access",
    "tunnel",
    "bridge",
    "width",
]

extra_node_tags = [
    "crossing",
    "lit",
    "kerb",
    "barrier",
    "traffic_signals",
]

ox.settings.useful_tags_way = list(
    set(ox.settings.useful_tags_way + extra_way_tags)
)

ox.settings.useful_tags_node = list(
    set(ox.settings.useful_tags_node + extra_node_tags)
)

ox.settings.log_console = True
ox.settings.use_cache = True

print("Chicago yaya grafı OpenStreetMap üzerinden indiriliyor...")

G = ox.graph_from_place(
    "Chicago, Illinois, USA",
    network_type="walk",
    simplify=True,
    retain_all=False,
    truncate_by_edge=True,
)

print(f"Düğüm sayısı: {len(G.nodes):,}")
print(f"Edge sayısı: {len(G.edges):,}")

# Her edge icin varsayilan yuruyus suresi (1.2 m/s)
walking_speed_mps = 1.2

for _, _, _, data in G.edges(keys=True, data=True):
    length_m = float(data.get("length", 0.0))
    data["walking_speed_mps"] = walking_speed_mps
    data["travel_time"] = length_m / walking_speed_mps

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

ox.save_graphml(G, OUTPUT_PATH)

print(f"Chicago grafı kaydedildi: {OUTPUT_PATH}")
