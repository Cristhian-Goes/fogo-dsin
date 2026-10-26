"""Prepara a pasta public/ para a Vercel, sem dependência externa."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
STATIC = ROOT / "static"


def main() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    shutil.copytree(STATIC, PUBLIC)
    page = PUBLIC / "404.html"
    if not page.is_file():
        raise SystemExit("404.html não foi copiado.")
    if not (PUBLIC / "index.html").is_file():
        raise SystemExit("index.html não foi copiado.")
    print(f"Build estático em {PUBLIC}")


if __name__ == "__main__":
    sys.exit(main() or 0)
