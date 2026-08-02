"""Read-only HTTP concurrency and overload acceptance benchmark."""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import time

import httpx


SCENARIOS = (
    ([-87.6403, 41.8789], [-87.6233, 41.8826]),
    ([-87.6368, 41.8990], [-87.6205, 41.8940]),
    ([-87.6359, 41.8670], [-87.6205, 41.8580]),
    ([-87.6850, 41.8950], [-87.6600, 41.8870]),
    ([-87.6050, 41.7950], [-87.5900, 41.7850]),
    ([-87.6500, 41.7800], [-87.6400, 41.7700]),
    ([-87.6700, 42.0100], [-87.6600, 42.0000]),
    ([-87.7700, 41.8900], [-87.7500, 41.8850]),
)


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1)
    return ordered[max(0, index)]


async def benchmark_level(
    client: httpx.AsyncClient,
    *,
    concurrency: int,
    request_count: int,
) -> dict:
    gate = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    queue_waits: list[float] = []
    computes: list[float] = []
    statuses: dict[int, int] = {}
    health_latencies: list[float] = []
    stop_health = asyncio.Event()

    async def route_request(index: int) -> None:
        start, end = SCENARIOS[index % len(SCENARIOS)]
        async with gate:
            started = time.perf_counter()
            response = await client.post(
                "/api/v1/route",
                json={"start": start, "end": end, "profile": "balanced"},
            )
            latencies.append((time.perf_counter() - started) * 1000.0)
            statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
            if response.status_code == 200:
                queue_waits.append(float(response.headers["X-Queue-Wait-Ms"]))
                computes.append(float(response.headers["X-Routing-Compute-Ms"]))

    async def health_poller() -> None:
        while not stop_health.is_set():
            started = time.perf_counter()
            response = await client.get("/health")
            if response.status_code == 200:
                health_latencies.append(
                    (time.perf_counter() - started) * 1000.0
                )
            await asyncio.sleep(0.05)

    started = time.perf_counter()
    poller = asyncio.create_task(health_poller())
    await asyncio.gather(*(route_request(i) for i in range(request_count)))
    stop_health.set()
    await poller
    elapsed = time.perf_counter() - started

    if statuses != {200: request_count}:
        raise AssertionError(
            f"Concurrency {concurrency} unexpected statuses: {statuses}"
        )

    result = {
        "concurrency": concurrency,
        "statuses": statuses,
        "rps": request_count / elapsed,
        "p50": statistics.median(latencies),
        "p95": percentile(latencies, 0.95),
        "p99": percentile(latencies, 0.99),
        "queue_p95": percentile(queue_waits, 0.95),
        "compute_p95": percentile(computes, 0.95),
        "health_p95": percentile(health_latencies, 0.95),
    }
    print(
        f"c={concurrency}: status={statuses}, rps={result['rps']:.2f}, "
        f"p50/p95/p99={result['p50']:.1f}/{result['p95']:.1f}/"
        f"{result['p99']:.1f} ms, queue-p95={result['queue_p95']:.1f} ms, "
        f"compute-p95={result['compute_p95']:.1f} ms, "
        f"health-p95={result['health_p95']:.1f} ms"
    )
    return result


async def verify_overload(
    client: httpx.AsyncClient,
    *,
    request_count: int,
) -> None:
    start, end = SCENARIOS[0]

    async def request() -> httpx.Response:
        return await client.post(
            "/api/v1/route",
            json={"start": start, "end": end, "profile": "balanced"},
        )

    responses = await asyncio.gather(*(request() for _ in range(request_count)))
    statuses: dict[int, int] = {}
    for response in responses:
        statuses[response.status_code] = statuses.get(response.status_code, 0) + 1

    overloaded = [response for response in responses if response.status_code == 503]
    if not overloaded:
        raise AssertionError(f"Queue saturation did not return HTTP 503: {statuses}")
    if any(not response.headers.get("Retry-After") for response in overloaded):
        raise AssertionError("At least one overload response lacks Retry-After")
    print(
        f"overload={statuses}; Retry-After="
        f"{overloaded[0].headers['Retry-After']}"
    )


async def async_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18002")
    parser.add_argument("--requests", type=int, default=16)
    parser.add_argument("--overload-requests", type=int, default=32)
    args = parser.parse_args()

    limits = httpx.Limits(max_connections=64, max_keepalive_connections=16)
    async with httpx.AsyncClient(
        base_url=args.base_url,
        timeout=60.0,
        limits=limits,
    ) as client:
        for concurrency in (1, 2, 4, 8):
            await benchmark_level(
                client,
                concurrency=concurrency,
                request_count=args.requests,
            )
        await verify_overload(client, request_count=args.overload_requests)
    print("[OK] HTTP concurrency, health responsiveness and overload passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
