"""Consulta operacional. Com chave, usa o modelo configurado. Sem chave, responde por regras."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any

import model
import ops_orders


def reply(data: dict, message: str, moment: datetime, confirm: bool = False) -> dict[str, Any]:
    text = " ".join((message or "").split())
    if len(text) < 2:
        raise model.Invalid("Escreva a pergunta.")
    local = _local(data, text, moment, confirm)
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key or local.get("confirm"):
        local["mode"] = "local"
        return local
    try:
        phrased = _remote(text, local["reply"])
        local["reply"] = phrased
        local["mode"] = "modelo"
        return local
    except Exception:
        local["mode"] = "local"
        local["reply"] += " A chave de IA não respondeu. Esta resposta veio das regras locais."
        return local


def briefing(data: dict, moment: datetime) -> dict[str, Any]:
    kpis = model.kpis(data)
    alerts = [item for item in model.derive_alerts(data, moment) if item.get("level") == "critico"][:5]
    orders = [item for item in ops_orders.present_all(data, moment) if item["status"] not in ("concluida", "cancelada")]
    late = [item for item in orders if item["overdue"]][:5]
    preview = model.predictions(data, moment)
    tips = [item["title"] for item in preview["recommendations"][:3]]
    lines = [
        f"Turno de {moment.strftime('%d/%m %H:%M')}.",
        f"Inventário: {kpis['operational']} operacionais de {kpis['total']}. Disponibilidade {model.fmt_num(kpis['availability_pct'])}%. Agentes em atividade: {kpis['agents_active']}.",
        f"OS abertas: {len(orders)}. SLA estourado: {len(late)}.",
    ]
    if alerts:
        lines.append("Alertas críticos: " + "; ".join(item["title"] for item in alerts) + ".")
    else:
        lines.append("Nenhum alerta crítico neste instante.")
    if tips:
        lines.append("Recomendações: " + "; ".join(tips) + ".")
    if late:
        lines.append("OS vencidas: " + ", ".join(item["number"] for item in late) + ".")
    return {"text": " ".join(lines), "mode": "modelo local"}


def _local(data: dict, text: str, moment: datetime, confirm: bool) -> dict[str, Any]:
    folded = text.lower()
    if "fornecedor" in folded and "relat" in folded:
        return {"reply": __import__("ops_gestao").report_text(data, moment, "fornecedor"), "targets": []}
    if "custo" in folded and any(word in folded for word in ("periodo", "período", "mes", "mês", "relat")):
        return {"reply": __import__("ops_gestao").report_text(data, moment, "custo"), "targets": []}
    if "sla" in folded and "equipe" in folded:
        return {"reply": __import__("ops_gestao").report_text(data, moment, "sla"), "targets": []}
    if any(word in folded for word in ("resumo", "briefing", "turno")):
        pack = briefing(data, moment)
        return {"reply": pack["text"], "targets": []}
    if folded.startswith("abre") or folded.startswith("abrir") or "abre uma os" in folded or "abrir os" in folded:
        eq = _match_equipment(data, folded)
        if eq is None:
            return {"reply": "Não achei o equipamento. Diga a série ou a rua.", "targets": []}
        if not confirm:
            return {
                "reply": f"Posso abrir uma OS corretiva alta para {eq['serial']} em {eq.get('street')}. Confirme para gravar.",
                "confirm": {"equipment_id": eq["id"]},
                "targets": [{"kind": "equipment", "id": eq["id"], "label": eq["serial"]}],
            }
        created = ops_orders.create(data, {"equipment_id": eq["id"], "kind": "corretiva", "priority": "alta", "description": text}, moment, "Chat")
        return {"reply": created["message"], "targets": [{"kind": "equipment", "id": eq["id"], "label": eq["serial"]}]}
    region = _match_region(folded)
    if region:
        board = next((item for item in model.region_board(data, model.city_index(data, moment, [])["regions"]) if item["region"] == region), None)
        if board:
            return {
                "reply": f"{region}: {board['state_label']}. {board['incidents_open']} ocorrência(s) aberta(s), {board['agents_free']} equipe(s) livre(s), {board['equipment_down']} equipamento(s) fora.",
                "targets": [{"kind": "region", "id": region, "label": region}],
            }
    if any(word in folded for word in ("crít", "crit", "alerta")):
        alerts = [item for item in model.derive_alerts(data, moment) if item.get("level") in ("critico", "alto")][:5]
        if not alerts:
            return {"reply": "Não há alerta crítico nem alto neste instante.", "targets": []}
        return {
            "reply": " ".join(f"{item['title']}." for item in alerts),
            "targets": [{"kind": item.get("target_type") or "region", "id": item.get("target_id") or item.get("region") or "", "label": item["title"]} for item in alerts if item.get("target_id") or item.get("region")],
        }
    if any(word in folded for word in ("previs", "refor", "amanh")):
        recs = model.predictions(data, moment)["recommendations"][:3]
        if not recs:
            return {"reply": "A previsão não pediu reforço neste recorte.", "targets": []}
        return {
            "reply": " ".join(item["title"] + "." for item in recs),
            "targets": [{"kind": "region", "id": item.get("region") or "", "label": item["title"]} for item in recs if item.get("region")],
        }
    kpis = model.kpis(data)
    return {
        "reply": f"Posso resumir o turno, listar o que está crítico, abrir uma OS, olhar a previsão ou montar o relatório de custo, de fornecedor e de SLA de equipes. Agora: {kpis['operational']} equipamentos operacionais e {kpis['agents_active']} agentes em atividade.",
        "targets": [],
    }


def _match_region(text: str) -> str | None:
    for name in model.REGIONS:
        if name.lower() in text:
            return name
    return None


def _match_equipment(data: dict, text: str) -> dict | None:
    for eq in data["equipment"]:
        if eq["serial"].lower() in text or (eq.get("street") or "").lower() in text and len(eq.get("street") or "") > 4:
            return eq
    return None


def _remote(question: str, facts: str) -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _anthropic(question, facts)
    return _openai(question, facts)


def _anthropic(question: str, facts: str) -> str:
    payload = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        "max_tokens": 400,
        "system": "Você resume a operação em português, curto, só com os fatos recebidos. Não invente número.",
        "messages": [{"role": "user", "content": f"Pergunta: {question}\nFatos:\n{facts}"}],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = json.loads(response.read().decode())
    parts = [block.get("text", "") for block in body.get("content") or [] if block.get("type") == "text"]
    return " ".join(parts).strip() or facts


def _openai(question: str, facts: str) -> str:
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": "Resuma a operação em português, curto, só com os fatos. Não invente número."},
            {"role": "user", "content": f"Pergunta: {question}\nFatos:\n{facts}"},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = json.loads(response.read().decode())
    return body["choices"][0]["message"]["content"].strip()
