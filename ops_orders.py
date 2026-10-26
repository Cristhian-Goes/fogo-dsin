"""Ordens de serviço do inventário. Não altera o número do esquema."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import model

KINDS = ("corretiva", "preventiva", "instalacao", "recolhimento")
STATUSES = ("aberta", "atribuida", "em_execucao", "concluida", "cancelada")
PRIORITIES = ("critica", "alta", "media", "baixa")
SLA_HOURS = {"critica": 4, "alta": 24, "media": 72, "baixa": 24 * 7}
OPEN = {"aberta", "atribuida", "em_execucao"}


def present(order: dict, moment: datetime) -> dict[str, Any]:
    out = dict(order)
    due = model.parse_iso(order["due_at"])
    left = int((due - moment).total_seconds())
    out["seconds_left"] = left
    out["overdue"] = left < 0 and order["status"] in OPEN
    out["events"] = list(order.get("events") or [])[:12]
    return out


def present_all(data: dict, moment: datetime | None = None) -> list[dict]:
    moment = moment or model.now_local()
    return [present(item, moment) for item in data.get("orders") or []]


def reconcile(data: dict, moment: datetime) -> None:
    data.setdefault("orders", [])
    data["meta"].setdefault("next_order", 1)
    today = moment.date()
    for eq in data.get("equipment") or []:
        if _open_for(data, eq["id"]):
            continue
        if eq.get("status") in ("mau_funcionamento", "furtado"):
            kind = "recolhimento" if eq["status"] == "furtado" else "corretiva"
            priority = "critica" if eq["status"] == "furtado" else "alta"
            _open(data, eq, kind, priority, f"{eq['serial']} está {eq['status'].replace('_', ' ')}.", moment, "sistema")
            continue
        flag = model.maintenance_flag(eq, today)
        if flag in ("imediata", "atrasada"):
            _open(data, eq, "preventiva", "alta" if flag == "imediata" else "media", "Manutenção vencida ou imediata.", moment, "sistema")


def create(data: dict, payload: dict, moment: datetime, actor: str) -> dict[str, Any]:
    eq = model._must(data["equipment"], str(payload.get("equipment_id") or ""), "Equipamento")
    if _open_for(data, eq["id"]):
        raise model.Invalid(f"Já existe OS aberta para {eq['serial']}.")
    kind = model._choice(payload.get("kind") or "corretiva", "o tipo", list(KINDS))
    priority = model._choice(payload.get("priority") or "alta", "a prioridade", list(PRIORITIES))
    description = model._clean_text(payload.get("description"), "a descrição", 400)
    order = _open(data, eq, kind, priority, description, moment, actor)
    return {"item": present(order, moment), "message": f"{order['number']} aberta para {eq['serial']}.", "focus": {"kind": "order", "id": order["id"]}}


def assign(data: dict, order_id: str, agent_id: str | None, moment: datetime, actor: str) -> dict[str, Any]:
    order = model._must(data.setdefault("orders", []), order_id, "Ordem de serviço")
    if order["status"] in ("concluida", "cancelada"):
        raise model.Invalid("Esta OS já foi encerrada.")
    agent = _agent(data, agent_id) if agent_id else _nearest(data, order)
    if agent is None:
        raise model.Invalid("Não há técnico disponível para esta OS.")
    order["agent_id"] = agent["id"]
    order["agent_name"] = agent["name"]
    order["status"] = "atribuida"
    order["updated_at"] = model.iso(moment)
    _event(order, moment, f"{actor} atribuiu a OS a {agent['name']}.")
    return {"item": present(order, moment), "message": f"{order['number']} atribuída a {agent['name']}.", "focus": {"kind": "order", "id": order["id"]}}


def advance(data: dict, order_id: str, status: str, note: str, moment: datetime, actor: str) -> dict[str, Any]:
    order = model._must(data.setdefault("orders", []), order_id, "Ordem de serviço")
    status = model._choice(status, "o status", list(STATUSES))
    if order["status"] in ("concluida", "cancelada"):
        raise model.Invalid("Esta OS já foi encerrada.")
    if status == "em_execucao" and not order.get("agent_id"):
        raise model.Invalid("Atribua um responsável antes de iniciar.")
    order["status"] = status
    order["updated_at"] = model.iso(moment)
    if note:
        order["notes"] = model._clean_text(note, "a observação", 400, required=False)
    if status == "concluida":
        order["closed_at"] = model.iso(moment)
        _restore(data, order, moment)
    if status == "cancelada":
        order["closed_at"] = model.iso(moment)
    _event(order, moment, f"{actor} mudou a OS para {status}." + (f" {order.get('notes')}" if note else ""))
    return {"item": present(order, moment), "message": f"{order['number']} está {status.replace('_', ' ')}.", "focus": {"kind": "order", "id": order["id"]}}


def pdf(data: dict, order_id: str, moment: datetime) -> bytes:
    order = present(model._must(data.get("orders") or [], order_id, "Ordem de serviço"), moment)
    lines = [
        f"F.O.G.O.  Ordem de servico {order['number']}",
        f"Equipamento: {order.get('serial')}  {order.get('street')}",
        f"Regiao: {order.get('region') or '-'}",
        f"Tipo: {order['kind']}   Prioridade: {order['priority']}",
        f"Status: {order['status']}",
        f"Responsavel: {order.get('agent_name') or 'nao atribuida'}",
        f"Aberta: {order['opened_at']}",
        f"Limite: {order['due_at']}",
        f"Descricao: {order.get('description') or '-'}",
        "",
        "Historico",
    ]
    for event in (order.get("events") or [])[:8]:
        lines.append(f"- {event.get('at', '')[:16]}  {event.get('text', '')}")
    return _pdf(lines)


def _open(data: dict, eq: dict, kind: str, priority: str, description: str, moment: datetime, actor: str) -> dict:
    data.setdefault("orders", [])
    data["meta"].setdefault("next_order", 1)
    number = data["meta"]["next_order"]
    data["meta"]["next_order"] = number + 1
    agent = _nearest(data, {"lat": eq.get("lat"), "lng": eq.get("lng")})
    order = {
        "id": f"OS-{number}",
        "number": f"OS-{number:04d}",
        "equipment_id": eq["id"],
        "serial": eq.get("serial"),
        "region": eq.get("region"),
        "street": eq.get("street"),
        "lat": eq.get("lat"),
        "lng": eq.get("lng"),
        "kind": kind,
        "priority": priority,
        "description": description,
        "status": "atribuida" if agent else "aberta",
        "agent_id": agent["id"] if agent else None,
        "agent_name": agent["name"] if agent else None,
        "opened_at": model.iso(moment),
        "due_at": model.iso(moment + timedelta(hours=SLA_HOURS[priority])),
        "closed_at": None,
        "updated_at": model.iso(moment),
        "notes": "",
        "events": [],
    }
    who = agent["name"] if agent else "ninguém disponível"
    _event(order, moment, f"{actor} abriu a OS. Sugestão de responsável: {who}.")
    data["orders"].insert(0, order)
    data["orders"] = data["orders"][:200]
    model.push_feed(data, "atencao", f"{order['number']} aberta para {eq.get('serial')}.", eq.get("region") or "", moment)
    if priority == "critica" and data.get("day_plan"):
        try:
            note = __import__("ops_dayroutes").insert_order(data, order, moment)
            if note:
                order.setdefault("events", []).insert(0, {"at": model.iso(moment), "text": note})
        except model.Invalid:
            pass
    return order


def _restore(data: dict, order: dict, moment: datetime) -> None:
    eq = next((item for item in data["equipment"] if item["id"] == order["equipment_id"]), None)
    if not eq or eq.get("status") == "furtado":
        return
    eq["status"] = "operacional"
    eq["maintenance_need"] = "agendada"
    eq["next_maintenance"] = (moment.date() + timedelta(days=90)).isoformat()
    eq["updated_at"] = model.iso(moment)
    eq["last_seen"] = model.iso(moment)
    eq.setdefault("history", []).insert(0, {"at": model.iso(moment), "text": f"{order['number']} concluída. Equipamento operacional e revisão em 90 dias."})
    del eq["history"][12:]


def _open_for(data: dict, equipment_id: str) -> dict | None:
    return next((item for item in data.get("orders") or [] if item["equipment_id"] == equipment_id and item["status"] in OPEN), None)


def _agent(data: dict, agent_id: str) -> dict:
    agent = model._must(data["agents"], agent_id, "Agente")
    if agent.get("status") == "fora_de_servico":
        raise model.Invalid(f"{agent['name']} está fora de serviço.")
    return agent


def _nearest(data: dict, order: dict) -> dict | None:
    if order.get("lat") is None:
        return None
    best = None
    best_m = None
    for agent in data.get("agents") or []:
        if agent.get("status") not in ("em_atividade", "em_deslocamento"):
            continue
        meters = model._haversine(order["lat"], order["lng"], agent["lat"], agent["lng"])
        if best_m is None or meters < best_m:
            best, best_m = agent, meters
    return best


def _event(order: dict, moment: datetime, text: str) -> None:
    order.setdefault("events", []).insert(0, {"at": model.iso(moment), "text": text})
    order["events"] = order["events"][:20]


def _plain(text: str) -> str:
    folded = str(text).translate(str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
        "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN",
    ))
    return folded.replace("\\", " ").replace("(", " ").replace(")", " ")[:90]


def _pdf(lines: list[str]) -> bytes:
    safe = [_plain(line) for line in lines]
    commands = ["BT", "/F1 12 Tf", "50 800 Td"]
    for index, line in enumerate(safe):
        if index:
            commands.append("0 -18 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{number} 0 obj\n".encode())
        body.extend(obj)
        body.extend(b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode())
    body.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(body)
