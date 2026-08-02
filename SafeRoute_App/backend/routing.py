# backend/routing.py
"""
OSMnx grafı üzerinde risk-ağırlıklı en güvenli rota hesaplama mantığı.
Çok Etkenli Risk Mimarisi: R_total = 0.65*Crime + 0.20*Lighting + 0.15*Live (0.0 - 1.0)

Maliyet Formülü:
Cost = length * (
    1.0
    + alpha * risk_weight
    + red_penalty * max(0, (risk_weight - red_threshold) / (1 - red_threshold))^2
)

Mesafe Ağırlıklı Rota Riski Formülü:
R_route = sum(length_e * risk_e) / sum(length_e)

Doğru Güvenlik Skoru Formülü:
SafetyScore = (1.0 - R_route) * 100.0
RiskScore = R_route * 100.0
"""

import networkx as nx
import osmnx as ox
from collections import defaultdict
import math
from config import settings
from routing_cost import (
    DEFAULT_RED_RISK_PENALTY,
    DEFAULT_RED_RISK_THRESHOLD,
    DEFAULT_UNKNOWN_RISK,
    risk_adjusted_length,
)
from h3_policy import (
    DEFAULT_EDGE_SAMPLE_SPACING_M,
    LEGACY_H3_RESOLUTION,
    aggregate_edge_cell_risks,
    edge_lat_lng_points,
    polyline_h3_cells,
    resolve_hierarchical_risk,
    validate_h3_resolution,
)

H3_RESOLUTION = LEGACY_H3_RESOLUTION

# Risk aversion katsayısı (Alpha)
RISK_AVERSION_ALPHA = 2.0
RED_RISK_THRESHOLD = DEFAULT_RED_RISK_THRESHOLD
RED_RISK_PENALTY = DEFAULT_RED_RISK_PENALTY
UNKNOWN_RISK = DEFAULT_UNKNOWN_RISK

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
        raise ValueError(f"Koordinat yaya ağına çok uzak: {distance:.1f} metre")

    return node_id


def build_h3_spatial_index(
    graph,
    h3_resolution: int | None = None,
    sample_spacing_m: float | None = None,
):
    """
    Grafın tüm kenarlarını geometrileri boyunca H3 hücrelerine bağlayan ters indeks oluşturur.
    O(1) risk güncellemesi için kullanılır.
    """
    h3_to_edges = defaultdict(list)
    selected_resolution = validate_h3_resolution(
        h3_resolution
        if h3_resolution is not None
        else getattr(settings, "routing_h3_resolution", H3_RESOLUTION)
    )
    spacing_m = (
        float(sample_spacing_m)
        if sample_spacing_m is not None
        else float(
            getattr(
                settings,
                "routing_edge_sample_spacing_m",
                DEFAULT_EDGE_SAMPLE_SPACING_M,
            )
        )
    )

    for u, v, k, data in graph.edges(keys=True, data=True):
        cells = polyline_h3_cells(
            edge_lat_lng_points(graph, u, v, data),
            resolution=selected_resolution,
            spacing_m=spacing_m,
        )
        for cell in cells:
            h3_to_edges[cell].append((u, v, k))

    return h3_to_edges

def build_risk_lookup(heatmap_points) -> dict[str, float]:
    """
    H3 kayıtlarını routing motorunun beklediği
    {h3_index: total_risk} sözlüğüne dönüştürür.
    """
    risk_lookup: dict[str, float] = {}

    for point in heatmap_points:
        h3_index = getattr(point, "h3_index", None)
        total_risk = getattr(point, "total_risk", None)

        if not h3_index:
            continue

        if total_risk is None:
            # Veri yokluğu "tam güvenli" değildir. Lookup dışında bırakılır ve
            # rota motoru kontrollü UNKNOWN_RISK değerini uygular.
            continue

        risk = float(total_risk)

        if not math.isfinite(risk) or not 0.0 <= risk <= 1.0:
            raise ValueError(
                f"Geçersiz total_risk: h3_index={h3_index}, "
                f"total_risk={total_risk}. Beklenen aralık 0.0–1.0."
            )

        risk_lookup[str(h3_index)] = risk

    return risk_lookup


