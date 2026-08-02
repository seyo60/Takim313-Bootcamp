# backend/routing_engine.py
"""
Ortak RoutingEngine Arayüzü, NetworkXEngine ve Yüksek Performanslı CompactCSREngine Uygulaması.

Bu dosya:
1. `BaseRoutingEngine`: Ortak soyut rotalama arayüzüdür.
2. `NetworkXEngine`: Mevcut NetworkX tabanlı rotalama motorudur (Tam geriye dönük uyumluluk).
3. `CompactCSREngine`: SciPy CSR matrisi, Metrik KDTree ve NumPy dizileri kullanan ultra hafif, yüksek hızlı rotalama motorudur.
"""

from abc import ABC, abstractmethod
import dataclasses
import hashlib
from functools import partial
import time
from pathlib import Path
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import KDTree

from config import settings
from routing_cost import (
    DEFAULT_RED_RISK_PENALTY,
    DEFAULT_RED_RISK_THRESHOLD,
    DEFAULT_UNKNOWN_RISK,
    risk_adjusted_length,
    risk_adjusted_lengths,
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
from routing_diversify import penalty_diversify_paths
from routing_budget_bracket import bracket_alpha_candidates
from routing_edge_lookup import EdgeIndexLookup
from routing_subgraph import build_budget_subgraph
from routing_profiles import (
    RouteCandidate,
    RouteSelectionResult,
    parse_candidate_alphas,
    select_route_candidate,
)

H3_RESOLUTION = LEGACY_H3_RESOLUTION
DEFAULT_ALPHA = 2.0
DEFAULT_RED_THRESHOLD = DEFAULT_RED_RISK_THRESHOLD
DEFAULT_RED_PENALTY = DEFAULT_RED_RISK_PENALTY
DEFAULT_NO_DATA_RISK = DEFAULT_UNKNOWN_RISK
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
    def set_absolute_risk_for_h3(self, target_h3: str, new_risk: float, alpha: float | None = None):
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

    @abstractmethod
    def compute_profiled_route(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        profile: str = "balanced",
    ) -> RouteSelectionResult:
        pass


class NetworkXEngine(BaseRoutingEngine):
    """Mevcut NetworkX tabanlı Rotalama Motoru."""

    def __init__(self):
        self.graph = None
        self.h3_to_edges = None
        self._cost_alpha = DEFAULT_ALPHA
        self._red_threshold = DEFAULT_RED_THRESHOLD
        self._red_penalty = DEFAULT_RED_PENALTY
        self._no_data_risk = DEFAULT_NO_DATA_RISK
        self._risk_lookup: dict[str, float] = {}
        self.graph_artifact_id = "unloaded"
        self.h3_resolution = validate_h3_resolution(
            getattr(settings, "routing_h3_resolution", H3_RESOLUTION)
        )

    def load_graph(self, graph_path: str):
        import osmnx as ox

        print(f"[NetworkXEngine] Graf yükleniyor: {graph_path}")
        with open(graph_path, "rb") as graph_file:
            digest = hashlib.sha256()
            for chunk in iter(lambda: graph_file.read(1024 * 1024), b""):
                digest.update(chunk)
        self.graph_artifact_id = f"sha256:{digest.hexdigest()}"
        self.graph = ox.load_graphml(graph_path)
        # Nitelik budama
        essential_nodes = {"x", "y"}
        essential_edges = {
            "length",
            "geometry",
            "name",
            "ref",
            "highway",
            "junction",
            "oneway",
            "risk_weight",
            "risk_adjusted_length",
            "risk_data_available",
        }
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
        import osmnx as ox

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
        self._risk_lookup = {
            str(key): max(0.0, min(1.0, float(value)))
            for key, value in risk_lookup.items()
        }
        risk_lookup = self._risk_lookup
        self.h3_to_edges = defaultdict(list)
        self._cost_alpha = float(alpha)
        self._red_threshold = float(getattr(settings, "routing_red_risk_threshold", DEFAULT_RED_THRESHOLD))
        self._red_penalty = float(getattr(settings, "routing_red_risk_penalty", DEFAULT_RED_PENALTY))
        self._no_data_risk = float(getattr(settings, "routing_unknown_risk", DEFAULT_NO_DATA_RISK))
        self.h3_resolution = validate_h3_resolution(
            getattr(settings, "routing_h3_resolution", self.h3_resolution)
        )
        parent_resolution = validate_h3_resolution(
            getattr(settings, "h3_parent_resolution", LEGACY_H3_RESOLUTION)
        )
        sample_spacing_m = float(
            getattr(
                settings,
                "routing_edge_sample_spacing_m",
                DEFAULT_EDGE_SAMPLE_SPACING_M,
            )
        )
        max_risk_weight = float(
            getattr(settings, "routing_edge_max_risk_weight", 0.65)
        )

        for u, v, key, data in self.graph.edges(keys=True, data=True):
            points = edge_lat_lng_points(self.graph, u, v, data)
            cells = polyline_h3_cells(
                points,
                resolution=self.h3_resolution,
                spacing_m=sample_spacing_m,
            )
            resolved_risks: list[float] = []
            resolved_data_flags: list[bool] = []
            for cell in cells:
                self.h3_to_edges[cell].append((u, v, key))
                risk_value, has_data, _source = resolve_hierarchical_risk(
                    cell,
                    risk_lookup,
                    parent_resolution=parent_resolution,
                    unknown_risk=self._no_data_risk,
                )
                resolved_risks.append(risk_value)
                resolved_data_flags.append(has_data)

            risk_weight = (
                aggregate_edge_cell_risks(
                    resolved_risks,
                    max_weight=max_risk_weight,
                )
                if resolved_risks
                else self._no_data_risk
            )
            data_available = any(resolved_data_flags)
            length = float(data.get("length", 1.0))
            norm_risk = max(0.0, min(1.0, float(risk_weight)))
            data["risk_weight"] = norm_risk
            data["risk_data_available"] = data_available
            data["risk_adjusted_length"] = risk_adjusted_length(
                length,
                norm_risk,
                alpha=self._cost_alpha,
                red_threshold=self._red_threshold,
                red_penalty=self._red_penalty,
            )

        return self.h3_to_edges

    def set_absolute_risk_for_h3(self, target_h3: str, new_risk: float, alpha: float | None = None):
        norm_risk = max(0.0, min(1.0, float(new_risk)))
        effective_alpha = self._cost_alpha if alpha is None else float(alpha)
        self._risk_lookup[str(target_h3)] = norm_risk
        # Çok hücreli bir kenarın diğer hücre risklerini ezmemek için tüm
        # birleşimi aynı deterministik politika ile yeniden hesapla.
        self.apply_risk_weights(self._risk_lookup, alpha=effective_alpha)

    def _edge_cost_for_alpha(self, edge_data: dict, alpha: float) -> float:
        return risk_adjusted_length(
            float(edge_data.get("length", 1.0)),
            float(edge_data.get("risk_weight", self._no_data_risk)),
            alpha=float(alpha),
            red_threshold=self._red_threshold,
            red_penalty=self._red_penalty,
        )

    def _candidate_weight(self, alpha: float):
        def weight(_u, _v, edge_data):
            # MultiDiGraph ağırlık callback'i key -> edge attributes sözlüğü
            # alabilir. Normal Graph sözlüğü de geriye dönük desteklenir.
            if "length" in edge_data:
                return self._edge_cost_for_alpha(edge_data, alpha)
            return min(
                self._edge_cost_for_alpha(data, alpha)
                for data in edge_data.values()
            )

        return weight

    def _calc_metrics(
        self,
        route_nodes,
        edge_weight: str = "length",
        candidate_alpha: float | None = None,
    ):
        coords = [[self.graph.nodes[n]["x"], self.graph.nodes[n]["y"]] for n in route_nodes]
        total_dist = 0.0
        risk_dist_sum = 0.0
        covered_dist = 0.0
        for i in range(len(route_nodes) - 1):
            options = self.graph.get_edge_data(route_nodes[i], route_nodes[i+1])
            if candidate_alpha is None:
                edge = min(
                    options.values(),
                    key=lambda d: d.get(edge_weight, float("inf")),
                )
            else:
                edge = min(
                    options.values(),
                    key=lambda d: self._edge_cost_for_alpha(d, candidate_alpha),
                )
            length = float(edge.get("length", 0.0))
            risk = float(edge.get("risk_weight", 0.0))
            total_dist += length
            risk_dist_sum += length * risk
            if bool(edge.get("risk_data_available", False)):
                covered_dist += length

        route_risk = (risk_dist_sum / total_dist) if total_dist > 0 else 0.0
        route_risk = max(0.0, min(1.0, route_risk))
        safety_score = round((1.0 - route_risk) * 100.0, 1)
        risk_coverage = round((covered_dist / total_dist * 100.0), 1) if total_dist > 0 else 0.0
        return coords, total_dist, safety_score, route_risk, risk_coverage

    def _candidate_from_nodes(
        self,
        route_nodes,
        *,
        alpha: float | None,
    ) -> RouteCandidate:
        metrics = self._calc_metrics(
            route_nodes,
            edge_weight="length" if alpha is None else "risk_adjusted_length",
            candidate_alpha=alpha,
        )
        return RouteCandidate(
            coordinates=metrics[0],
            distance_m=metrics[1],
            safety_score=metrics[2],
            route_risk=metrics[3],
            risk_coverage=metrics[4],
            alpha=alpha,
            path_signature=tuple(str(node) for node in route_nodes),
        )

    def compute_safe_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, alpha: float = DEFAULT_ALPHA):
        import networkx as nx

        start_node, _ = self.find_nearest_node(start_lat, start_lng)
        end_node, _ = self.find_nearest_node(end_lat, end_lng)
        route_nodes = nx.shortest_path(self.graph, source=start_node, target=end_node, weight="risk_adjusted_length")
        return self._calc_metrics(route_nodes, edge_weight="risk_adjusted_length")

    def compute_shortest_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        import networkx as nx

        start_node, _ = self.find_nearest_node(start_lat, start_lng)
        end_node, _ = self.find_nearest_node(end_lat, end_lng)
        route_nodes = nx.shortest_path(self.graph, source=start_node, target=end_node, weight="length")
        return self._calc_metrics(route_nodes, edge_weight="length")

    def compute_profiled_route(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        profile: str = "balanced",
    ) -> RouteSelectionResult:
        import networkx as nx

        start_node, _ = self.find_nearest_node(start_lat, start_lng)
        end_node, _ = self.find_nearest_node(end_lat, end_lng)
        shortest_nodes = nx.shortest_path(
            self.graph,
            source=start_node,
            target=end_node,
            weight="length",
        )
        shortest = self._candidate_from_nodes(shortest_nodes, alpha=None)

        candidates: list[RouteCandidate] = []
        for alpha in parse_candidate_alphas(
            getattr(settings, "routing_candidate_alphas", None),
            required_alpha=self._cost_alpha,
        ):
            route_nodes = nx.shortest_path(
                self.graph,
                source=start_node,
                target=end_node,
                weight=self._candidate_weight(alpha),
            )
            candidates.append(
                self._candidate_from_nodes(route_nodes, alpha=alpha)
            )

        return select_route_candidate(
            shortest=shortest,
            candidates=candidates,
            profile=profile,
            balanced_max_detour_pct=float(
                getattr(settings, "routing_balanced_max_detour_pct", 15.0)
            ),
            safer_max_detour_pct=float(
                getattr(settings, "routing_safer_max_detour_pct", 25.0)
            ),
            min_meaningful_risk_reduction_pct=float(
                getattr(
                    settings,
                    "routing_min_meaningful_risk_reduction_pct",
                    5.0,
                )
            ),
            balanced_marginal_gain_floor=float(
                getattr(settings, "routing_balanced_marginal_gain_floor", 0.0)
            ),
            balanced_detour_penalty=float(
                getattr(settings, "routing_balanced_detour_penalty", 2.0)
            ),
        )


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
        self._edge_uv_order = None
        self._edge_uv_keys_sorted = None
        self._edge_lookup_cache = None
        self.edge_risk = None
        self.edge_has_data = None
        self.risk_adjusted_edge_length = None
        self.kdtree = None
        self.h3_keys_map = {}  # h3_index -> np.ndarray of edge_ids
        self.N = 0
        self.M = 0
        self.csr_shortest = None
        self.csr_shortest_b = None
        self.csr_safe = None
        self.csr_safe_b = None
        self._candidate_route_cache: dict[
            float,
            tuple[csr_matrix, csr_matrix | None],
        ] = {}
        self._cost_alpha = DEFAULT_ALPHA
        self._red_threshold = DEFAULT_RED_THRESHOLD
        self._red_penalty = DEFAULT_RED_PENALTY
        self._no_data_risk = DEFAULT_NO_DATA_RISK
        self._risk_lookup: dict[str, float] = {}
        self.h3_resolution = validate_h3_resolution(
            getattr(settings, "routing_h3_resolution", H3_RESOLUTION)
        )
        self.graph_format_version = "1.0"
        self.graph_artifact_id = "unloaded"
        self.navigation_sidecar_id = "unavailable"
        self._nav_node_osm_id = None
        self._nav_edge_key = None
        self._nav_edge_name_id = None
        self._nav_street_names = None
        self._nav_edge_ref_id = None
        self._nav_street_refs = None
        self._nav_edge_highway_id = None
        self._nav_highway_types = None

    def _load_navigation_sidecar(self) -> None:
        path = Path(settings.navigation_sidecar_path)
        required = settings.navigation_sidecar_required or (
            settings.app_environment in {"staging", "production"}
        )
        if not path.is_file():
            if required:
                raise RuntimeError(
                    "[CompactCSREngine FAIL-FAST] Navigation sidecar bulunamadı: "
                    f"{path.resolve()}"
                )
            return

        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        sidecar = np.load(path, allow_pickle=False)
        required_keys = {
            "version",
            "compact_graph_sha256",
            "node_osm_id",
            "edge_key",
            "edge_name_id",
            "street_names",
            "edge_ref_id",
            "street_refs",
            "edge_highway_id",
            "highway_types",
        }
        missing = required_keys - set(sidecar.files)
        if missing:
            raise RuntimeError(
                "[CompactCSREngine FAIL-FAST] Navigation sidecar eksik alanlar "
                f"içeriyor: {missing}"
            )
        if str(sidecar["version"][0]) != "1.0":
            raise RuntimeError("Unsupported navigation sidecar version")
        compact_digest = self.graph_artifact_id.removeprefix("sha256:")
        if str(sidecar["compact_graph_sha256"][0]) != compact_digest:
            raise RuntimeError(
                "[CompactCSREngine FAIL-FAST] Navigation sidecar graph hash'i "
                "compact graph ile eşleşmiyor."
            )
        if (
            len(sidecar["node_osm_id"]) != self.N
            or len(sidecar["edge_key"]) != self.M
            or len(sidecar["edge_name_id"]) != self.M
        ):
            raise RuntimeError(
                "[CompactCSREngine FAIL-FAST] Navigation sidecar node/edge "
                "sayısı compact graph ile eşleşmiyor."
            )
        self._nav_node_osm_id = sidecar["node_osm_id"]
        self._nav_edge_key = sidecar["edge_key"]
        self._nav_edge_name_id = sidecar["edge_name_id"]
        self._nav_street_names = sidecar["street_names"]
        self._nav_edge_ref_id = sidecar["edge_ref_id"]
        self._nav_street_refs = sidecar["street_refs"]
        self._nav_edge_highway_id = sidecar["edge_highway_id"]
        self._nav_highway_types = sidecar["highway_types"]
        self.navigation_sidecar_id = f"sha256:{digest.hexdigest()}"

    def load_graph(self, npz_path: str = "../data-science/compact_graph.npz"):
        p = Path(npz_path)
        if not p.exists():
            # Eğer ortam "compact" olarak ayarlanmış ve NPZ yoksa FAIL-FAST
            raise RuntimeError(
                f"[CompactCSREngine FAIL-FAST] İkili graf dosyası bulunamadı: {p.resolve()}. "
                f"Lütfen 'python build_compact_graph.py' komutunu çalıştırın."
            )

        print(f"[CompactCSREngine] İkili graf yükleniyor ve doğrulanıyor: {p}")
        digest = hashlib.sha256()
        with p.open("rb") as graph_file:
            for chunk in iter(lambda: graph_file.read(1024 * 1024), b""):
                digest.update(chunk)
        self.graph_artifact_id = f"sha256:{digest.hexdigest()}"
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
            if fmt_ver not in {"1.0", "2.0"}:
                raise RuntimeError(
                    "[CompactCSREngine FAIL-FAST] Uyumsuz NPZ format sürümü: "
                    f"{fmt_ver} (Desteklenen: 1.0, 2.0)"
                )
            self.graph_format_version = fmt_ver

        graph_h3_resolution = (
            int(data["h3_resolution"][0])
            if "h3_resolution" in data.files
            else LEGACY_H3_RESOLUTION
        )
        graph_h3_resolution = validate_h3_resolution(graph_h3_resolution)
        configured_resolution = validate_h3_resolution(
            getattr(settings, "routing_h3_resolution", H3_RESOLUTION)
        )
        if graph_h3_resolution != configured_resolution:
            raise RuntimeError(
                "[CompactCSREngine FAIL-FAST] NPZ H3 çözünürlüğü ile çalışma "
                "ayarının eşleşmesi gerekir: "
                f"NPZ=Res-{graph_h3_resolution}, "
                f"ROUTING_H3_RESOLUTION=Res-{configured_resolution}."
            )
        self.h3_resolution = graph_h3_resolution

        self.node_x = data["node_x"]
        self.node_y = data["node_y"]
        self.edge_src = data["edge_src"]
        self.edge_dst = data["edge_dst"]
        self.edge_length = data["edge_length"]

        h3_keys = data["h3_keys"]
        offsets = data["h3_edge_offsets"]
        values = data["h3_edge_values"]

        self.h3_keys_map.clear()
        for idx, key in enumerate(h3_keys):
            start = offsets[idx]
            end = offsets[idx + 1]
            self.h3_keys_map[key] = values[start:end]

        self.N = len(self.node_x)
        self.M = len(self.edge_src)
        # Path metric calculation is on the request hot path.  Keep one compact,
        # sorted (u, v) index so selecting the best parallel edge is O(log M)
        # instead of allocating and scanning an M-sized boolean mask per step.
        self._build_edge_lookup()
        self.edge_risk = np.full(self.M, self._no_data_risk, dtype=np.float32)
        self.edge_has_data = np.zeros(self.M, dtype=np.bool_)
        self.risk_adjusted_edge_length = None

        # KDTree İndeksi (ox.nearest_nodes ile %100 birebir düğüm eşleşmesi)
        coords = np.column_stack((self.node_x, self.node_y))
        self.kdtree = KDTree(coords)

        # Standart en kısa yol için paralel kenar tekleştirmeli CSR matrisleri (ileri ve geri)
        self.csr_shortest = _build_deduplicated_csr(self.N, self.edge_src, self.edge_dst, self.edge_length)
        self.csr_shortest_b = (
            _build_deduplicated_csr(
                self.N,
                self.edge_dst,
                self.edge_src,
                self.edge_length,
            )
            if settings.routing_search_algorithm == "bidirectional_a_star"
            else None
        )
        self._candidate_route_cache.clear()
        self.csr_safe = None
        self.csr_safe_b = None
        self._load_navigation_sidecar()
        t1 = time.time()
        print(
            f"[CompactCSREngine] BAŞARILI! Düğüm: {self.N:,}, "
            f"Kenar: {self.M:,}, H3 Res-{self.h3_resolution}, "
            f"NPZ v{self.graph_format_version} ({t1 - t0:.3f} sn)"
        )
        return self

    def find_nearest_node(self, lat: float, lng: float) -> tuple[int, float]:
        """KDTree ile $O(\\log N)$ sürede ve metre cinsinden en yakın düğümü bulur."""
        dist_deg, idx = self.kdtree.query([lng, lat])
        dist_m = dist_deg * METERS_PER_DEG_LAT

        if dist_m > MAX_SNAP_DISTANCE_M:
            raise ValueError(f"Koordinat yaya ağına çok uzak: {dist_m:.1f} metre")
        return int(idx), float(dist_m)

    def apply_risk_weights(self, risk_lookup: dict, alpha: float = DEFAULT_ALPHA):
        """H3 risklerini çok-hücreli kenarlara hiyerarşik ve konservatif biçimde aktarır."""
        self._risk_lookup = {
            str(key): max(0.0, min(1.0, float(value)))
            for key, value in risk_lookup.items()
        }
        risk_lookup = self._risk_lookup
        self._cost_alpha = float(alpha)
        self._red_threshold = float(getattr(settings, "routing_red_risk_threshold", DEFAULT_RED_THRESHOLD))
        self._red_penalty = float(getattr(settings, "routing_red_risk_penalty", DEFAULT_RED_PENALTY))
        self._no_data_risk = float(getattr(settings, "routing_unknown_risk", DEFAULT_NO_DATA_RISK))
        self.edge_risk.fill(self._no_data_risk)
        if self.edge_has_data is None or len(self.edge_has_data) != self.M:
            self.edge_has_data = np.zeros(self.M, dtype=np.bool_)
        else:
            self.edge_has_data.fill(False)

        parent_resolution = validate_h3_resolution(
            getattr(settings, "h3_parent_resolution", LEGACY_H3_RESOLUTION)
        )
        max_risk_weight = max(
            0.0,
            min(
                1.0,
                float(getattr(settings, "routing_edge_max_risk_weight", 0.65)),
            ),
        )
        edge_risk_sum = np.zeros(self.M, dtype=np.float64)
        edge_risk_max = np.zeros(self.M, dtype=np.float64)
        edge_cell_count = np.zeros(self.M, dtype=np.int32)
        edge_data_count = np.zeros(self.M, dtype=np.int32)

        for h3_idx, edge_ids in self.h3_keys_map.items():
            if edge_ids is None or len(edge_ids) == 0:
                continue
            risk_value, has_data, _source = resolve_hierarchical_risk(
                h3_idx,
                risk_lookup,
                parent_resolution=parent_resolution,
                unknown_risk=self._no_data_risk,
            )
            norm_risk = max(0.0, min(1.0, float(risk_value)))
            np.add.at(edge_risk_sum, edge_ids, norm_risk)
            np.maximum.at(edge_risk_max, edge_ids, norm_risk)
            np.add.at(edge_cell_count, edge_ids, 1)
            if has_data:
                np.add.at(edge_data_count, edge_ids, 1)

        mapped_mask = edge_cell_count > 0
        if np.any(mapped_mask):
            means = np.zeros(self.M, dtype=np.float64)
            means[mapped_mask] = (
                edge_risk_sum[mapped_mask] / edge_cell_count[mapped_mask]
            )
            combined = (
                max_risk_weight * edge_risk_max
                + (1.0 - max_risk_weight) * means
            )
            self.edge_risk[mapped_mask] = np.clip(
                combined[mapped_mask],
                0.0,
                1.0,
            ).astype(np.float32)
            self.edge_has_data[mapped_mask] = edge_data_count[mapped_mask] > 0

        # Her rota isteğinde milyon kenarı yeniden ağırlıklandırmamak için aday
        # alpha matrisleri risk snapshot'ı yüklenirken bir kez hazırlanır.
        candidate_alphas = parse_candidate_alphas(
            getattr(settings, "routing_candidate_alphas", None),
            required_alpha=self._cost_alpha,
        )
        new_candidate_route_cache: dict[
            float,
            tuple[csr_matrix, csr_matrix | None],
        ] = {}
        for candidate_alpha in candidate_alphas:
            candidate_costs = risk_adjusted_lengths(
                self.edge_length,
                self.edge_risk,
                alpha=candidate_alpha,
                red_threshold=self._red_threshold,
                red_penalty=self._red_penalty,
            )
            matrix_f = _build_deduplicated_csr(
                self.N,
                self.edge_src,
                self.edge_dst,
                candidate_costs,
            )
            matrix_b = (
                _build_deduplicated_csr(
                    self.N,
                    self.edge_dst,
                    self.edge_src,
                    candidate_costs,
                )
                if settings.routing_search_algorithm == "bidirectional_a_star"
                else None
            )
            new_candidate_route_cache[candidate_alpha] = (
                matrix_f,
                matrix_b,
            )

        active_alpha = min(
            new_candidate_route_cache,
            key=lambda value: abs(value - self._cost_alpha),
        )
        # Tam snapshot hazır olmadan mevcut isteklerin kullandığı cache'i
        # değiştirme. Atama CPython'da tek adımda gerçekleşir.
        self._candidate_route_cache = new_candidate_route_cache
        self.risk_adjusted_edge_length = None
        self.csr_safe, self.csr_safe_b = self._candidate_route_cache[active_alpha]
        return self.h3_keys_map

    def _build_edge_lookup(self) -> None:
        edge_uv_keys = (
            self.edge_src.astype(np.int64) * self.N
            + self.edge_dst.astype(np.int64)
        )
        self._edge_uv_order = np.argsort(edge_uv_keys, kind="stable")
        self._edge_uv_keys_sorted = edge_uv_keys[self._edge_uv_order]
        self._edge_lookup_cache = None

    def set_absolute_risk_for_h3(self, target_h3: str, new_risk: float, alpha: float | None = None):
        norm_risk = max(0.0, min(1.0, float(new_risk)))
        effective_alpha = self._cost_alpha if alpha is None else float(alpha)
        self._risk_lookup[str(target_h3)] = norm_risk
        self.apply_risk_weights(self._risk_lookup, alpha=effective_alpha)

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

    def _best_edge_index(
        self,
        source: int,
        target: int,
        *,
        edge_costs: np.ndarray | None,
        candidate_alpha: float | None,
    ) -> int | None:
        uv_key = np.int64(source) * self.N + np.int64(target)
        start = int(
            np.searchsorted(self._edge_uv_keys_sorted, uv_key, side="left")
        )
        end = int(
            np.searchsorted(self._edge_uv_keys_sorted, uv_key, side="right")
        )
        if start == end:
            return None
        matching_indices = self._edge_uv_order[start:end]
        if edge_costs is not None:
            candidate_costs = edge_costs[matching_indices]
        elif candidate_alpha is not None:
            candidate_costs = risk_adjusted_lengths(
                self.edge_length[matching_indices],
                self.edge_risk[matching_indices],
                alpha=candidate_alpha,
                red_threshold=self._red_threshold,
                red_penalty=self._red_penalty,
            )
        else:
            candidate_costs = self.edge_length[matching_indices]
        return int(matching_indices[np.argmin(candidate_costs)])

    def _path_edge_indices(
        self,
        path_nodes: list[int],
        *,
        edge_costs: np.ndarray | None,
        candidate_alpha: float | None,
    ) -> list[int]:
        """Yol kenarlarını tek vektörize aramayla bulur.

        Aday sayısı yüksek olduğu için kenar araması düğüm başına ayrı ayrı
        yapıldığında istek gecikmesi saniyelere çıkıyordu. `searchsorted` toplu
        çağrılır; paralel kenarı olan (nadir) konumlar için yalnızca o konumlarda
        en düşük maliyetli kenar seçilir.
        """
        if len(path_nodes) < 2:
            return []
        if self._edge_uv_order is None or self._edge_uv_keys_sorted is None:
            self._build_edge_lookup()

        sources = np.asarray(path_nodes[:-1], dtype=np.int64)
        targets = np.asarray(path_nodes[1:], dtype=np.int64)
        uv_keys = sources * np.int64(self.N) + targets

        left = np.searchsorted(self._edge_uv_keys_sorted, uv_keys, side="left")
        right = np.searchsorted(self._edge_uv_keys_sorted, uv_keys, side="right")
        span = right - left

        missing = np.flatnonzero(span <= 0)
        if missing.size:
            position = int(missing[0])
            raise RuntimeError(
                "Path contains missing directed edge: "
                f"{path_nodes[position]}->{path_nodes[position + 1]}"
            )

        edge_indices = np.empty(uv_keys.shape[0], dtype=np.int64)
        single = span == 1
        edge_indices[single] = self._edge_uv_order[left[single]]

        for position in np.flatnonzero(span > 1):
            matching_indices = self._edge_uv_order[left[position] : right[position]]
            if edge_costs is not None:
                candidate_costs = edge_costs[matching_indices]
            elif candidate_alpha is not None:
                candidate_costs = risk_adjusted_lengths(
                    self.edge_length[matching_indices],
                    self.edge_risk[matching_indices],
                    alpha=candidate_alpha,
                    red_threshold=self._red_threshold,
                    red_penalty=self._red_penalty,
                )
            else:
                candidate_costs = self.edge_length[matching_indices]
            edge_indices[position] = matching_indices[int(np.argmin(candidate_costs))]

        return [int(index) for index in edge_indices]

    def _navigation_metadata(
        self,
        edge_indices: list[int],
    ) -> tuple[
        tuple[str, ...],
        tuple[str | None, ...],
        tuple[str | None, ...],
    ]:
        if (
            self._nav_node_osm_id is None
            or self._nav_edge_key is None
            or self._nav_edge_name_id is None
            or self._nav_street_names is None
            or self._nav_edge_ref_id is None
            or self._nav_street_refs is None
            or self._nav_edge_highway_id is None
            or self._nav_highway_types is None
        ):
            return (), (), ()
        identities: list[str] = []
        street_names: list[str | None] = []
        way_types: list[str | None] = []
        for edge_index in edge_indices:
            source_index = int(self.edge_src[edge_index])
            target_index = int(self.edge_dst[edge_index])
            identities.append(
                "osm:"
                f"{int(self._nav_node_osm_id[source_index])}:"
                f"{int(self._nav_node_osm_id[target_index])}:"
                f"{int(self._nav_edge_key[edge_index])}"
            )
            name = str(
                self._nav_street_names[
                    int(self._nav_edge_name_id[edge_index])
                ]
            ).strip()
            ref = str(
                self._nav_street_refs[
                    int(self._nav_edge_ref_id[edge_index])
                ]
            ).strip()
            highway = str(
                self._nav_highway_types[
                    int(self._nav_edge_highway_id[edge_index])
                ]
            ).strip()
            street_names.append(name or ref or None)
            way_types.append(highway or None)
        return tuple(identities), tuple(street_names), tuple(way_types)

    def _calc_path_metrics(
        self,
        path_nodes: list,
        edge_costs: np.ndarray | None = None,
        candidate_alpha: float | None = None,
        edge_indices: list[int] | None = None,
    ):
        coords = [[float(self.node_x[n]), float(self.node_y[n])] for n in path_nodes]

        # Small synthetic tests and embedders may inject arrays directly instead
        # of calling load_graph(). Build the same hot-path index lazily for them.
        if self._edge_uv_order is None or self._edge_uv_keys_sorted is None:
            self._build_edge_lookup()

        if edge_indices is None:
            edge_indices = self._path_edge_indices(
                path_nodes,
                edge_costs=edge_costs,
                candidate_alpha=candidate_alpha,
            )

        if not edge_indices:
            return coords, 0.0, round(100.0, 1), 0.0, 0.0

        index_array = np.asarray(edge_indices, dtype=np.int64)
        lengths = self.edge_length[index_array].astype(np.float64, copy=False)
        risks = self.edge_risk[index_array].astype(np.float64, copy=False)

        total_dist = float(lengths.sum())
        risk_dist_sum = float((lengths * risks).sum())
        covered_dist = (
            float(lengths[self.edge_has_data[index_array]].sum())
            if self.edge_has_data is not None
            else 0.0
        )

        route_risk = (risk_dist_sum / total_dist) if total_dist > 0 else 0.0
        route_risk = max(0.0, min(1.0, route_risk))
        safety_score = round((1.0 - route_risk) * 100.0, 1)
        risk_coverage = round((covered_dist / total_dist * 100.0), 1) if total_dist > 0 else 0.0

        return coords, total_dist, safety_score, route_risk, risk_coverage

    def _path_for_matrices(
        self,
        start_idx: int,
        end_idx: int,
        matrix_f: csr_matrix,
        matrix_b: csr_matrix | None,
    ) -> list[int]:
        search_algorithm = getattr(
            settings,
            "routing_search_algorithm",
            "scipy_dijkstra",
        )
        if search_algorithm == "bidirectional_a_star" and matrix_b is not None:
            path_nodes = self._bidirectional_a_star(
                start_idx,
                end_idx,
                matrix_f,
                matrix_b,
            )
        else:
            _dist_matrix, predecessors = dijkstra(
                csgraph=matrix_f,
                directed=True,
                indices=start_idx,
                return_predecessors=True,
            )
            path_nodes = []
            curr = end_idx
            while curr != -9999 and curr != start_idx:
                path_nodes.append(int(curr))
                curr = int(predecessors[curr])
            if curr == start_idx:
                path_nodes.append(start_idx)
            path_nodes.reverse()

        if not path_nodes or path_nodes[0] != start_idx or path_nodes[-1] != end_idx:
            raise ValueError("Başlangıç ve bitiş arasında yürünebilir rota bulunamadı.")
        return path_nodes

    def _candidate_from_path(
        self,
        path_nodes: list[int],
        *,
        alpha: float | None,
        edge_costs: np.ndarray | None,
        with_navigation: bool = True,
    ) -> RouteCandidate:
        """Yol düğümlerinden aday rota üretir.

        ``with_navigation=False`` yalnızca seçim için gereken fiziksel metrikleri
        hesaplar. Sokak adı/kimlik üretimi kenar başına string işlemi gerektirdiği
        için onlarca aday üretilirken ertelenir; seçim sonrası tamamlanır.
        """
        edge_indices = self._path_edge_indices(
            path_nodes,
            edge_costs=edge_costs,
            candidate_alpha=alpha,
        )
        metrics = self._calc_path_metrics(
            path_nodes,
            edge_costs=edge_costs,
            candidate_alpha=alpha,
            edge_indices=edge_indices,
        )
        edge_signature, street_names, way_types = (
            self._navigation_metadata(edge_indices)
            if with_navigation
            else ((), (), ())
        )
        return RouteCandidate(
            coordinates=metrics[0],
            distance_m=metrics[1],
            safety_score=metrics[2],
            route_risk=metrics[3],
            risk_coverage=metrics[4],
            alpha=alpha,
            path_signature=tuple(str(node) for node in path_nodes),
            edge_signature=edge_signature,
            street_names=street_names,
            way_types=way_types,
        )

    def _extra_safer_alphas(self) -> tuple[float, ...]:
        """Yapılandırmadaki ek risk ağırlıklarını ayrıştırır."""
        raw = getattr(settings, "routing_extra_safer_alphas", "") or ""
        values: list[float] = []
        for token in str(raw).split(","):
            token = token.strip()
            if not token:
                continue
            try:
                alpha = float(token)
            except ValueError:
                continue
            if alpha > 0.0:
                values.append(alpha)
        return tuple(sorted(set(values)))

    def _edge_index_lookup(self) -> EdgeIndexLookup:
        """Motorun hazır ``(u, v)`` sıralı indeksini yeniden kullanan arama nesnesi."""
        if self._edge_uv_order is None or self._edge_uv_keys_sorted is None:
            self._build_edge_lookup()
        cached = getattr(self, "_edge_lookup_cache", None)
        if cached is None or cached.node_count != self.N:
            cached = EdgeIndexLookup(
                node_count=self.N,
                edge_src=self.edge_src,
                edge_dst=self.edge_dst,
                order=self._edge_uv_order,
                keys_sorted=self._edge_uv_keys_sorted,
            )
            self._edge_lookup_cache = cached
        return cached

    def _build_csr_pair(self, costs: np.ndarray) -> tuple[csr_matrix, csr_matrix | None]:
        matrix_f = _build_deduplicated_csr(
            self.N,
            self.edge_src,
            self.edge_dst,
            costs,
        )
        matrix_b = (
            _build_deduplicated_csr(
                self.N,
                self.edge_dst,
                self.edge_src,
                costs,
            )
            if getattr(settings, "routing_search_algorithm", "scipy_dijkstra")
            == "bidirectional_a_star"
            else None
        )
        return matrix_f, matrix_b

    def _diversified_path_candidates(
        self,
        start_idx: int,
        end_idx: int,
        base_costs: np.ndarray,
        *,
        alpha: float | None,
        max_distance_m: float | None = None,
        max_iterations: int | None = None,
        build_csr=None,
        path_finder=None,
    ) -> list[RouteCandidate]:
        max_iterations = int(
            max_iterations
            if max_iterations is not None
            else getattr(settings, "routing_diversify_iterations", 5)
        )
        penalty_factor = float(
            getattr(settings, "routing_diversify_penalty_factor", 2.5)
        )
        if max_iterations <= 1:
            return []

        paths = penalty_diversify_paths(
            start_idx=start_idx,
            end_idx=end_idx,
            base_costs=base_costs,
            edge_src=self.edge_src,
            edge_dst=self.edge_dst,
            build_csr=build_csr or self._build_csr_pair,
            path_finder=path_finder or self._path_for_matrices,
            max_iterations=max_iterations,
            penalty_factor=penalty_factor,
            max_distance_m=max_distance_m,
            physical_lengths=self.edge_length,
            edge_lookup=self._edge_index_lookup(),
        )
        candidates: list[RouteCandidate] = []
        for path_nodes in paths[1:]:
            candidates.append(
                self._candidate_from_path(
                    path_nodes,
                    alpha=alpha,
                    edge_costs=None,
                    with_navigation=False,
                )
            )
        return candidates

    def compute_safe_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float, alpha: float = DEFAULT_ALPHA):
        start_idx, _ = self.find_nearest_node(start_lat, start_lng)
        end_idx, _ = self.find_nearest_node(end_lat, end_lng)

        matrix_f = self.csr_safe if self.csr_safe is not None else self.csr_shortest
        matrix_b = self.csr_safe_b if self.csr_safe_b is not None else self.csr_shortest_b

        path_nodes = self._path_for_matrices(
            start_idx,
            end_idx,
            matrix_f,
            matrix_b,
        )
        return self._calc_path_metrics(
            path_nodes,
            candidate_alpha=self._cost_alpha,
        )

    def compute_shortest_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float):
        start_idx, _ = self.find_nearest_node(start_lat, start_lng)
        end_idx, _ = self.find_nearest_node(end_lat, end_lng)

        matrix_f = self.csr_shortest
        matrix_b = self.csr_shortest_b

        path_nodes = self._path_for_matrices(
            start_idx,
            end_idx,
            matrix_f,
            matrix_b,
        )
        return self._calc_path_metrics(path_nodes)

    def compute_profiled_route(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        profile: str = "balanced",
    ) -> RouteSelectionResult:
        start_idx, _ = self.find_nearest_node(start_lat, start_lng)
        end_idx, _ = self.find_nearest_node(end_lat, end_lng)

        shortest_nodes = self._path_for_matrices(
            start_idx,
            end_idx,
            self.csr_shortest,
            self.csr_shortest_b,
        )
        shortest = self._candidate_from_path(
            shortest_nodes,
            alpha=None,
            edge_costs=None,
        )

        safer_max_distance_m = shortest.distance_m * (
            1.0
            + float(getattr(settings, "routing_safer_max_detour_pct", 25.0))
            / 100.0
        )

        # Bütçe elipsi dışındaki düğümler hiçbir bütçe uyumlu rotanın parçası
        # olamaz; kırpma aday kalitesini değiştirmeden Dijkstra maliyetini düşürür.
        subgraph = None
        if bool(getattr(settings, "routing_subgraph_enabled", True)):
            subgraph = build_budget_subgraph(
                node_x=self.node_x,
                node_y=self.node_y,
                edge_src=self.edge_src,
                edge_dst=self.edge_dst,
                start_idx=start_idx,
                end_idx=end_idx,
                max_distance_m=safer_max_distance_m,
                margin=float(getattr(settings, "routing_subgraph_margin", 1.10)),
                max_node_ratio=float(
                    getattr(settings, "routing_subgraph_max_node_ratio", 0.70)
                ),
            )
        build_csr = subgraph.build_csr if subgraph is not None else self._build_csr_pair
        path_finder = (
            subgraph.path_finder if subgraph is not None else self._path_for_matrices
        )

        candidates: list[RouteCandidate] = []
        for alpha in sorted(self._candidate_route_cache):
            if subgraph is not None:
                alpha_costs = risk_adjusted_lengths(
                    self.edge_length,
                    self.edge_risk,
                    alpha=alpha,
                    red_threshold=self._red_threshold,
                    red_penalty=self._red_penalty,
                )
                matrix_f, matrix_b = build_csr(alpha_costs)
            else:
                matrix_f, matrix_b = self._candidate_route_cache[alpha]
            path_nodes = path_finder(
                start_idx,
                end_idx,
                matrix_f,
                matrix_b,
            )
            candidates.append(
                self._candidate_from_path(
                    path_nodes,
                    alpha=alpha,
                    edge_costs=None,
                    with_navigation=False,
                )
            )

        # Alpha ızgarasının üst sınırında sıkışan güzergâhlarda (ör. risk farkı
        # yalnızca çok yüksek ağırlıkta ortaya çıkanlar) ek adaylar üretilir.
        for extra_alpha in self._extra_safer_alphas():
            if extra_alpha in self._candidate_route_cache:
                continue
            extra_costs = risk_adjusted_lengths(
                self.edge_length,
                self.edge_risk,
                alpha=extra_alpha,
                red_threshold=self._red_threshold,
                red_penalty=self._red_penalty,
            )
            matrix_f, matrix_b = build_csr(extra_costs)
            try:
                extra_nodes = path_finder(start_idx, end_idx, matrix_f, matrix_b)
            except ValueError:
                continue
            candidates.append(
                self._candidate_from_path(
                    extra_nodes,
                    alpha=extra_alpha,
                    edge_costs=None,
                    with_navigation=False,
                )
            )

        candidates.extend(
            self._diversified_path_candidates(
                start_idx,
                end_idx,
                self.edge_length.astype(np.float64, copy=False),
                alpha=None,
                max_distance_m=safer_max_distance_m,
                build_csr=build_csr,
                path_finder=path_finder,
            )
        )
        diversify_alphas = sorted(
            {
                float(alpha)
                for alpha in (
                    4.0,
                    8.0,
                    16.0,
                    max(self._candidate_route_cache.keys())
                    if self._candidate_route_cache
                    else 16.0,
                )
                if alpha in self._candidate_route_cache
            }
        )
        for candidate_alpha in diversify_alphas:
            risk_costs = risk_adjusted_lengths(
                self.edge_length,
                self.edge_risk,
                alpha=candidate_alpha,
                red_threshold=self._red_threshold,
                red_penalty=self._red_penalty,
            )
            candidates.extend(
                self._diversified_path_candidates(
                    start_idx,
                    end_idx,
                    risk_costs,
                    alpha=candidate_alpha,
                    max_distance_m=safer_max_distance_m,
                    max_iterations=int(
                        getattr(
                            settings,
                            "routing_diversify_risk_iterations",
                            4,
                        )
                    ),
                    build_csr=build_csr,
                    path_finder=path_finder,
                )
            )

        if bool(getattr(settings, "routing_budget_bracket_enabled", True)):
            balanced_pct = float(
                getattr(settings, "routing_balanced_max_detour_pct", 15.0)
            )
            safer_pct = float(
                getattr(settings, "routing_safer_max_detour_pct", 25.0)
            )
            mid_pct = (balanced_pct + safer_pct) / 2.0
            candidates.extend(
                bracket_alpha_candidates(
                    start_idx=start_idx,
                    end_idx=end_idx,
                    shortest_distance_m=shortest.distance_m,
                    edge_length=self.edge_length.astype(np.float64, copy=False),
                    edge_risk=self.edge_risk.astype(np.float64, copy=False),
                    red_threshold=self._red_threshold,
                    red_penalty=self._red_penalty,
                    target_detour_pcts=(balanced_pct, mid_pct, safer_pct),
                    build_csr_pair=build_csr,
                    path_for_matrices=path_finder,
                    candidate_from_path=partial(
                        self._candidate_from_path,
                        with_navigation=False,
                    ),
                    max_steps=int(
                        getattr(settings, "routing_budget_bracket_steps", 6)
                    ),
                    alpha_hi=float(
                        getattr(settings, "routing_budget_bracket_alpha_hi", 64.0)
                    ),
                )
            )

        selection = select_route_candidate(
            shortest=shortest,
            candidates=candidates,
            profile=profile,
            balanced_max_detour_pct=float(
                getattr(settings, "routing_balanced_max_detour_pct", 15.0)
            ),
            safer_max_detour_pct=float(
                getattr(settings, "routing_safer_max_detour_pct", 25.0)
            ),
            min_meaningful_risk_reduction_pct=float(
                getattr(
                    settings,
                    "routing_min_meaningful_risk_reduction_pct",
                    5.0,
                )
            ),
            balanced_marginal_gain_floor=float(
                getattr(settings, "routing_balanced_marginal_gain_floor", 0.0)
            ),
            balanced_detour_penalty=float(
                getattr(settings, "routing_balanced_detour_penalty", 2.0)
            ),
        )
        # Navigasyon talimatları yalnızca kullanıcıya dönen rota için gerekli.
        return dataclasses.replace(
            selection,
            selected=self._ensure_navigation_metadata(selection.selected),
        )

    def _ensure_navigation_metadata(
        self,
        candidate: RouteCandidate,
    ) -> RouteCandidate:
        """Aday üretiminde ertelenen sokak adı/kimlik verisini tamamlar."""
        if candidate.edge_signature:
            return candidate
        path_nodes = [int(node) for node in candidate.path_signature]
        if len(path_nodes) < 2:
            return candidate
        return self._candidate_from_path(
            path_nodes,
            alpha=candidate.alpha,
            edge_costs=None,
            with_navigation=True,
        )


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
