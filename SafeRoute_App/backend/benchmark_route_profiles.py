"""Salt-okunur HTTP rota profili karşılaştırması.

Çalışan SafeRoute API'sine aynı Chicago yolculuklarını shortest, balanced ve
safer profilleriyle gönderir. Veritabanına veya dosyalara yazmaz.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCENARIOS = (
    ("Loop", (-87.6403, 41.8789), (-87.6233, 41.8826)),
    ("Near North", (-87.6368, 41.8990), (-87.6205, 41.8940)),
    ("South Loop", (-87.6359, 41.8670), (-87.6205, 41.8580)),
    ("West Town", (-87.6850, 41.8950), (-87.6600, 41.8870)),
    ("Hyde Park", (-87.6050, 41.7950), (-87.5900, 41.7850)),
    ("Englewood", (-87.6500, 41.7800), (-87.6400, 41.7700)),
    ("Rogers Park", (-87.6700, 42.0100), (-87.6600, 42.0000)),
    ("Austin", (-87.7700, 41.8900), (-87.7500, 41.8850)),
    ("Lakeview", (-87.6600, 41.9400), (-87.6400, 41.9300)),
    ("Bronzeville", (-87.6200, 41.8300), (-87.6000, 41.8200)),
)
PROFILES = ("shortest", "balanced", "safer")


def request_route(
    base_url: str,
    start: tuple[float, float],
    end: tuple[float, float],
    profile: str,
    *,
    timeout_s: float,
) -> tuple[dict, float]:
    body = json.dumps(
        {
            "start": list(start),
            "end": list(end),
            "hour": 21,
            "profile": profile,
        }
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/api/v1/route",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urlopen(request, timeout=timeout_s) as response:
        payload = json.load(response)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return payload, elapsed_ms


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1),
    )
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SafeRoute çok-adaylı rota profili salt-okunur benchmark"
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8002",
        help="Çalışan SafeRoute API adresi",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    rows: list[dict] = []
    errors: list[str] = []
    for name, start, end in SCENARIOS:
        for profile in PROFILES:
            try:
                payload, latency_ms = request_route(
                    args.base_url,
                    start,
                    end,
                    profile,
                    timeout_s=args.timeout,
                )
            except (HTTPError, URLError, TimeoutError) as exc:
                errors.append(f"{name}/{profile}: {exc}")
                continue

            safe = payload["safe_route"]
            comparison = payload["comparison"]
            navigation_steps = [
                step
                for step in safe["steps"]
                if step["maneuver"] != "arrive"
            ]
            rows.append(
                {
                    "scenario": name,
                    "profile": profile,
                    "distance_m": float(safe["distance_m"]),
                    "shortest_distance_m": float(
                        payload["shortest_route"]["distance_m"]
                    ),
                    "route_risk": float(safe["route_risk"]),
                    "risk_coverage": float(safe["risk_coverage"]),
                    "named_steps": sum(
                        bool(step.get("street_name"))
                        for step in navigation_steps
                    ),
                    "unlabeled_steps": sum(
                        not step.get("street_name")
                        and not step.get("way_type")
                        for step in navigation_steps
                    ),
                    "risk_reduction_pct": float(
                        comparison["risk_reduction_pct"]
                    ),
                    "extra_distance_pct": float(
                        comparison["extra_distance_pct"]
                    ),
                    "candidate_count": int(comparison["candidate_count"]),
                    "meaningful": bool(
                        comparison["meaningful_safer_alternative"]
                    ),
                    "decision": str(comparison["decision_reason"]),
                    "latency_ms": latency_ms,
                }
            )

    print(
        "Scenario             Profile    Dist(m)  Risk    Risk%   "
        "Extra%  Cover%  Name  Unlab  Cand  Meaningful  Latency(ms)  Decision"
    )
    print("-" * 125)
    for row in rows:
        print(
            f"{row['scenario'][:20]:20} "
            f"{row['profile']:9} "
            f"{row['distance_m']:8.1f} "
            f"{row['route_risk']:7.4f} "
            f"{row['risk_reduction_pct']:7.1f} "
            f"{row['extra_distance_pct']:7.1f} "
            f"{row['risk_coverage']:7.1f} "
            f"{row['named_steps']:5d} "
            f"{row['unlabeled_steps']:6d} "
            f"{row['candidate_count']:5d} "
            f"{str(row['meaningful']):10} "
            f"{row['latency_ms']:11.1f}  "
            f"{row['decision']}"
        )

    violations = [
        row
        for row in rows
        if (
            row["profile"] == "balanced"
            and row["extra_distance_pct"] > 15.0 + 0.1
        )
        or (
            row["profile"] == "safer"
            and row["extra_distance_pct"] > 25.0 + 0.1
        )
        or (
            row["profile"] == "shortest"
            and row["extra_distance_pct"] > 0.1
        )
    ]
    metric_violations = [
        row
        for row in rows
        if not (0.0 <= row["route_risk"] <= 1.0)
        or not (0.0 <= row["risk_coverage"] <= 100.0)
        or row["unlabeled_steps"] != 0
        or (
            row["profile"] == "shortest"
            and abs(row["distance_m"] - row["shortest_distance_m"]) > 0.1
        )
    ]
    latencies = [row["latency_ms"] for row in rows]
    meaningful = [
        row
        for row in rows
        if row["profile"] != "shortest" and row["meaningful"]
    ]
    profiled_count = sum(row["profile"] != "shortest" for row in rows)

    print("\nÖZET")
    print(f"Başarılı istek: {len(rows)}/{len(SCENARIOS) * len(PROFILES)}")
    print(f"Mesafe bütçesi ihlali: {len(violations)}")
    print(f"Risk/coverage/shortest metric ihlali: {len(metric_violations)}")
    if latencies:
        print(f"Median gecikme: {statistics.median(latencies):.1f} ms")
        print(f"P95 gecikme: {percentile_95(latencies):.1f} ms")
    if profiled_count:
        print(
            "Anlamlı güvenli alternatif oranı: "
            f"%{len(meaningful) / profiled_count * 100.0:.1f}"
        )
    if errors:
        print("\nHATALAR")
        for error in errors:
            print(f"- {error}")

    return 1 if errors or violations or metric_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
