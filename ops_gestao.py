"""Camada de valor para gestão. Preenche campos faltantes sem trocar o esquema."""

from __future__ import annotations

from datetime import datetime, timedelta

import ops_compliance
import ops_finance
import ops_intel
import ops_ledger
import ops_memory
import ops_orders
import ops_presence
import ops_staffing

LIFE = {
    "radar": 8, "camera": 7, "balanca": 10, "cancela": 12, "veiculo_autonomo": 6,
    "transporte": 8, "totem": 6, "patinete": 4, "moto_agente": 5, "viatura_gm": 8, "viatura_pm": 8,
}
TIPS = (
    "Conferir a vedação antes de fechar a caixa.",
    "Levar fonte reserva quando o sintoma é apagão.",
    "Fotografar o conector oxidado para o fornecedor.",
    "Reiniciar o rádio e esperar dois minutos antes de trocar peça.",
)
CONTRACTS = (
    ("Sinal Norte", 180000, 4, 1500),
    ("Via Leste", 96000, 24, 400),
    ("Ótica Centro", 72000, 24, 350),
    ("Peso Certo", 110000, 12, 700),
)


def settings_of(data: dict) -> dict:
    base = {
        "orcamento_mensal": 28000,
        "raio_presenca_m": 150,
        "tempo_minimo_min": {"corretiva": 20, "preventiva": 30, "instalacao": 45, "recolhimento": 25, "afericao": 20},
        "janelas_afericao_dias": [30, 15, 7],
        "autuacao_por_vencido": 0.4,
        "espera_sla_min": 60,
    }
    current = dict(data.get("value_settings") or {})
    for key, value in base.items():
        current.setdefault(key, value)
    return current


def ensure(data: dict, moment: datetime) -> bool:
    changed = False
    settings = settings_of(data)
    if data.get("value_settings") != settings:
        data["value_settings"] = settings
        changed = True
    if not data.get("contracts"):
        data["contracts"] = [
            {"id": f"CT-{index + 1}", "supplier": name, "valor": value, "sla_horas": sla, "multa": fine}
            for index, (name, value, sla, fine) in enumerate(CONTRACTS)
        ]
        changed = True
    today = moment.date()
    for index, eq in enumerate(data.get("equipment") or []):
        if "custo_hora_indisponibilidade" not in eq:
            eq["custo_hora_indisponibilidade"] = ops_finance.hour_cost(eq)
            changed = True
        if "vida_util_anos" not in eq:
            eq["vida_util_anos"] = LIFE.get(eq.get("type"), 8)
            changed = True
        if eq.get("type") in ops_compliance.CALIBRATED and not eq.get("validade_afericao"):
            slot = index % 7
            if slot == 0:
                delta = -12
            elif slot == 1:
                delta = 5
            elif slot == 2:
                delta = 12
            elif slot == 3:
                delta = 22
            else:
                delta = 160
            eq["validade_afericao"] = (today + timedelta(days=delta)).isoformat()
            eq["orgao_certificador"] = "INMETRO"
            changed = True
        if "horas_parada_mes" not in eq:
            if eq.get("status") == "operacional":
                eq["horas_parada_mes"] = 0
            else:
                eq["horas_parada_mes"] = 8 + (sum(ord(char) for char in eq.get("id") or "x") % 29)
            changed = True
        if not eq.get("supplier"):
            eq["supplier"] = ops_intel.SUPPLIERS[index % len(ops_intel.SUPPLIERS)]
            changed = True
    for index, order in enumerate(data.get("orders") or []):
        if order.get("status") == "concluida" and "custo_mao_de_obra" not in order:
            order["custo_mao_de_obra"] = 160
            order["custo_pecas"] = 40 if index % 2 else 220
            order["custo_deslocamento"] = 45
            changed = True
        if order.get("status") == "concluida" and order.get("closed_at") and not order.get("minutos_no_local"):
            import model
            closed = model.parse_iso(order["closed_at"])
            minutes = 8 if index % 5 == 0 else 40
            order["started_at"] = model.iso(closed - timedelta(minutes=minutes))
            order["minutos_no_local"] = minutes
            changed = True
        if order.get("status") == "concluida" and "conclusao" not in order:
            order["started_at"] = order.get("started_at") or order.get("opened_at")
            order["checkin"] = {"lat": order.get("lat"), "lng": order.get("lng"), "at": order.get("closed_at"), "metros": 12}
            order["checkout"] = {"at": order.get("closed_at")}
            order["foto_antes"] = "registro-sintetico-antes"
            order["foto_depois"] = "registro-sintetico-depois"
            if index % 5 == 0:
                order["conclusao"] = "suspeita"
                order["motivos"] = ["tempo curto (demonstração)"]
            else:
                order["conclusao"] = "valida"
                order["motivos"] = []
            order["dica_do_tecnico"] = TIPS[index % len(TIPS)]
            changed = True
    for eq in data.get("equipment") or []:
        if ops_compliance.bucket(eq, today) != "vencida":
            continue
        if any(item.get("equipment_id") == eq["id"] and item.get("kind") == "afericao" and item.get("status") in ops_orders.OPEN for item in data.get("orders") or []):
            continue
        ops_orders._open(data, eq, "afericao", "media", "Aferição vencida. Confirmar o prazo com o órgão competente.", moment, "sistema")
        changed = True
    if not data.get("ledger"):
        ops_ledger.append(data, moment, "sistema", "carga da demonstração", "store", {"origem": "seed"})
        changed = True
    return changed


