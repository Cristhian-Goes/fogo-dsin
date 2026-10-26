"""Janela de preventiva sem deixar a cobertura vizinha descoberta no pico."""

from __future__ import annotations

from datetime import datetime, timedelta

PEAKS = ((7, 9), (17, 19))


def in_peak(moment: datetime, peaks: tuple = PEAKS) -> bool:
    for start, end in peaks:
        if start <= moment.hour < end:
            return True
    return False


def suggest(data: dict, equipment: dict, moment: datetime) -> dict:
    conflicts = []
    region = equipment.get("region")
    for other in data.get("equipment") or []:
        if other.get("id") == equipment.get("id") or other.get("region") != region:
            continue
        if other.get("status") not in (None, "operacional", "desativado"):
            conflicts.append(f"{other.get('serial')} já está fora em {region}.")
    for order in data.get("orders") or []:
        if order.get("status") not in ("aberta", "atribuida", "em_execucao"):
            continue
        if order.get("region") == region and order.get("equipment_id") != equipment.get("id") and order.get("kind") == "preventiva":
            conflicts.append(f"{order.get('number')} já tira outro equipamento de {region}.")
    if in_peak(moment):
        conflicts.append("O horário pedido cai na janela de pico (7h–9h ou 17h–19h).")
    suggestion = moment
    if conflicts:
        suggestion = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        guard = 0
        while (in_peak(suggestion) or suggestion.hour < 8) and guard < 30:
            suggestion += timedelta(hours=1)
            guard += 1
    return {
        "ok": not conflicts,
        "conflicts": conflicts[:6],
        "suggestion": suggestion.strftime("%Y-%m-%d %H:%M"),
        "method": "Conflito se outro equipamento da mesma região está fora, se já há preventiva aberta ali, ou se o horário é pico.",
    }
