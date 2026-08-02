"""Yol düğümlerinden kenar indekslerine vektörize erişim.

Kenar aramasının düğüm başına ``(edge_src == u) & (edge_dst == v)`` maskesiyle
yapılması, milyon kenarlı grafta yol uzunluğu × kenar sayısı kadar iş çıkarıyor
ve aday üretimini saniyelere taşıyordu. Burada ``(u, v)`` anahtarları bir kez
sıralanır ve tüm sorgular toplu ``searchsorted`` ile çözülür.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


class EdgeIndexLookup:
    """Sıralı ``(u, v)`` anahtar dizisi üzerinden kenar indeksi araması."""

    def __init__(
        self,
        *,
        node_count: int,
        edge_src: np.ndarray,
        edge_dst: np.ndarray,
        order: np.ndarray | None = None,
        keys_sorted: np.ndarray | None = None,
    ) -> None:
        self.node_count = int(node_count)
        if order is None or keys_sorted is None:
            keys = (
                edge_src.astype(np.int64) * np.int64(self.node_count)
                + edge_dst.astype(np.int64)
            )
            order = np.argsort(keys, kind="stable")
            keys_sorted = keys[order]
        self._order = order
        self._keys_sorted = keys_sorted

    def _spans(self, path_nodes: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
        sources = np.asarray(path_nodes[:-1], dtype=np.int64)
        targets = np.asarray(path_nodes[1:], dtype=np.int64)
        keys = sources * np.int64(self.node_count) + targets
        left = np.searchsorted(self._keys_sorted, keys, side="left")
        right = np.searchsorted(self._keys_sorted, keys, side="right")
        return left, right

    def all_edge_indices(self, path_nodes: Sequence[int]) -> np.ndarray:
        """Yoldaki her adımın tüm paralel kenar indekslerini döndürür."""
        if len(path_nodes) < 2:
            return np.empty(0, dtype=np.int64)

        left, right = self._spans(path_nodes)
        span = right - left

        parts: list[np.ndarray] = []
        single = span == 1
        if np.any(single):
            parts.append(self._order[left[single]])
        for position in np.flatnonzero(span > 1):
            parts.append(self._order[left[position] : right[position]])

        if not parts:
            return np.empty(0, dtype=np.int64)
        return np.concatenate(parts)

    def min_cost_edge_indices(
        self,
        path_nodes: Sequence[int],
        costs: np.ndarray,
    ) -> np.ndarray:
        """Her adım için en düşük maliyetli kenarın indeksini döndürür."""
        if len(path_nodes) < 2:
            return np.empty(0, dtype=np.int64)

        left, right = self._spans(path_nodes)
        span = right - left
        present = np.flatnonzero(span > 0)
        if present.size == 0:
            return np.empty(0, dtype=np.int64)

        selected = np.empty(present.shape[0], dtype=np.int64)
        for slot, position in enumerate(present):
            if span[position] == 1:
                selected[slot] = self._order[left[position]]
                continue
            matching = self._order[left[position] : right[position]]
            selected[slot] = matching[int(np.argmin(costs[matching]))]
        return selected
