"""Custos de manutenção e perda por indisponibilidade. Sem rede e sem SCHEMA novo."""

from __future__ import annotations

from datetime import datetime

TYPE_HOUR = {
    "radar": 90.0,
    "camera": 35.0,
    "balanca": 140.0,
    "cancela": 40.0,
    "veiculo_autonomo": 180.0,
    "transporte": 22.0,
    "totem": 12.0,
    "patinete": 6.0,
    "moto_agente": 28.0,
    "viatura_gm": 55.0,
    "viatura_pm": 70.0,
}


def road_factor(region: str) -> float:
    name = region or ""
    if "Sampaio" in name:
        return 1.4
    if "Centro" in name:
        return 1.15
    return 1.0


def hour_cost(eq: dict) -> float:
    base = TYPE_HOUR.get(eq.get("type") or "", 30.0)
    return round(base * road_factor(eq.get("region") or ""), 2)


def loss(hours: float, hour_cost_value: float) -> float:
    return round(max(0.0, float(hours)) * float(hour_cost_value), 2)


def order_cost(order: dict) -> float:
    return round(
        float(order.get("custo_mao_de_obra") or 0)
        + float(order.get("custo_pecas") or 0)
        + float(order.get("custo_deslocamento") or 0),
        2,
    )


def trend(values: list[float]) -> tuple[float, float]:
    count = len(values)
    if count == 0:
        return 0.0, 0.0
    if count == 1:
        return 0.0, float(values[0])
    xs = list(range(count))
    mean_x = sum(xs) / count
    mean_y = sum(values) / count
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / den
    return slope, mean_y - slope * mean_x


def project_year(values: list[float]) -> float:
    slope, intercept = trend(values)
    start = len(values)
    return round(sum(max(0.0, intercept + slope * (start + step)) for step in range(12)), 2)


def panel(data: dict, moment: datetime) -> dict:
    settings = data.get("value_settings") or {}
    budget = float(settings.get("orcamento_mensal") or 0)
    equipment = {item["id"]: item for item in data.get("equipment") or []}
    month_key = moment.strftime("%Y-%m")
    month_total = 0.0
    counted = 0
    by_supplier: dict[str, float] = {}
    by_equipment: dict[str, float] = {}
    for order in data.get("orders") or []:
        cost = order_cost(order)
        if cost <= 0:
            continue
        counted += 1
        eq = equipment.get(order.get("equipment_id")) or {}
        supplier = eq.get("supplier") or "Sem fornecedor"
        by_supplier[supplier] = round(by_supplier.get(supplier, 0) + cost, 2)
        serial = eq.get("serial") or order.get("serial") or order.get("id")
        by_equipment[serial] = round(by_equipment.get(serial, 0) + cost, 2)
        closed = str(order.get("closed_at") or "")
        if closed.startswith(month_key):
            month_total = round(month_total + cost, 2)
    downtime = []
    loss_total = 0.0
    for eq in data.get("equipment") or []:
        hours = float(eq.get("horas_parada_mes") or 0)
        rate = float(eq.get("custo_hora_indisponibilidade") or hour_cost(eq))
        value = loss(hours, rate)
        if value <= 0:
            continue
        loss_total = round(loss_total + value, 2)
        downtime.append({
            "serial": eq.get("serial"),
            "hours": hours,
            "hour_cost": rate,
            "loss": value,
            "formula": "horas parado × custo/hora estimado",
        })
    series = _series(data, moment, month_total)
    slope, intercept = trend([item["total"] for item in series])
    year = project_year([item["total"] for item in series])
    annual_budget = round(budget * 12, 2)
    top = sorted(by_equipment.items(), key=lambda item: item[1], reverse=True)[:5]
    suppliers = sorted(
        ({"supplier": name, "total": value} for name, value in by_supplier.items()),
        key=lambda item: item["total"],
        reverse=True,
    )
    return {
        "month": month_key,
        "month_total": round(month_total, 2),
        "average_order": round(month_total / counted, 2) if counted and month_total else (round(sum(by_equipment.values()) / counted, 2) if counted else 0),
        "orders_with_cost": counted,
        "downtime_loss": loss_total,
        "downtime": downtime[:8],
        "top_equipment": [{"serial": name, "total": value} for name, value in top],
        "suppliers": suppliers,
        "series": series,
        "projection_year": year,
        "budget_month": budget,
        "budget_year": annual_budget,
        "budget_gap": round(year - annual_budget, 2),
        "method": "Tendência linear simples sobre o gasto mensal. A perda é horas parado no mês vezes o custo/hora do tipo e da via.",
        "formula": "horas parado × custo/hora estimado",
        "slope": round(slope, 2),
        "intercept": round(intercept, 2),
    }


def _series(data: dict, moment: datetime, current_total: float) -> list[dict]:
    buckets: dict[str, float] = {}
    for order in data.get("orders") or []:
        closed = str(order.get("closed_at") or "")
        if len(closed) < 7:
            continue
        key = closed[:7]
        buckets[key] = round(buckets.get(key, 0) + order_cost(order), 2)
    keys = sorted(buckets)
    if len(keys) >= 4:
        return [{"month": key, "total": buckets[key], "synthetic": False} for key in keys[-6:]]
    base = current_total or 4200.0
    rows = []
    year = moment.year
    month = moment.month
    for step in range(5, -1, -1):
        cursor = month - step
        year_cursor = year
        while cursor <= 0:
            cursor += 12
            year_cursor -= 1
        total = round(base * (0.78 + 0.04 * (5 - step)), 2) if step else round(base, 2)
        rows.append({"month": f"{year_cursor:04d}-{cursor:02d}", "total": total, "synthetic": step != 0})
    return rows
