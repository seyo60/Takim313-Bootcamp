"""Sapma bütçesi elipsi ile kayıpsız alt graf kırpma.

Bir rotanın toplam yol uzunluğu ``L``'yi aşmıyorsa, rotadaki her düğüm ``n``
için ``d_yol(s,n) + d_yol(n,e) <= L`` olur. Kuş uçuşu mesafe daima yol
mesafesinden küçük veya ona eşit olduğundan ``d_kuş(s,n) + d_kuş(n,e) <= L``
da sağlanır. Bu nedenle bütçe elipsinin dışında kalan düğümler hiçbir bütçe
uyumlu rotanın parçası olamaz ve **kaliteden ödün vermeden** atılabilir.

Kazanç: Chicago grafı 318K düğüm / 1.07M kenar. Tipik 5 km'lik bir güzergâh
için elips içinde kalan düğüm oranı ~%5-15 olduğundan aday üretimindeki her
Dijkstra çağrısı belirgin şekilde hızlanır (Adım 4 gecikme optimizasyonu).
"""

from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra


# Chicago enlemi (~41.88°) için düzlemsel metrik yaklaşımı. Elips testi bir
# üst sınır kontrolü olduğu için bu yaklaşım güvenli tarafta kalır.
_METERS_PER_DEG_LAT = 110574.0
_METERS_PER_DEG_LNG = 82700.0

NO_PREDECESSOR = -9999


class EllipseSubgraph:
    """Bütçe elipsi içindeki düğümlerle sınırlı, yeniden indekslenmiş graf görünümü.

    ``build_csr`` ve ``path_finder`` imzaları motorun ``_build_csr_pair`` ve
    ``_path_for_matrices`` metodlarıyla uyumludur; böylece ``routing_diversify``
    ve ``routing_budget_bracket`` modülleri değişiklik olmadan çalışır.
    """

    def __init__(
        self,
        *,
        node_x: np.ndarray,
        node_y: np.ndarray,
        edge_src: np.ndarray,
        edge_dst: np.ndarray,
        start_idx: int,
        end_idx: int,
        max_distance_m: float,
        margin: float = 1.10,
    ) -> None:
        total_nodes = int(node_x.shape[0])
        budget_m = float(max_distance_m) * float(margin)

        d_start = _planar_distance(node_x, node_y, node_x[start_idx], node_y[start_idx])
        d_end = _planar_distance(node_x, node_y, node_x[end_idx], node_y[end_idx])
        node_keep = (d_start + d_end) <= budget_m
        # Uç düğümler her koşulda korunur; kayan nokta sınır durumlarına karşı.
        node_keep[start_idx] = True
        node_keep[end_idx] = True

        self.total_nodes = total_nodes
        self.node_count = int(np.count_nonzero(node_keep))
        self.budget_m = budget_m

        sub_nodes = np.flatnonzero(node_keep).astype(np.int64)
        old_to_new = np.full(total_nodes, -1, dtype=np.int64)
        old_to_new[sub_nodes] = np.arange(sub_nodes.shape[0], dtype=np.int64)

        edge_keep = node_keep[edge_src] & node_keep[edge_dst]

        self._sub_nodes = sub_nodes
        self._old_to_new = old_to_new
        self._edge_keep = edge_keep
        self._sub_src = old_to_new[edge_src[edge_keep]]
        self._sub_dst = old_to_new[edge_dst[edge_keep]]
        self._uv_keys = self._sub_src * np.int64(self.node_count) + self._sub_dst
        self.edge_count = int(self._sub_src.shape[0])

    @property
    def node_ratio(self) -> float:
        """Alt grafın tam grafa göre düğüm oranı."""
        if self.total_nodes <= 0:
            return 1.0
        return self.node_count / float(self.total_nodes)

    def build_csr(self, costs_full: np.ndarray) -> tuple[csr_matrix, None]:
        """Tam kenar maliyet dizisinden alt graf CSR matrisini üretir.

        Paralel kenarlarda maliyetler toplanmaz; her (u, v) çifti için en küçük
        maliyetli kenar seçilir (motorun tam graf davranışıyla aynı politika).
        """
        costs = np.asarray(costs_full, dtype=np.float64)[self._edge_keep]
        order = np.argsort(costs)
        sorted_keys = self._uv_keys[order]
        _unique_keys, unique_indices = np.unique(sorted_keys, return_index=True)

        return (
            csr_matrix(
                (
                    costs[order][unique_indices],
                    (
                        self._sub_src[order][unique_indices],
                        self._sub_dst[order][unique_indices],
                    ),
                ),
                shape=(self.node_count, self.node_count),
            ),
            None,
        )

    def path_finder(
        self,
        start_idx: int,
        end_idx: int,
        matrix_f: csr_matrix,
        _matrix_b: csr_matrix | None = None,
    ) -> list[int]:
        """Alt grafta en kısa yolu bulur ve düğümleri tam graf indekslerine çevirir."""
        start_sub = int(self._old_to_new[start_idx])
        end_sub = int(self._old_to_new[end_idx])
        if start_sub < 0 or end_sub < 0:
            raise ValueError("Uç düğüm bütçe alt grafının dışında.")

        _distances, predecessors = dijkstra(
            csgraph=matrix_f,
            directed=True,
            indices=start_sub,
            return_predecessors=True,
        )

        path_sub: list[int] = []
        curr = end_sub
        while curr != NO_PREDECESSOR and curr != start_sub:
            path_sub.append(int(curr))
            curr = int(predecessors[curr])
        if curr == start_sub:
            path_sub.append(start_sub)
        path_sub.reverse()

        if not path_sub or path_sub[0] != start_sub or path_sub[-1] != end_sub:
            raise ValueError("Başlangıç ve bitiş arasında yürünebilir rota bulunamadı.")
        return [int(self._sub_nodes[node]) for node in path_sub]


def _planar_distance(
    node_x: np.ndarray,
    node_y: np.ndarray,
    ref_x: float,
    ref_y: float,
) -> np.ndarray:
    dx = (node_x.astype(np.float64) - float(ref_x)) * _METERS_PER_DEG_LNG
    dy = (node_y.astype(np.float64) - float(ref_y)) * _METERS_PER_DEG_LAT
    return np.sqrt(dx * dx + dy * dy)


def build_budget_subgraph(
    *,
    node_x: np.ndarray,
    node_y: np.ndarray,
    edge_src: np.ndarray,
    edge_dst: np.ndarray,
    start_idx: int,
    end_idx: int,
    max_distance_m: float,
    margin: float = 1.10,
    max_node_ratio: float = 0.70,
    min_nodes: int = 32,
) -> EllipseSubgraph | None:
    """Kırpma anlamlı bir kazanç sağlıyorsa alt grafı döndürür, aksi halde None.

    ``max_node_ratio`` üzerindeki oranlarda kırpma maliyeti kazancından fazla
    olacağı için çağıran tam grafla devam etmelidir.
    """
    if max_distance_m <= 0.0:
        return None

    subgraph = EllipseSubgraph(
        node_x=node_x,
        node_y=node_y,
        edge_src=edge_src,
        edge_dst=edge_dst,
        start_idx=start_idx,
        end_idx=end_idx,
        max_distance_m=max_distance_m,
        margin=margin,
    )
    if subgraph.node_count < min_nodes:
        return None
    if subgraph.node_ratio > max_node_ratio:
        return None
    return subgraph
