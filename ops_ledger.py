"""Cadeia de auditoria SHA-256. Cada registro inclui o hash do anterior."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

GENESIS = "0" * 64


def canonical(record: dict) -> str:
    body = {
        "id": record.get("id"),
        "at": record.get("at"),
        "actor": record.get("actor"),
        "action": record.get("action"),
        "entity": record.get("entity"),
        "payload": record.get("payload") or {},
        "hash_anterior": record.get("hash_anterior"),
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(record: dict) -> str:
    return hashlib.sha256(canonical(record).encode("utf-8")).hexdigest()


def append(data: dict, moment: datetime, actor: str, action: str, entity: str, payload: dict | None = None) -> dict:
    import model

    chain = data.setdefault("ledger", [])
    previous = chain[-1]["hash_atual"] if chain else GENESIS
    record = {
        "id": f"LG-{len(chain) + 1}",
        "at": model.iso(moment),
        "actor": actor or "sistema",
        "action": action,
        "entity": entity,
        "payload": payload or {},
        "hash_anterior": previous,
    }
    record["hash_atual"] = digest(record)
    chain.append(record)
    data["ledger"] = chain[-500:]
    return record


def verify(chain: list[dict]) -> dict:
    previous = GENESIS
    for index, record in enumerate(chain):
        if record.get("hash_anterior") != previous:
            return {"ok": False, "index": index, "id": record.get("id"), "reason": "O hash anterior não encadeia."}
        if digest(record) != record.get("hash_atual"):
            return {"ok": False, "index": index, "id": record.get("id"), "reason": "O conteúdo não confere com o hash gravado."}
        previous = record.get("hash_atual")
    return {"ok": True, "count": len(chain), "reason": "A cadeia confere."}


def pdf(chain: list[dict], verdict: dict) -> bytes:
    import ops_orders

    lines = [
        "F.O.G.O.  Integridade da cadeia de auditoria",
        verdict.get("reason") or "",
        f"Registros: {len(chain)}",
        "",
    ]
    for record in chain[-18:]:
        lines.append(f"{record.get('id')}  {str(record.get('at') or '')[:16]}  {record.get('action')}  {record.get('entity')}")
        lines.append(f"hash {str(record.get('hash_atual') or '')[:16]}")
    return ops_orders._pdf(lines)
