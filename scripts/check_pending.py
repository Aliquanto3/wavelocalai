#!/usr/bin/env python3
"""Vérifie si les modèles « en attente de support » sont devenus exécutables.

Certains modèles intéressants ne se chargent pas encore : leur architecture
n'est pas supportée par llama.cpp, dont dépend Ollama. Ce script interroge le
ticket de suivi de chacun et indique s'il est temps de réessayer.

    python scripts/check_pending.py

Aucun téléchargement : seuls des appels à l'API GitHub sont effectués.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
CATALOG = ROOT / "config" / "models_catalog.json"


def github_issue_state(url: str) -> tuple[str, str] | None:
    """Retourne (état, titre) du ticket GitHub, ou None si illisible."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)", url)
    if not m:
        return None
    owner, repo, _kind, number = m.groups()
    api = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    try:
        req = urllib.request.Request(api, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "wavelocalai-check-pending"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        state = data.get("state", "?")
        if data.get("pull_request", {}).get("merged_at"):
            state = "merged"
        return state, data.get("title", "")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"    (ticket illisible : {e})")
        return None


def main() -> int:
    if not CATALOG.exists():
        sys.exit(f"Catalogue introuvable : {CATALOG}")
    models = json.loads(CATALOG.read_text(encoding="utf-8"))["models"]
    pending = {n: e for n, e in models.items() if e.get("status") == "pending"}

    if not pending:
        print("Aucun modèle en attente.")
        return 0

    print(f"{len(pending)} modèle(s) en attente :\n")
    ready = 0
    for name, entry in pending.items():
        print(f"  {name} ({entry.get('size_gb', '?')})")
        print(f"    Blocage  : {entry.get('blocked_by', '—')}")
        print(f"    Vérifié  : {entry.get('checked_on', '—')}")
        tracking = entry.get("tracking")
        if tracking:
            print(f"    Suivi    : {tracking}")
            result = github_issue_state(tracking)
            if result:
                state, title = result
                verdict = ("RÉSOLU — réessayez l'import" if state in ("closed", "merged")
                           else "toujours ouvert")
                print(f"    État     : {state} ({verdict})")
                print(f"               {title[:70]}")
                ready += state in ("closed", "merged")
        print()

    if ready:
        print(f"{ready} verrou(s) levé(s). Pour réessayer un modèle :")
        print("  1. retirez son entrée de PENDING dans scripts/build_catalog.py")
        print("  2. relancez scripts/build_catalog.py puis bench_here.py install")
    else:
        print("Aucun verrou levé : rien à faire pour l'instant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
