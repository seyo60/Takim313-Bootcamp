# backend/routing.py
"""
OSMnx grafi uzerinde risk-agirlikli en guvenli rota hesaplama mantigi.

Akis:
1. Graf dosyasi (test_network.graphml / ileride Mehmet Ali'nin tam Chicago grafi) yuklenir.
2. h3_heatmap tablosundaki risk_weight degerleri, ilgili H3 hucrelerine gore
   grafin her sokak parcasina (edge) "ek agirlik" olarak islenir.
3. Kullanicinin verdigi baslangic/bitis koordinatlari, grafin en yakin
   kavsak noktalarina (node) eslenir.
4. NetworkX'in Dijkstra tabanli shortest_path fonksiyonu, bu agirliklara gore
   en az riskli / en kisa rotayi bulur.
5. Sonuc, Mapbox'in anlayacagi [lng, lat] koordinat listesine cevrilir.
"""
import networkx as nx
import osmnx as ox
import h3

H3_RESOLUTION = 9

# Risk agirliginin mesafeye ne kadar etki edecegini kontrol eden katsayi.
# Buyudukce, algoritma riskli sokaklardan daha agresif kacinir.
RISK_WEIGHT_FACTOR = 10.0

_graph_cache = None


def load_graph(graphml_path: str = "test_network.graphml"):
    """
    Graf dosyasini bir kere yukler ve bellekte tutar.
    main.py'deki lifespan icinde, uygulama baslarken bir kere cagrilmali.
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
    {h3_index: risk_weight} seklinde hizli bir sozluk olusturur.
    Ayni h3_index'e birden fazla kayit dusuyorsa ortalamasini alir.
    """
    risk_sums: dict = {}
    for point in heatmap_points:
        risk_sums.setdefault(point.h3_index, []).append(point.risk_weight)
    return {h3_idx: sum(values) / len(values) for h3_idx, values in risk_sums.items()}


def apply_risk_weights(graph, risk_lookup: dict):
    """
    Grafin her kenarina (edge), o kenarin orta noktasinin dustugu
    H3 hucresine gore bir risk agirligi ekler.

    agirlikli_mesafe = mesafe_metre * (1 + risk_weight / RISK_WEIGHT_FACTOR)

    Riskli bir sokak, algoritmaya "daha uzunmus gibi" gosterilir,
    boylece en kisa yol algoritmasi dogal olarak bu sokaktan kacinir.
    """
    for u, v, key, data in graph.edges(keys=True, data=True):
        u_lat, u_lng = graph.nodes[u]["y"], graph.nodes[u]["x"]
        v_lat, v_lng = graph.nodes[v]["y"], graph.nodes[v]["x"]
        mid_lat = (u_lat + v_lat) / 2
        mid_lng = (u_lng + v_lng) / 2

        cell = h3.latlng_to_cell(mid_lat, mid_lng, H3_RESOLUTION)
        risk_weight = risk_lookup.get(cell, 0.0)

        length_meters = data.get("length", 1.0)
        data["risk_adjusted_length"] = length_meters * (1 + risk_weight / RISK_WEIGHT_FACTOR)
        data["risk_weight"] = risk_weight

    return graph


def compute_safe_route(graph, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
    """
    Baslangic ve bitis koordinatlarina en yakin dugumleri bulur,
    risk agirlikli en kisa yolu hesaplar.

    Donen deger: (coordinates, distance_meters, safety_score)
    """
    start_node = ox.nearest_nodes(graph, X=start_lng, Y=start_lat)
    end_node = ox.nearest_nodes(graph, X=end_lng, Y=end_lat)

    route_nodes = nx.shortest_path(
        graph, source=start_node, target=end_node, weight="risk_adjusted_length"
    )

    coordinates = [[graph.nodes[n]["x"], graph.nodes[n]["y"]] for n in route_nodes]

    # Gercek (risk agirliksiz) toplam mesafe ve ortalama risk skorunu hesapla
    total_distance = 0.0
    total_risk = 0.0
    segment_count = 0

    for i in range(len(route_nodes) - 1):
        edge_data_options = graph.get_edge_data(route_nodes[i], route_nodes[i + 1])
        # MultiDiGraph oldugu icin ayni iki nokta arasinda birden fazla yol olabilir, en kisasini al
        edge = min(edge_data_options.values(), key=lambda d: d.get("length", 0))
        total_distance += edge.get("length", 0)
        total_risk += edge.get("risk_weight", 0)
        segment_count += 1

    avg_risk = total_risk / segment_count if segment_count > 0 else 0.0
    # Basit bir guvenlik skoru: risk ne kadar dusukse skor o kadar yuksek (0-100 arasi)
    safety_score = max(0.0, min(100.0, 100.0 - avg_risk * 10))

    return coordinates, total_distance, safety_score