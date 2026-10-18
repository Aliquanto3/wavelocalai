"""Lanceur `wavelocalai-v2` (squelette : le serveur arrive avec la story 1.2)."""

from __future__ import annotations

DEFAULT_PORT = 8502


def main() -> int:
    """Point d'entrée du script `wavelocalai-v2`."""
    print(f"wavelocalai v2 : squelette, serveur à venir (port par défaut {DEFAULT_PORT}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
