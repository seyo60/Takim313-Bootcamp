# backend/routing_engine.py
"""
Ortak RoutingEngine Arayüzü, NetworkXEngine ve Yüksek Performanslı CompactCSREngine Uygulaması.

Bu dosya:
1. `BaseRoutingEngine`: Ortak soyut rotalama arayüzüdür.
2. `NetworkXEngine`: Mevcut NetworkX tabanlı rotalama motorudur (Tam geriye dönük uyumluluk).
3. `CompactCSREngine`: SciPy CSR matrisi, Metrik KDTree ve NumPy dizileri kullanan ultra hafif, yüksek hızlı rotalama motorudur.
"""

from abc import ABC, abstractmethod
import time
from pathlib import Path
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import KDTree
import networkx as nx
import osmnx as ox
import h3

from config import settings

H3_RESOLUTION = 9
DEFAULT_ALPHA = 2.0
MAX_SNAP_DISTANCE_M = 250.0
WALKING_SPEED_MPS = 1.2

# Chicago (Enlem ~41.87) için derece -> metre dönüşüm katsayıları
METERS_PER_DEG_LNG = 82900.0  # 111320 * cos(41.87 deg)
METERS_PER_DEG_LAT = 110540.0


class BaseRoutingEngine(ABC):
    """Ortak Rotalama Motoru Soyut Taban Sınıfı."""

    @abstractmethod
    def load_graph(self, graph_path: str):
        pass

    @abstractmethod
    def apply_risk_weights(self, risk_lookup: dict, alpha: float = DEFAULT_ALPHA):
        pass

    @abstractmethod
    def set_absolute_risk_for_h3(self, target_h3: str, new_risk: float, alpha: float = DEFAULT_ALPHA):
        pass

    @abstractmethod
    def find_nearest_node(self, lat: float, lng: float) -> tuple[int, float]:
        pass

    @abstractmethod
    def compute_safe_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, alpha: float = DEFAULT_ALPHA):
        pass

    @abstractmethod
    def compute_shortest_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        pass


