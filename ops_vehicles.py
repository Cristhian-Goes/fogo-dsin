"""Frota operacional: consumo por veículo, custo e despacho com rota viária."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import model
import routing

TYPES = ("moto", "carro", "caminhonete", "caminhao")
STATUS = ("disponivel", "em_atendimento", "parado", "indisponivel", "em_manutencao")
FUEL = ("gasolina", "etanol", "flex", "diesel", "eletrico")


def present(vehicle: dict) -> dict[str, Any]:
    out = dict(vehicle)
    out["history"] = list(vehicle.get("history") or [])[:8]
    return out


def present_all(data: dict) -> list[dict]:
    return [present(item) for item in data.get("vehicles") or []]


def trip_cost(vehicle: dict, distance_km: float) -> dict[str, Any]:
    unit = vehicle.get("consumption_unit") or "km/l"
    try:
        consumption = float(vehicle.get("consumption") or 0)
        price = float(vehicle.get("fuel_price") or 0)
        other_km = float(vehicle.get("other_cost_per_km") or 0)
    except (TypeError, ValueError):
        raise model.Invalid("Consumo ou preço de combustível inválido.")
    if consumption <= 0:
        raise model.Invalid(f"{vehicle.get('name')} está sem consumo configurado.")
    if price < 0 or other_km < 0:
        raise model.Invalid("Preço e custos não podem ser negativos.")
    amount = distance_km / consumption
    fuel = amount * price
    other = distance_km * other_km
    return {
        "amount": round(amount, 2),
        "amount_unit": "kWh" if unit == "km/kWh" else "L",
        "consumption_unit": unit,
        "fuel_cost": round(fuel, 2),
        "other_cost": round(other, 2),
        "total_cost": round(fuel + other, 2),
    }


def origin(vehicle: dict) -> tuple[float, float, str]:
    if vehicle.get("location_source") == "atual" and vehicle.get("lat") is not None:
        return float(vehicle["lat"]), float(vehicle["lng"]), "localização atual"
    if vehicle.get("base_lat") is None:
        raise model.Invalid(f"{vehicle.get('name')} não tem base nem localização atual.")
    return float(vehicle["base_lat"]), float(vehicle["base_lng"]), "base cadastrada, sem localização atual"


def road_leg(origin_xy: list[float], target: list[float], label: str, fallback_km: float) -> dict[str, Any]:
    route = {
        "origin": origin_xy,
        "target": target,
        "distance_km": round(fallback_km, 1),
        "eta_min": model._eta(fallback_km),
        "label": label,
        "road": False,
    }
    try:
        driven = routing.road([(origin_xy[0], origin_xy[1]), (target[0], target[1])], "carro")
    except routing.RoadError as exc:
        route["road_error"] = str(exc)
        return route
    if len(driven.get("polyline") or []) < 3:
        route["road_error"] = "A resposta não trouxe a geometria da via."
        return route
    route.update({
        "polyline": driven["polyline"],
        "road": True,
        "distance_km": driven["distance_km"],
        "eta_min": driven["duration_min"],
        "traffic_note": driven["note"],
        "steps": driven["steps"],
    })
    return route


def drive_plan(agent: dict, ordered: list[dict]) -> dict[str, Any]:
    try:
        driven = routing.road([(agent["lat"], agent["lng"])] + [(stop["lat"], stop["lng"]) for stop in ordered], "carro")
    except routing.RoadError as exc:
        raise model.Invalid(str(exc))
    if len(driven.get("polyline") or []) < 3:
        raise model.Invalid("A resposta não trouxe a geometria da via.")
    for index, stop in enumerate(ordered, start=1):
        leg = driven["legs"][index - 1] if index - 1 < len(driven["legs"]) else {}
        stop["order"] = index
        stop["leg_km"] = leg.get("distance_km", 0)
    return driven


def _quote(incident: dict, vehicle: dict) -> dict[str, Any]:
    lat, lng, origin_note = origin(vehicle)
    found = routing.alternatives((lat, lng), (float(incident["lat"]), float(incident["lng"])), vehicle["type"])
    options = []
    for route in found["routes"]:
        if len(route.get("polyline") or []) < 3:
            continue
        options.append({**route, **trip_cost(vehicle, route["distance_km"]), "profile_note": found["profile_note"]})
    if not options:
        raise model.Invalid("Nenhum percurso viário.")
    fastest = min(options, key=lambda item: (item["duration_min"], item["distance_km"]))
    cheapest = min(options, key=lambda item: (item["total_cost"], item["duration_min"]))
    same = fastest["distance_km"] == cheapest["distance_km"] and fastest["duration_min"] == cheapest["duration_min"]
    return {
        "vehicle": present(vehicle),
        "origin_note": origin_note,
        "options_count": len(options),
        "same_route": same,
        "fastest": {**fastest, "choice": "rapida"},
        "economical": {**cheapest, "choice": "economica"},
        "profile_note": found["profile_note"],
    }


def compare(data: dict, incident_id: str) -> dict[str, Any]:
    incident = model._must(data["incidents"], incident_id, "Ocorrência")
    if incident.get("status") in ("encerrada", "ciencia"):
        raise model.Invalid("Esta ocorrência já foi encerrada.")
    rows = []
    failures = []
    for vehicle in data.get("vehicles") or []:
        if not vehicle.get("active", True) or vehicle.get("status") != "disponivel":
            continue
        try:
            rows.append(_quote(incident, vehicle))
        except (routing.RoadError, model.Invalid) as exc:
            failures.append({"id": vehicle["id"], "name": vehicle["name"], "error": str(exc)})
    if not rows and failures:
        raise model.Invalid(failures[0]["error"])
    recommendation = {}
    if rows:
        recommendation = {
            "fastest_vehicle_id": min(rows, key=lambda item: item["fastest"]["duration_min"])["vehicle"]["id"],
            "economical_vehicle_id": min(rows, key=lambda item: item["economical"]["total_cost"])["vehicle"]["id"],
        }
    return {
        "incident_id": incident["id"],
        "rows": rows,
        "failures": failures,
        "recommendation": recommendation,
        "note": "Só aparecem percursos que o mapa devolveu. Se houver um único caminho, as duas colunas mostram o mesmo trajeto.",
    }


def _agent_for(data: dict, vehicle: dict, incident: dict) -> dict:
    linked = next((agent for agent in data["agents"] if agent["id"] == vehicle.get("agent_id")), None)
    if linked and linked.get("status") not in ("fora_de_servico", "em_pausa") and not linked.get("mission"):
        return linked
    for region in (vehicle.get("base_region"), incident.get("region")):
        for agent in data["agents"]:
            if agent.get("region") == region and agent.get("status") not in ("fora_de_servico", "em_pausa") and not agent.get("mission"):
                return agent
    for agent in data["agents"]:
        if agent.get("status") not in ("fora_de_servico", "em_pausa") and not agent.get("mission"):
            return agent
    raise model.Invalid("Não há equipe livre para sair com este veículo.")


def dispatch(data: dict, incident_id: str, vehicle_id: str, choice: str, moment: datetime, actor: str) -> dict[str, Any]:
    if choice not in ("rapida", "economica"):
        raise model.Invalid("Escolha a rota mais rápida ou a mais econômica.")
    vehicle = model._must(data.setdefault("vehicles", []), vehicle_id, "Veículo")
    if not vehicle.get("active", True) or vehicle.get("status") != "disponivel":
        raise model.Invalid(f"{vehicle['name']} não está livre para atendimento.")
    incident = model._must(data["incidents"], incident_id, "Ocorrência")
    try:
        row = _quote(incident, vehicle)
    except routing.RoadError as exc:
        raise model.Invalid(str(exc))
    chosen = row["fastest"] if choice == "rapida" else row["economical"]
    if len(chosen.get("polyline") or []) < 3:
        raise model.Invalid("A resposta não trouxe a geometria da via.")
    agent = _agent_for(data, vehicle, incident)
    result = model.dispatch(data, incident_id, agent["id"], moment)
    route = {
        "origin": [chosen["polyline"][0][0], chosen["polyline"][0][1]],
        "target": [incident["lat"], incident["lng"]],
        "polyline": chosen["polyline"],
        "road": True,
        "distance_km": chosen["distance_km"],
        "eta_min": chosen["duration_min"],
        "label": f"{vehicle['name']} → ocorrência {model.incident_number(incident)}",
        "choice": choice,
        "fuel_cost": chosen["fuel_cost"],
        "total_cost": chosen["total_cost"],
        "liters": chosen["amount"],
        "origin_note": row["origin_note"],
        "profile_note": row["profile_note"],
        "traffic_note": chosen["note"],
        "vehicle_id": vehicle["id"],
        "vehicle_name": vehicle["name"],
        "steps": chosen.get("steps") or [],
    }
    incident["route"] = route
    incident["eta_planned"] = chosen["duration_min"]
    incident["assigned_vehicle_id"] = vehicle["id"]
    agent["route"] = route
    vehicle["status"] = "em_atendimento"
    vehicle["incident_id"] = incident["id"]
    vehicle["location_source"] = "atual"
    vehicle["lat"], vehicle["lng"] = agent["lat"], agent["lng"]
    vehicle["updated_at"] = model.iso(moment)
    label = "mais rápida" if choice == "rapida" else "mais econômica"
    text = f"{actor} despachou {vehicle['name']} pela rota {label}: {chosen['distance_km']} km, {chosen['duration_min']} min, R$ {chosen['total_cost']:.2f}."
    vehicle.setdefault("history", []).insert(0, {"at": model.iso(moment), "text": text})
    vehicle["history"] = vehicle["history"][:12]
    model._log_incident(incident, text, moment)
    result["message"] = text
    return result


def release(data: dict, vehicle_id: str | None, moment: datetime) -> None:
    if not vehicle_id:
        return
    vehicle = next((item for item in data.get("vehicles") or [] if item["id"] == vehicle_id), None)
    if not vehicle:
        return
    vehicle["status"] = "disponivel"
    vehicle["incident_id"] = None
    vehicle["updated_at"] = model.iso(moment)
    vehicle.setdefault("history", []).insert(0, {"at": model.iso(moment), "text": "Veículo liberado após o atendimento."})
    vehicle["history"] = vehicle["history"][:12]


def follow(data: dict) -> None:
    for vehicle in data.get("vehicles") or []:
        if vehicle.get("status") != "em_atendimento" or not vehicle.get("incident_id"):
            continue
        incident = next((item for item in data["incidents"] if item["id"] == vehicle["incident_id"]), None)
        agent = next((item for item in data["agents"] if incident and item["id"] == incident.get("assigned_agent_id")), None)
        if not agent:
            continue
        vehicle["lat"], vehicle["lng"] = agent["lat"], agent["lng"]
        vehicle["location_source"] = "atual"


def _payload(data: dict, payload: dict, ignore: str | None) -> dict[str, Any]:
    kind = model._choice(payload.get("type"), "o tipo", list(TYPES))
    fuel = model._choice(payload.get("fuel"), "o combustível", list(FUEL))
    default_unit = "km/kWh" if fuel == "eletrico" else "km/l"
    unit = model._choice(payload.get("consumption_unit") or default_unit, "a unidade de consumo", ["km/l", "km/kWh"])
    if fuel == "eletrico" and unit != "km/kWh":
        raise model.Invalid("Veículo elétrico usa consumo em km/kWh.")
    if fuel != "eletrico" and unit != "km/l":
        raise model.Invalid("Este combustível usa consumo em km/l.")
    status = model._choice(payload.get("status") or "disponivel", "a disponibilidade", list(STATUS))
    plate = model._clean_text(payload.get("plate"), "a placa", 8).upper().replace("-", "")
    if len(plate) < 7:
        raise model.Invalid("Informe a placa.")
    for other in data.get("vehicles") or []:
        if other["id"] != ignore and other["plate"] == plate:
            raise model.Invalid("Já existe um veículo com esta placa.")
    try:
        year = int(payload.get("year"))
        consumption = float(payload.get("consumption"))
        price = float(payload.get("fuel_price"))
        other_cost = float(payload.get("other_cost_per_km") or 0)
    except (TypeError, ValueError):
        raise model.Invalid("Ano, consumo e preço precisam ser numéricos.")
    if not 1990 <= year <= 2030:
        raise model.Invalid("Ano fora do intervalo.")
    if consumption <= 0 or price < 0 or other_cost < 0:
        raise model.Invalid("Consumo, preço e custos operacionais inválidos.")
    region = model._choice(payload.get("base_region"), "a base", list(model.REGIONS))
    meta = model.REGIONS[region]
    lat = payload.get("lat")
    lng = payload.get("lng")
    if lat in (None, "") or lng in (None, ""):
        lat, lng = meta["lat"], meta["lng"]
        source = "base"
    else:
        lat = model._coord(lat, "a latitude", -34, 6)
        lng = model._coord(lng, "a longitude", -74, -32)
        source = "atual" if payload.get("location_source") == "atual" else "base"
    return {
        "name": model._clean_text(payload.get("name"), "o nome", 80),
        "type": kind,
        "brand": model._clean_text(payload.get("brand"), "a marca", 40),
        "model": model._clean_text(payload.get("model"), "o modelo", 40),
        "year": year,
        "plate": plate,
        "fuel": fuel,
        "consumption": round(consumption, 2),
        "consumption_unit": unit,
        "fuel_price": round(price, 2),
        "other_cost_per_km": round(other_cost, 2),
        "status": status,
        "active": bool(payload.get("active", True)),
        "base_region": region,
        "base_lat": meta["lat"],
        "base_lng": meta["lng"],
        "lat": lat,
        "lng": lng,
        "location_source": source,
        "notes": model._clean_text(payload.get("notes"), "as observações", 400, required=False),
        "color": model._clean_text(payload.get("color"), "a cor", 30, required=False),
        "capacity": model._clean_text(payload.get("capacity"), "a capacidade", 40, required=False),
        "responsible": model._clean_text(payload.get("responsible"), "o responsável", 80, required=False),
        "odometer_km": _optional_km(payload.get("odometer_km")),
    }


def _optional_km(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise model.Invalid("Quilometragem inválida.")
    if value < 0:
        raise model.Invalid("Quilometragem inválida.")
    return round(value, 1)


def _fresh_id(data: dict) -> str:
    data["meta"].setdefault("next_vehicle", 1)
    taken = {item["id"] for item in data.get("vehicles") or []}
    while True:
        vid = model._next_id(data, "vehicle", "VH")
        if vid not in taken:
            return vid


def create(data: dict, payload: dict, moment: datetime, actor: str) -> dict[str, Any]:
    fields = _payload(data, payload, None)
    data.setdefault("vehicles", [])
    item = {
        "id": _fresh_id(data),
        **fields,
        "agent_id": None,
        "incident_id": None,
        "updated_at": model.iso(moment),
        "history": [{"at": model.iso(moment), "text": f"{actor} cadastrou o veículo."}],
    }
    data["vehicles"].append(item)
    return item


def update(data: dict, vehicle_id: str, payload: dict, moment: datetime, actor: str) -> dict[str, Any]:
    vehicle = model._must(data.setdefault("vehicles", []), vehicle_id, "Veículo")
    fields = _payload(data, payload, vehicle_id)
    changes = []
    if fields["fuel_price"] != vehicle.get("fuel_price"):
        changes.append(f"preço do combustível de {vehicle.get('fuel_price')} para {fields['fuel_price']}")
    if fields["consumption"] != vehicle.get("consumption"):
        changes.append(f"consumo de {vehicle.get('consumption')} para {fields['consumption']}")
    if fields["status"] != vehicle.get("status"):
        changes.append(f"disponibilidade para {fields['status']}")
    if fields["active"] != vehicle.get("active", True):
        changes.append("ativado" if fields["active"] else "inativado")
    vehicle.update(fields)
    vehicle["updated_at"] = model.iso(moment)
    text = f"{actor} alterou o veículo" + (": " + "; ".join(changes) + "." if changes else ".")
    vehicle.setdefault("history", []).insert(0, {"at": model.iso(moment), "text": text})
    vehicle["history"] = vehicle["history"][:12]
    return vehicle


def seed(data: dict, moment: datetime) -> None:
    if data.get("vehicles"):
        return
    data["meta"]["next_vehicle"] = data["meta"].get("next_vehicle", 6)
    samples = [
        ("VH-1", "Moto Sampaio 01", "moto", "Honda", "CG 160", 2022, "FGT1A23", "gasolina", 38, 6.29, 0.12, "Sampaio Vidal", -22.2168, -49.9642, "atual"),
        ("VH-2", "Carro Centro 02", "carro", "Fiat", "Cronos", 2021, "FGT2B45", "flex", 13.2, 6.29, 0.22, "Centro Marília", -22.2144, -49.9462, "atual"),
        ("VH-3", "Caminhonete Fragata 03", "caminhonete", "Toyota", "Hilux", 2020, "FGT3C67", "diesel", 9.4, 6.09, 0.48, "Fragata", -22.2058, -49.9782, "atual"),
        ("VH-4", "Carro Assis 04", "carro", "Volkswagen", "Voyage", 2019, "ASS4D89", "gasolina", 12.1, 6.29, 0.2, "Centro Assis", -22.6619, -50.4116, "base"),
        ("VH-5", "Moto Mota 05", "moto", "Yamaha", "Factor 150", 2018, "MOT5E10", "gasolina", 40, 6.29, 0.1, "Cândido Mota", -22.7464, -50.3868, "base"),
    ]
    data["vehicles"] = []
    for vid, name, kind, brand, model_name, year, plate, fuel, consumption, price, other, region, lat, lng, source in samples:
        meta = model.REGIONS[region]
        data["vehicles"].append({
            "id": vid, "name": name, "type": kind, "brand": brand, "model": model_name, "year": year,
            "plate": plate, "fuel": fuel, "consumption": consumption, "consumption_unit": "km/l",
            "fuel_price": price, "other_cost_per_km": other,
            "status": "em_manutencao" if vid == "VH-5" else "disponivel", "active": True,
            "base_region": region, "base_lat": meta["lat"], "base_lng": meta["lng"],
            "lat": lat, "lng": lng, "location_source": source,
            "notes": "Veículo de demonstração. O consumo é desta ficha, não uma média da frota.",
            "agent_id": None, "incident_id": None, "updated_at": model.iso(moment),
            "history": [{"at": model.iso(moment), "text": "Veículo incluído na frota de demonstração."}],
        })


def ensure(data: dict, moment: datetime | None = None) -> bool:
    if data.get("vehicles"):
        return False
    seed(data, moment or model.now_local())
    return True
