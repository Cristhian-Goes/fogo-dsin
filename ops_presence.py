"""Prova de presença no fechamento da OS. Distância por haversine."""

from __future__ import annotations

from datetime import datetime


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import model
    return float(model._haversine(lat1, lng1, lat2, lng2))


def review(order: dict, equipment: dict | None, proof: dict, settings: dict, moment: datetime) -> dict:
    import model

    radius = float(settings.get("raio_presenca_m") or 150)
    minimums = settings.get("tempo_minimo_min") or {}
    kind = order.get("kind") or "corretiva"
    minimum = float(minimums.get(kind) or 20)
    reasons = []
    fields: dict = {
        "custo_mao_de_obra": float(proof.get("custo_mao_de_obra") or order.get("custo_mao_de_obra") or 0),
        "custo_pecas": float(proof.get("custo_pecas") or order.get("custo_pecas") or 0),
        "custo_deslocamento": float(proof.get("custo_deslocamento") or order.get("custo_deslocamento") or 0),
    }
    lat = _num(proof.get("checkin_lat"))
    lng = _num(proof.get("checkin_lng"))
    if lat is None or lng is None:
        reasons.append("sem check-in")
    else:
        fields["checkin"] = {"lat": lat, "lng": lng, "at": model.iso(moment)}
        if equipment and equipment.get("lat") is not None:
            meters = distance_m(lat, lng, equipment["lat"], equipment["lng"])
            fields["checkin"]["metros"] = round(meters, 1)
            if meters > radius:
                reasons.append(f"fora do raio ({round(meters)} m, limite {int(radius)} m)")
    before = str(proof.get("foto_antes") or "").strip()
    after = str(proof.get("foto_depois") or "").strip()
    if before:
        fields["foto_antes"] = before[:80]
    if after:
        fields["foto_depois"] = after[:80]
    if not before or not after:
        reasons.append("sem foto antes e depois")
    started = order.get("started_at")
    if not started:
        reasons.append("sem início registrado")
        minutes = 0.0
    else:
        minutes = (moment - model.parse_iso(started)).total_seconds() / 60
        if minutes < minimum:
            reasons.append(f"tempo curto ({int(minutes)} min, mínimo {int(minimum)} min)")
    fields["minutos_no_local"] = round(minutes, 1)
    fields["checkout"] = {"at": model.iso(moment)}
    tip = str(proof.get("dica") or "").strip()
    if tip:
        fields["dica_do_tecnico"] = tip[:180]
    return {
        "conclusao": "valida" if not reasons else "suspeita",
        "motivos": reasons,
        "fields": fields,
        "raio_m": radius,
        "minimo_min": minimum,
    }


def kpi(orders: list[dict]) -> dict:
    closed = [item for item in orders if item.get("status") == "concluida"]
    valid = [item for item in closed if item.get("conclusao") == "valida"]
    suspect = [item for item in closed if item.get("conclusao") == "suspeita"]
    percent = round(100 * len(valid) / len(closed), 1) if closed else 0.0
    return {
        "closed": len(closed),
        "valid": len(valid),
        "suspect": len(suspect),
        "percent": percent,
        "method": "Válida quando há check-in dentro do raio, foto antes e depois e tempo mínimo do tipo.",
    }


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
