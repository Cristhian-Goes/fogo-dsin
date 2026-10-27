"""Usuários, sessão e auditoria da central.

A senha de demonstração é a mesma para as contas locais e fica só no
arquivo de acesso, em hash. O servidor confere o perfil antes de gravar.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import model

ROOT = Path(__file__).resolve().parent


def data_dir() -> Path:
    return Path(os.environ.get("FOGO_DATA") or (ROOT / "data"))


def access_file() -> Path:
    return data_dir() / "access.json"


def geo_file() -> Path:
    return data_dir() / "geo-cache.json"
DEMO_PASSWORD = "demonstracao"
ADMIN_EMAIL = "fogo@adm"
ADMIN_PASSWORD = "Fogo2026!"

DEFAULT_GROUPS = [
    ("GP-ADM", "Administrador", "administrador"),
    ("GP-ESTADUAL", "Gestor estadual", "gestor_estadual"),
    ("GP-MUNICIPAL", "Gestor municipal", "gestor_municipal"),
    ("GP-SUPERVISAO", "Supervisor", "supervisor"),
    ("GP-CCO", "Operador da CCO", "operador"),
    ("GP-CAMPO", "Agente de campo", "agente"),
    ("GP-AUDITORIA", "Auditor", "auditor"),
]

SCREENS = [
    ("cco", "Central"),
    ("inteligencia", "O que fazer agora"),
    ("ordens", "Ordens de serviço"),
    ("rotas", "Rotas"),
    ("inventario", "Equipamentos"),
    ("agentes", "Agentes"),
    ("previsao", "Previsões"),
    ("impacto", "Impacto"),
    ("ocorrencias", "Ocorrências"),
    ("frota", "Veículos"),
    ("regioes", "Regiões"),
    ("alertas", "Alertas"),
    ("linha", "Linha do tempo"),
    ("historico", "Histórico"),
    ("campo", "Modo campo"),
    ("acessos", "Configurações"),
    ("financeiro", "Financeiro"),
    ("conformidade", "Conformidade"),
    ("dimensionamento", "Equipes"),
    ("conhecimento", "Conhecimento"),
    ("integridade", "Integridade"),
    ("valor", "Valor entregue"),
]
SCREEN_LABEL = dict(SCREENS)
_ALL = [item[0] for item in SCREENS]
_DESK = ["cco", "inteligencia", "ordens", "rotas", "ocorrencias", "alertas", "agentes", "frota"]
_SHIFT = _DESK + ["inventario", "previsao", "linha", "financeiro", "conformidade", "dimensionamento", "conhecimento", "valor"]
_CITY = _SHIFT + ["regioes"]
_STATE = [item for item in _ALL if item not in ("acessos", "campo")]
_AUDIT = ["cco", "ordens", "inventario", "previsao", "impacto", "regioes", "alertas", "linha", "historico", "financeiro", "conformidade", "dimensionamento", "conhecimento", "valor", "integridade"]

ROLES = {
    "administrador": {"label": "Administrador", "write": True, "dispatch": True, "admin": True, "scope": "brasil", "views": _ALL},
    "gestor_estadual": {"label": "Gestor estadual", "write": True, "dispatch": True, "admin": False, "scope": "uf", "views": _STATE},
    "gestor_municipal": {"label": "Gestor municipal", "write": True, "dispatch": True, "admin": False, "scope": "municipio", "views": _CITY},
    "supervisor": {"label": "Supervisor", "write": True, "dispatch": True, "admin": False, "scope": "operacao", "views": _SHIFT},
    "operador": {"label": "Operador da CCO", "write": True, "dispatch": True, "admin": False, "scope": "operacao", "views": _DESK},
    "agente": {"label": "Agente de campo", "write": False, "dispatch": False, "admin": False, "scope": "proprio", "views": ["campo"]},
    "auditor": {"label": "Auditor", "write": False, "dispatch": False, "admin": False, "scope": "operacao", "views": _AUDIT},
}

OPERATION_CITIES = {"Marília", "Assis", "Cândido Mota"}

UFS = [
    ("AC", "Acre", -9.02, -70.81),
    ("AL", "Alagoas", -9.57, -36.78),
    ("AP", "Amapá", 1.41, -51.77),
    ("AM", "Amazonas", -3.47, -65.10),
    ("BA", "Bahia", -12.28, -41.93),
    ("CE", "Ceará", -5.20, -39.53),
    ("DF", "Distrito Federal", -15.78, -47.93),
    ("ES", "Espírito Santo", -19.57, -40.67),
    ("GO", "Goiás", -15.93, -49.84),
    ("MA", "Maranhão", -5.42, -45.44),
    ("MT", "Mato Grosso", -12.64, -55.42),
    ("MS", "Mato Grosso do Sul", -20.51, -54.54),
    ("MG", "Minas Gerais", -18.51, -44.55),
    ("PA", "Pará", -3.79, -52.48),
    ("PB", "Paraíba", -7.24, -36.78),
    ("PR", "Paraná", -24.63, -51.43),
    ("PE", "Pernambuco", -8.38, -37.86),
    ("PI", "Piauí", -7.72, -42.73),
    ("RJ", "Rio de Janeiro", -22.17, -42.66),
    ("RN", "Rio Grande do Norte", -5.81, -36.59),
    ("RS", "Rio Grande do Sul", -29.75, -53.15),
    ("RO", "Rondônia", -10.83, -63.34),
    ("RR", "Roraima", 1.99, -61.33),
    ("SC", "Santa Catarina", -27.45, -50.95),
    ("SP", "São Paulo", -22.19, -48.79),
    ("SE", "Sergipe", -10.57, -37.45),
    ("TO", "Tocantins", -10.17, -48.30),
]


class Denied(Exception):
    pass


def _hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 80_000).hex()
    return f"{salt}${digest}"


def _check(password: str, stored: str) -> bool:
    salt, _, digest = stored.partition("$")
    if not digest:
        return False
    return secrets.compare_digest(_hash(password, salt), stored)


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")


def _blank() -> dict:
    people = [
        ("Administrador geral", "admin@fogo.local", "administrador", "SP", "", ""),
        ("Helena Vasconcelos", "estadual.sp@fogo.local", "gestor_estadual", "SP", "", ""),
        ("Paulo Henrique Luz", "municipal.marilia@fogo.local", "gestor_municipal", "SP", "Marília", ""),
        ("Sandra Ribeiro", "supervisor@fogo.local", "supervisor", "SP", "Marília", ""),
        ("Operador da CCO", "operador@fogo.local", "operador", "SP", "Marília", ""),
        ("Ana Luiza Ferreira", "agente@fogo.local", "agente", "SP", "Marília", "AT-2401"),
        ("Auditor da operação", "auditor@fogo.local", "auditor", "SP", "Marília", ""),
    ]
    users = []
    for name, email, role, uf, city, registration in people:
        users.append({
            "id": "US-" + secrets.token_hex(3),
            "name": name,
            "email": email,
            "password": _hash(DEMO_PASSWORD),
            "registration": registration,
            "agency": "Central de operações",
            "uf": uf,
            "city": city,
            "role": role,
            "group_id": _group_for_role(role),
            "active": True,
        })
    users.insert(0, _admin_record())
    return {"users": users, "groups": _default_groups(), "audit": []}


def _default_groups() -> list[dict]:
    return [{"id": gid, "name": name, "role": role, "uf": "SP", "city": "", "active": True} for gid, name, role in DEFAULT_GROUPS]


def _group_for_role(role: str) -> str:
    for gid, _name, group_role in DEFAULT_GROUPS:
        if group_role == role:
            return gid
    return "GP-CCO"


def _admin_record() -> dict:
    return {
        "id": "US-ADM",
        "name": "Administrador",
        "email": ADMIN_EMAIL,
        "password": _hash(ADMIN_PASSWORD),
        "registration": "",
        "agency": "Central de operações",
        "uf": "SP",
        "city": "Marília",
        "role": "administrador",
        "group_id": "GP-ADM",
        "active": True,
    }


def _ensure_accounts(data: dict) -> bool:
    changed = False
    data.setdefault("groups", [])
    by_id = {item.get("id"): item for item in data["groups"]}
    for item in _default_groups():
        current = by_id.get(item["id"])
        if not current:
            data["groups"].append(item)
            changed = True
            continue
        if current.get("name") != item["name"] or current.get("role") != item["role"]:
            current["name"] = item["name"]
            current["role"] = item["role"]
            changed = True
    role_of = {gid: role for gid, _name, role in DEFAULT_GROUPS}
    for user in data["users"]:
        expected = role_of.get(user.get("group_id"))
        if expected and user.get("role") != expected:
            user["role"] = expected
            changed = True
    if not any(item.get("email", "").lower() == ADMIN_EMAIL for item in data["users"]):
        data["users"].insert(0, _admin_record())
        changed = True
    for user in data["users"]:
        if not user.get("group_id"):
            user["group_id"] = _group_for_role(user.get("role") or "operador")
            changed = True
    return changed


def _group(group_id: str) -> dict:
    return next((item for item in load().get("groups") or [] if item.get("id") == group_id), {})


def load() -> dict:
    path = access_file()
    if not path.exists():
        data = _blank()
        save(data)
        return data
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("users", [])
    data.setdefault("audit", [])
    changed = _ensure_accounts(data)
    if changed:
        save(data)
    return data


def save(data: dict) -> None:
    path = access_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


SESSIONS: dict[str, str] = {}
REVOKED: set[str] = set()
SESSION_SECONDS = 24 * 60 * 60


def _session_key() -> bytes:
    # A mesma chave em todo processo. Sem isso, a Vercel esquece o login
    # quando a próxima tela cai em outra instância.
    return (os.environ.get("FOGO_SESSION_SECRET") or "fogo-session-demo").encode()


def _issue_token(user_id: str) -> str:
    exp = int(time.time()) + SESSION_SECONDS
    body = base64.urlsafe_b64encode(f"{user_id}|{exp}".encode()).decode().rstrip("=")
    sig = hmac.new(_session_key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def _user_id_from_token(token: str) -> str | None:
    if token.count(".") != 1:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(_session_key(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    pad = "=" * (-len(body) % 4)
    try:
        user_id, exp_s = base64.urlsafe_b64decode(body + pad).decode().rsplit("|", 1)
        if int(exp_s) < int(time.time()):
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return user_id


def public_user(user: dict) -> dict:
    role = ROLES[user["role"]]
    group = _group(user.get("group_id") or "")
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "registration": user.get("registration") or "",
        "agency": user.get("agency") or "",
        "uf": user.get("uf") or "",
        "city": user.get("city") or "",
        "role": user["role"],
        "role_label": role["label"],
        "group_id": group.get("id") or "",
        "group_name": group.get("name") or "Sem grupo",
        "active": user.get("active", True),
        "can_write": role["write"],
        "can_dispatch": role["dispatch"],
        "can_admin": role["admin"],
        "views": list(role.get("views") or []),
    }


def user_by_token(token: str | None) -> dict | None:
    if not token or token in REVOKED:
        return None
    uid = SESSIONS.get(token) or _user_id_from_token(token)
    if not uid:
        return None
    data = load()
    user = next((item for item in data["users"] if item["id"] == uid and item.get("active")), None)
    return user


def login(email: str, password: str) -> dict:
    data = load()
    found = next((item for item in data["users"] if item["email"].lower() == email.strip().lower()), None)
    if not found or not found.get("active") or not _check(password, found["password"]):
        raise Denied("E-mail ou senha não conferem.")
    return _open_session(found, found["email"])


def login_identity(email: str, via: str) -> dict:
    data = load()
    found = next((item for item in data["users"] if item["email"].lower() == email.strip().lower() and item.get("active")), None)
    if not found:
        raise Denied("Esta identidade da Cloudflare não tem usuário na central. O administrador cria a conta em Acessos.")
    return _open_session(found, f"{found['email']} · {via}")


def _open_session(found: dict, detail: str) -> dict:
    token = _issue_token(found["id"])
    SESSIONS[token] = found["id"]
    audit(found, "entrou", detail)
    return {"token": token, "user": public_user(found)}


def logout(token: str | None) -> None:
    if not token:
        return
    REVOKED.add(token)
    SESSIONS.pop(token, None)


def require(token: str | None) -> dict:
    user = user_by_token(token)
    if not user:
        raise Denied("Entre com um perfil para fazer esta operação.")
    return user


def require_view(user: dict, view: str) -> None:
    if view not in (ROLES.get(user["role"], {}).get("views") or []):
        raise Denied(f"Seu perfil não acessa {SCREEN_LABEL.get(view, view)}.")


def guard(user: dict, kind: str) -> None:
    role = ROLES[user["role"]]
    if kind == "admin" and not role["admin"]:
        raise Denied("Seu perfil não administra usuários.")
    if kind == "dispatch" and not role["dispatch"]:
        raise Denied("Seu perfil não despacha equipe.")
    if kind == "write" and not role["write"]:
        raise Denied("Seu perfil consulta a operação e não altera cadastros.")
    if kind == "advance" and user["role"] == "auditor":
        raise Denied("O auditor não registra atendimento.")
    if kind == "advance" and user["role"] not in ("agente",) and not role["dispatch"] and not role["write"]:
        raise Denied("Seu perfil não atualiza ocorrência.")


def city_of(region: str | None) -> str:
    meta = model.REGIONS.get(region or "")
    return meta["city"] if meta else ""


def uf_of(region: str | None) -> str:
    meta = model.REGIONS.get(region or "")
    return meta["uf"] if meta else ""


def allows(user: dict, region: str | None) -> bool:
    role = user["role"]
    if role == "administrador" or not region:
        return True
    if role == "gestor_estadual":
        return uf_of(region) == user.get("uf")
    if role == "gestor_municipal":
        return city_of(region) == user.get("city")
    if role in ("supervisor", "operador", "auditor", "agente"):
        return city_of(region) in OPERATION_CITIES
    return False


def ensure_scope(user: dict, region: str | None) -> None:
    if region and not allows(user, region):
        raise Denied(f"Seu perfil não alcança a região {region}.")


def audit(user: dict | None, action: str, detail: str) -> None:
    data = load()
    data["audit"].insert(0, {
        "at": _now(),
        "user": user["name"] if user else "sistema",
        "email": user["email"] if user else "",
        "role": user["role"] if user else "",
        "action": action,
        "detail": detail[:240],
    })
    data["audit"] = data["audit"][:200]
    save(data)


def list_users(actor: dict) -> list[dict]:
    guard(actor, "admin")
    return [public_user(item) for item in load()["users"]]


def create_user(actor: dict, body: dict) -> dict:
    guard(actor, "admin")
    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip().lower()
    role = str(body.get("role") or "")
    password = str(body.get("password") or "")
    if not name or not email or "@" not in email:
        raise model.Invalid("Informe nome e e-mail válidos.")
    if role not in ROLES:
        raise model.Invalid("Escolha um perfil da lista.")
    if len(password) < 8:
        raise model.Invalid("A senha precisa ter pelo menos 8 caracteres.")
    data = load()
    group_id = str(body.get("group_id") or _group_for_role(role)).strip()
    group = next((item for item in data.get("groups") or [] if item.get("id") == group_id and item.get("active", True)), None)
    if not group:
        raise model.Invalid("Escolha um grupo ativo.")
    if any(item["email"] == email for item in data["users"]):
        raise model.Invalid("Já existe um usuário com este e-mail.")
    user = {
        "id": "US-" + secrets.token_hex(3),
        "name": name,
        "email": email,
        "password": _hash(password),
        "registration": str(body.get("registration") or "").strip(),
        "agency": str(body.get("agency") or "").strip(),
        "uf": str(body.get("uf") or group.get("uf") or "").strip().upper(),
        "city": str(body.get("city") or group.get("city") or "").strip(),
        "role": role,
        "group_id": group_id,
        "active": True,
    }
    data["users"].append(user)
    save(data)
    audit(actor, "criou usuário", f"{email} · {ROLES[role]['label']} · {group['name']}")
    return public_user(user)


def list_groups(actor: dict) -> list[dict]:
    guard(actor, "admin")
    return [_public_group(item) for item in load().get("groups") or []]


def create_group(actor: dict, body: dict) -> dict:
    guard(actor, "admin")
    name = str(body.get("name") or "").strip()
    role = str(body.get("role") or "")
    if not name:
        raise model.Invalid("Informe o nome do grupo.")
    if role not in ROLES:
        raise model.Invalid("Escolha o acesso deste grupo.")
    data = load()
    group = {
        "id": "GP-" + secrets.token_hex(3).upper(),
        "name": name,
        "role": role,
        "uf": str(body.get("uf") or "").strip().upper(),
        "city": str(body.get("city") or "").strip(),
        "active": True,
    }
    data.setdefault("groups", []).append(group)
    save(data)
    audit(actor, "criou grupo", f"{name} · {ROLES[role]['label']}")
    return _public_group(group)


def update_group(actor: dict, group_id: str, body: dict) -> dict:
    guard(actor, "admin")
    data = load()
    group = next((item for item in data.get("groups") or [] if item.get("id") == group_id), None)
    if not group:
        raise model.Invalid("Grupo não encontrado.")
    if "name" in body and str(body["name"]).strip():
        group["name"] = str(body["name"]).strip()
    if "role" in body:
        if body["role"] not in ROLES:
            raise model.Invalid("Acesso inválido.")
        group["role"] = body["role"]
    if "active" in body:
        group["active"] = bool(body["active"])
    for key in ("uf", "city"):
        if key in body:
            group[key] = str(body[key]).strip()
    save(data)
    audit(actor, "alterou grupo", f"{group['name']} · {ROLES[group['role']]['label']}")
    return _public_group(group)


def _public_group(group: dict) -> dict:
    role = ROLES.get(group.get("role") or "", {})
    return {
        "id": group.get("id"),
        "name": group.get("name") or "",
        "role": group.get("role") or "",
        "role_label": role.get("label") or group.get("role") or "",
        "uf": group.get("uf") or "",
        "city": group.get("city") or "",
        "active": group.get("active", True),
        "screens": [SCREEN_LABEL[item] for item in ROLES.get(group.get("role") or "", {}).get("views") or []],
    }


def update_user(actor: dict, uid: str, body: dict) -> dict:
    guard(actor, "admin")
    if uid == actor["id"] and "role" in body and body["role"] != actor["role"]:
        raise Denied("Você não altera o próprio perfil.")
    if uid == actor["id"] and body.get("active") is False:
        raise Denied("Você não desativa a própria conta.")
    data = load()
    user = next((item for item in data["users"] if item["id"] == uid), None)
    if not user:
        raise model.Invalid("Usuário não encontrado.")
    if "group_id" in body:
        group_id = str(body.get("group_id") or "").strip()
        group = next((item for item in data.get("groups") or [] if item.get("id") == group_id), None)
        if group_id and not group:
            raise model.Invalid("Grupo inválido.")
        user["group_id"] = group_id
        if group and group.get("role") in ROLES:
            user["role"] = group["role"]
    elif "role" in body:
        if body["role"] not in ROLES:
            raise model.Invalid("Perfil inválido.")
        user["role"] = body["role"]
        user["group_id"] = _group_for_role(body["role"])
    if uid == actor["id"] and user["role"] != actor["role"]:
        raise Denied("Você não altera o próprio perfil.")
    if "password" in body and str(body.get("password") or ""):
        if len(str(body["password"])) < 8:
            raise model.Invalid("A senha precisa ter pelo menos 8 caracteres.")
        user["password"] = _hash(str(body["password"]))
    if "active" in body:
        user["active"] = bool(body["active"])
        if not user["active"]:
            for token, owner in list(SESSIONS.items()):
                if owner == uid:
                    SESSIONS.pop(token, None)
    for key in ("name", "agency", "uf", "city", "registration"):
        if key in body and str(body[key]).strip():
            user[key] = str(body[key]).strip()
    if user["role"] == "administrador" and not any(item["role"] == "administrador" and item.get("active") for item in data["users"]):
        raise Denied("A central precisa de um administrador ativo.")
    save(data)
    audit(actor, "alterou usuário", f"{user['email']} · {ROLES[user['role']]['label']}")
    return public_user(user)


def audit_view(actor: dict) -> list[dict]:
    if actor["role"] not in ("administrador", "gestor_estadual"):
        raise Denied("Seu perfil não consulta a auditoria.")
    return load()["audit"][:80]


def territory() -> dict:
    return {
        "ufs": [{"sigla": sigla, "nome": nome, "lat": lat, "lng": lng} for sigla, nome, lat, lng in UFS],
        "operation": {
            "id": "piloto-oeste-paulista",
            "label": "Operação de demonstração · Marília, Assis e Cândido Mota",
            "uf": "SP",
            "cities": sorted(OPERATION_CITIES),
            "lat": -22.48,
            "lng": -50.15,
            "note": "Única área com equipamentos, agentes e ocorrências. Os registros são simulados e estão identificados na central.",
        },
    }


def lookup_place(query: str) -> dict:
    text = " ".join(query.strip().split())
    if len(text) < 2:
        raise model.Invalid("Digite o município, a UF ou o bairro.")
    key = text.lower()
    for sigla, nome, lat, lng in UFS:
        if key in {sigla.lower(), nome.lower()}:
            return {
                "name": nome,
                "uf": sigla,
                "lat": lat,
                "lng": lng,
                "zoom": 6,
                "kind": "uf",
                "source": "Recorte territorial local, centróide aproximado da UF.",
                "operational": False,
                "note": f"{nome} está no mapa. Não há cadastro operacional neste estado fora da demonstração em São Paulo.",
            }
    for city, lat, lng in (("Marília", -22.21, -49.95), ("Assis", -22.66, -50.41), ("Cândido Mota", -22.75, -50.39)):
        if key in {city.lower(), f"{city.lower()} sp"}:
            return {
                "name": city,
                "uf": "SP",
                "lat": lat,
                "lng": lng,
                "zoom": 12,
                "kind": "municipio",
                "source": "Coordenada da operação de demonstração.",
                "operational": True,
                "note": f"{city} faz parte da operação de demonstração. Os equipamentos e as ocorrências desta cidade são simulados.",
            }
    cached = _geo_cache().get(key)
    if cached:
        return cached
    found = _nominatim(text)
    _geo_cache_save(key, found)
    return found


def _geo_cache() -> dict:
    if not geo_file().exists():
        return {}
    try:
        return json.loads(geo_file().read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _geo_cache_save(key: str, value: dict) -> None:
    data = _geo_cache()
    data[key] = value
    if len(data) > 200:
        for old in list(data)[:-200]:
            data.pop(old, None)
    path = geo_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _nominatim(text: str) -> dict:
    import urllib.parse
    import urllib.request

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": f"{text}, Brasil",
        "format": "jsonv2",
        "limit": "1",
        "addressdetails": "1",
    })
    request = urllib.request.Request(url, headers={"User-Agent": "FOGO-CCO/1.0 (demonstracao local)"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise model.Invalid("A busca territorial não respondeu. Tente a sigla da UF ou Marília, Assis e Cândido Mota.")
    if not rows:
        raise model.Invalid("Nenhum município encontrado com esse nome.")
    row = rows[0]
    address = row.get("address") or {}
    uf = (address.get("ISO3166-2-lvl4") or "").replace("BR-", "")
    name = address.get("city") or address.get("town") or address.get("municipality") or row.get("name") or text
    return {
        "name": name,
        "uf": uf,
        "lat": float(row["lat"]),
        "lng": float(row["lon"]),
        "zoom": 12,
        "kind": "municipio",
        "source": "OpenStreetMap / Nominatim. Referência territorial, sem cadastro operacional.",
        "operational": False,
        "note": f"{name} foi localizado no mapa. Não há agentes, equipamentos nem ocorrências cadastrados aqui.",
    }
