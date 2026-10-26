"""Ordem de paradas: vizinho mais próximo, 2-opt e inserção mais barata.

Não chama rede. A matriz de minutos pode vir do OSRM ou da estimativa
haversine a 30 km/h. Complexidade prática O(n²) por equipe, com n limitado
pelo turno. Não serve para centenas de paradas.
"""

from __future__ import annotations

import math
from typing import Any

SERVICE_MIN = 30
SPEED_KMH = 30
SHIFT_MIN = 8 * 60
MAX_STOPS = 6
PRIORITY_BIAS = {"critica": 0, "alta": 15, "media": 35, "baixa": 60}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, a)))


def travel_min(km: float, rush: float = 1.0, rain: float = 1.0, speed: float = SPEED_KMH) -> float:
    if km <= 0 or speed <= 0:
        return 0.0
    return (km / speed) * 60.0 * rush * rain


def matrix_from_coords(points: list[tuple[float, float]], rush: float = 1.0, rain: float = 1.0) -> tuple[list[list[float]], list[list[float]]]:
    size = len(points)
    dist = [[0.0] * size for _ in range(size)]
    dur = [[0.0] * size for _ in range(size)]
    for i in range(size):
        for j in range(size):
            if i == j:
                continue
            km = haversine_km(points[i][0], points[i][1], points[j][0], points[j][1])
            dist[i][j] = km
            dur[i][j] = travel_min(km, rush, rain)
    return dist, dur


def scale_durations(dur: list[list[float]], factor: float) -> list[list[float]]:
    return [[value * factor for value in row] for row in dur]


def nearest_neighbor(stops: list[int], dur: list[list[float]], start: int, bias: dict[int, float] | None = None) -> list[int]:
    bias = bias or {}
    pending = list(stops)
    order: list[int] = []
    current = start
    while pending:
        nxt = min(pending, key=lambda item: dur[current][item] + bias.get(item, 0))
        order.append(nxt)
        pending.remove(nxt)
        current = nxt
    return order


def route_minutes(order: list[int], dur: list[list[float]], start: int, end: int, service: float = 0) -> float:
    if not order:
        return dur[start][end]
    total = 0.0
    current = start
    for stop in order:
        total += dur[current][stop]
        total += service
        current = stop
    return total + dur[current][end]


def two_opt(
    order: list[int],
    dur: list[list[float]],
    start: int,
    end: int,
    dues: dict[int, float] | None = None,
    critical: set[int] | None = None,
    service: float = SERVICE_MIN,
) -> list[int]:
    """Melhora a ordem. Não aceita troca que aumente o número de críticas atrasadas."""
    best = list(order)
    if len(best) < 2:
        return best

    def score(seq: list[int]) -> tuple:
        ev = evaluate(seq, dur, dur, start, end, dues or {}, service)
        late_critical = sum(1 for item in ev["late"] if item in (critical or set()))
        return (late_critical, route_minutes(seq, dur, start, end, service))

    best_score = score(best)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for k in range(i + 1, len(best)):
                candidate = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                candidate_score = score(candidate)
                if candidate_score < best_score:
                    best, best_score = candidate, candidate_score
                    improved = True
                    break
            if improved:
                break
    return best


def evaluate(
    order: list[int],
    dur: list[list[float]],
    dist: list[list[float]],
    start: int,
    end: int,
    dues: dict[int, float] | None = None,
    service: float = SERVICE_MIN,
) -> dict[str, Any]:
    dues = dues or {}
    clock = 0.0
    km = 0.0
    current = start
    rows = []
    late = []
    for stop in order:
        leg_min = dur[current][stop]
        km += dist[current][stop]
        clock += leg_min
        is_late = stop in dues and clock > dues[stop]
        if is_late:
            late.append(stop)
        rows.append({
            "index": stop,
            "arrive_min": round(clock),
            "leg_min": round(leg_min, 1),
            "late": is_late,
        })
        clock += service
        current = stop
    back = dur[current][end] if order else dur[start][end]
    km += dist[current][end] if order else dist[start][end]
    clock += back
    return {
        "stops": rows,
        "km": round(km, 2),
        "minutes": round(clock),
        "late": late,
        "fits_shift": clock <= SHIFT_MIN and len(order) <= MAX_STOPS,
    }


def insertion_cost(
    order: list[int],
    new_index: int,
    dur: list[list[float]],
    start: int,
    end: int,
    service: float = SERVICE_MIN,
) -> tuple[int, float] | None:
    """Posição e minutos extras. None se a jornada ou a capacidade estouram."""
    if len(order) >= MAX_STOPS:
        return None
    base = route_minutes(order, dur, start, end, service)
    best: tuple[int, float] | None = None
    for pos in range(len(order) + 1):
        candidate = order[:pos] + [new_index] + order[pos:]
        spent = route_minutes(candidate, dur, start, end, service)
        if spent > SHIFT_MIN:
            continue
        extra = spent - base
        if best is None or extra < best[1]:
            best = (pos, extra)
    return best