class NetworkXEngine(BaseRoutingEngine):
    """Mevcut NetworkX tabanlı Rotalama Motoru."""

    def __init__(self):
        self.graph = None
        self.h3_to_edges = None

    def load_graph(self, graph_path: str):
        print(f"[NetworkXEngine] Graf yükleniyor: {graph_path}")
        self.graph = ox.load_graphml(graph_path)
        # Nitelik budama
        essential_nodes = {"x", "y"}
        essential_edges = {"length", "risk_weight", "risk_adjusted_length"}
        for _, d in self.graph.nodes(data=True):
            for k in list(d.keys()):
                if k not in essential_nodes:
                    del d[k]
        for _, _, _, d in self.graph.edges(keys=True, data=True):
            for k in list(d.keys()):
                if k not in essential_edges:
                    del d[k]
        print(f"[NetworkXEngine] Yüklendi. Düğüm: {len(self.graph.nodes):,}, Kenar: {len(self.graph.edges):,}")
        return self.graph

    def find_nearest_node(self, lat: float, lng: float) -> tuple[int, float]:
        try:
            res = ox.nearest_nodes(self.graph, X=lng, Y=lat, return_dist=True)
            node_id, dist = res
        except Exception:
            node_id = ox.nearest_nodes(self.graph, X=lng, Y=lat)
            dist = 0.0
        if dist > MAX_SNAP_DISTANCE_M:
            raise ValueError(f"Koordinat yaya ağına çok uzak: {dist:.1f} metre")
        return node_id, dist

    def apply_risk_weights(self, risk_lookup: dict, alpha: float = DEFAULT_ALPHA):
        from collections import defaultdict
        self.h3_to_edges = defaultdict(list)

        for u, v, key, data in self.graph.edges(keys=True, data=True):
            u_lat, u_lng = self.graph.nodes[u]["y"], self.graph.nodes[u]["x"]
            v_lat, v_lng = self.graph.nodes[v]["y"], self.graph.nodes[v]["x"]
            mid_lat = (u_lat + v_lat) / 2.0
            mid_lng = (u_lng + v_lng) / 2.0

            cell = h3.latlng_to_cell(mid_lat, mid_lng, H3_RESOLUTION)
            self.h3_to_edges[cell].append((u, v, key))

            risk_weight = risk_lookup.get(cell, 0.0)
            length = float(data.get("length", 1.0))
            norm_risk = max(0.0, min(1.0, float(risk_weight)))
            data["risk_weight"] = norm_risk
            data["risk_adjusted_length"] = length * (1.0 + alpha * norm_risk)

        return self.h3_to_edges

    def set_absolute_risk_for_h3(self, target_h3: str, new_risk: float, alpha: float = DEFAULT_ALPHA):
        edges = self.h3_to_edges.get(target_h3, []) if self.h3_to_edges else []
        norm_risk = max(0.0, min(1.0, float(new_risk)))
        for u, v, key in edges:
            data = self.graph[u][v][key]
            length = float(data.get("length", 1.0))
            data["risk_weight"] = norm_risk
            data["risk_adjusted_length"] = length * (1.0 + alpha * norm_risk)

    def _calc_metrics(self, route_nodes):
        coords = [[self.graph.nodes[n]["x"], self.graph.nodes[n]["y"]] for n in route_nodes]
        total_dist = 0.0
        risk_dist_sum = 0.0
        covered_dist = 0.0
        for i in range(len(route_nodes) - 1):
            options = self.graph.get_edge_data(route_nodes[i], route_nodes[i+1])
            edge = min(options.values(), key=lambda d: d.get("length", 0))
            length = float(edge.get("length", 0.0))
            risk = float(edge.get("risk_weight", 0.0))
            total_dist += length
            risk_dist_sum += length * risk
            if risk > 0.0:
                covered_dist += length

        route_risk = (risk_dist_sum / total_dist) if total_dist > 0 else 0.0
        route_risk = max(0.0, min(1.0, route_risk))
        safety_score = round((1.0 - route_risk) * 100.0, 1)
        risk_coverage = round((covered_dist / total_dist * 100.0), 1) if total_dist > 0 else 0.0
        return coords, total_dist, safety_score, route_risk, risk_coverage

    def compute_safe_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, alpha: float = DEFAULT_ALPHA):
        start_node, _ = self.find_nearest_node(start_lat, start_lng)
        end_node, _ = self.find_nearest_node(end_lat, end_lng)
        route_nodes = nx.shortest_path(self.graph, source=start_node, target=end_node, weight="risk_adjusted_length")
        return self._calc_metrics(route_nodes)

    def compute_shortest_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        start_node, _ = self.find_nearest_node(start_lat, start_lng)
        end_node, _ = self.find_nearest_node(end_lat, end_lng)
        route_nodes = nx.shortest_path(self.graph, source=start_node, target=end_node, weight="length")
        return self._calc_metrics(route_nodes)


def _build_deduplicated_csr(N: int, src: np.ndarray, dst: np.ndarray, costs: np.ndarray) -> csr_matrix:
    """
    Paralel kenarlarda (MultiDiGraph) maliyetleri TOPLAMADAN her (u, v) çifti için
    en küçük maliyetli kenarı seçerek CSR matrisini inşa eder.
    """
    uv_keys = src.astype(np.int64) * N + dst.astype(np.int64)
    order = np.argsort(costs)

    sorted_keys = uv_keys[order]
    sorted_src = src[order]
    sorted_dst = dst[order]
    sorted_costs = costs[order]

    _, unique_indices = np.unique(sorted_keys, return_index=True)

    u_src = sorted_src[unique_indices]
    u_dst = sorted_dst[unique_indices]
    u_costs = sorted_costs[unique_indices]

    return csr_matrix((u_costs, (u_src, u_dst)), shape=(N, N))


