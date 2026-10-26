"""Rotas pela malha viária, via OSRM.

O serviço público usa o perfil de automóvel do OpenStreetMap. Não há
trânsito ao vivo nem perfil próprio de moto ou caminhonete. A URL pode
ser trocada com a variável de ambiente OSRM_URL. Nenhuma chave vai ao navegador.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
CACHE_PATH = Path(os.environ.get("FOGO_DATA") or (Path(__file__).resolve().parent / "data")) / "osrm-cache.json"
TTL_S = 600

PROFILE_NOTE = {
    "moto": "O OSRM público não tem perfil de motocicleta. O percurso usa o perfil de automóvel; restrições exclusivas de moto não foram verificadas.",
    "carro": "Perfil de automóvel do OSRM, sobre a malha do OpenStreetMap.",
    "caminhonete": "O OSRM público não aplica altura, largura nem peso. O percurso usa o perfil de automóvel, sem essas restrições.",
    "caminhao": "O OSRM público não aplica altura, largura nem peso de caminhão. O percurso usa o perfil de automóvel, sem essas restrições.",
}


class RoadError(Exception):
    pass


def profile_note(kind: str) -> str:
    return PROFILE_NOTE.get(kind, PROFILE_NOTE["carro"])


def alternatives(origin: tuple[float, float], dest: tuple[float, float], kind: str) -> dict:
    """Até as alternativas que o motor realmente devolver. Não inventa um segundo trajeto."""
    routes = _request([origin, dest], alternatives=True)
    return {"routes": routes, "profile_note": profile_note(kind), "traffic": False}


def road(points: list[tuple[float, float]], kind: str = "carro") -> dict:
    routes = _request(points, alternatives=False)
    if not routes:
        raise RoadError("O motor de rotas não devolveu um percurso.")
    chosen = routes[0]
    chosen["profile_note"] = profile_note(kind)
    return chosen


def route_or_estimate(points: list[tuple[float, float]], timeout: float = 3) -> dict:
    """Geometria viária, ou estimativa haversine a 30 km/h se o OSRM não responder em 3 s."""
    if len(points) < 2:
        raise RoadError("Informe origem e destino.")
    try:
        found = _request(points, alternatives=False, timeout=timeout)
    except RoadError:
        return _estimate(points)
    chosen = dict(found[0])
    chosen["approximate"] = False
    chosen["road"] = len(chosen.get("polyline") or []) >= 3
    return chosen


def table(points: list[tuple[float, float]], timeout: float = 3) -> dict:
    """Matriz de minutos e km. Sem resposta, a matriz é haversine a 30 km/h."""
    if len(points) < 2:
        raise RoadError("A matriz precisa de ao menos dois pontos.")
    key = "table|" + ";".join(f"{round(lat, 4)},{round(lng, 4)}" for lat, lng in points)
    cached = _cache_get(key)
    if cached:
        return cached[0]
    coord = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    url = f"{BASE}/table/v1/driving/{coord}?annotations=duration,distance"
    request = urllib.request.Request(url, headers={"User-Agent": "FOGO-CCO/1.0 (demonstracao local)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        payload = None
    if not payload or payload.get("code") != "Ok":
        dist, dur = _haversine_matrix(points)
        return {"durations_min": dur, "distances_km": dist, "approximate": True, "note": "estimativa aproximada"}
    durations = []
    distances = []
    for row_dur, row_dist in zip(payload.get("durations") or [], payload.get("distances") or []):
        durations.append([0 if value is None else round(value / 60, 2) for value in row_dur])
        distances.append([0 if value is None else round(value / 1000, 3) for value in row_dist])
    packed = {
        "durations_min": durations,
        "distances_km": distances,
        "approximate": False,
        "note": "Tempos da matriz OSRM, sem trânsito ao vivo.",
    }
    _cache_put(key, [packed])
    return packed


def _estimate(points: list[tuple[float, float]]) -> dict:
    dist, dur = _haversine_matrix(points)
    legs = []
    steps_km = 0.0
    steps_min = 0.0
    for index in range(len(points) - 1):
        km = dist[index][index + 1]
        minutes = dur[index][index + 1]
        steps_km += km
        steps_min += minutes
        legs.append({"distance_km": round(km, 2), "duration_min": max(1, round(minutes))})
    return {
        "distance_km": round(steps_km, 2),
        "duration_min": max(1, round(steps_min)),
        "polyline": [[round(lat, 6), round(lng, 6)] for lat, lng in points],
        "legs": legs,
        "steps": [],
        "approximate": True,
        "road": False,
        "note": "estimativa aproximada",
    }


def _haversine_matrix(points: list[tuple[float, float]]) -> tuple[list[list[float]], list[list[float]]]:
    import optimizer
    return optimizer.matrix_from_coords(points)


def _request(points: list[tuple[float, float]], alternatives: bool, timeout: float = 12) -> list[dict]:
    if len(points) < 2:
        raise RoadError("Informe origem e destino.")
    key = _key(points, alternatives)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    coord = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    query = urllib.parse.urlencode({
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "alternatives": "true" if alternatives and len(points) == 2 else "false",
    })
    url = f"{BASE}/route/v1/driving/{coord}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "FOGO-CCO/1.0 (demonstracao local)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RoadError("O serviço de roteirização não respondeu. Nenhum trajeto em linha reta foi usado no lugar.") from exc
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RoadError("Não há rota viária entre estes pontos.")
    routes = [_shape(item) for item in payload["routes"]]
    _cache_put(key, routes)
    return routes


def _shape(route: dict) -> dict:
    coords = route.get("geometry", {}).get("coordinates") or []
    polyline = [[round(lat, 6), round(lng, 6)] for lng, lat in coords]
    if len(polyline) < 2:
        raise RoadError("A resposta não trouxe a geometria da via.")
    steps = []
    legs = []
    for leg in route.get("legs") or []:
        legs.append({
            "distance_km": round(leg.get("distance", 0) / 1000, 2),
            "duration_min": max(1, round(leg.get("duration", 0) / 60)),
        })
        for step in leg.get("steps") or []:
            name = step.get("name") or "via sem nome"
            kind = (step.get("maneuver") or {}).get("type") or "continue"
            verb = {
                "depart": "Siga",
                "arrive": "Chegue",
                "turn": "Vire",
                "new name": "Continue",
                "continue": "Continue",
                "merge": "Entre",
                "on ramp": "Acesse",
                "off ramp": "Saia",
                "fork": "Na bifurcação",
                "end of road": "No fim da via",
                "roundabout": "Rotatória",
                "rotary": "Rotatória",
                "exit roundabout": "Saia da rotatória",
            }.get(kind, "Siga")
            steps.append({"text": f"{verb} · {name}", "meters": round(step.get("distance") or 0)})
    return {
        "distance_km": round(route.get("distance", 0) / 1000, 2),
        "duration_min": max(1, round(route.get("duration", 0) / 60)),
        "polyline": polyline,
        "legs": legs,
        "steps": steps[:12],
        "note": "Tempo estimado pelo OSRM na malha viária. Não há leitura de trânsito em tempo real.",
    }


def _key(points: list[tuple[float, float]], alternatives: bool) -> str:
    body = ";".join(f"{round(lat, 4)},{round(lng, 4)}" for lat, lng in points)
    return f"{'alt' if alternatives else 'one'}|{body}"


def _cache_get(key: str):
    data = _read()
    item = data.get(key)
    if not item:
        return None
    if time.time() - item.get("at", 0) > TTL_S:
        return None
    return item.get("routes")


def _cache_put(key: str, routes: list[dict]) -> None:
    data = _read()
    data[key] = {"at": time.time(), "routes": routes}
    if len(data) > 120:
        ordered = sorted(data, key=lambda name: data[name].get("at", 0))
        for old in ordered[:-120]:
            data.pop(old, None)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")


def _read() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
