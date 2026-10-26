"""Rotas do dia para as ordens de serviço abertas.

A ordem sai do optimizer. O desenho pede a geometria ao OSRM e, em 3 s sem
resposta, guarda uma estimativa a 30 km/h marcada como aproximada.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta
from typing import Any

import model
import optimizer
import routing

COLORS = ("#1f4e79", "#1b6b45", "#8a5a00")
SPECS = (
    ("EQ-1", "Equipe 1 · Sampaio", "Sampaio Vidal", ["geral", "radar", "balanca"]),
    ("EQ-2", "Equipe 2 · Centro", "Centro Marília", ["geral", "camera", "radar"]),
    ("EQ-3", "Equipe 3 · Assis", "Centro Assis", ["geral", "camera"]),
)


def ensure_scenario(data: dict, moment: datetime) -> bool:
    changed = False
    if not data.get("crews"):
        data["crews"] = _crews(data)
        changed = True
    if not data.get("meta", {}).get("routing_seeded"):
        _top_up(data, moment)
        data.setdefault("meta", {})["routing_seeded"] = True
        changed = True
    return changed


def present(data: dict) -> dict[str, Any]:
    plan = data.get("day_plan") or {"crews": [], "unassigned": [], "note": "Nenhuma rota do dia calculada."}
    return plan


def optimize(data: dict, moment: datetime, crew_id: str | None = None, allow_network: bool = True) -> dict[str, Any]:
    ensure_scenario(data, moment)
    _remember(data)
    if crew_id:
        plan = _reoptimize_one(data, crew_id, moment, allow_network)
    else:
        plan = _reoptimize_all(data, moment, allow_network)
    data["day_plan"] = plan
    saved = plan.get("saved_min") or 0
    if saved > 0:
        delta = f"{saved} min a menos"
    elif saved < 0:
        delta = f"{abs(saved)} min a mais para proteger o SLA"
    else:
        delta = "o mesmo tempo"
    message = (
        f"Rotas do dia prontas. {plan['stop_count']} paradas em {len(plan['crews'])} equipes. "
        f"A rota ingênua levaria {plan['naive_min']} min; a otimizada, {plan['optimized_min']} min "
        f"({delta})."
    )
    model.push_feed(data, "info", message, "", moment)
    return {"message": message, "plan": plan}


def reorder(data: dict, crew_id: str, order_ids: list[str], moment: datetime, allow_network: bool = True) -> dict[str, Any]:
    plan = data.get("day_plan")
    if not plan:
        raise model.Invalid("Calcule as rotas do dia antes de reordenar.")
    crew = _crew_plan(plan, crew_id)
    by_id = {item["id"]: item for item in crew["stops"]}
    if len(order_ids) != len(by_id) or set(order_ids) != set(by_id):
        raise model.Invalid("A nova ordem precisa conter as mesmas paradas.")
    _remember(data)
    crew["stops"] = [_with_order(by_id[item], index) for index, item in enumerate(order_ids, start=1)]
    _draw(data, crew, moment, allow_network)
    _totals(plan)
    plan["created_at"] = model.iso(moment)
    plan["manual"] = True
    return {"message": f"{crew['name']} reordenada. O ETA foi recalculado.", "plan": plan}


def undo(data: dict, moment: datetime) -> dict[str, Any]:
    previous = data.get("day_plan_undo")
    if not previous:
        raise model.Invalid("Não há uma versão anterior da rota.")
    data["day_plan"] = previous
    data["day_plan_undo"] = None
    return {"message": "Rota anterior restaurada.", "plan": previous}


def release_crew(data: dict, crew_id: str, moment: datetime, allow_network: bool = True) -> dict[str, Any]:
    plan = data.get("day_plan")
    if not plan:
        raise model.Invalid("Não há rota do dia para redistribuir.")
    crew = _crew_plan(plan, crew_id)
    source = next((item for item in data.get("crews") or [] if item["id"] == crew_id), None)
    if source:
        source["active"] = False
    lost = list(crew["stops"])
    _remember(data)
    crew["stops"] = []
    crew["active"] = False
    crew["polyline"] = []
    moved = []
    for stop in lost:
        note = _insert_stop(data, stop, moment, allow_network)
        moved.append(note)
    plan["created_at"] = model.iso(moment)
    text = f"{crew['name']} ficou indisponível. " + " ".join(moved)
    model.push_feed(data, "atencao", text, crew.get("region") or "", moment)
    return {"message": text, "plan": plan}


def insert_order(data: dict, order: dict, moment: datetime, allow_network: bool = True) -> str:
    if not data.get("day_plan"):
        return ""
    stop = _stop_from_order(data, order, moment)
    if stop is None:
        return ""
    note = _insert_stop(data, stop, moment, allow_network)
    data["day_plan"]["created_at"] = model.iso(moment)
    model.push_feed(data, "atencao", note, order.get("region") or "", moment)
    return note


def sequence_plan(agent: dict, points: list[dict], keep_order: bool) -> tuple[list[dict], dict, dict]:
    ordered = list(points) if keep_order or len(points) < 2 else optimizer.reorder(agent["lat"], agent["lng"], points)
    path = [(agent["lat"], agent["lng"])] + [(item["lat"], item["lng"]) for item in ordered]
    driven = routing.route_or_estimate(path)
    clock = 0
    for index, stop in enumerate(ordered, start=1):
        leg = driven["legs"][index - 1] if index - 1 < len(driven.get("legs") or []) else {}
        clock += leg.get("duration_min") or 0
        stop["order"] = index
        stop["leg_km"] = leg.get("distance_km", 0)
        stop["eta_min"] = clock
    naive = list(points)
    comparison = _local_compare(agent, naive, ordered)
    return ordered, driven, comparison


def pdf(data: dict, crew_id: str) -> bytes:
    plan = data.get("day_plan") or {}
    crew = _crew_plan(plan, crew_id)
    lines = [
        crew["name"],
        f"Distância {crew.get('distance_km', 0)} km · {crew.get('duration_min', 0)} min",
        "Estimativa aproximada" if crew.get("approximate") else "Geometria pelas vias",
        f"Chegada de volta: {crew.get('return_label') or '-'}",
    ]
    for stop in crew.get("stops") or []:
        flag = " · SLA em risco" if stop.get("late") else ""
        lines.append(f"{stop.get('order')}. {stop.get('label')} · ETA {stop.get('eta_label') or '-'}{flag}")
    return _pdf(lines)


def maps_url(crew: dict) -> str:
    stops = crew.get("stops") or []
    base = crew.get("base") or []
    if len(base) < 2 or not stops:
        return ""
    origin = f"{base[0]},{base[1]}"
    waypoints = "|".join(f"{item['lat']},{item['lng']}" for item in stops)
    return "https://www.google.com/maps/dir/?api=1&origin=" + origin + "&destination=" + origin + "&waypoints=" + urllib.parse.quote(waypoints)


def _reoptimize_all(data: dict, moment: datetime, allow_network: bool) -> dict[str, Any]:
    crews = [item for item in data.get("crews") or [] if item.get("active", True)]
    stops = _open_stops(data, moment)
    rush, rain, note = _factors(moment, crews, allow_network)
    points = [_base(item) for item in crews] + [(item["lat"], item["lng"]) for item in stops]
    dist, dur, approx, matrix_note = _matrix(points, rush * rain, allow_network)
    for index, crew in enumerate(crews):
        crew["matrix"] = index
    for index, stop in enumerate(stops):
        stop["matrix"] = len(crews) + index
    assigned = optimizer.assign_crews(crews, stops, dur, dist) if stops else {"crews": [], "unassigned": []}
    by_matrix = {item["matrix"]: item for item in stops}
    plan_crews = []
    for index, crew in enumerate(crews):
        found = next((item for item in assigned.get("crews") or [] if item["id"] == crew["id"]), None)
        order = found["order"] if found else []
        chosen = []
        for position, matrix in enumerate(order, start=1):
            stop = dict(by_matrix[matrix])
            chosen.append(_with_order(stop, position))
        row = _crew_row(crew, chosen, found)
        plan_crews.append(row)
    plan = _shell(plan_crews, [item.get("id") for item in assigned.get("unassigned") or []], note, matrix_note, approx, moment)
    for row in plan["crews"]:
        _draw(data, row, moment, allow_network)
        _mark_late(row, by_matrix, assigned)
    _totals(plan)
    return plan


def _reoptimize_one(data: dict, crew_id: str, moment: datetime, allow_network: bool) -> dict[str, Any]:
    plan = data.get("day_plan")
    if not plan:
        return _reoptimize_all(data, moment, allow_network)
    crew = _crew_plan(plan, crew_id)
    stops = list(crew.get("stops") or [])
    if len(stops) < 2:
        return plan
    origin = tuple(crew["base"])
    ordered = optimizer.reorder(origin[0], origin[1], stops)
    crew["stops"] = [_with_order(item, index) for index, item in enumerate(ordered, start=1)]
    _draw(data, crew, moment, allow_network)
    plan["created_at"] = model.iso(moment)
    _totals(plan)
    return plan


def _insert_stop(data: dict, stop: dict, moment: datetime, allow_network: bool) -> str:
    plan = data.setdefault("day_plan", {"crews": [], "unassigned": []})
    active = [item for item in plan.get("crews") or [] if item.get("active", True)]
    best = None
    for crew in active:
        if stop.get("skill") not in (crew.get("skills") or []):
            continue
        route = [tuple(crew["base"])] + [(item["lat"], item["lng"]) for item in crew.get("stops") or []] + [tuple(crew["base"])]
        extra = optimizer.detour_min(route, (stop["lat"], stop["lng"]))
        if len(crew.get("stops") or []) >= optimizer.MAX_STOPS:
            continue
        if best is None or extra < best[0]:
            best = (extra, crew)
    if best is None:
        plan.setdefault("unassigned", []).append(stop["id"])
        return f"{stop['label']} ficou sem equipe compatível."
    extra, crew = best
    crew.setdefault("stops", []).append(_with_order(stop, len(crew["stops"]) + 1))
    _draw(data, crew, moment, allow_network)
    _totals(plan)
    return f"{stop['label']} inserida na {crew['name']}, +{max(1, round(extra))} min no trajeto."


def _draw(data: dict, crew: dict, moment: datetime, allow_network: bool) -> None:
    points = [tuple(crew["base"])] + [(item["lat"], item["lng"]) for item in crew.get("stops") or []] + [tuple(crew["base"])]
    if len(points) < 2:
        crew.update({"polyline": [], "road": False, "approximate": False, "distance_km": 0, "duration_min": 0})
        return
    if allow_network:
        driven = routing.route_or_estimate(points)
    else:
        driven = routing._estimate(points)
    clock = moment
    for index, stop in enumerate(crew.get("stops") or []):
        leg = driven["legs"][index] if index < len(driven.get("legs") or []) else {}
        minutes = leg.get("duration_min") or 1
        clock = clock + timedelta(minutes=minutes + optimizer.SERVICE_MIN)
        stop["eta_min"] = minutes
        stop["eta_label"] = clock.strftime("%H:%M")
        stop["leg_km"] = leg.get("distance_km", 0)
        due = stop.get("due_at")
        stop["late"] = bool(due and model.parse_iso(due) < clock)
    crew["polyline"] = driven.get("polyline") or []
    crew["road"] = bool(driven.get("road"))
    crew["approximate"] = bool(driven.get("approximate"))
    crew["distance_km"] = driven.get("distance_km") or 0
    crew["duration_min"] = driven.get("duration_min") or 0
    crew["return_label"] = clock.strftime("%H:%M")
    crew["note"] = driven.get("note") or ""
    crew["maps_url"] = maps_url(crew)


def _matrix(points, factor: float, allow_network: bool):
    if allow_network and len(points) >= 2:
        try:
            packed = routing.table(points)
            dur = optimizer.scale_durations(packed["durations_min"], factor)
            return packed["distances_km"], dur, packed["approximate"], packed["note"]
        except routing.RoadError:
            pass
    dist, dur = optimizer.matrix_from_coords(points)
    dur = optimizer.scale_durations(dur, factor)
    return dist, dur, True, "estimativa aproximada"


def _factors(moment: datetime, crews: list[dict], allow_network: bool) -> tuple[float, float, str]:
    rush = 1.35 if moment.hour in (7, 8, 9, 17, 18, 19) else 1.0
    rush_note = "Pico simulado: tempo × 1,35." if rush > 1 else "Fora do pico simulado."
    rain = 1.0
    rain_note = "Sem acréscimo de chuva."
    if allow_network and crews:
        lat, lng = _base(crews[0])
        rain, rain_note = _rain(lat, lng)
    return rush, rain, f"{rush_note} {rain_note} O OSRM não traz trânsito ao vivo."


def _rain(lat: float, lng: float) -> tuple[float, str]:
    import json
    import urllib.request
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat:.3f}&longitude={lng:.3f}&current=precipitation"
    request = urllib.request.Request(url, headers={"User-Agent": "FOGO-CCO/1.0 (demonstracao local)"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        amount = float((payload.get("current") or {}).get("precipitation") or 0)
    except Exception:
        return 1.0, "Open-Meteo não respondeu. A rota segue sem acréscimo de chuva."
    if amount >= 1:
        return 1.25, f"Chuva de {amount:.1f} mm. Deslocamento +25%."
    return 1.0, "Open-Meteo sem chuva relevante agora."


def _open_stops(data: dict, moment: datetime) -> list[dict]:
    rows = []
    for order in data.get("orders") or []:
        if order.get("status") not in ("aberta", "atribuida", "em_execucao") or order.get("parent_id"):
            continue
        stop = _stop_from_order(data, order, moment)
        if stop:
            rows.append(stop)
    for mother in data.get("mothers") or []:
        if mother.get("status") != "aberto":
            continue
        rows.append({
            "id": mother["id"],
            "label": mother["title"],
            "lat": mother["lat"],
            "lng": mother["lng"],
            "skill": mother.get("skill") or "geral",
            "priority": "critica",
            "due_min": 60,
            "due_at": mother.get("due_at"),
            "kind": "mother",
        })
    return rows


def _stop_from_order(data: dict, order: dict, moment: datetime) -> dict | None:
    if order.get("lat") is None:
        return None
    eq = next((item for item in data.get("equipment") or [] if item["id"] == order.get("equipment_id")), None)
    kind = (eq or {}).get("type")
    skill = "radar" if kind == "radar" else "balanca" if kind == "balanca" else "geral"
    due = model.parse_iso(order["due_at"]) if order.get("due_at") else moment + timedelta(hours=24)
    return {
        "id": order["id"],
        "label": f"{order.get('number')} · {order.get('serial') or order.get('street')}",
        "lat": order["lat"],
        "lng": order["lng"],
        "skill": skill,
        "priority": order.get("priority") or "media",
        "due_min": max(0, int((due - moment).total_seconds() // 60)),
        "due_at": order.get("due_at"),
        "kind": "order",
    }


def _crews(data: dict) -> list[dict]:
    rows = []
    for index, (crew_id, name, region, skills) in enumerate(SPECS):
        agent = next((item for item in data.get("agents") or [] if item.get("base_region") == region), None)
        if agent is None:
            continue
        agent["skills"] = list(skills)
        rows.append({
            "id": crew_id,
            "name": name,
            "region": region,
            "skills": list(skills),
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "base": [agent.get("base_lat"), agent.get("base_lng")],
            "color": COLORS[index],
            "active": True,
        })
    return rows


def _top_up(data: dict, moment: datetime) -> None:
    import ops_orders
    open_count = sum(1 for item in data.get("orders") or [] if item.get("status") in ops_orders.OPEN)
    for eq in data.get("equipment") or []:
        if open_count >= 12:
            return
        if eq.get("lat") is None or eq.get("status") == "ainda_nao_instalado":
            continue
        if ops_orders._open_for(data, eq["id"]):
            continue
        if eq.get("type") not in ("radar", "camera", "balanca", "cancela", "totem"):
            continue
        ops_orders._open(data, eq, "preventiva", "media", "Parada do cenário de roteirização.", moment, "sistema")
        open_count += 1


def _base(crew: dict) -> tuple[float, float]:
    return float(crew["base"][0]), float(crew["base"][1])


def _crew_row(crew: dict, stops: list[dict], found: dict | None) -> dict:
    return {
        "id": crew["id"],
        "name": crew["name"],
        "region": crew.get("region"),
        "skills": crew.get("skills") or [],
        "agent_id": crew.get("agent_id"),
        "agent_name": crew.get("agent_name"),
        "base": crew.get("base"),
        "color": crew.get("color"),
        "active": True,
        "stops": stops,
        "naive_km": (found or {}).get("naive_km") or 0,
        "naive_min": (found or {}).get("naive_min") or 0,
        "saved_km": (found or {}).get("saved_km") or 0,
        "saved_min": (found or {}).get("saved_min") or 0,
        "matrix_min": ((found or {}).get("evaluation") or {}).get("minutes") or 0,
    }


def _shell(crews, unassigned, factor_note, matrix_note, approximate, moment) -> dict:
    return {
        "created_at": model.iso(moment),
        "crews": crews,
        "unassigned": unassigned,
        "factor_note": factor_note,
        "matrix_note": matrix_note,
        "approximate": approximate,
        "saved_km": 0,
        "saved_min": 0,
        "naive_min": 0,
        "optimized_min": 0,
        "stop_count": 0,
    }


def _totals(plan: dict) -> None:
    plan["saved_km"] = round(sum(item.get("saved_km") or 0 for item in plan.get("crews") or []), 2)
    plan["saved_min"] = sum(item.get("saved_min") or 0 for item in plan.get("crews") or [])
    plan["naive_min"] = sum(item.get("naive_min") or 0 for item in plan.get("crews") or [])
    plan["optimized_min"] = sum(item.get("matrix_min") or item.get("duration_min") or 0 for item in plan.get("crews") or [])
    plan["stop_count"] = sum(len(item.get("stops") or []) for item in plan.get("crews") or [])


def _mark_late(row, by_matrix, assigned) -> None:
    found = next((item for item in assigned.get("crews") or [] if item["id"] == row["id"]), None)
    late = set((found or {}).get("evaluation", {}).get("late") or [])
    for stop in row["stops"]:
        if stop.get("matrix") in late:
            stop["late"] = True


def _with_order(stop: dict, index: int) -> dict:
    item = dict(stop)
    item["order"] = index
    return item


def _crew_plan(plan: dict, crew_id: str) -> dict:
    found = next((item for item in plan.get("crews") or [] if item["id"] == crew_id), None)
    if not found:
        raise model.Invalid("Equipe não encontrada na rota do dia.")
    return found


def _remember(data: dict) -> None:
    if data.get("day_plan"):
        data["day_plan_undo"] = json_copy(data["day_plan"])


def json_copy(value):
    import json
    return json.loads(json.dumps(value))


def _local_compare(agent: dict, naive: list[dict], ordered: list[dict]) -> dict:
    origin = (agent["lat"], agent["lng"])

    def cost(seq: list[dict]) -> tuple[float, int]:
        coords = [origin] + [(item["lat"], item["lng"]) for item in seq]
        dist, dur = optimizer.matrix_from_coords(coords)
        indexes = list(range(1, len(coords)))
        ev = optimizer.evaluate(indexes, dur, dist, 0, indexes[-1] if indexes else 0, service=0)
        return ev["km"], ev["minutes"]

    naive_km, naive_min = cost(naive)
    opt_km, opt_min = cost(ordered)
    return {"naive_km": naive_km, "naive_min": naive_min, "saved_km": round(naive_km - opt_km, 2), "saved_min": naive_min - opt_min}


def _signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def _pdf(lines: list[str]) -> bytes:
    safe = [line.encode("latin-1", "replace").decode("latin-1") for line in lines]
    text = "BT /F1 11 Tf 40 800 Td " + " T* ".join(f"({_pdf_escape(line)}) Tj" for line in safe) + " ET"
    stream = text.encode("latin-1")
    body = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        b"4 0 obj " + body + b" endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for item in objects:
        offsets.append(len(output))
        output.extend(item)
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(output)


def _pdf_escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