def snapshot(data: dict, moment: datetime) -> dict:
    finance = ops_finance.panel(data, moment)
    compliance = ops_compliance.panel(data, moment)
    presence = ops_presence.kpi(data.get("orders") or [])
    staff = ops_staffing.curve(data, moment, float((data.get("value_settings") or {}).get("espera_sla_min") or 60))
    return {
        "finance": finance,
        "compliance": compliance,
        "presence": presence,
        "staffing": staff,
        "knowledge": ops_memory.catalog(data),
        "suspects": [
            {
                "id": item.get("id"),
                "number": item.get("number"),
                "serial": item.get("serial"),
                "motivos": item.get("motivos") or [],
            }
            for item in data.get("orders") or []
            if item.get("conclusao") == "suspeita"
        ],
        "value": valor(data, moment, finance, compliance, presence, staff),
        "settings": settings_of(data),
    }


def valor(data: dict, moment: datetime, finance: dict | None = None, compliance: dict | None = None, presence: dict | None = None, staff: dict | None = None) -> dict:
    finance = finance or ops_finance.panel(data, moment)
    compliance = compliance or ops_compliance.panel(data, moment)
    presence = presence or ops_presence.kpi(data.get("orders") or [])
    staff = staff or ops_staffing.curve(data, moment)
    plan = data.get("day_plan") or {}
    saved = float(plan.get("saved_min") or 0)
    trip_value = round(max(0, saved) * 1.8, 2)
    fines = 0.0
    for contract in data.get("contracts") or []:
        name = contract.get("supplier")
        row = next((item for item in finance.get("suppliers") or [] if item["supplier"] == name), None)
        if not row:
            continue
        # A multa identificada usa o ranking já calculado na inteligência quando existir.
    vendor_rows = []
    try:
        vendor_rows = __import__("ops_intel")._vendors(data)
    except Exception:
        vendor_rows = []
    violations = sum(int(item.get("violations") or 0) for item in vendor_rows)
    fine_rate = 800
    if data.get("contracts"):
        fine_rate = int(data["contracts"][0].get("multa") or 800)
    fines = violations * fine_rate
    return {
        "trip_savings": trip_value,
        "saved_min": saved,
        "fines_identified": fines,
        "violations": violations,
        "expired_equipment": compliance.get("expired") or 0,
        "citations_simulated": compliance.get("citations") or 0,
        "presence_pct": presence.get("percent") or 0,
        "staff_recommendation": staff.get("sentence"),
        "budget_gap": finance.get("budget_gap"),
        "premises": "Valores estimados. A hora de rota evitada vale R$ 1,80 nesta premissa. A multa usa o valor do primeiro contrato. A autuação é simulada.",
        "method": "Soma premissas parametrizáveis sobre a rota do dia, os contratos e a aferição. Não é um laudo.",
    }


