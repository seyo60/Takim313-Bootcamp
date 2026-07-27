# backend/routing.py
"""
OSMnx grafı üzerinde risk-ağırlıklı en güvenli rota hesaplama mantığı.
Çok Etkenli Risk Mimarisi: R_total = 0.65*Crime + 0.20*Lighting + 0.15*Live (0.0 - 1.0)

Maliyet Formülü:
Cost = length * (1.0 + alpha * risk_weight)

Mesafe Ağırlıklı Rota Riski Formülü:
R_route = sum(length_e * risk_e) / sum(length_e)

Doğru Güvenlik Skoru Formülü:
SafetyScore = (1.0 - R_route) * 100.0
RiskScore = R_route * 100.0
"""

import networkx as nx
import osmnx as ox
import h3
from collections import defaultdict

H3_RESOLUTION = 9

# Risk aversion katsayısı (Alpha)
# risk=0.0 -> maliyet * 1.0, risk=0.5 -> maliyet * 2.0, risk=1.0 -> maliyet * 3.0
RISK_AVERSION_ALPHA = 2.0

<<<<<<< Updated upstream
=======
# Ortalama yürüyüş hızı (m/s) - duration_s hesabında kullanılır.
WALKING_SPEED_MPS = 1.2

# Maksimum izin verilen snap (bağlanma) mesafesi (metre)
MAX_SNAP_DISTANCE_M = 250.0

# Chicago şehir sınırları için bounding box.
CHICAGO_BOUNDS = {
    "min_lat": 41.62,
    "max_lat": 42.05,
    "min_lng": -87.95,
    "max_lng": -87.50,
}


def find_nearest_valid_node(graph, lat: float, lng: float):
    """
    Koordinata en yakın graf düğümünü bulur ve mesafe kontrolü yapar.
    250 metreden uzak koordinatlar için ValueError fırlatır.
    """
    try:
        res = ox.nearest_nodes(graph, X=lng, Y=lat, return_dist=True)
    except TypeError:
        res = ox.nearest_nodes(graph, X=lng, Y=lat)

    if isinstance(res, tuple):
        node_id, distance = res
    else:
        node_id, distance = res, 0.0

    if distance > MAX_SNAP_DISTANCE_M:
        raise ValueError(
            f"Koordinat yaya ağına çok uzak: {distance:.1f} metre"
        )

    return node_id


def is_within_chicago(lat: float, lng: float) -> bool:
    """Koordinat Chicago bounding box'ı içinde mi?"""
    return (
        CHICAGO_BOUNDS["min_lat"] <= lat <= CHICAGO_BOUNDS["max_lat"]
        and CHICAGO_BOUNDS["min_lng"] <= lng <= CHICAGO_BOUNDS["max_lng"]
    )


>>>>>>> Stashed changes
_graph_cache = None


def prune_graph_attributes(G) -> None:
    """
    RAM kullanımını optimize etmek için graf üzerindeki gereksiz metin niteliklerini budar.
    Sadece rotalama ve koordinat için gerekli temel nitelikleri korur.
    """
    essential_node_attrs = {"x", "y"}
    essential_edge_attrs = {"length", "risk_weight", "risk_adjusted_length"}

    for node, data in G.nodes(data=True):
        keys_to_remove = [k for k in data.keys() if k not in essential_node_attrs]
        for k in keys_to_remove:
            del data[k]

    for u, v, k, data in G.edges(keys=True, data=True):
        keys_to_remove = [key for key in data.keys() if key not in essential_edge_attrs]
        for key in keys_to_remove:
            del data[key]


def load_graph(graphml_path: str = "test_network.graphml"):
    """
    Graf dosyasını bir kere yükler, nitelikleri budar ve bellekte tutar.
    """
    global _graph_cache
    if _graph_cache is None:
        print(f"Graf yükleniyor: {graphml_path}")
        _graph_cache = ox.load_graphml(graphml_path)
        print(f"Graf yüklendi: {len(_graph_cache.nodes)} kavşak, {len(_graph_cache.edges)} sokak parçası")
        print("Bellek optimizasyonu: Gereksiz graf nitelikleri budanıyor...")
        prune_graph_attributes(_graph_cache)
    return _graph_cache


