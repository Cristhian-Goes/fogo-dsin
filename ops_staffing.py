"""Dimensionamento por simulação de eventos discretos. Chegada exponencial, atendimento fixo."""

from __future__ import annotations

import random
from datetime import datetime


def arrivals_per_hour(data: dict, moment: datetime) -> float:
    import model

    since = moment.timestamp() - 90 * 24 * 3600
    count = 0
    for order in data.get("orders") or []:
        opened = order.get("opened_at")
        if not opened:
            continue
        try:
            if model.parse_iso(opened).timestamp() >= since:
                count += 1
        except (TypeError, ValueError):
            continue
    if count < 40:
        return 3.0
    return round(min(6.0, count / (90 * 8)), 3)


def mean_service_min(data: dict) -> float:
    import model

    samples = []
    for order in data.get("orders") or []:
        if order.get("minutos_no_local"):
            minutes = float(order["minutos_no_local"])
            if 5 <= minutes <= 240:
                samples.append(minutes)
            continue
        if not order.get("started_at") or not order.get("closed_at"):
            continue
        try:
            minutes = (model.parse_iso(order["closed_at"]) - model.parse_iso(order["started_at"])).total_seconds() / 60
        except (TypeError, ValueError):
            continue
        if 5 <= minutes <= 240:
            samples.append(minutes)
    if not samples:
        return 35.0
    return round(sum(samples) / len(samples), 1)


def simulate_day(rate_per_hour: float, service_min: float, teams: int, hours: int = 8, seed: int = 7, wait_limit: float = 60) -> dict:
    teams = max(1, int(teams))
    rng = random.Random(seed)
    arrivals = []
    clock = 0.0
    horizon = hours * 60
    rate_per_min = max(rate_per_hour, 0.05) / 60
    while clock < horizon:
        clock += rng.expovariate(rate_per_min)
        if clock < horizon:
            arrivals.append(clock)
    if not arrivals:
        return {"teams": teams, "arrivals": 0, "sla_pct": 100.0, "wait_min": 0.0, "utilization_pct": 0.0}
    free_at = [0.0] * teams
    waits = []
    within = 0
    for arrival in arrivals:
        team = min(range(teams), key=lambda index: free_at[index])
        start = max(arrival, free_at[team])
        wait = start - arrival
        free_at[team] = start + service_min
        waits.append(wait)
        if wait <= wait_limit:
            within += 1
    count = len(arrivals) or 1
    busy = service_min * len(arrivals)
    capacity = teams * horizon
    return {
        "teams": teams,
        "arrivals": len(arrivals),
        "sla_pct": round(100 * within / count, 1),
        "wait_min": round(sum(waits) / count, 1) if waits else 0.0,
        "utilization_pct": round(100 * min(1.0, busy / capacity), 1),
    }


def curve(data: dict, moment: datetime, wait_limit: float = 60) -> dict:
    rate = arrivals_per_hour(data, moment)
    service = mean_service_min(data)
    rows = [simulate_day(rate, service, teams, seed=11, wait_limit=wait_limit) for teams in range(1, 16)]
    target = next((row["teams"] for row in rows if row["sla_pct"] >= 95), None)
    return {
        "rate_per_hour": rate,
        "service_min": service,
        "wait_limit_min": wait_limit,
        "rows": rows,
        "recommendation": target,
        "sentence": (
            "O mínimo para atingir 95% é 1 equipe."
            if target == 1
            else f"O mínimo para atingir 95% é {target} equipes."
            if target
            else "Nenhuma quantidade até 15 equipes atinge 95% com estas premissas."
        ),
        "method": (
            "Simulação de eventos discretos de um turno de 8 h. "
            "O intervalo entre chegadas é exponencial e o atendimento usa a duração média das OS. "
            "SLA aqui é a espera até o início, no limite parametrizável de minutos."
        ),
    }
