"""Lightweight authenticated API load test (read-only requests).

Example:
  $env:LOAD_TEST_TOKEN="..."
  python scripts/load_test.py --base-url http://localhost:8000 --users 500 --seconds 60
"""
import argparse
import asyncio
import os
import random
import statistics
import time

import httpx


async def virtual_user(client: httpx.AsyncClient, number: int, deadline: float, results: list[tuple[float, int]]) -> None:
    endpoints = ("/auth/me", "/dashboard/summary?range=day&status=open", "/notifications/live")
    await asyncio.sleep(random.uniform(0, min(15, max(1, deadline - time.monotonic()))))
    while time.monotonic() < deadline:
        endpoint = endpoints[number % len(endpoints)]
        started = time.perf_counter()
        try:
            response = await client.get(endpoint)
            results.append(((time.perf_counter() - started) * 1000, response.status_code))
        except httpx.HTTPError:
            results.append(((time.perf_counter() - started) * 1000, 0))
        await asyncio.sleep(random.uniform(1.0, 3.0))


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentage))]


async def run(args: argparse.Namespace) -> int:
    token = os.getenv("LOAD_TEST_TOKEN")
    if not token:
        raise SystemExit("Defina LOAD_TEST_TOKEN com um token JWT de homologação.")
    results: list[tuple[float, int]] = []
    limits = httpx.Limits(max_connections=args.users, max_keepalive_connections=min(args.users, 200))
    timeout = httpx.Timeout(args.timeout)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), headers=headers, limits=limits, timeout=timeout) as client:
        deadline = time.monotonic() + args.seconds
        await asyncio.gather(*(virtual_user(client, number, deadline, results) for number in range(args.users)))

    durations = [duration for duration, _ in results]
    failures = sum(status == 0 or status >= 400 for _, status in results)
    print(f"requests={len(results)} failures={failures} error_rate={(failures / len(results) * 100 if results else 100):.2f}%")
    print(f"latency_ms mean={statistics.fmean(durations) if durations else 0:.1f} p50={percentile(durations, .50):.1f} p95={percentile(durations, .95):.1f} p99={percentile(durations, .99):.1f}")
    return 1 if failures or percentile(durations, .95) > args.p95_limit else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--p95-limit", type=float, default=1000, help="limite de p95 em ms")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
