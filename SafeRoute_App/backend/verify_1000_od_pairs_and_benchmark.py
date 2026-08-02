"""Res-10 grafında 1.000 OD çifti için doğruluk ve gecikme doğrulaması.

SciPy Dijkstra referans kabul edilir. Bidirectional A* için erişilebilirlik,
başlangıç/bitiş, yönlü edge bağlantısı, objective cost ve uzunluk-ağırlıklı risk
eşitliği doğrulanır. Betik veritabanına yazmaz.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import time

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from config import settings
from routing_engine import CompactCSREngine, METERS_PER_DEG_LAT


DEFAULT_GRAPH = (
    Path(__file__).resolve().parents[1]
    / "data-science"
    / "compact_graph_res10.npz"
)


def percentile(values: list[float], value: float) -> float:
    return float(np.percentile(values, value)) if values else 0.0


def verify_edge_monotonicity(
    engine: CompactCSREngine,
    *,
    target_count: int,
) -> None:
    """Sample targets while checking every directed edge for each target."""
    rng = np.random.default_rng(42)
    targets = rng.integers(0, engine.N, size=target_count)
    costs = engine.edge_length * (1.0 + 2.0 * engine.edge_risk)
    violations = 0

    for target in targets:
        target_x = float(engine.node_x[target])
        target_y = float(engine.node_y[target])
        meters_lng = 111_320.0 * np.cos(
            np.radians((engine.node_y + target_y) / 2.0)
        )
        dx = (engine.node_x - target_x) * meters_lng
        dy = (engine.node_y - target_y) * METERS_PER_DEG_LAT
        heuristic = 0.50 * np.sqrt(dx * dx + dy * dy)
        diff = heuristic[engine.edge_src] - (
            costs + heuristic[engine.edge_dst]
        )
        violations += int(np.count_nonzero(diff > 0.20))

    checks = target_count * engine.M
    print(
        f"Heuristic consistency: {checks:,} edge-target kontrolü, "
        f"{violations} ihlal"
    )
    if violations:
        raise AssertionError(f"Heuristic consistency ihlali: {violations}")


def reconstruct_path(
    predecessors: np.ndarray,
    start: int,
    end: int,
) -> list[int]:
    path: list[int] = []
    current = end
    while current != -9999 and current != start:
        path.append(current)
        current = int(predecessors[current])
    if current != start:
        return []
    path.append(start)
    path.reverse()
    return path


def csr_path_cost(matrix: csr_matrix, path: list[int]) -> float:
    total = 0.0
    for source, target in zip(path, path[1:]):
        start = int(matrix.indptr[source])
        end = int(matrix.indptr[source + 1])
        row_targets = matrix.indices[start:end]
        position = int(np.searchsorted(row_targets, target))
        if position >= len(row_targets) or int(row_targets[position]) != target:
            raise AssertionError(f"Yönlü edge bulunamadı: {source}->{target}")
        total += float(matrix.data[start + position])
    return total


def generate_pairs(engine: CompactCSREngine, count: int) -> list[tuple[int, int]]:
    rng = np.random.default_rng(42)
    pairs: list[tuple[int, int]] = []
    while len(pairs) < count:
        start = int(rng.integers(0, engine.N))
        end = int(rng.integers(0, engine.N))
        if start != end:
            pairs.append((start, end))
    return pairs


def benchmark(
    engine: CompactCSREngine,
    *,
    pair_count: int,
    astar_pair_count: int,
) -> None:
    pairs = generate_pairs(engine, pair_count)
    dijkstra_ms: list[float] = []
    astar_ms: list[float] = []
    cost_relative_diffs: list[float] = []
    risk_diffs: list[float] = []
    reachable = 0
    valid = 0
    reachability_mismatches = 0
    started = time.perf_counter()

    for index, (source, target) in enumerate(pairs, start=1):
        before = time.perf_counter()
        distances, predecessors = dijkstra(
            csgraph=engine.csr_safe,
            directed=True,
            indices=source,
            return_predecessors=True,
        )
        dijkstra_ms.append((time.perf_counter() - before) * 1000.0)
        reference_path = (
            reconstruct_path(predecessors, source, target)
            if math.isfinite(float(distances[target]))
            else []
        )

        compare_astar = index <= astar_pair_count
        if compare_astar:
            before = time.perf_counter()
            astar_path = engine._bidirectional_a_star(
                source,
                target,
                engine.csr_safe,
                engine.csr_safe_b,
            )
            astar_ms.append((time.perf_counter() - before) * 1000.0)
        else:
            # SciPy Dijkstra is the production algorithm; reconstruction and
            # directed-edge validation still run for every requested OD pair.
            astar_path = reference_path

        if compare_astar and bool(reference_path) != bool(astar_path):
            reachability_mismatches += 1
            continue
        if not reference_path:
            continue

        reachable += 1
        if astar_path[0] != source or astar_path[-1] != target:
            continue

        reference_cost = float(distances[target])
        astar_cost = csr_path_cost(engine.csr_safe, astar_path)
        relative_diff = abs(reference_cost - astar_cost) / max(
            abs(reference_cost),
            1.0,
        )
        cost_relative_diffs.append(relative_diff)

        reference_metrics = engine._calc_path_metrics(
            reference_path,
            candidate_alpha=engine._cost_alpha,
        )
        astar_metrics = engine._calc_path_metrics(
            astar_path,
            candidate_alpha=engine._cost_alpha,
        )
        if compare_astar:
            risk_diffs.append(abs(reference_metrics[3] - astar_metrics[3]))
        valid += 1

        if index % 250 == 0:
            print(f"OD ilerleme: {index}/{pair_count}")

    elapsed = time.perf_counter() - started
    max_cost_diff = max(cost_relative_diffs, default=0.0)
    max_risk_diff = max(risk_diffs, default=0.0)
    print(f"OD çifti: {pair_count}; erişilebilir: {reachable}; geçerli: {valid}")
    print(f"A* karşılaştırılan çift: {min(astar_pair_count, pair_count)}")
    print(f"Erişilebilirlik uyuşmazlığı: {reachability_mismatches}")
    print(f"Maks objective göreli fark: {max_cost_diff:.3e}")
    print(f"Maks risk farkı: {max_risk_diff:.3e}")
    print(
        "Dijkstra ms p50/p95/p99: "
        f"{percentile(dijkstra_ms, 50):.2f}/"
        f"{percentile(dijkstra_ms, 95):.2f}/"
        f"{percentile(dijkstra_ms, 99):.2f}"
    )
    print(
        "Bidirectional A* ms p50/p95/p99: "
        f"{percentile(astar_ms, 50):.2f}/"
        f"{percentile(astar_ms, 95):.2f}/"
        f"{percentile(astar_ms, 99):.2f}"
    )
    print(f"Toplam: {elapsed:.2f}s; throughput: {pair_count / elapsed:.2f} OD/s")

    if reachability_mismatches:
        raise AssertionError("Dijkstra ve A* erişilebilirlik sonucu farklı")
    if valid != reachable:
        raise AssertionError("En az bir A* rotasının yönlü edge zinciri geçersiz")
    if max_cost_diff >= 1e-6:
        raise AssertionError(f"Objective cost farkı kabul dışında: {max_cost_diff}")
    if max_risk_diff >= 1e-6:
        raise AssertionError(f"Risk farkı kabul dışında: {max_risk_diff}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--pairs", type=int, default=1_000)
    parser.add_argument("--astar-pairs", type=int, default=100)
    parser.add_argument("--consistency-targets", type=int, default=25)
    args = parser.parse_args()

    # This verifier explicitly compares the optional A* implementation. The
    # production default avoids reverse CSR allocation when SciPy is selected.
    settings.routing_search_algorithm = "bidirectional_a_star"
    engine = CompactCSREngine()
    engine.load_graph(str(args.graph))
    engine.apply_risk_weights({}, alpha=2.0)
    verify_edge_monotonicity(
        engine,
        target_count=args.consistency_targets,
    )
    benchmark(
        engine,
        pair_count=args.pairs,
        astar_pair_count=min(args.astar_pairs, args.pairs),
    )
    print("[OK] Res-10 OD doğrulaması geçti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
