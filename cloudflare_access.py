"""Cloudflare Access.

A central só cobra o token quando CF_ACCESS_TEAM e CF_ACCESS_AUD estão no
ambiente. Sem esses dois valores, o login local continua valendo. A
assinatura RS256 é conferida com a chave pública publicada pela Cloudflare,
sem biblioteca extra.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.request

import access

_CERTS: dict = {"at": 0.0, "keys": []}
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def team_host() -> str:
    raw = os.environ.get("CF_ACCESS_TEAM", "").strip().rstrip("/")
    raw = raw.removeprefix("https://").removeprefix("http://")
    if not raw:
        return ""
    if "." not in raw:
        raw = f"{raw}.cloudflareaccess.com"
    return raw.split("/")[0]


def configured() -> bool:
    return bool(team_host() and os.environ.get("CF_ACCESS_AUD", "").strip())


def required() -> bool:
    return configured() and os.environ.get("CF_ACCESS_REQUIRED", "").strip().lower() in ("1", "true", "sim", "yes")


def public_status() -> dict:
    return {"enabled": configured(), "required": required()}


def turnstile_sitekey() -> str:
    if not os.environ.get("CF_TURNSTILE_SECRET", "").strip():
        return ""
    return os.environ.get("CF_TURNSTILE_SITEKEY", "").strip()


def verify_turnstile(token: str, remote_ip: str) -> None:
    secret = os.environ.get("CF_TURNSTILE_SECRET", "").strip()
    if not secret:
        return
    # O widget deste site key recusa 127.0.0.1 (erro 110200) e trava a tela.
    # Neste computador a senha entra direto, sem chamar a Cloudflare.
    if remote_ip in {"127.0.0.1", "::1", "localhost"}:
        return
    if not token:
        raise access.Denied("Confirme a verificação da Cloudflare antes de entrar.")
    import urllib.parse
    body = urllib.parse.urlencode({
        "secret": secret,
        "response": token,
        "remoteip": remote_ip or "",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=body,
        headers={"User-Agent": "FOGO-CCO/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise access.Denied("A Cloudflare não respondeu a verificação. Tente de novo.")
    if not payload.get("success"):
        raise access.Denied("A verificação da Cloudflare não confere.")


def identity(token: str | None) -> dict:
    if not configured():
        raise access.Denied("A Cloudflare Access ainda não está configurada. Coloque CF_ACCESS_TEAM e CF_ACCESS_AUD no arquivo .env e reinicie o servidor.")
    if not token:
        raise access.Denied("O navegador não enviou o token da Cloudflare. Abra a central pelo domínio protegido no painel Zero Trust.")
    header, payload, signing = _parts(token)
    key = _key(header.get("kid"))
    if not _verify(signing, token.rsplit(".", 1)[0].encode("ascii"), key):
        raise access.Denied("O token da Cloudflare não confere.")
    now = int(time.time())
    if int(payload.get("nbf") or 0) > now + 30:
        raise access.Denied("O token da Cloudflare ainda não vale.")
    if int(payload.get("exp") or 0) < now:
        raise access.Denied("O token da Cloudflare expirou. Entre de novo pelo domínio protegido.")
    aud = payload.get("aud")
    expected = os.environ.get("CF_ACCESS_AUD", "").strip()
    audiences = aud if isinstance(aud, list) else [aud]
    if expected not in audiences:
        raise access.Denied("O token da Cloudflare é de outra aplicação. Confira CF_ACCESS_AUD no .env.")
    issuer = f"https://{team_host()}"
    if payload.get("iss") != issuer:
        raise access.Denied("O token da Cloudflare não saiu da equipe configurada em CF_ACCESS_TEAM.")
    email = str(payload.get("email") or "").strip().lower()
    if "@" not in email:
        raise access.Denied("A Cloudflare não informou o e-mail desta pessoa.")
    return {"email": email, "name": str(payload.get("name") or payload.get("common_name") or email)}


def _parts(token: str) -> tuple[dict, dict, bytes]:
    pieces = token.split(".")
    if len(pieces) != 3:
        raise access.Denied("O token da Cloudflare não confere.")
    try:
        header = json.loads(_b64(pieces[0]))
        payload = json.loads(_b64(pieces[1]))
        signature = _b64(pieces[2])
    except (json.JSONDecodeError, ValueError):
        raise access.Denied("O token da Cloudflare não confere.")
    if header.get("alg") != "RS256":
        raise access.Denied("O token da Cloudflare não confere.")
    return header, payload, signature


def _b64(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _key(kid: str | None) -> tuple[int, int]:
    keys = _certs()
    found = next((item for item in keys if item.get("kid") == kid), None) or (keys[0] if len(keys) == 1 else None)
    if not found or found.get("kty") != "RSA":
        raise access.Denied("A Cloudflare não publicou a chave deste token. Confira CF_ACCESS_TEAM.")
    return int.from_bytes(_b64(found["n"]), "big"), int.from_bytes(_b64(found["e"]), "big")


def _certs() -> list[dict]:
    if _CERTS["keys"] and time.time() - _CERTS["at"] < 3600:
        return _CERTS["keys"]
    host = team_host()
    request = urllib.request.Request(
        f"https://{host}/cdn-cgi/access/certs",
        headers={"User-Agent": "FOGO-CCO/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise access.Denied("Não foi possível ler as chaves da Cloudflare Access. Confira CF_ACCESS_TEAM no .env.")
    keys = body.get("keys") or body.get("public_certs") or []
    if isinstance(keys, dict):
        keys = list(keys.values())
    normalized = []
    for item in keys:
        if "n" in item and "e" in item:
            normalized.append(item)
            continue
        cert = item.get("cert") if isinstance(item, dict) else None
        if cert:
            continue
    if not normalized:
        raise access.Denied("A Cloudflare não devolveu chave pública. Confira CF_ACCESS_TEAM no .env.")
    _CERTS["at"] = time.time()
    _CERTS["keys"] = normalized
    return normalized


def _verify(signature: bytes, message: bytes, key: tuple[int, int]) -> bool:
    modulus, exponent = key
    width = (modulus.bit_length() + 7) // 8
    if len(signature) != width:
        return False
    opened = pow(int.from_bytes(signature, "big"), exponent, modulus).to_bytes(width, "big")
    if opened[:2] != b"\x00\x01":
        return False
    try:
        split = opened.index(b"\x00", 2)
    except ValueError:
        return False
    digest = hashlib.sha256(message).digest()
    return secrets.compare_digest(opened[split + 1:], SHA256_PREFIX + digest)
