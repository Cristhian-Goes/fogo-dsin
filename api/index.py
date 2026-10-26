"""Entrada serverless da Vercel. Reusa o mesmo roteador da central local."""

from __future__ import annotations

import os

os.environ.setdefault("FOGO_ENV", "production")
os.environ.setdefault("FOGO_DATA", "/tmp/fogo")

from server import Handler, load_store

_READY = False


def _ensure() -> None:
    global _READY
    if _READY:
        return
    load_store()
    _READY = True


class handler(Handler):
    def _route(self, method: str) -> None:
        _ensure()
        super()._route(method)
