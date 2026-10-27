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


def pdf(chain: list[dict], verdict: dict, moment: datetime | None = None, issuer: str = "sistema") -> bytes:
    import ops_pdf

    moment = moment or datetime.now().astimezone()
    rows = [[
        record.get("id") or "",
        str(record.get("at") or "")[:16].replace("T", " "),
        record.get("actor") or "",
        record.get("action") or "",
        str(record.get("hash_atual") or "")[:12],
    ] for record in chain[-24:]]
    return ops_pdf.render({
        "org": "F.O.G.O.  Central de Controle Operacional",
        "title": "Auditoria",
        "number": f"{len(chain)} registros",
        "id": "auditoria",
        "issued_at": moment.strftime("%d/%m/%Y %H:%M"),
        "issued_by": issuer,
        "verify": True,
        "sections": [
            {"title": "Cadeia", "lines": [verdict.get("reason") or ""]},
            {"title": "Registros", "table": {
                "headers": ["Registro", "Quando", "Quem", "Ação", "Hash"],
                "rows": rows or [["—", "", "", "Nenhum registro", ""]],
            }},
        ],
    })
