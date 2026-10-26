"""Aferição parametrizável. Os prazos da tela não substituem a legislação."""

from __future__ import annotations

from datetime import date, datetime, timedelta

CALIBRATED = {"radar", "balanca"}
NOTE = (
    "As regras reais de aferição devem ser confirmadas com a legislação e o órgão competente. "
    "Os prazos deste sistema são parametrizáveis."
)


def due_date(eq: dict) -> date | None:
    raw = str(eq.get("validade_afericao") or "")[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def bucket(eq: dict, today: date, windows: list[int] | None = None) -> str:
    if eq.get("type") not in CALIBRATED:
        return ""
    due = due_date(eq)
    if due is None:
        return ""
    windows = windows or [30, 15, 7]
    delta = (due - today).days
    if delta < 0:
        return "vencida"
    for limit in sorted(windows):
        if delta <= limit:
            return f"{limit}"
    return "ok"


def annotate(eq: dict, today: date) -> bool:
    return bucket(eq, today) == "vencida"


def panel(data: dict, moment: datetime) -> dict:
    today = moment.date() if isinstance(moment, datetime) else moment
    windows = list((data.get("value_settings") or {}).get("janelas_afericao_dias") or [30, 15, 7])
    rate = float((data.get("value_settings") or {}).get("autuacao_por_vencido") or 0.4)
    rows = []
    expired = 0
    for eq in data.get("equipment") or []:
        state = bucket(eq, today, windows)
        if not state or state == "ok":
            continue
        if state == "vencida":
            expired += 1
        rows.append({
            "id": eq.get("id"),
            "serial": eq.get("serial"),
            "type": eq.get("type"),
            "region": eq.get("region"),
            "validade_afericao": eq.get("validade_afericao"),
            "orgao": eq.get("orgao_certificador") or "",
            "bucket": state,
            "fora_de_conformidade": state == "vencida",
        })
    order = {"vencida": 0, "7": 1, "15": 2, "30": 3}
    rows.sort(key=lambda item: (order.get(item["bucket"], 9), item["serial"] or ""))
    citations = int(round(expired * rate))
    return {
        "rows": rows,
        "expired": expired,
        "citations": citations,
        "windows": windows,
        "note": NOTE,
        "method": "A lista usa a data de validade do cadastro. A autuação é simulada: quantidade vencida vezes a taxa parametrizável.",
    }