def emit(data: dict, event: str, payload: dict) -> None:
    import hashlib
    import hmac
    import json
    import urllib.request

    body = json.dumps({"event": event, "payload": payload}, ensure_ascii=False).encode("utf-8")
    for hook in data.get("webhooks") or []:
        if event not in (hook.get("events") or []):
            continue
        secret = str(hook.get("secret") or "").encode("utf-8")
        signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            hook.get("url") or "",
            data=body,
            headers={"Content-Type": "application/json", "X-FOGO-Signature": signature, "User-Agent": "FOGO-CCO/1.0"},
        )
        try:
            urllib.request.urlopen(request, timeout=2)
        except Exception:
            continue


def openapi() -> dict:
    paths = {
        "/api/health": {"get": {"summary": "Saúde do processo"}},
        "/api/session": {"post": {"summary": "Entrar com usuário e senha"}},
        "/api/bootstrap": {"get": {"summary": "Estado da central"}},
        "/api/orders": {"get": {"summary": "Listar OS"}, "post": {"summary": "Abrir OS"}},
        "/api/gestao": {"get": {"summary": "Painéis de custo, conformidade, equipe e valor"}},
        "/api/integridade": {"get": {"summary": "Verificar a cadeia de hash"}},
        "/api/webhooks": {"post": {"summary": "Cadastrar webhook com segredo HMAC"}},
        "/api/chat": {"post": {"summary": "Pergunta operacional ou relatório por palavra-chave"}},
    }
    return {
        "openapi": "3.0.3",
        "info": {"title": "F.O.G.O.", "version": "1", "description": "API local da central. Sessão no cabeçalho X-Session."},
        "paths": paths,
        "webhooks": {
            "os.criada": {"description": "OS aberta. Corpo assinado com HMAC-SHA256 em X-FOGO-Signature."},
            "alerta.critico": {"description": "Alerta crítico publicado na fita."},
        },
    }


def docs_html() -> str:
    spec = openapi()
    rows = "".join(f"<li><code>{method.upper()} {path}</code> — {item['summary']}</li>" for path, methods in spec["paths"].items() for method, item in methods.items())
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>F.O.G.O. · API</title>
<style>body{{font:16px/1.45 Segoe UI,sans-serif;margin:32px;color:#1c2430;max-width:760px}} code{{background:#f4f6f8;padding:2px 6px}}</style></head>
<body><h1>API da central</h1>
<p>O contrato em JSON está em <a href="/openapi.json">/openapi.json</a>. As rotas de escrita pedem o cabeçalho <code>X-Session</code>.</p>
<p>Webhooks cadastrados em <code>POST /api/webhooks</code> recebem <code>os.criada</code> e <code>alerta.critico</code>. A assinatura é HMAC-SHA256 do corpo, no cabeçalho <code>X-FOGO-Signature</code>.</p>
<ul>{rows}</ul>
<p>No chat, sem chave de IA, as frases "relatório de fornecedor", "custo do período" e "sla de equipes" devolvem o recorte já calculado.</p>
</body></html>"""


def report_text(data: dict, moment: datetime, kind: str) -> str:
    pack = snapshot(data, moment)
    if kind == "fornecedor":
        lines = ["Desempenho de fornecedor (estimado pelas OS com custo)."]
        for item in pack["finance"]["suppliers"][:6]:
            lines.append(f"{item['supplier']}: R$ {item['total']:.2f}")
        if not pack["finance"]["suppliers"]:
            lines.append("Ainda não há custo lançado por fornecedor.")
        return " ".join(lines)
    if kind == "custo":
        finance = pack["finance"]
        return (
            f"Custo de manutenção no mês {finance['month']}: R$ {finance['month_total']:.2f}. "
            f"Média por OS com custo: R$ {finance['average_order']:.2f}. "
            f"Perda por indisponibilidade: R$ {finance['downtime_loss']:.2f}. "
            f"Projeção linear do ano: R$ {finance['projection_year']:.2f} contra orçamento de R$ {finance['budget_year']:.2f}."
        )
    staff = pack["staffing"]
    return f"SLA de espera. {staff['sentence']} Chegadas estimadas: {staff['rate_per_hour']} por hora. Atendimento médio: {staff['service_min']} min."