def build_risk_lookup(heatmap_points) -> dict:
    """
    crud.get_all_heatmap_points()'ten dönen kayıtları kullanarak
    {h3_index: total_risk} şeklinde sözlük oluşturur.
    """
    risk_sums: dict = {}
    for point in heatmap_points:
        risk_sums.setdefault(point.h3_index, []).append(point.total_risk)
    return {h3_idx: sum(values) / len(values) for h3_idx, values in risk_sums.items()}


def _set_edge_risk(data: dict, risk_weight: float, alpha: float = RISK_AVERSION_ALPHA) -> None:
    """Bir kenarın risk ağırlığını ve alpha tabanlı ayarlanmış uzunluğunu set eder."""
    length_meters = float(data.get("length", 1.0))
    norm_risk = max(0.0, min(1.0, float(risk_weight)))
    data["risk_weight"] = norm_risk
    data["risk_adjusted_length"] = length_meters * (1.0 + alpha * norm_risk)


def apply_risk_weights(graph, risk_lookup: dict, alpha: float = RISK_AVERSION_ALPHA) -> dict:
    """
    Grafın her kenarına risk ağırlığını ekler ve H3 -> kenarlar ters dizini oluşturur.
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
        _set_edge_risk(data, risk_weight, alpha=alpha)

    return h3_to_edges


def set_absolute_risk_for_h3(graph, h3_to_edges: dict, target_h3: str, new_total_risk: float, alpha: float = RISK_AVERSION_ALPHA) -> None:
    """
    H3 hücresindeki sokakların risk değerini doğrudan günceller.
    """
    edges_in_cell = h3_to_edges.get(target_h3, [])
    if not edges_in_cell:
        return

    for u, v, key in edges_in_cell:
        data = graph[u][v][key]
        _set_edge_risk(data, new_total_risk, alpha=alpha)


def _calculate_route_metrics(graph, route_nodes):
    """
    Mesafe ağırlıklı rota riski R_route = sum(L_e * R_e) / sum(L_e) ve
    doğru SafetyScore = (1 - R_route) * 100 metriklerini hesaplar.
    """
    coordinates = [[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in route_nodes]

    total_distance = 0.0
    risk_distance_sum = 0.0

    for i in range(len(route_nodes) - 1):
        edge_data_options = graph.get_edge_data(route_nodes[i], route_nodes[i + 1])
        edge = min(edge_data_options.values(), key=lambda d: d.get("length", 0))
        length = float(edge.get("length", 0.0))
        risk = float(edge.get("risk_weight", 0.0))

        total_distance += length
        risk_distance_sum += length * risk

    route_risk = (risk_distance_sum / total_distance) if total_distance > 0 else 0.0
    route_risk = max(0.0, min(1.0, route_risk))
    
    safety_score = round((1.0 - route_risk) * 100.0, 1)
    risk_score = round(route_risk * 100.0, 1)

    return coordinates, total_distance, route_risk, safety_score, risk_score


def compute_safe_route(graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float, alpha: float = RISK_AVERSION_ALPHA):
    """
    Risk ağırlıklı en güvenli rotayı hesaplar.
    """
    start_node = find_nearest_valid_node(graph, start_lat, start_lng)
    end_node = find_nearest_valid_node(graph, end_lat, end_lng)

    route_nodes = nx.shortest_path(
        graph, source=start_node, target=end_node, weight="risk_adjusted_length"
    )

<<<<<<< Updated upstream
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
=======
    coordinates, total_distance, route_risk, safety_score, risk_score = _calculate_route_metrics(graph, route_nodes)
    return coordinates, total_distance, safety_score, route_risk


def compute_shortest_route(graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    """
    Standart fiziksel en kısa yolu hesaplar. Mesafe ağırlıklı risk hesabı aynı yöntemle yapılır.
    """
    start_node = find_nearest_valid_node(graph, start_lat, start_lng)
    end_node = find_nearest_valid_node(graph, end_lat, end_lng)

    route_nodes = nx.shortest_path(
        graph, source=start_node, target=end_node, weight="length"
    )

    coordinates, total_distance, route_risk, safety_score, risk_score = _calculate_route_metrics(graph, route_nodes)
    return coordinates, total_distance, safety_score, route_risk
>>>>>>> Stashed changes
