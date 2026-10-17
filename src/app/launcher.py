"""Lanceur de l'application : `uv run wavelocalai [options Streamlit]`.

Se place à la racine du dépôt (Streamlit ne lit `.streamlit/config.toml` que dans le
répertoire courant ; sinon le serveur écouterait sur le réseau), crée `data/models.json`
au premier lancement, puis démarre `streamlit run src/app/Accueil.py`.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ensure_models_json(root: Path = ROOT) -> bool:
    """Crée data/models.json depuis le catalogue versionné s'il n'existe pas.

    Ne modifie jamais un fichier existant. Retourne True si le fichier a été créé.
    """
    target = root / "data" / "models.json"
    if target.exists():
        return False
    catalog = json.loads((root / "config" / "models_catalog.json").read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "x", encoding="utf-8") as f:  # "x" : n'écrase jamais
        json.dump(catalog["models"], f, indent=4, ensure_ascii=False)
    return True


def main(argv: list[str] | None = None) -> int:
    from streamlit.web import cli as stcli

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    # Hors installation éditable (`uv tool install`, `--no-editable`), ROOT pointe dans
    # site-packages, sans config/ ni .streamlit/ : refuser plutôt que d'écouter sur le réseau.
    required = [ROOT / "src" / "app" / "Accueil.py", ROOT / ".streamlit" / "config.toml"]
    missing = [p for p in required if not p.exists()]
    if missing:
        print(
            f"Racine du dépôt introuvable ({ROOT}) : lancer `uv run wavelocalai` depuis le"
            " clone du dépôt (installation éditable).",
            file=sys.stderr,
        )
        return 1
    os.chdir(ROOT)
    try:
        if ensure_models_json(ROOT):
            print("data/models.json créé depuis config/models_catalog.json")
    except (OSError, ValueError, KeyError) as exc:
        print(
            f"Impossible de créer data/models.json depuis le catalogue : {exc!r}", file=sys.stderr
        )
        return 1
    extra = sys.argv[1:] if argv is None else argv
    sys.argv = ["streamlit", "run", str(ROOT / "src" / "app" / "Accueil.py"), *extra]
    return stcli.main() or 0


if __name__ == "__main__":
    sys.exit(main())
