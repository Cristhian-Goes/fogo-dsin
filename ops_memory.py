"""Dicas de técnico. A relevância é a sobreposição de tipo e de palavras, não um modelo."""

from __future__ import annotations


def remember(order: dict, tip: str) -> None:
    text = " ".join(str(tip or "").split())
    if text:
        order["dica_do_tecnico"] = text[:180]


def search(data: dict, query: str = "", type_name: str = "", limit: int = 3) -> list[dict]:
    equipment = {item["id"]: item for item in data.get("equipment") or []}
    words = [part for part in query.lower().split() if len(part) > 2]
    scored = []
    for order in data.get("orders") or []:
        tip = str(order.get("dica_do_tecnico") or "").strip()
        if not tip:
            continue
        eq = equipment.get(order.get("equipment_id")) or {}
        score = 0
        if type_name and eq.get("type") == type_name:
            score += 3
        if type_name and (eq.get("model") or "").lower() == type_name.lower():
            score += 4
        blob = f"{tip} {order.get('description') or ''} {eq.get('model') or ''} {eq.get('type') or ''}".lower()
        score += sum(1 for word in words if word in blob)
        if not words and not type_name:
            score = 1
        if score <= 0 and (words or type_name):
            continue
        scored.append((score, {
            "order": order.get("number") or order.get("id"),
            "serial": eq.get("serial") or order.get("serial"),
            "model": eq.get("model") or "",
            "type": eq.get("type") or "",
            "tip": tip,
        }))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _score, item in scored[:limit]]


def catalog(data: dict) -> list[dict]:
    grouped: dict[str, list] = {}
    for item in search(data, limit=200):
        key = item["model"] or item["type"] or "Sem modelo"
        grouped.setdefault(key, [])
        if item["tip"] not in grouped[key]:
            grouped[key].append(item["tip"])
    return [{"model": key, "tips": values[:8]} for key, values in sorted(grouped.items())]