def update_graph_risks(graph, risk_lookup: dict, h3_to_edges: dict, alpha: float = RISK_AVERSION_ALPHA):
    """
    Tüm graf kenarlarının risk ağırlıklarını H3 tablosundaki değerlerle günceller.
    Kırmızı risk eşiği üzerinde karesel bariyer cezası uygular.
    """
    for u, v, k, data in graph.edges(keys=True, data=True):
        length = float(data.get("length", 0.0))
        data["risk_weight"] = UNKNOWN_RISK
        data["risk_data_available"] = False
        data["risk_adjusted_length"] = risk_adjusted_length(
            length,
            UNKNOWN_RISK,
            alpha=alpha,
            red_threshold=RED_RISK_THRESHOLD,
            red_penalty=RED_RISK_PENALTY,
        )

    parent_resolution = validate_h3_resolution(
        getattr(settings, "h3_parent_resolution", LEGACY_H3_RESOLUTION)
    )
    max_weight = float(
        getattr(settings, "routing_edge_max_risk_weight", 0.65)
    )
    edge_samples: dict[tuple, list[tuple[float, bool]]] = defaultdict(list)
    for cell, edges in h3_to_edges.items():
        cell_risk, data_available, _source = resolve_hierarchical_risk(
            cell,
            risk_lookup,
            parent_resolution=parent_resolution,
            unknown_risk=UNKNOWN_RISK,
        )
        for edge_key in edges:
            edge_samples[tuple(edge_key)].append((cell_risk, data_available))

    for (u, v, k), samples in edge_samples.items():
        if not graph.has_edge(u, v, key=k):
            continue
        edge_data = graph[u][v][k]
        norm_risk = aggregate_edge_cell_risks(
            (risk for risk, _available in samples),
            max_weight=max_weight,
        )
        edge_data["risk_weight"] = norm_risk
        edge_data["risk_data_available"] = any(
            available for _risk, available in samples
        )
        length = edge_data.get("length", 0.0)
        edge_data["risk_adjusted_length"] = risk_adjusted_length(
            length,
            norm_risk,
            alpha=alpha,
            red_threshold=RED_RISK_THRESHOLD,
            red_penalty=RED_RISK_PENALTY,
        )


def set_absolute_risk_for_h3(graph, h3_to_edges: dict, target_h3: str, new_risk: float, alpha: float = RISK_AVERSION_ALPHA):
    """
    Belirli bir H3 hücresindeki tüm kenarların riskini doğrudan new_risk yapar.
    """
    edges = h3_to_edges.get(target_h3, [])
    norm_risk = max(0.0, min(1.0, float(new_risk)))

    for u, v, k in edges:
        if graph.has_edge(u, v, key=k):
            edge_data = graph[u][v][k]
            edge_data["risk_weight"] = norm_risk
            edge_data["risk_data_available"] = True
            length = edge_data.get("length", 0.0)
            edge_data["risk_adjusted_length"] = risk_adjusted_length(
                length,
                norm_risk,
                alpha=alpha,
                red_threshold=RED_RISK_THRESHOLD,
                red_penalty=RED_RISK_PENALTY,
            )


def _calculate_route_metrics(graph, route_nodes: list, edge_weight: str = "length"):
    """
    Bir rota düğüm dizisi için doğru uzunluk-ağırlıklı risk ve güvenlik skorunu hesaplar.
    """
    coordinates = [[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in route_nodes]

    total_distance = 0.0
    weighted_risk_sum = 0.0

    for i in range(len(route_nodes) - 1):
        u, v = route_nodes[i], route_nodes[i + 1]
        edge_data_options = graph.get_edge_data(u, v)
        edge = min(edge_data_options.values(), key=lambda d: d.get(edge_weight, float("inf")))

        length = edge.get("length", 0.0)
        risk = edge.get("risk_weight", 0.0)

        total_distance += length
        weighted_risk_sum += length * risk

    if total_distance > 0:
        route_risk = weighted_risk_sum / total_distance
    else:
        route_risk = 0.0

    route_risk = max(0.0, min(1.0, route_risk))
    risk_score = route_risk * 100.0
    safety_score = (1.0 - route_risk) * 100.0

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

    coordinates, total_distance, route_risk, safety_score, risk_score = _calculate_route_metrics(
        graph,
        route_nodes,
        edge_weight="risk_adjusted_length",
    )
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

    coordinates, total_distance, route_risk, safety_score, risk_score = _calculate_route_metrics(
        graph,
        route_nodes,
        edge_weight="length",
    )
    return coordinates, total_distance, safety_score, route_risk
