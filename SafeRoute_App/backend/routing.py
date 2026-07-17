# backend/routing.py
"""
OSMnx grafi uzerinde risk-agirlikli en guvenli rota hesaplama mantigi.
Milyonluk kayitlarda O(1) guncelleme icin Ters Dizin (Inverted Index) kullanilir.

ONEMLI MIMARI KARAR: Bu dosya artik risk formulunu KENDI HESAPLAMAZ.
Agirlikli toplama formulu (historical/live/social) TEK YERDE, crud.py
icinde tanimli. Burada sadece DB'den gelen NIHAI total_risk degeri
RAM'deki grafa yaziliyor - boylece RAM ve DB arasinda asla sapma olmuyor.
"""
import networkx as nx
import osmnx as ox
import h3
from collections import defaultdict

H3_RESOLUTION = 9

# Risk agirliginin mesafeye ne kadar etki edecegini kontrol eden katsayi.
RISK_WEIGHT_FACTOR = 10.0

# Ortalama yuruyus hizi (m/s) - duration_s hesabinda kullanilir.
WALKING_SPEED_MPS = 1.2

# Chicago sehir sinirlari icin yaklasik bounding box.
# Bu kutunun disindan gelen rota/ihbar istekleri HTTP 400 ile reddedilir.
CHICAGO_BOUNDS = {
    "min_lat": 41.62,
    "max_lat": 42.05,
    "min_lng": -87.95,
    "max_lng": -87.50,
}


def is_within_chicago(lat: float, lng: float) -> bool:
    """Koordinat Chicago bounding box'i icinde mi?"""
    return (
        CHICAGO_BOUNDS["min_lat"] <= lat <= CHICAGO_BOUNDS["max_lat"]
        and CHICAGO_BOUNDS["min_lng"] <= lng <= CHICAGO_BOUNDS["max_lng"]
    )

_graph_cache = None


def load_graph(graphml_path: str = "test_network.graphml"):
    """
    Graf dosyasini bir kere yukler ve bellekte tutar.
    """
    global _graph_cache
    if _graph_cache is None:
        print(f"Graf yukleniyor: {graphml_path}")
        _graph_cache = ox.load_graphml(graphml_path)
        print(f"Graf yuklendi: {len(_graph_cache.nodes)} kavsak, {len(_graph_cache.edges)} sokak parcasi")
    return _graph_cache


def build_risk_lookup(heatmap_points) -> dict:
    """
    crud.get_all_heatmap_points()'ten donen kayitlari kullanarak
    {h3_index: total_risk} seklinde hizli bir sozluk olusturur.
    """
    risk_sums: dict = {}
    for point in heatmap_points:
        risk_sums.setdefault(point.h3_index, []).append(point.total_risk)
    return {h3_idx: sum(values) / len(values) for h3_idx, values in risk_sums.items()}


def _set_edge_risk(data: dict, risk_weight: float) -> None:
    """Bir kenarin (edge) risk agirligini ve buna gore ayarlanmis mesafesini set eder."""
    length_meters = data.get("length", 1.0)
    data["risk_weight"] = risk_weight
    data["risk_adjusted_length"] = length_meters * (1 + risk_weight / RISK_WEIGHT_FACTOR)


def apply_risk_weights(graph, risk_lookup: dict) -> dict:
    """
    Grafin her kenarina risk agirligini ekler ve O(1) guncellemeler icin
    H3 hucresinden -> kenarlara (edges) dogru bir ters dizin (Inverted Index) olusturur.
    Bu fonksiyon SADECE uygulama baslarken (lifespan icinde) bir kere cagrilir.
    """
    h3_to_edges = defaultdict(list)

    for u, v, key, data in graph.edges(keys=True, data=True):
        u_lat, u_lng = graph.nodes[u]["y"], graph.nodes[u]["x"]
        v_lat, v_lng = graph.nodes[v]["y"], graph.nodes[v]["x"]
        mid_lat = (u_lat + v_lat) / 2
        mid_lng = (u_lng + v_lng) / 2

        cell = h3.latlng_to_cell(mid_lat, mid_lng, H3_RESOLUTION)
        h3_to_edges[cell].append((u, v, key))

        risk_weight = risk_lookup.get(cell, 0.0)
        _set_edge_risk(data, risk_weight)

    return h3_to_edges


def set_absolute_risk_for_h3(graph, h3_to_edges: dict, target_h3: str, new_total_risk: float) -> None:
    """
    SADECE ihbarin geldigi H3 hucresindeki sokaklarin risk degerini,
    DB'den donen NIHAI (agirlikli formulle hesaplanmis) total_risk ile
    DOGRUDAN DEGISTIRIR (ekleme yapmaz).

    Bu fonksiyon eskiden 'update_dynamic_risk_for_h3' idi ve eklenen
    ham degeri mevcut agirliga TOPLUYORDU - bu, DB'deki agirlikli
    formulden farkli bir sonuc uretip zamanla RAM/DB arasinda sapmaya
    yol aciyordu. Artik RAM her zaman DB'nin hesapladigi son degeri
    birebir yansitiyor.

    Karmasiklik: O(1) - sadece bu H3 hucresine ait birkac kenar guncellenir.
    """
    edges_in_cell = h3_to_edges.get(target_h3, [])
    if not edges_in_cell:
        return

    for u, v, key in edges_in_cell:
        data = graph[u][v][key]
        _set_edge_risk(data, new_total_risk)


def compute_safe_route(graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    """
    Baslangic ve bitis koordinatlarina en yakin dugumleri bulur,
    risk agirlikli en kisa yolu hesaplar.
    """
    start_node = ox.nearest_nodes(graph, X=start_lng, Y=start_lat)
    end_node = ox.nearest_nodes(graph, X=end_lng, Y=end_lat)

    route_nodes = nx.shortest_path(
        graph, source=start_node, target=end_node, weight="risk_adjusted_length"
    )

    coordinates = [[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in route_nodes]

    total_distance = 0.0
    total_risk = 0.0
    segment_count = 0

    for i in range(len(route_nodes) - 1):
        edge_data_options = graph.get_edge_data(route_nodes[i], route_nodes[i + 1])
        edge = min(edge_data_options.values(), key=lambda d: d.get("length", 0))
        total_distance += edge.get("length", 0)
        total_risk += edge.get("risk_weight", 0)
        segment_count += 1

    avg_risk = total_risk / segment_count if segment_count > 0 else 0.0
    safety_score = max(0.0, min(100.0, 100.0 - avg_risk * 10))

    return coordinates, total_distance, safety_score


def compute_shortest_route(graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    """
    Rota kiyaslama ekrani icin STANDART en kisa yolu hesaplar.
    Risk agirligi KULLANILMAZ - sadece fiziksel yol uzunlugu ("length").

    Returns:
        (coordinates, total_distance) - [[lng, lat], ...] ve metre cinsinden mesafe
    """
    start_node = ox.nearest_nodes(graph, X=start_lng, Y=start_lat)
    end_node = ox.nearest_nodes(graph, X=end_lng, Y=end_lat)

    route_nodes = nx.shortest_path(
        graph, source=start_node, target=end_node, weight="length"
    )

    coordinates = [[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in route_nodes]

    total_distance = 0.0
    for i in range(len(route_nodes) - 1):
        edge_data_options = graph.get_edge_data(route_nodes[i], route_nodes[i + 1])
        edge = min(edge_data_options.values(), key=lambda d: d.get("length", 0))
        total_distance += edge.get("length", 0)

    return coordinates, total_distance