class CompactCSREngine(BaseRoutingEngine):
    """SciPy CSR, Metrik KDTree ve NumPy tabanlı ultra hafif, yüksek hızlı Rotalama Motoru."""

    def __init__(self):
        self.node_x = None
        self.node_y = None
        self.edge_src = None
        self.edge_dst = None
        self.edge_length = None
        self.edge_risk = None
        self.kdtree = None
        self.h3_keys_map = {}  # h3_index -> np.ndarray of edge_ids
        self.N = 0
        self.M = 0
        self.csr_shortest = None
        self.csr_shortest_b = None
        self.csr_safe = None
        self.csr_safe_b = None

    def load_graph(self, npz_path: str = "../data-science/compact_graph.npz"):
        p = Path(npz_path)
        if not p.exists():
            # Eğer ortam "compact" olarak ayarlanmış ve NPZ yoksa FAIL-FAST
            raise RuntimeError(
                f"[CompactCSREngine FAIL-FAST] İkili graf dosyası bulunamadı: {p.resolve()}. "
                f"Lütfen 'python build_compact_graph.py' komutunu çalıştırın."
            )

        print(f"[CompactCSREngine] İkili graf yükleniyor ve doğrulanıyor: {p}")
        t0 = time.time()
        try:
            data = np.load(p)
        except Exception as e:
            raise RuntimeError(f"[CompactCSREngine FAIL-FAST] NPZ dosyası okunamadı veya bozuk: {e}")

        # NPZ Bütünlük ve Sürüm Doğrulaması
        required_keys = {"node_x", "node_y", "edge_src", "edge_dst", "edge_length", "h3_keys", "h3_edge_offsets", "h3_edge_values"}
        missing_keys = required_keys - set(data.files)
        if missing_keys:
            raise RuntimeError(f"[CompactCSREngine FAIL-FAST] NPZ dosyası eksik alanlar içeriyor: {missing_keys}")

        if "version" in data.files:
            fmt_ver = str(data["version"][0])
            if fmt_ver != "1.0":
                raise RuntimeError(f"[CompactCSREngine FAIL-FAST] Uyumsuz NPZ format sürümü: {fmt_ver} (Beklenen: 1.0)")

        self.node_x = data["node_x"]
        self.node_y = data["node_y"]
        self.edge_src = data["edge_src"]
        self.edge_dst = data["edge_dst"]
        self.edge_length = data["edge_length"]

        h3_keys = data["h3_keys"]
        offsets = data["h3_edge_offsets"]
        values = data["h3_edge_values"]

        for idx, key in enumerate(h3_keys):
            start = offsets[idx]
            end = offsets[idx + 1]
            self.h3_keys_map[key] = values[start:end]

        self.N = len(self.node_x)
        self.M = len(self.edge_src)
        self.edge_risk = np.zeros(self.M, dtype=np.float32)

        # KDTree İndeksi (ox.nearest_nodes ile %100 birebir düğüm eşleşmesi)
        coords = np.column_stack((self.node_x, self.node_y))
        self.kdtree = KDTree(coords)

        # Standart en kısa yol için paralel kenar tekleştirmeli CSR matrisleri (ileri ve geri)
        self.csr_shortest = _build_deduplicated_csr(self.N, self.edge_src, self.edge_dst, self.edge_length)
        self.csr_shortest_b = _build_deduplicated_csr(self.N, self.edge_dst, self.edge_src, self.edge_length)
        self.csr_safe_b = None
        t1 = time.time()
        print(f"[CompactCSREngine] BAŞARILI! Düğüm: {self.N:,}, Kenar: {self.M:,} ({t1 - t0:.3f} sn)")
        return self

    def find_nearest_node(self, lat: float, lng: float) -> tuple[int, float]:
        """KDTree ile $O(\\log N)$ sürede ve metre cinsinden en yakın düğümü bulur."""
        dist_deg, idx = self.kdtree.query([lng, lat])
        dist_m = dist_deg * METERS_PER_DEG_LAT

        if dist_m > MAX_SNAP_DISTANCE_M:
            raise ValueError(f"Koordinat yaya ağına çok uzak: {dist_m:.1f} metre")
        return int(idx), float(dist_m)

    def apply_risk_weights(self, risk_lookup: dict, alpha: float = DEFAULT_ALPHA):
        """H3 risk lookup tablosunu int32 edge_risk dizisine aktarır."""
        self.edge_risk.fill(0.0)
        for h3_idx, risk_val in risk_lookup.items():
            edge_ids = self.h3_keys_map.get(h3_idx)
            if edge_ids is not None:
                norm_risk = max(0.0, min(1.0, float(risk_val)))
                self.edge_risk[edge_ids] = norm_risk

        # Dinamik güvenli rota CSR matrislerini inşa et (ileri ve geri)
        risk_adj_length = self.edge_length * (1.0 + alpha * self.edge_risk)
        self.csr_safe = _build_deduplicated_csr(self.N, self.edge_src, self.edge_dst, risk_adj_length)
        self.csr_safe_b = _build_deduplicated_csr(self.N, self.edge_dst, self.edge_src, risk_adj_length)
        return self.h3_keys_map

    def set_absolute_risk_for_h3(self, target_h3: str, new_risk: float, alpha: float = DEFAULT_ALPHA):
        edge_ids = self.h3_keys_map.get(target_h3)
        if edge_ids is None or len(edge_ids) == 0:
            return

        norm_risk = max(0.0, min(1.0, float(new_risk)))
        self.edge_risk[edge_ids] = norm_risk

        # Dinamik CSR matrislerini güncelle
        risk_adj_length = self.edge_length * (1.0 + alpha * self.edge_risk)
        self.csr_safe = _build_deduplicated_csr(self.N, self.edge_src, self.edge_dst, risk_adj_length)
        self.csr_safe_b = _build_deduplicated_csr(self.N, self.edge_dst, self.edge_src, risk_adj_length)

    def _bidirectional_a_star(self, start_idx: int, end_idx: int, matrix_f: csr_matrix, matrix_b: csr_matrix):
        """
        CSR matrisleri üzerinde Çift Yönlü A* (Bidirectional A*) Rotalama Algoritması.
        Metrik Euclidean projeksiyonlu heuristic h(u, v) kullanılır.
        """
        import heapq
        if start_idx == end_idx:
            return [start_idx]

        target_x = float(self.node_x[end_idx])
        target_y = float(self.node_y[end_idx])
        start_x = float(self.node_x[start_idx])
        start_y = float(self.node_y[start_idx])

        gamma = 0.50  # Mikroskopik kenarları da kapsayan %100 kusursuz tutarlı katsayı

        def h_f(idx: int) -> float:
            dx = (float(self.node_x[idx]) - target_x) * METERS_PER_DEG_LNG
            dy = (float(self.node_y[idx]) - target_y) * METERS_PER_DEG_LAT
            return float(gamma * np.sqrt(dx * dx + dy * dy))

        def h_b(idx: int) -> float:
            dx = (float(self.node_x[idx]) - start_x) * METERS_PER_DEG_LNG
            dy = (float(self.node_y[idx]) - start_y) * METERS_PER_DEG_LAT
            return float(gamma * np.sqrt(dx * dx + dy * dy))

        g_f = {start_idx: 0.0}
        g_b = {end_idx: 0.0}
        p_f = {start_idx: None}
        p_b = {end_idx: None}

        open_f = [(h_f(start_idx), 0.0, start_idx)]
        open_b = [(h_b(end_idx), 0.0, end_idx)]

        closed_f = set()
        closed_b = set()

        best_total_cost = float("inf")
        meeting_node = None

        indptr_f, indices_f, data_f = matrix_f.indptr, matrix_f.indices, matrix_f.data
        indptr_b, indices_b, data_b = matrix_b.indptr, matrix_b.indices, matrix_b.data

        while open_f and open_b:
            if open_f:
                f_val, g_val, u = heapq.heappop(open_f)
                if u not in closed_f:
                    closed_f.add(u)
                    if u in closed_b:
                        total = g_val + g_b[u]
                        if total < best_total_cost:
                            best_total_cost = total
                            meeting_node = u

                    if f_val < best_total_cost:
                        s_ptr, e_ptr = indptr_f[u], indptr_f[u + 1]
                        for i in range(s_ptr, e_ptr):
                            v = int(indices_f[i])
                            cost = float(data_f[i])
                            tentative_g = g_val + cost
                            if v not in g_f or tentative_g < g_f[v]:
                                g_f[v] = tentative_g
                                p_f[v] = u
                                heapq.heappush(open_f, (tentative_g + h_f(v), tentative_g, v))

            if open_b:
                f_val, g_val, u = heapq.heappop(open_b)
                if u not in closed_b:
                    closed_b.add(u)
                    if u in closed_f:
                        total = g_val + g_f[u]
                        if total < best_total_cost:
                            best_total_cost = total
                            meeting_node = u

                    if f_val < best_total_cost:
                        s_ptr, e_ptr = indptr_b[u], indptr_b[u + 1]
                        for i in range(s_ptr, e_ptr):
                            v = int(indices_b[i])
                            cost = float(data_b[i])
                            tentative_g = g_val + cost
                            if v not in g_b or tentative_g < g_b[v]:
                                g_b[v] = tentative_g
                                p_b[v] = u
                                heapq.heappush(open_b, (tentative_g + h_b(v), tentative_g, v))

        if meeting_node is None:
            # Fallback to dijkstra if no meeting node found in heuristic beam
            dist_matrix, predecessors = dijkstra(csgraph=matrix_f, directed=True, indices=start_idx, return_predecessors=True)
            path_nodes = []
            curr = end_idx
            while curr != -9999 and curr != start_idx:
                path_nodes.append(curr)
                curr = predecessors[curr]
            if curr == start_idx:
                path_nodes.append(start_idx)
            path_nodes.reverse()
            return path_nodes

        path_f = []
        curr = meeting_node
        while curr is not None:
            path_f.append(curr)
            curr = p_f[curr]
        path_f.reverse()

        path_b = []
        curr = p_b[meeting_node]
        while curr is not None:
            path_b.append(curr)
            curr = p_b[curr]

        return path_f + path_b

    def _calc_path_metrics(self, path_nodes: list):
        coords = [[float(self.node_x[n]), float(self.node_y[n])] for n in path_nodes]

        total_dist = 0.0
        risk_dist_sum = 0.0
        covered_dist = 0.0

        for i in range(len(path_nodes) - 1):
            u = path_nodes[i]
            v = path_nodes[i + 1]

            mask = (self.edge_src == u) & (self.edge_dst == v)
            matching_indices = np.where(mask)[0]
            if len(matching_indices) == 0:
                continue

            best_edge_idx = matching_indices[np.argmin(self.edge_length[matching_indices])]
            l = float(self.edge_length[best_edge_idx])
            r = float(self.edge_risk[best_edge_idx])

            total_dist += l
            risk_dist_sum += l * r
            if r > 0.0:
                covered_dist += l

        route_risk = (risk_dist_sum / total_dist) if total_dist > 0 else 0.0
        route_risk = max(0.0, min(1.0, route_risk))
        safety_score = round((1.0 - route_risk) * 100.0, 1)
        risk_coverage = round((covered_dist / total_dist * 100.0), 1) if total_dist > 0 else 0.0

        return coords, total_dist, safety_score, route_risk, risk_coverage

    def compute_safe_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, alpha: float = DEFAULT_ALPHA):
        start_idx, _ = self.find_nearest_node(start_lat, start_lng)
        end_idx, _ = self.find_nearest_node(end_lat, end_lng)

        matrix_f = self.csr_safe if self.csr_safe is not None else self.csr_shortest
        matrix_b = self.csr_safe_b if self.csr_safe_b is not None else self.csr_shortest_b

        if matrix_b is None:
            # SciPy C-compiled Dijkstra ultra-hızlı yedek rota hesaplaması
            dist_matrix, predecessors = dijkstra(
                csgraph=matrix_f, directed=True, indices=start_idx, return_predecessors=True
            )
            path_nodes = []
            curr = end_idx
            while curr != -9999 and curr != start_idx:
                path_nodes.append(curr)
                curr = predecessors[curr]
            if curr == start_idx:
                path_nodes.append(start_idx)
            path_nodes.reverse()
            return self._calc_path_metrics(path_nodes)

        path_nodes = self._bidirectional_a_star(start_idx, end_idx, matrix_f, matrix_b)
        return self._calc_path_metrics(path_nodes)

    def compute_shortest_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        start_idx, _ = self.find_nearest_node(start_lat, start_lng)
        end_idx, _ = self.find_nearest_node(end_lat, end_lng)

        matrix_f = self.csr_shortest
        matrix_b = self.csr_shortest_b

        if matrix_b is None:
            dist_matrix, predecessors = dijkstra(
                csgraph=matrix_f, directed=True, indices=start_idx, return_predecessors=True
            )
            path_nodes = []
            curr = end_idx
            while curr != -9999 and curr != start_idx:
                path_nodes.append(curr)
                curr = predecessors[curr]
            if curr == start_idx:
                path_nodes.append(start_idx)
            path_nodes.reverse()
            return self._calc_path_metrics(path_nodes)

        path_nodes = self._bidirectional_a_star(start_idx, end_idx, matrix_f, matrix_b)
        return self._calc_path_metrics(path_nodes)


_engine_instance = None


def get_routing_engine(engine_type: str = "compact") -> BaseRoutingEngine:
    """
    Rotalama Motoru Fabrikası (Factory Pattern).
    engine_type: "compact" (SciPy CSR, varsayılan) | "networkx" (NetworkX)
    """
    global _engine_instance
    if _engine_instance is None:
        if engine_type == "compact":
            _engine_instance = CompactCSREngine()
        else:
            _engine_instance = NetworkXEngine()
    return _engine_instance