def assign_crews(
    crews: list[dict],
    stops: list[dict],
    dur: list[list[float]],
    dist: list[list[float]],
) -> dict[str, Any]:
    """crews e stops usam 'matrix' como índice na matriz. O índice 0.. não é o depósito.

    Cada crew tem matrix = índice do depósito, skills, id.
    Cada stop tem matrix, skill, priority, due_min.
    """
    ranked = sorted(stops, key=lambda item: (PRIORITY_BIAS.get(item.get("priority"), 35), item.get("due_min") or 10_000))
    routes: dict[str, list[int]] = {crew["id"]: [] for crew in crews}
    unassigned = []
    for stop in ranked:
        options = []
        for crew in crews:
            if stop.get("skill") not in crew.get("skills", []):
                continue
            found = insertion_cost(routes[crew["id"]], stop["matrix"], dur, crew["matrix"], crew["matrix"])
            if found is None:
                continue
            options.append((found[1], crew, found[0]))
        if not options:
            unassigned.append(stop)
            continue
        _, crew, pos = min(options, key=lambda item: item[0])
        routes[crew["id"]].insert(pos, stop["matrix"])
    naive = _naive(crews, ranked, dur, dist)
    optimized = []
    for crew in crews:
        order = routes[crew["id"]]
        bias = {stop["matrix"]: PRIORITY_BIAS.get(stop.get("priority"), 35) for stop in stops}
        seeded = nearest_neighbor(order, dur, crew["matrix"], bias) if order else []
        critical = {stop["matrix"] for stop in stops if stop.get("priority") == "critica"}
        dues = {stop["matrix"]: stop["due_min"] for stop in stops if stop.get("due_min") is not None}
        improved = two_opt(seeded, dur, crew["matrix"], crew["matrix"], dues, critical)
        ev = evaluate(improved, dur, dist, crew["matrix"], crew["matrix"], dues)
        naive_ev = next(item for item in naive["crews"] if item["id"] == crew["id"])
        optimized.append({
            "id": crew["id"],
            "order": improved,
            "evaluation": ev,
            "naive_km": naive_ev["km"],
            "naive_min": naive_ev["minutes"],
            "saved_km": round(naive_ev["km"] - ev["km"], 2),
            "saved_min": naive_ev["minutes"] - ev["minutes"],
        })
    return {"crews": optimized, "unassigned": unassigned, "naive_km": naive["km"], "naive_min": naive["minutes"]}


def _naive(crews: list[dict], stops: list[dict], dur: list[list[float]], dist: list[list[float]]) -> dict[str, Any]:
    """Reparte na ordem recebida, sem olhar a distância. É o comparativo ingênuo."""
    buckets: dict[str, list[int]] = {crew["id"]: [] for crew in crews}
    cursor = 0
    skilled = [crew for crew in crews]
    for stop in stops:
        choices = [crew for crew in skilled if stop.get("skill") in crew.get("skills", [])]
        if not choices:
            continue
        crew = choices[cursor % len(choices)]
        cursor += 1
        if len(buckets[crew["id"]]) >= MAX_STOPS:
            continue
        buckets[crew["id"]].append(stop["matrix"])
    rows = []
    km = 0.0
    minutes = 0
    dues = {stop["matrix"]: stop["due_min"] for stop in stops if stop.get("due_min") is not None}
    for crew in crews:
        ev = evaluate(buckets[crew["id"]], dur, dist, crew["matrix"], crew["matrix"], dues)
        rows.append({"id": crew["id"], "km": ev["km"], "minutes": ev["minutes"]})
        km += ev["km"]
        minutes += ev["minutes"]
    return {"crews": rows, "km": round(km, 2), "minutes": minutes}


def reorder(lat: float, lng: float, stops: list[dict]) -> list[dict]:
    """Uma equipe, depósito no agente, sem volta obrigatória no desenho."""
    if len(stops) < 2:
        return list(stops)
    coords = [(lat, lng)] + [(float(item["lat"]), float(item["lng"])) for item in stops]
    dist, dur = matrix_from_coords(coords)
    indexes = list(range(1, len(coords)))
    bias = {index: PRIORITY_BIAS.get(stops[index - 1].get("priority") or "media", 35) for index in indexes}
    order = two_opt(nearest_neighbor(indexes, dur, 0, bias), dur, 0, 0, service=0)
    return [stops[index - 1] for index in order]


def detour_min(route: list[tuple[float, float]], extra: tuple[float, float]) -> float:
    """Minutos extras, a 30 km/h, para encaixar um ponto no meio do trajeto."""
    if len(route) < 2:
        return travel_min(haversine_km(route[0][0], route[0][1], extra[0], extra[1])) if route else 0.0
    best = None
    for index in range(len(route) - 1):
        a, b = route[index], route[index + 1]
        direct = haversine_km(a[0], a[1], b[0], b[1])
        via = haversine_km(a[0], a[1], extra[0], extra[1]) + haversine_km(extra[0], extra[1], b[0], b[1])
        extra_min = travel_min(max(0.0, via - direct))
        if best is None or extra_min < best:
            best = extra_min
    return best or 0.0


def greedy_cover(cells: list[str], candidates: dict[str, set[str]]) -> dict[str, Any]:
    pending = set(cells)
    chosen = []
    recovered: set[str] = set()
    while pending:
        best_id = None
        best_hit: set[str] = set()
        for name, covered in candidates.items():
            if name in chosen:
                continue
            hit = covered & pending
            if len(hit) > len(best_hit):
                best_id, best_hit = name, hit
        if not best_id or not best_hit:
            break
        chosen.append(best_id)
        recovered |= best_hit
        pending -= best_hit
        break
    total = len(cells) or 1
    return {
        "chosen": chosen[0] if chosen else None,
        "recovered": len(recovered),
        "uncovered": len(cells) - len(recovered),
        "pct": round(100 * len(recovered) / total),
    }
