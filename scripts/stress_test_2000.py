"""Ensaio local de 2.000 sessões autenticadas concorrentes.

Recebe tokens separados por vírgula em STRESS_ACCESS_TOKENS. Os tokens podem
representar perfis diferentes; nunca são impressos no relatório.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from uuid import uuid4

import httpx
import jwt


BASE_URL = os.getenv("STRESS_BASE_URL", "http://localhost:8000").rstrip("/")
VIRTUAL_USERS = int(os.getenv("STRESS_VIRTUAL_USERS", "2000"))
REQUEST_TIMEOUT = float(os.getenv("STRESS_TIMEOUT_SECONDS", "90"))
RAMP_SECONDS = float(os.getenv("STRESS_RAMP_SECONDS", "20"))
TOKEN_CLOCK_MARGIN_SECONDS = int(os.getenv("STRESS_TOKEN_CLOCK_MARGIN_SECONDS", "30"))


def load_tokens() -> list[str]:
    configured = [token.strip() for token in os.environ.get("STRESS_ACCESS_TOKENS", "").split(",") if token.strip()]
    if configured:
        return configured
    if not sys.stdin.isatty():
        payload = sys.stdin.read().strip()
        if payload:
            decoded = json.loads(payload)
            if isinstance(decoded, list) and all(isinstance(token, str) for token in decoded):
                return decoded
    return []


def expand_local_sessions(tokens: list[str]) -> list[str]:
    """Cria JWTs distintos para o ensaio sem fazer uma tempestade de logins.

    Uso exclusivamente local; exige que o segredo seja informado pelo operador.
    """
    secret = os.getenv("STRESS_JWT_SECRET", "")
    if not secret or len(tokens) >= VIRTUAL_USERS:
        return tokens
    algorithm = os.getenv("STRESS_JWT_ALGORITHM", "HS256")
    # O Docker Desktop pode apresentar pequeno desvio de relógio em relação ao
    # host Windows; a validade continua sendo verificada pela própria API.
    claims = [jwt.decode(token, secret, algorithms=[algorithm], options={"verify_iat": False}) for token in tokens]
    return [
        jwt.encode(
            {
                **claims[index % len(claims)],
                # Usa o relógio do gerador com pequena margem; Docker Desktop e
                # host Windows podem divergir por alguns segundos.
                "iat": int(time.time()) - TOKEN_CLOCK_MARGIN_SECONDS,
                "jti": str(uuid4()),
            },
            secret,
            algorithm=algorithm,
        )
        for index in range(VIRTUAL_USERS)
    ]


async def main() -> None:
    tokens = expand_local_sessions(load_tokens())
    if not tokens:
        raise SystemExit("Defina STRESS_ACCESS_TOKENS ou envie uma lista JSON de tokens pela entrada padrão.")

    limits = httpx.Limits(
        max_connections=VIRTUAL_USERS,
        max_keepalive_connections=min(VIRTUAL_USERS, 500),
        keepalive_expiry=15,
    )
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=REQUEST_TIMEOUT, pool=REQUEST_TIMEOUT)
    start_gate = asyncio.Event()

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def virtual_user(index: int):
            token = tokens[index % len(tokens)]
            path = "/api/routes" if index % 2 == 0 else "/api/auth/me"
            await start_gate.wait()
            # Todos os tokens já representam sessões ativas; apenas a ação do
            # usuário é distribuída no intervalo, como ocorre no aplicativo.
            if RAMP_SECONDS > 0:
                await asyncio.sleep((index / VIRTUAL_USERS) * RAMP_SECONDS)
            started = time.perf_counter()
            try:
                response = await client.get(
                    BASE_URL + path,
                    headers={"Authorization": f"Bearer {token}"},
                )
                return str(response.status_code), response.text[:160], (time.perf_counter() - started) * 1000
            except Exception as exc:  # relatório agrega também falhas de transporte
                return type(exc).__name__, str(exc)[:160], (time.perf_counter() - started) * 1000

        tasks = [asyncio.create_task(virtual_user(index)) for index in range(VIRTUAL_USERS)]
        test_started = time.perf_counter()
        start_gate.set()
        results = await asyncio.gather(*tasks)
        duration = time.perf_counter() - test_started

    counts: dict[str, int] = {}
    samples: dict[str, str] = {}
    for status, detail, _ in results:
        counts[status] = counts.get(status, 0) + 1
        if status != "200" and status not in samples:
            samples[status] = detail
    latencies = sorted(latency for _, _, latency in results)
    report = {
        "virtual_users": VIRTUAL_USERS,
        "ramp_seconds": RAMP_SECONDS,
        "duration_seconds": round(duration, 2),
        "requests_per_second": round(VIRTUAL_USERS / duration, 2),
        "results": counts,
        "error_samples": samples,
        "latency_ms": {
            "average": round(statistics.mean(latencies), 2),
            "p50": round(latencies[int(len(latencies) * 0.50)], 2),
            "p95": round(latencies[int(len(latencies) * 0.95)], 2),
            "p99": round(latencies[int(len(latencies) * 0.99)], 2),
            "maximum": round(latencies[-1], 2),
        },
    }
    print(json.dumps(report, ensure_ascii=False))
    if counts != {"200": VIRTUAL_USERS}:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
