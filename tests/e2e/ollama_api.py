"""
Appels à l'API locale d'Ollama depuis les tests e2e : liste des modèles installés et
déchargement d'un modèle. Jamais de téléchargement (`/api/pull` n'est pas appelé).
"""

import json
import time
import urllib.request

# Hôte Ollama de l'app (OllamaProvider, défaut non configurable) : la machine locale.
OLLAMA_URL = "http://localhost:11434"


def normalize_tag(tag: str) -> str:
    """« gemma3 » et « gemma3:latest » désignent le même modèle."""
    return tag if ":" in tag else f"{tag}:latest"


def ollama_get(path: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(f"{OLLAMA_URL}{path}", timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def ollama_post(path: str, payload: dict, timeout: float = 60.0) -> dict:
    request = urllib.request.Request(  # noqa: S310 - hôte local fixe
        f"{OLLAMA_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
        lines = resp.read().decode("utf-8").strip().splitlines()
    return json.loads(lines[-1]) if lines else {}


def unload_model(tag: str) -> None:
    """Décharge un modèle de la mémoire d'Ollama (keep_alive 0) : le prochain appel repart
    à froid et mesure le chargement."""
    ollama_post("/api/generate", {"model": tag, "keep_alive": 0})


def loaded_models() -> set[str]:
    """Modèles chargés en mémoire dans Ollama (`/api/ps`), tags normalisés."""
    return {
        normalize_tag(m.get("model") or m.get("name") or "")
        for m in ollama_get("/api/ps").get("models", [])
    }


def ensure_cold(tag: str, timeout_s: float = 30.0) -> None:
    """Décharge `tag` et vérifie par `/api/ps` qu'il n'est plus en mémoire : le prochain appel
    mesure un vrai premier chargement."""
    unload_model(tag)
    deadline = time.monotonic() + timeout_s
    while normalize_tag(tag) in loaded_models():
        if time.monotonic() > deadline:
            raise AssertionError(
                f"{tag} toujours chargé dans Ollama (/api/ps) après {timeout_s:.0f} s"
            )
        time.sleep(0.5)
