"""Servidor do F.O.G.O.

Só a biblioteca padrão do Python 3.10+. Sobe a central, guarda o cadastro
em data/store.json e empurra a cidade ao vivo por Server-Sent Events.

    py -3 server.py
"""

from __future__ import annotations

import hmac
import json
import os
import queue
import random
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import access
import assistant
import model
import ops_orders
import ops_vehicles

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
BUNDLED = ROOT / "data"


def data_dir() -> Path:
    return Path(os.environ.get("FOGO_DATA") or BUNDLED)


def data_path() -> Path:
    return data_dir() / "store.json"


def prepare_runtime() -> None:
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if folder.resolve() == BUNDLED.resolve():
        return
    for name in ("store.json", "access.json", "geo-cache.json"):
        source = BUNDLED / name
        target = folder / name
        if source.is_file() and not target.exists():
            target.write_bytes(source.read_bytes())
LOCK = threading.RLock()
STOP = threading.Event()
CLIENTS: list[queue.Queue] = []
STORE: dict | None = None

MIMES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
}


def save_store() -> None:
    path = data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(STORE, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_store() -> None:
    global STORE
    prepare_runtime()
    if data_path().exists():
        try:
            loaded = json.loads(data_path().read_text(encoding="utf-8"))
            if loaded.get("meta", {}).get("schema") == model.SCHEMA:
                STORE = loaded
                now = model.now_local()
                grew = model.ensure_inventory_size(STORE, now)
                before = len(STORE.get("orders") or [])
                ops_orders.reconcile(STORE, now)
                ops_vehicles.ensure(STORE, now)
                if grew or len(STORE.get("orders") or []) != before:
                    save_store()
                return
            print("O cadastro anterior é de outra versão. A demonstração da central foi recriada.")
        except (json.JSONDecodeError, OSError):
            broken = data_path().with_suffix(".corrompido.json")
            try:
                data_path().replace(broken)
                print(f"Cadastro ilegível. A cópia foi para {broken.name} e a demonstração foi recriada.")
            except OSError:
                print("Cadastro ilegível. A demonstração foi recriada.")
    STORE = model.build_demo(model.now_local())
    ops_vehicles.ensure(STORE, model.now_local())
    ops_orders.reconcile(STORE, model.now_local())
    save_store()


def broadcast(payload: dict) -> None:
    dead = []
    for client in list(CLIENTS):
        try:
            client.put_nowait(payload)
        except queue.Full:
            dead.append(client)
    for client in dead:
        if client in CLIENTS:
            CLIENTS.remove(client)


def mutate(fn):
    with LOCK:
        result = fn(STORE, model.now_local())
        save_store()
        focus = result.get("focus") if isinstance(result, dict) else None
        message = result.get("message") if isinstance(result, dict) else None
    broadcast({"kind": "reload", "focus": focus, "message": message})
    return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        request = args[0] if args else ""
        if isinstance(request, str) and any(piece in request for piece in ("/api/stream", "/css/", "/js/", "/vendor/", "/favicon")):
            return
        super().log_message(fmt, *args)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_PUT(self) -> None:
        self._route("PUT")

    def do_PATCH(self) -> None:
        self._route("PATCH")

    def do_DELETE(self) -> None:
        self._route("DELETE")

    def _route(self, method: str) -> None:
        try:
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if parts[:1] == ["api"]:
                self._api(method, parts[1:], parse_qs(parsed.query))
                return
            if method != "GET":
                self.send_json({"error": "Método não aceito."}, 405)
                return
            self._static(parsed.path)
        except access.Denied as exc:
            self.send_json({"error": str(exc)}, 403)
        except model.Invalid as exc:
            self.send_json({"error": str(exc)}, 400)
        except BrokenPipeError:
            return
        except Exception:
            traceback.print_exc()
            try:
                self.send_json({"error": "Falha interna ao processar o pedido."}, 500)
            except Exception:
                return

    def _api(self, method: str, parts: list[str], query: dict) -> None:
        if parts == ["health"] and method == "GET":
            self.send_json({"ok": True, "name": "F.O.G.O."})
            return
        if parts == ["stream"] and method == "GET":
            self._stream()
            return
        if parts == ["bootstrap"] and method == "GET":
            with LOCK:
                payload = model.bootstrap(STORE, model.now_local())
                payload["user"] = access.public_user(user) if (user := access.user_by_token(self.headers.get("X-Session"))) else None
                payload["territory"] = access.territory()
                if (payload.get("user") or {}).get("role") == "agente":
                    for vehicle in payload.get("vehicles") or []:
                        vehicle["plate"] = ""
            self.send_json(payload)
            return
        if parts == ["session"] and method == "GET":
            user = access.user_by_token(self.headers.get("X-Session"))
            self.send_json({"user": access.public_user(user) if user else None})
            return
        if parts == ["session"] and method == "POST":
            body = self.read_json()
            with LOCK:
                payload = access.login(str(body.get("email") or ""), str(body.get("password") or ""))
            self.send_json(payload)
            return
        if parts == ["session"] and method == "DELETE":
            access.logout(self.headers.get("X-Session"))
            self.send_json({"ok": True})
            return
        if parts == ["users"] and method == "GET":
            with LOCK:
                rows = access.list_users(access.require(self.headers.get("X-Session")))
            self.send_json({"users": rows, "roles": [{"id": key, "label": value["label"]} for key, value in access.ROLES.items()]})
            return
        if parts == ["users"] and method == "POST":
            body = self.read_json()
            with LOCK:
                created = access.create_user(access.require(self.headers.get("X-Session")), body)
            self.send_json({"ok": True, "user": created})
            return
        if len(parts) == 2 and parts[0] == "users" and method == "PATCH":
            body = self.read_json()
            with LOCK:
                updated = access.update_user(access.require(self.headers.get("X-Session")), parts[1], body)
            self.send_json({"ok": True, "user": updated})
            return
        if parts == ["audit"] and method == "GET":
            with LOCK:
                rows = access.audit_view(access.require(self.headers.get("X-Session")))
            self.send_json({"audit": rows})
            return
        if parts == ["geo"] and method == "GET":
            found = access.lookup_place(query.get("q", [""])[0])
            self.send_json(found)
            return
        if parts == ["predictions"] and method == "GET":
            focus = None
            if query.get("date"):
                try:
                    focus = date.fromisoformat(query["date"][0])
                except ValueError:
                    raise model.Invalid("Data inválida. Use AAAA-MM-DD.")
            with LOCK:
                payload = model.predictions(STORE, model.now_local(), focus)
            self.send_json(payload)
            return
        if parts == ["equipment"] and method == "POST":
            body = self.read_json()
            actor = self._actor("write")
            access.ensure_scope(actor, body.get("region"))
            created = mutate(lambda data, now: {"item": model.create_equipment(data, body, now)})
            access.audit(actor, "cadastrou equipamento", created["item"]["id"])
            self.send_json({"ok": True, "id": created["item"]["id"]})
            return
        if len(parts) == 2 and parts[0] == "equipment" and method in ("PUT", "PATCH", "DELETE"):
            eid = parts[1]
            actor = self._actor("write")
            current = next((item for item in STORE["equipment"] if item["id"] == eid), None)
            access.ensure_scope(actor, current.get("region") if current else None)
            if method == "DELETE":
                mutate(lambda data, now: model.delete_equipment(data, eid, now) or {"ok": True})
                access.audit(actor, "removeu equipamento", eid)
                self.send_json({"ok": True})
                return
            body = self.read_json()
            access.ensure_scope(actor, body.get("region") or (current.get("region") if current else None))
            if method == "PUT":
                mutate(lambda data, now: {"item": model.update_equipment(data, eid, body, now)})
            else:
                mutate(lambda data, now: {"item": model.patch_equipment(data, eid, body, now)})
            access.audit(actor, "atualizou equipamento", eid)
            self.send_json({"ok": True})
            return
        if parts == ["agents"] and method == "POST":
            body = self.read_json()
            actor = self._actor("write")
            access.ensure_scope(actor, body.get("region"))
            created = mutate(lambda data, now: {"item": model.create_agent(data, body, now)})
            access.audit(actor, "cadastrou agente", created["item"]["id"])
            self.send_json({"ok": True, "id": created["item"]["id"]})
            return
        if len(parts) == 2 and parts[0] == "agents" and method in ("PUT", "DELETE"):
            aid = parts[1]
            actor = self._actor("write")
            current = next((item for item in STORE["agents"] if item["id"] == aid), None)
            access.ensure_scope(actor, current.get("region") if current else None)
            if method == "DELETE":
                mutate(lambda data, now: model.delete_agent(data, aid, now) or {"ok": True})
                access.audit(actor, "removeu agente", aid)
            else:
                body = self.read_json()
                access.ensure_scope(actor, body.get("region") or (current.get("region") if current else None))
                mutate(lambda data, now: {"item": model.update_agent(data, aid, body, now)})
                access.audit(actor, "atualizou agente", aid)
            self.send_json({"ok": True})
            return
        if len(parts) == 3 and parts[0] == "incidents" and parts[2] == "ack" and method == "POST":
            iid = parts[1]
            actor = self._actor("write")
            mutate(lambda data, now: {"item": model.acknowledge(data, iid, now)})
            access.audit(actor, "encerrou ocorrência", iid)
            self.send_json({"ok": True})
            return
        if len(parts) == 3 and parts[0] == "incidents" and parts[2] == "dispatch" and method == "POST":
            iid = parts[1]
            body = self.read_json()
            actor = self._actor("dispatch")
            incident = next((item for item in STORE["incidents"] if item["id"] == iid), None)
            access.ensure_scope(actor, incident.get("region") if incident else None)
            result = mutate(lambda data, now: model.dispatch(data, iid, body.get("agent_id"), now))
            access.audit(actor, "despachou equipe", iid)
            self.send_json({"ok": True, **result})
            return
        if parts == ["vehicles"] and method == "POST":
            body = self.read_json()
            actor = self._actor("write")
            access.ensure_scope(actor, body.get("base_region"))
            created = mutate(lambda data, now: {"item": ops_vehicles.create(data, body, now, actor.get("name") or actor.get("email") or "Operador"), "message": "Cadastro realizado com sucesso."})
            access.audit(actor, "cadastrou veículo", created["item"]["id"])
            self.send_json({"ok": True, "id": created["item"]["id"], "message": "Cadastro realizado com sucesso."})
            return
        if len(parts) == 2 and parts[0] == "vehicles" and method == "PUT":
            vid = parts[1]
            body = self.read_json()
            actor = self._actor("write")
            current = next((item for item in STORE.get("vehicles") or [] if item["id"] == vid), None)
            access.ensure_scope(actor, (current or {}).get("base_region"))
            access.ensure_scope(actor, body.get("base_region") or (current or {}).get("base_region"))
            mutate(lambda data, now: {"item": ops_vehicles.update(data, vid, body, now, actor.get("name") or actor.get("email") or "Operador"), "message": "Alterações salvas."})
            access.audit(actor, "atualizou veículo", vid)
            self.send_json({"ok": True, "message": "Alterações salvas."})
            return
        if parts == ["routing", "compare"] and method == "POST":
            body = self.read_json()
            actor = self._actor("dispatch")
            incident_id = str(body.get("incident_id") or "")
            with LOCK:
                incident = next((item for item in STORE["incidents"] if item["id"] == incident_id), None)
                access.ensure_scope(actor, incident.get("region") if incident else None)
                snapshot = json.loads(json.dumps(STORE))
            compared = ops_vehicles.compare(snapshot, incident_id)
            self.send_json(compared)
            return
        if len(parts) == 3 and parts[0] == "incidents" and parts[2] == "dispatch-vehicle" and method == "POST":
            iid = parts[1]
            body = self.read_json()
            actor = self._actor("dispatch")
            incident = next((item for item in STORE["incidents"] if item["id"] == iid), None)
            access.ensure_scope(actor, incident.get("region") if incident else None)
            vehicle = next((item for item in STORE.get("vehicles") or [] if item["id"] == body.get("vehicle_id")), None)
            access.ensure_scope(actor, (vehicle or {}).get("base_region"))
            result = mutate(lambda data, now: ops_vehicles.dispatch(
                data, iid, str(body.get("vehicle_id") or ""), str(body.get("choice") or ""), now, actor.get("name") or actor.get("email") or "Operador",
            ))
            access.audit(actor, "despachou veículo", iid)
            self.send_json({"ok": True, **result})
            return
        if len(parts) == 3 and parts[0] == "incidents" and parts[2] == "advance" and method == "POST":
            iid = parts[1]
            body = self.read_json()
            actor = self._actor("advance")
            incident = next((item for item in STORE["incidents"] if item["id"] == iid), None)
            if actor["role"] == "agente":
                assigned = next((item for item in STORE["agents"] if incident and item["id"] == incident.get("assigned_agent_id")), None)
                if not assigned or assigned.get("registration") != actor.get("registration"):
                    raise access.Denied("O agente de campo só atualiza a própria missão.")
            else:
                access.ensure_scope(actor, incident.get("region") if incident else None)
            result = mutate(lambda data, now: model.advance(data, iid, body.get("step"), body.get("note") or "", now))
            access.audit(actor, "atualizou atendimento", f"{iid} · {body.get('step')}")
            self.send_json({"ok": True, **result})
            return
        if parts == ["routes"] and method == "POST":
            body = self.read_json()
            actor = self._actor("dispatch")
            agent = next((item for item in STORE["agents"] if item["id"] == body.get("agent_id")), None)
            access.ensure_scope(actor, agent.get("region") if agent else None)
            result = mutate(lambda data, now: model.plan_route(data, body, now))
            access.audit(actor, "planejou rota", body.get("agent_id") or "")
            self.send_json({"ok": True, **result})
            return
        if len(parts) == 2 and parts[0] == "routes" and method == "DELETE":
            aid = parts[1]
            actor = self._actor("dispatch")
            result = mutate(lambda data, now: model.clear_plan(data, aid, now))
            access.audit(actor, "removeu rota", aid)
            self.send_json({"ok": True, **result})
            return
        if parts == ["replay"] and method == "GET":
            at = query.get("at", [None])[0]
            with LOCK:
                payload = model.replay_view(STORE, at)
            self.send_json(payload)
            return
        if len(parts) == 2 and parts[0] == "scenarios" and method == "POST":
            name = parts[1]
            actor = self._actor("write")
            result = mutate(lambda data, now: model.apply_scenario(data, name, now))
            access.audit(actor, "exercício", name)
            self.send_json({"ok": True, **result})
            return
        if parts == ["reset"] and method == "POST":
            actor = self._actor("admin")
            def _reset(data, now):
                fresh = model.build_demo(now)
                ops_vehicles.ensure(fresh, now)
                data.clear()
                data.update(fresh)
                return {"message": "Demonstração restaurada.", "focus": {"kind": "clear"}}

            result = mutate(_reset)
            access.audit(actor, "restaurou demonstração", "store")
            self.send_json({"ok": True, **result})
            return
        if parts == ["orders"] and method == "GET":
            self._actor("write")
            with LOCK:
                rows = ops_orders.present_all(STORE, model.now_local())
            self.send_json({"orders": rows})
            return
        if parts == ["orders"] and method == "POST":
            body = self.read_json()
            actor = self._actor("write")
            eq = next((item for item in STORE["equipment"] if item["id"] == body.get("equipment_id")), None)
            access.ensure_scope(actor, eq.get("region") if eq else None)
            created = mutate(lambda data, now: ops_orders.create(data, body, now, actor.get("name") or "Operador"))
            access.audit(actor, "abriu OS", created["item"]["id"])
            self.send_json({"ok": True, **created})
            return
        if len(parts) == 3 and parts[0] == "orders" and parts[2] == "pdf" and method == "GET":
            self._actor("write")
            with LOCK:
                blob = ops_orders.pdf(STORE, parts[1], model.now_local())
            self.send_bytes(blob, "application/pdf", f"{parts[1]}.pdf")
            return
        if len(parts) == 3 and parts[0] == "orders" and parts[2] == "assign" and method == "POST":
            body = self.read_json()
            actor = self._actor("write")
            result = mutate(lambda data, now: ops_orders.assign(data, parts[1], body.get("agent_id"), now, actor.get("name") or "Operador"))
            access.audit(actor, "atribuiu OS", parts[1])
            self.send_json({"ok": True, **result})
            return
        if len(parts) == 3 and parts[0] == "orders" and parts[2] == "status" and method == "POST":
            body = self.read_json()
            actor = self._actor("write")
            result = mutate(lambda data, now: ops_orders.advance(data, parts[1], str(body.get("status") or ""), str(body.get("note") or ""), now, actor.get("name") or "Operador"))
            access.audit(actor, "atualizou OS", parts[1])
            self.send_json({"ok": True, **result})
            return
        if len(parts) == 2 and parts[0] == "cep" and method == "GET":
            self.send_json(lookup_cep(parts[1]))
            return
        if parts == ["chat"] and method == "POST":
            body = self.read_json()
            actor = access.require(self.headers.get("X-Session"))
            if body.get("confirm"):
                result = mutate(lambda data, now: assistant.reply(data, str(body.get("message") or ""), now, True))
                access.audit(actor, "confirmou ação do chat", "os")
            else:
                with LOCK:
                    result = assistant.reply(STORE, str(body.get("message") or ""), model.now_local(), False)
            self.send_json(result)
            return
        if parts == ["briefing"] and method == "GET":
            access.require(self.headers.get("X-Session"))
            with LOCK:
                pack = assistant.briefing(STORE, model.now_local())
            self.send_json(pack)
            return
        if parts == ["events"] and method == "POST":
            body = self.read_json()
            actor = access.require(self.headers.get("X-Session"))
            agent = next((item for item in STORE["agents"] if item["id"] == body.get("agent_id")), None)
            if actor.get("role") == "agente":
                if not agent or agent.get("registration") != actor.get("registration"):
                    raise access.Denied("O agente só registra a própria jornada.")
            else:
                access.guard(actor, "write")
            access.ensure_scope(actor, agent.get("region") if agent else None)
            result = mutate(lambda data, now: model.record_shift(data, body, now, actor.get("name") or "Operador"))
            access.audit(actor, "registrou jornada", str(body.get("agent_id") or ""))
            self.send_json({"ok": True, **result})
            return
        if parts == ["webhooks", "supabase"] and method == "POST":
            secret = os.environ.get("FOGO_WEBHOOK_SECRET", "")
            sent = self.headers.get("X-Webhook-Secret", "")
            if not secret or not secrets_equal(secret, sent):
                self.send_json({"error": "Webhook não autorizado."}, 401)
                return
            self.read_json()
            self.send_json({"ok": True, "received": True})
            return
        if parts == ["config"] and method == "GET":
            self.send_json({
                "supabaseUrl": os.environ.get("SUPABASE_URL", ""),
                "supabaseAnonKey": os.environ.get("SUPABASE_ANON_KEY", ""),
                "environment": os.environ.get("FOGO_ENV", "development"),
            })
            return
        self.send_json({"error": "Caminho não encontrado."}, 404)

    def _stream(self) -> None:
        client: queue.Queue = queue.Queue(maxsize=20)
        CLIENTS.append(client)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while not STOP.is_set():
                try:
                    payload = client.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.wfile.write(b"data: " + blob + b"\n\n")
                self.wfile.flush()
        except Exception:
            return
        finally:
            if client in CLIENTS:
                CLIENTS.remove(client)

    def _static(self, path: str) -> None:
        if path in ("/favicon.ico", "/favicon.svg"):
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/":
            path = "/index.html"
        root = STATIC.resolve()
        target = (STATIC / path.lstrip("/")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            missing = STATIC / "404.html"
            if missing.is_file() and "." not in Path(path).name:
                body = missing.read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_json({"error": "Arquivo não encontrado."}, 404)
            return
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIMES.get(target.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 1_000_000:
            raise model.Invalid("Pedido grande demais.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise model.Invalid("JSON inválido.")
        if not isinstance(data, dict):
            raise model.Invalid("O corpo precisa ser um objeto.")
        return data

    def send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def send_bytes(self, payload: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self._cors()
        self.end_headers()
        self.wfile.write(payload)

    def _cors(self) -> None:
        origin = os.environ.get("FOGO_ORIGIN", "")
        if not origin:
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session, X-Webhook-Secret")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")

    def _actor(self, kind: str) -> dict:
        user = access.require(self.headers.get("X-Session"))
        access.guard(user, kind)
        return user


def simulate() -> None:
    rng = random.Random()
    last_save = time.time()
    while not STOP.is_set():
        if STOP.wait(3):
            return
        try:
            with LOCK:
                model.simulate_tick(STORE, rng, model.now_local())
                payload = model.tick_payload(STORE, model.now_local())
                if time.time() - last_save > 60:
                    save_store()
                    last_save = time.time()
            broadcast(payload)
        except Exception:
            traceback.print_exc()


def serve(port: int) -> ThreadingHTTPServer:
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def pick_server() -> tuple[ThreadingHTTPServer, int]:
    last_error = None
    for port in range(8080, 8095):
        try:
            return serve(port), port
        except OSError as exc:
            last_error = exc
            continue
    raise SystemExit(f"Nenhuma porta livre entre 8080 e 8094. Último erro: {last_error}")


def lookup_cep(raw: str) -> dict:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 8:
        raise model.Invalid("CEP precisa ter 8 dígitos.")
    request = urllib.request.Request(f"https://viacep.com.br/ws/{digits}/json/", headers={"User-Agent": "FOGO-CCO/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode())
    except Exception as exc:
        raise model.Invalid("O ViaCEP não respondeu. Preencha o endereço manualmente.") from exc
    if payload.get("erro"):
        raise model.Invalid("CEP não encontrado. Preencha o endereço manualmente.")
    result = {
        "cep": payload.get("cep") or digits,
        "street": payload.get("logradouro") or "",
        "neighborhood": payload.get("bairro") or "",
        "city": payload.get("localidade") or "",
        "uf": payload.get("uf") or "",
    }
    if result["street"] and result["city"]:
        try:
            place = access.lookup_place(f"{result['street']}, {result['city']}, {result['uf']}")
            result["lat"] = place.get("lat")
            result["lng"] = place.get("lng")
        except Exception:
            pass
    return result


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def main(argv: list[str]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except Exception:
            pass
    if "--check" in argv:
        model.self_check()
        return
    if sys.version_info < (3, 10):
        raise SystemExit("Precisa de Python 3.10 ou superior.")
    load_store()
    thread = threading.Thread(target=simulate, name="fogo-cidade", daemon=True)
    thread.start()
    httpd, port = pick_server()
    url = f"http://127.0.0.1:{port}"
    print()
    print("F.O.G.O. no ar", flush=True)
    print(f"Central: {url}", flush=True)
    print("Encerre com Ctrl+C", flush=True)
    print(flush=True)
    if "--no-browser" not in argv:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCentral encerrada.")
    finally:
        STOP.set()
        httpd.shutdown()
        with LOCK:
            try:
                save_store()
            except Exception:
                traceback.print_exc()


if __name__ == "__main__":
    main(sys.argv[1:])
