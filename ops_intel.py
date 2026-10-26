"""Inteligência operacional: zumbi, causa raiz, fila, diagnóstico e impacto.

As contas são regras e estatística. Cada número mostrado na tela tem a fórmula
correspondente em METHOD. Nada aqui chama a rede.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

import model
import optimizer

SUPPLIERS = (
    "Sinal Norte", "Via Leste", "Ótica Centro", "Peso Certo", "Guarda Fixa", "Fluxo Oeste",
    "Radar Sul", "Imagem Alta", "Nó Público", "Sinal Assis", "Campo Mota", "Pátio Local",
)
RISK = {
    "Sampaio Vidal": 4, "Alto Cafezal": 4, "Fragata": 3, "Vila Xavier": 3,
    "Centro Assis": 3, "Centro Marília": 2, "Campus": 2, "Cândido Mota": 2,
}
METHOD = {
    "zombie": "Dois intervalos seguidos abaixo de 20% do baseline daquela hora. O baseline é a taxa esperada do tipo no horário, com pico de manhã e de tarde.",
    "mother": "Três ou mais falhas em 10 minutos, ou 60% de um mesmo nó. Confiança = percentual dos equipamentos daquele nó que caíram juntos.",
    "wait": "Custo da espera = registros esperados por hora × horas parado × peso da via. O peso de Sampaio Vidal é 1,4.",
    "cover": "Grade de pontos ao redor do sensor. Escolhe o posto que recupera mais pontos. A conta é gulosa, não um mapa de cobertura real.",
    "ride": "Entra na rota se a preventiva vence em 14 dias e o desvio, a 30 km/h, fica em até 8 minutos.",
    "vendor": "Média das horas entre abertura e conclusão comparada com o SLA do contrato daquele fornecedor.",
    "confidence": "Começa em 100. Perde ponto por lacuna de telemetria, por zumbi e por valor fora da faixa.",
}

ROAD_WEIGHT = {"Sampaio Vidal": 1.4}


def is_zombie(expected: float, windows: list[float], ratio: float = 0.2) -> bool:
    if expected <= 0 or len(windows) < 2:
        return False
    limit = expected * ratio
    return windows[-1] < limit and windows[-2] < limit


def cluster_cause(failures: list[dict], population: dict[tuple[str, str], int]) -> dict | None:
    best = None
    for field in ("energy_node", "network_node", "supplier", "firmware"):
        groups: dict[str, list] = {}
        for item in failures:
            groups.setdefault(item.get(field) or "", []).append(item)
        for key, rows in groups.items():
            if not key:
                continue
            size = population.get((field, key), len(rows)) or len(rows)
            share = len(rows) / size
            if len(rows) < 3 and share < 0.6:
                continue
            found = {
                "field": field,
                "key": key,
                "count": len(rows),
                "size": size,
                "confidence": min(99, round(100 * share)),
                "ids": [item["id"] for item in rows],
            }
            if best is None or (found["count"], found["confidence"]) > (best["count"], best["confidence"]):
                best = found
    return best


def wait_cost(per_hour: float, hours: float, weight: float = 1.0) -> int:
    return max(0, round(per_hour * hours * weight))


def data_confidence(gaps: int, zombie: bool, out_of_range: bool) -> int:
    score = 100 - min(40, gaps * 10)
    if zombie:
        score -= 30
    if out_of_range:
        score -= 15
    return max(0, score)


def similar_cases(signature: dict, past: list[dict]) -> list[dict]:
    def score(item: dict) -> int:
        return sum(1 for key in ("type", "supplier", "firmware", "event") if signature.get(key) and signature.get(key) == item.get(key))
    ranked = sorted(past, key=score, reverse=True)
    return [item for item in ranked if score(item) > 0][:3]


def ensure(data: dict, moment: datetime) -> bool:
    changed = False
    data.setdefault("meta", {})
    sensors = [eq for eq in data.get("equipment") or [] if eq.get("type") in ("camera", "radar", "balanca")]
    for index, eq in enumerate(data.get("equipment") or []):
        if eq.get("supplier"):
            continue
        changed = True
        eq["supplier"] = SUPPLIERS[index % len(SUPPLIERS)]
        eq["contract_sla_hours"] = (4, 8, 24, 48)[index % 4]
        eq["network_node"] = f"R-{(index % 8) + 1:02d}"
        eq["firmware"] = ("fw-1.2", "fw-2.0", "fw-3.1")[index % 3]
        years = 2 + (index % 11)
        eq["life_years"] = 12
        eq["installed_at"] = eq.get("installed_at") or (moment.date() - timedelta(days=365 * years)).isoformat()
        eq["repair_cost"] = 800 + (index % 9) * 450
        eq["replacement_cost"] = 12000 if eq.get("type") in ("radar", "balanca", "camera") else 4000
        eq["baseline_hour"] = [_expected(eq.get("type"), hour) for hour in range(24)]
        eq["recent_windows"] = [eq["baseline_hour"][moment.hour], eq["baseline_hour"][moment.hour]]
        eq["frame_age_min"] = 0
        eq["moved_this_shift"] = True
    for index, eq in enumerate(sensors):
        if eq.get("energy_node"):
            continue
        changed = True
        eq["energy_node"] = "N-07" if index < 8 else f"N-{(index % 12) + 1:02d}"
    for eq in data.get("equipment") or []:
        if not eq.get("energy_node"):
            eq["energy_node"] = "N-01"
            changed = True
    if not data.get("risk_zones"):
        data["risk_zones"] = dict(RISK)
        changed = True
    if not data["meta"].get("diagnosis_seeded"):
        _seed_resolutions(data, moment)
        data["meta"]["diagnosis_seeded"] = True
        changed = True
    data.setdefault("impact", _blank_impact())
    return changed


def snapshot(data: dict, moment: datetime) -> dict[str, Any]:
    zombies = _zombies(data, moment)
    mothers = [item for item in data.get("mothers") or [] if item.get("status") == "aberto"]
    decisions = _queue(data, moment, zombies, mothers)
    return {
        "zombies": len(zombies),
        "zombie_rows": zombies[:8],
        "mothers": mothers[:4],
        "decisions": decisions,
        "piggyback": _rides(data, moment)[:6],
        "coverage": data.get("coverage_suggestion"),
        "safety": list(data.get("safety_alerts") or [])[:4],
        "prompts": [agent["id"] for agent in data.get("agents") or [] if agent.get("safety_asked_at") and not agent.get("safety_ok")],
        "vendors": _vendors(data)[:12],
        "problems": _problems(data, moment)[:6],
        "impact": data.get("impact") or _blank_impact(),
        "impact_before": data.get("impact_before") or _blank_impact(),
        "methods": METHOD,
        "consolidated": (data.get("impact") or {}).get("orders_consolidated") or 0,
    }


def annotate(rows: list[dict], data: dict, moment: datetime) -> None:
    by_id = {item["id"]: item for item in data.get("equipment") or []}
    for row in rows:
        source = by_id.get(row.get("id")) or {}
        expected = _expected_now(source, moment)
        windows = source.get("recent_windows") or [expected, expected]
        zombie = is_zombie(expected, windows)
        frozen = source.get("type") == "camera" and (source.get("frame_age_min") or 0) >= 20
        still = source.get("type") in ("patinete", "viatura_gm", "viatura_pm", "moto_agente") and not source.get("moved_this_shift", True)
        reason = ""
        if zombie:
            reason = f"Esperado cerca de {expected:g} registros nesta hora. Os dois últimos intervalos ficaram em {windows[-2]:g} e {windows[-1]:g}."
        elif frozen:
            reason = "A imagem simulada não mudou nos últimos minutos."
        elif still:
            reason = "Este equipamento móvel não se deslocou no turno."
        row["suspicion"] = "zumbi" if zombie else "imagem_congelada" if frozen else "sem_movimento" if still else ""
        row["suspicion_reason"] = reason
        row["confidence"] = data_confidence(0 if windows[-1] else 2, bool(row["suspicion"]), False)
        row["supplier"] = source.get("supplier")
        row["energy_node"] = source.get("energy_node")


def decide(data: dict, item_id: str, action: str, reason: str, moment: datetime, actor: str) -> dict[str, Any]:
    action = model._choice(action, "a decisão", ["aceitar", "adiar", "dispensar"])
    if action != "aceitar" and not str(reason or "").strip():
        raise model.Invalid("Diga o motivo para adiar ou dispensar.")
    data.setdefault("decision_log", []).insert(0, {
        "id": item_id, "action": action, "reason": reason, "at": model.iso(moment), "actor": actor,
    })
    data["decision_log"] = data["decision_log"][:80]
    if action == "aceitar" and item_id.startswith("eq:"):
        eq = model._must(data["equipment"], item_id.split(":", 1)[1], "Equipamento")
        import ops_orders
        if not ops_orders._open_for(data, eq["id"]):
            ops_orders._open(data, eq, "corretiva", "alta", "Aceito na fila de decisões.", moment, actor)
        return {"message": f"OS aberta para {eq.get('serial')}."}
    if action == "aceitar" and item_id.startswith("mother:"):
        return {"message": "A OS-mãe segue com uma equipe. As filhas continuam agrupadas."}
    verb = "adiada" if action == "adiar" else "dispensada"
    return {"message": f"Ação {verb}. Isso reduz o peso deste tipo de alerta nas próximas filas."}


def remote_restart(data: dict, equipment_id: str, moment: datetime, rng: random.Random | None = None) -> dict[str, Any]:
    eq = model._must(data["equipment"], equipment_id, "Equipamento")
    rng = rng or random.Random()
    ok = rng.random() < 0.6
    data.setdefault("impact", _blank_impact())
    if ok:
        if eq.get("status") == "mau_funcionamento":
            eq["status"] = "operacional"
        hour = eq.get("baseline_hour") or [1] * 24
        eq["recent_windows"] = [hour[moment.hour], hour[moment.hour]]
        eq["frame_age_min"] = 0
        data["impact"]["trips_avoided"] = data["impact"].get("trips_avoided", 0) + 1
        text = f"Reinício remoto de {eq.get('serial')} funcionou. Uma viagem foi evitada."
    else:
        text = f"Reinício remoto de {eq.get('serial')} não voltou. A equipe ainda precisa ir."
    eq.setdefault("history", []).insert(0, {"at": model.iso(moment), "text": text})
    return {"message": text, "ok": ok}


def accept_ride(data: dict, crew_id: str, equipment_id: str, moment: datetime) -> dict[str, Any]:
    eq = model._must(data["equipment"], equipment_id, "Equipamento")
    import ops_orders
    order = ops_orders._open_for(data, eq["id"]) or ops_orders._open(
        data, eq, "preventiva", "baixa", "Manutenção carona aceita na rota.", moment, "operador",
    )
    note = ""
    if data.get("day_plan"):
        note = __import__("ops_dayroutes").insert_order(data, order, moment, allow_network=False)
    separate = optimizer.haversine_km(eq["lat"], eq["lng"], eq["lat"], eq["lng"])
    saved = max(1.0, round(optimizer.travel_min(2.5), 1))
    data.setdefault("impact", _blank_impact())
    data["impact"]["km_saved"] = round(data["impact"].get("km_saved", 0) + separate + 2.5, 1)
    return {"message": note or f"{eq.get('serial')} entrou na rota. Uma viagem separada de cerca de {saved:.0f} min foi evitada."}


def safety_ask(data: dict, agent_id: str, moment: datetime) -> dict[str, Any]:
    agent = model._must(data["agents"], agent_id, "Agente")
    agent["safety_asked_at"] = model.iso(moment)
    agent["safety_ok"] = False
    return {"message": f"Pergunta enviada a {agent['name']}. Sem resposta em 2 minutos, o supervisor é avisado."}


def safety_ok(data: dict, agent_id: str, moment: datetime) -> dict[str, Any]:
    agent = model._must(data["agents"], agent_id, "Agente")
    agent["safety_ok"] = True
    agent["safety_asked_at"] = None
    return {"message": f"{agent['name']} confirmou que está bem."}


def safety_silent(data: dict, agent_id: str, moment: datetime) -> dict[str, Any]:
    agent = model._must(data["agents"], agent_id, "Agente")
    return _escalate(data, agent, moment, "Sem resposta ao check-in.")


def safety_tick(data: dict, moment: datetime) -> None:
    for agent in data.get("agents") or []:
        asked = agent.get("safety_asked_at")
        if not asked or agent.get("safety_ok") or agent.get("safety_escalated"):
            continue
        if (moment - model.parse_iso(asked)).total_seconds() >= 120:
            _escalate(data, agent, moment, "Check-in sem resposta há 2 minutos.")


def handoff(data: dict, moment: datetime) -> dict[str, Any]:
    intel = snapshot(data, moment)
    open_orders = [item for item in data.get("orders") or [] if item.get("status") in ("aberta", "atribuida", "em_execucao")]
    lines = [
        f"Passagem de turno · {moment.strftime('%d/%m %H:%M')}.",
        f"OS abertas: {len(open_orders)}. Zumbis agora: {intel['zombies']}. OS-mãe abertas: {len(intel['mothers'])}.",
        "O que mudou: " + ("; ".join(item.get("title") or "" for item in (data.get("feed") or [])[:3]) or "sem novidade na fita."),
        "Próximas 4 horas: " + (intel["decisions"][0]["what"] if intel["decisions"] else "nenhuma ação urgente na fila."),
        "Decisões registradas: " + str(len(data.get("decision_log") or [])),
        "Este texto é um modelo determinístico. Se houver chave de IA no ambiente, o chat pode reescrever o mesmo fato.",
    ]
    return {"text": "\n".join(lines), "mode": "modelo local"}


def demo_step(data: dict, step: int, moment: datetime) -> dict[str, Any]:
    ensure(data, moment)
    if step == 1:
        if not data.get("impact_before"):
            data["impact_before"] = dict(data.get("impact") or _blank_impact())
        return _demo_mother(data, moment)
    if step == 2:
        return _demo_zombie(data, moment)
    if step == 3:
        row = _queue(data, moment, _zombies(data, moment), [item for item in data.get("mothers") or [] if item.get("status") == "aberto"])
        top = row[0] if row else None
        text = top["why"] if top else "A fila não tem ação urgente neste instante."
        return {"message": text, "step": 3}
    if step == 4:
        return _demo_cover(data, moment)
    if step == 5:
        agent = next((item for item in data["agents"] if item.get("base_region") in ("Sampaio Vidal", "Alto Cafezal")), data["agents"][0])
        safety_ask(data, agent["id"], moment)
        note = safety_silent(data, agent["id"], moment)
        return {"message": f"Check-in de {agent['name']} na zona {data['risk_zones'].get(agent.get('base_region'), 1)}. {note['message']} Na operação real o silêncio espera 2 minutos; aqui a demonstração confirma na hora.", "step": 5}
    if step == 6:
        impact = data.setdefault("impact", _blank_impact())
        plan = data.get("day_plan") or {}
        impact["km_saved"] = round(impact.get("km_saved", 0) + max(0, plan.get("saved_km") or 0), 1)
        text = (
            f"Viagens evitadas {impact.get('trips_avoided', 0)}. "
            f"OS consolidadas {impact.get('orders_consolidated', 0)}. "
            f"Km economizados {impact.get('km_saved', 0)}. "
            f"Cobertura recuperada {impact.get('coverage_pct', 0)}%."
        )
        return {"message": text, "step": 6}
    raise model.Invalid("Passo de demonstração desconhecido.")


def resolve_mother(data: dict, mother_id: str, moment: datetime, actor: str) -> dict[str, Any]:
    mother = next((item for item in data.get("mothers") or [] if item["id"] == mother_id), None)
    if not mother or mother.get("status") != "aberto":
        raise model.Invalid("OS-mãe não encontrada.")
    import ops_orders
    for order_id in mother.get("order_ids") or []:
        order = next((item for item in data.get("orders") or [] if item["id"] == order_id), None)
        if order and order.get("status") in ops_orders.OPEN:
            ops_orders.advance(data, order_id, "concluida", "Encerrada com a OS-mãe.", moment, actor)
    mother["status"] = "resolvida"
    return {"message": f"{mother['title']} resolvida. As filhas foram encerradas e os equipamentos voltaram a operacional, exceto furto."}


def _demo_mother(data: dict, moment: datetime) -> dict[str, Any]:
    group = [eq for eq in data["equipment"] if eq.get("energy_node") == "N-07"][:8]
    import ops_orders
    for eq in group:
        eq["status"] = "mau_funcionamento"
        eq["updated_at"] = model.iso(moment)
        eq.setdefault("history", []).insert(0, {"at": model.iso(moment), "text": "Queda junto com o nó de energia N-07."})
        if not ops_orders._open_for(data, eq["id"]):
            ops_orders._open(data, eq, "corretiva", "alta", "Caiu com o nó N-07.", moment, "sistema")
    failures = [{"id": eq["id"], "energy_node": eq.get("energy_node"), "network_node": eq.get("network_node"), "supplier": eq.get("supplier"), "firmware": eq.get("firmware")} for eq in group]
    population = {}
    for eq in data["equipment"]:
        for field in ("energy_node", "network_node", "supplier", "firmware"):
            population[(field, eq.get(field) or "")] = population.get((field, eq.get(field) or ""), 0) + 1
    found = cluster_cause(failures, population)
    orders = [ops_orders._open_for(data, eq["id"]) for eq in group]
    orders = [item for item in orders if item]
    mother_id = f"MAE-{(data.get('meta') or {}).get('next_mother', 1)}"
    data.setdefault("meta", {})["next_mother"] = data["meta"].get("next_mother", 1) + 1
    lat = sum(eq["lat"] for eq in group) / len(group)
    lng = sum(eq["lng"] for eq in group) / len(group)
    label = {"energy_node": "nó de energia", "network_node": "nó de rede", "supplier": "fornecedor", "firmware": "firmware"}.get((found or {}).get("field"), "nó")
    title = f"{len(group)} equipamentos caíram. Causa provável: {label} {(found or {}).get('key')} (confiança {(found or {}).get('confidence', 0)}%)."
    mother = {
        "id": mother_id,
        "title": title,
        "status": "aberto",
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "skill": "radar" if any(eq.get("type") == "radar" for eq in group) else "geral",
        "order_ids": [item["id"] for item in orders],
        "confidence": (found or {}).get("confidence", 0),
        "due_at": model.iso(moment + timedelta(hours=4)),
    }
    for order in orders:
        order["parent_id"] = mother_id
    data.setdefault("mothers", []).insert(0, mother)
    data.setdefault("impact", _blank_impact())["orders_consolidated"] = data["impact"].get("orders_consolidated", 0) + max(0, len(orders) - 1)
    data["impact"]["blind_hours"] = round(data["impact"].get("blind_hours", 0) + 0.5 * len(group), 1)
    extra = ""
    if data.get("day_plan"):
        extra = " " + __import__("ops_dayroutes")._insert_stop(data, {
            "id": mother_id, "label": mother_id, "lat": mother["lat"], "lng": mother["lng"],
            "skill": mother["skill"], "priority": "critica", "due_at": mother["due_at"], "kind": "mother",
        }, moment, False)
    return {"message": title + " Uma equipe vai ao nó, não a cada equipamento." + extra, "step": 1}


def _demo_zombie(data: dict, moment: datetime) -> dict[str, Any]:
    radar = next((eq for eq in data["equipment"] if eq.get("type") == "radar" and eq.get("status") == "operacional"), None)
    if radar is None:
        radar = next(eq for eq in data["equipment"] if eq.get("type") == "radar")
    radar["recent_windows"] = [0, 0]
    expected = _expected_now(radar, moment)
    return {"message": f"{radar.get('serial')} está operacional suspeito. Esperado {expected:g} registros nesta hora e os dois últimos intervalos vieram zerados. O heartbeat sozinho não basta.", "step": 2}


def _demo_cover(data: dict, moment: datetime) -> dict[str, Any]:
    failed = next((eq for eq in data["equipment"] if eq.get("type") in ("camera", "radar") and eq.get("status") != "operacional"), None)
    if failed is None:
        failed = next(eq for eq in data["equipment"] if eq.get("type") == "camera")
        failed["status"] = "mau_funcionamento"
    radius = 0.8 if failed.get("type") == "radar" else 0.4
    cells = [f"{x}:{y}" for x in range(-2, 3) for y in range(-2, 3)]
    agents = [agent for agent in data["agents"] if agent.get("status") in ("em_atividade", "em_deslocamento")][:3]
    candidates = {}
    for index, agent in enumerate(agents):
        cover = set(cells[: 8 - index])
        candidates[agent["name"]] = cover
    found = optimizer.greedy_cover(cells, candidates or {"posto": set(cells[:8])})
    data["coverage_suggestion"] = {
        "equipment_id": failed["id"],
        "serial": failed.get("serial"),
        "lat": failed.get("lat"),
        "lng": failed.get("lng"),
        "radius_km": radius,
        "chosen": found["chosen"],
        "pct": found["pct"],
        "note": f"Área do {failed.get('serial')} descoberta. {found['chosen'] or 'Ninguém'} recupera {found['pct']}% dos pontos da grade.",
    }
    data.setdefault("impact", _blank_impact())["coverage_pct"] = found["pct"]
    return {"message": data["coverage_suggestion"]["note"], "step": 4}


def _zombies(data: dict, moment: datetime) -> list[dict]:
    rows = []
    for eq in data.get("equipment") or []:
        expected = _expected_now(eq, moment)
        windows = eq.get("recent_windows") or [expected, expected]
        frozen = eq.get("type") == "camera" and (eq.get("frame_age_min") or 0) >= 20
        still = eq.get("type") in ("patinete", "viatura_gm", "viatura_pm", "moto_agente") and not eq.get("moved_this_shift", True)
        if not is_zombie(expected, windows) and not frozen and not still:
            continue
        rows.append({
            "id": eq["id"],
            "serial": eq.get("serial"),
            "region": eq.get("region"),
            "expected": expected,
            "observed": windows[-1],
            "reason": "Dois intervalos abaixo de 20% do esperado." if is_zombie(expected, windows) else "Imagem parada." if frozen else "Sem movimento no turno.",
        })
    return rows


def _queue(data: dict, moment: datetime, zombies: list[dict], mothers: list[dict]) -> list[dict]:
    penalty = {}
    for item in data.get("decision_log") or []:
        if item.get("action") == "dispensar":
            kind = item["id"].split(":", 1)[0]
            penalty[kind] = penalty.get(kind, 0) + 8
    rows = []
    for mother in mothers:
        rows.append(_card(f"mother:{mother['id']}", "Atender o nó, não cada equipamento", mother["title"], "Uma equipe", 100, penalty))
    for row in zombies:
        hours = 2
        cost = wait_cost(row["expected"] or 1, hours, ROAD_WEIGHT.get(row.get("region"), 1))
        rows.append(_card(
            f"eq:{row['id']}",
            f"Verificar {row['serial']}",
            f"{row['reason']} ~{cost} veículos sem esse registro nas próximas {hours} h.",
            "Equipe da região",
            80,
            penalty,
        ))
    ranked = sorted(rows, key=lambda item: item["score"], reverse=True)
    return ranked[:7]


def _card(item_id, what, why, who, score, penalty) -> dict:
    kind = item_id.split(":", 1)[0]
    return {"id": item_id, "what": what, "why": why, "who": who, "score": score - penalty.get(kind, 0)}


def _rides(data: dict, moment: datetime) -> list[dict]:
    plan = data.get("day_plan") or {}
    today = moment.date()
    found = []
    for crew in plan.get("crews") or []:
        route = [tuple(crew.get("base") or [0, 0])]
        route += [(item["lat"], item["lng"]) for item in crew.get("stops") or []]
        route.append(tuple(crew.get("base") or [0, 0]))
        if len(route) < 2:
            continue
        for eq in data.get("equipment") or []:
            due = eq.get("next_maintenance")
            if not due or eq.get("lat") is None:
                continue
            try:
                when = datetime.fromisoformat(due).date()
            except ValueError:
                continue
            if not (0 <= (when - today).days <= 14):
                continue
            extra = optimizer.detour_min(route, (eq["lat"], eq["lng"]))
            if extra <= 8:
                found.append({
                    "crew_id": crew["id"],
                    "crew": crew["name"],
                    "equipment_id": eq["id"],
                    "serial": eq.get("serial"),
                    "extra_min": round(extra, 1),
                })
    return found


def _vendors(data: dict) -> list[dict]:
    buckets: dict[str, list] = {}
    equipment = {item["id"]: item for item in data.get("equipment") or []}
    for order in data.get("orders") or []:
        if order.get("status") != "concluida" or not order.get("closed_at") or not order.get("opened_at"):
            continue
        eq = equipment.get(order.get("equipment_id")) or {}
        supplier = eq.get("supplier")
        if not supplier:
            continue
        hours = (model.parse_iso(order["closed_at"]) - model.parse_iso(order["opened_at"])).total_seconds() / 3600
        sla = eq.get("contract_sla_hours") or 24
        buckets.setdefault(supplier, []).append((hours, sla))
    rows = []
    for name, pairs in buckets.items():
        mean = sum(item[0] for item in pairs) / len(pairs)
        sla = pairs[0][1]
        rows.append({
            "supplier": name,
            "mean_hours": round(mean, 1),
            "sla_hours": sla,
            "violations": sum(1 for hours, limit in pairs if hours > limit),
            "notice": f"{name} atendeu em {mean:.1f} h, acima das {sla} h do contrato." if mean > sla else f"{name} dentro do contrato ({mean:.1f} h de {sla} h).",
        })
    rows.sort(key=lambda item: item["violations"], reverse=True)
    return rows


def _problems(data: dict, moment: datetime) -> list[dict]:
    since = moment - timedelta(days=90)
    rows = []
    for eq in data.get("equipment") or []:
        count = 0
        for order in data.get("orders") or []:
            if order.get("equipment_id") != eq["id"] or order.get("kind") != "corretiva":
                continue
            opened = order.get("opened_at")
            if opened and model.parse_iso(opened) >= since:
                count += 1
        if count < 3 and (eq.get("repair_cost") or 0) < (eq.get("replacement_cost") or 1):
            continue
        replace = (eq.get("repair_cost") or 0) >= (eq.get("replacement_cost") or 1)
        rows.append({
            "id": eq["id"],
            "serial": eq.get("serial"),
            "repairs": count,
            "repair_cost": eq.get("repair_cost") or 0,
            "replacement_cost": eq.get("replacement_cost") or 0,
            "advice": "Trocar" if replace else "Continuar consertando",
            "why": f"Reparo acumulado R$ {eq.get('repair_cost') or 0} contra troca de R$ {eq.get('replacement_cost') or 0}. {count} corretiva(s) em 90 dias.",
        })
    return rows


def _seed_resolutions(data: dict, moment: datetime) -> None:
    sample = [eq for eq in data.get("equipment") or [] if eq.get("type") in ("radar", "camera")][:4]
    data.setdefault("resolutions", [])
    data.setdefault("orders", [])
    for index, eq in enumerate(sample):
        opened = moment - timedelta(days=20 + index, hours=6)
        closed = opened + timedelta(hours=30 if index == 0 else 3)
        number = data["meta"].get("next_order", 1)
        data["meta"]["next_order"] = number + 1
        data["orders"].append({
            "id": f"OS-{number}",
            "number": f"OS-{number:04d}",
            "equipment_id": eq["id"],
            "serial": eq.get("serial"),
            "region": eq.get("region"),
            "street": eq.get("street"),
            "lat": eq.get("lat"),
            "lng": eq.get("lng"),
            "kind": "corretiva",
            "priority": "alta",
            "description": "Histórico para diagnóstico.",
            "status": "concluida",
            "opened_at": model.iso(opened),
            "closed_at": model.iso(closed),
            "due_at": model.iso(opened + timedelta(hours=24)),
            "resolution": "Fonte queimada" if index == 0 else "Conector oxidado",
            "parts": ["fonte 12V"] if index == 0 else ["conector"],
            "events": [],
        })
        data["resolutions"].append({
            "type": eq.get("type"),
            "supplier": SUPPLIERS[index % len(SUPPLIERS)],
            "firmware": ("fw-1.2", "fw-2.0", "fw-3.1")[index % 3],
            "event": "falha",
            "cause": "Fonte queimada" if index == 0 else "Conector oxidado",
            "remote": "Reiniciar o rádio antes de sair.",
            "parts": ["fonte 12V"] if index == 0 else ["conector"],
        })
        if index == 0:
            eq["supplier"] = "Sinal Norte"
            eq["contract_sla_hours"] = 4
            eq["repair_cost"] = 18000
            eq["replacement_cost"] = 12000


def _escalate(data: dict, agent: dict, moment: datetime, reason: str) -> dict[str, Any]:
    agent["safety_escalated"] = True
    near = sorted(data.get("agents") or [], key=lambda item: optimizer.haversine_km(agent["lat"], agent["lng"], item["lat"], item["lng"]))
    names = [item["name"] for item in near if item["id"] != agent["id"]][:3]
    alert = {
        "id": f"SEG-{len(data.get('safety_alerts') or []) + 1}",
        "agent_id": agent["id"],
        "agent": agent["name"],
        "region": agent.get("region"),
        "lat": agent.get("lat"),
        "lng": agent.get("lng"),
        "reason": reason,
        "nearest": names,
        "at": model.iso(moment),
    }
    data.setdefault("safety_alerts", []).insert(0, alert)
    model.push_feed(data, "critico", f"Segurança: {agent['name']} sem resposta. Próximos: {', '.join(names) or 'sem outra equipe'}.", agent.get("region") or "", moment)
    return {"message": f"Alerta crítico para o supervisor. {agent['name']} em {agent.get('region')}. Mais próximos: {', '.join(names) or 'ninguém'}."}


def _expected(kind: str | None, hour: int) -> float:
    base = {"radar": 40, "camera": 12, "balanca": 6}.get(kind or "", 2)
    rush = 1.8 if hour in (7, 8, 9, 17, 18, 19) else 0.7 if hour < 6 or hour >= 22 else 1
    return round(base * rush, 1)


def _expected_now(eq: dict, moment: datetime) -> float:
    hours = eq.get("baseline_hour") or []
    if len(hours) == 24:
        value = hours[moment.hour]
    else:
        value = _expected(eq.get("type"), moment.hour)
    if moment.weekday() >= 5:
        value = round(value * 0.7, 1)
    return value


def _blank_impact() -> dict[str, Any]:
    return {
        "trips_avoided": 0,
        "orders_consolidated": 0,
        "km_saved": 0,
        "blind_hours": 0,
        "coverage_pct": 0,
    }


def diagnosis_for(data: dict, equipment_id: str) -> dict[str, Any]:
    eq = model._must(data["equipment"], equipment_id, "Equipamento")
    signature = {"type": eq.get("type"), "supplier": eq.get("supplier"), "firmware": eq.get("firmware"), "event": "falha"}
    found = similar_cases(signature, data.get("resolutions") or [])
    top = found[0] if found else None
    return {
        "serial": eq.get("serial"),
        "cause": top["cause"] if top else "Sem caso parecido no histórico.",
        "remote": top["remote"] if top else "Não há tentativa remota sugerida.",
        "parts": top["parts"] if top else [],
        "method": "A semelhança soma tipo, fornecedor, firmware e tipo de evento. Não é um modelo treinado.",
    }
