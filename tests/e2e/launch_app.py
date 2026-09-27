"""
Lanceur de l'app pour les tests e2e : fournisseurs réels (Ollama), données dans un dossier
temporaire.

    python tests/e2e/launch_app.py <port> <dossier_de_données>

Tout ce que l'app peut écrire pendant les parcours est redirigé vers <dossier_de_données>
(`redirect_data`) : Chroma, suivi carbone (CodeCarbon) et historique d'émissions, fichiers
des outils de l'agent (`outputs/`), base et exports de benchmark. Jamais `data/` ni
`outputs/` réels. Aucun fournisseur n'est simulé. L'environnement (télémétrie coupée, clés cloud vides, SMTP) est préparé par
`conftest.py`.

Toute connexion réseau de ce processus (le serveur, pas ses éventuels sous-processus) vers
une adresse autre que la machine locale, ainsi que toute résolution DNS d'un nom externe, est
consignée dans <dossier_de_données>/external_connections.log, dès le démarrage. `conftest.py`
vérifie ce journal après chaque test et, en entier, à l'arrêt de l'app.

Délai court (optionnel) : WAVELOCALAI_E2E_TIMEOUT_TAGS (tags Ollama séparés par des
virgules) et WAVELOCALAI_E2E_SHORT_TIMEOUT_S (secondes, > 0) imposent ce délai d'inférence aux
seuls modèles cités, pour observer « Délai dépassé » avec un vrai modèle ; les autres gardent
le délai de l'application.
"""

import ipaddress
import os
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

ROOT_DIR = Path(__file__).resolve().parents[2]

EXTERNAL_LOG_NAME = "external_connections.log"
TIMEOUT_TAGS_ENV = "WAVELOCALAI_E2E_TIMEOUT_TAGS"
SHORT_TIMEOUT_S_ENV = "WAVELOCALAI_E2E_SHORT_TIMEOUT_S"

_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", ""}
_HOSTNAME = socket.gethostname().lower()


def is_local_host(host) -> bool:
    """Adresse ou nom de la machine locale (boucle locale, ou son propre nom d'hôte)."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    host = str(host).strip("[]").lower()
    if host in _LOCAL_NAMES or host == _HOSTNAME:
        return True
    try:
        address = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def is_external_url(url: str) -> bool:
    """URL réseau (http, https, ws, wss) vers une autre machine ; data:, blob: et about: ne
    sortent pas de la machine."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https", "ws", "wss"}:
        return False
    return not is_local_host(parts.hostname or "")


def install_network_audit(log_path: Path) -> None:
    """Consigne les connexions et résolutions DNS vers l'extérieur (hook d'audit Python)."""
    lock = threading.Lock()

    def record(line: str) -> None:
        with lock, open(log_path, "a", encoding="utf-8") as log:
            log.write(line + "\n")

    def hook(event, args):
        if event == "socket.connect":
            address = args[1]
            # Socket Unix (chemin) : local par nature.
            if isinstance(address, tuple) and address and not is_local_host(address[0]):
                record(f"connect {address[0]}:{address[1] if len(address) > 1 else ''}")
        elif event == "socket.getaddrinfo":
            host = args[0]
            if not is_local_host(host):
                record(f"dns {host}")

    sys.addaudithook(hook)


def redirect_data(data_dir: Path) -> None:
    """Redirige vers `data_dir` toutes les écritures que l'app peut faire pendant les
    parcours (attributs de module lus à l'appel ; aucun fichier de src/ modifié)."""
    import src.core.agent_tools as agent_tools
    import src.core.config as config
    import src.core.green_monitor as green_monitor
    import src.core.rag.vector_store as vector_store
    from src.core.exporters.metrics_exporter import MetricsExporter
    from src.core.repositories.benchmark_repository import BenchmarkRepository

    chroma_dir = data_dir / "chroma"
    logs_dir = data_dir / "logs"
    outputs_dir = data_dir / "outputs"
    for folder in (chroma_dir, logs_dir, outputs_dir):
        folder.mkdir(parents=True, exist_ok=True)
    vector_store.CHROMA_DIR = chroma_dir
    green_monitor.LOGS_DIR = logs_dir
    config.CHROMA_DIR = chroma_dir
    config.LOGS_DIR = logs_dir
    config.EMISSIONS_DIR = logs_dir / "emissions"
    config.BENCHMARKS_DIR = logs_dir / "benchmarks"
    # Rapports, documents et graphiques des outils de l'agent (outputs/ par défaut).
    agent_tools.OUTPUT_DIR = outputs_dir

    # Base de benchmark (data/benchmarks.db) et exports (data/exports) : chemins par défaut
    # calculés dans le constructeur, remplacés ici.
    repository_init = BenchmarkRepository.__init__
    exporter_init = MetricsExporter.__init__

    def repository(self, db_path=None):
        repository_init(self, db_path or data_dir / "benchmarks.db")

    def exporter(self, output_dir=None):
        exporter_init(self, output_dir or data_dir / "exports")

    BenchmarkRepository.__init__ = repository
    MetricsExporter.__init__ = exporter


def short_timeout_s() -> float:
    """Délai court de WAVELOCALAI_E2E_SHORT_TIMEOUT_S (0,05 s par défaut), nombre > 0."""
    raw = os.environ.get(SHORT_TIMEOUT_S_ENV, "0.05")
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if not value > 0:
        raise SystemExit(f"{SHORT_TIMEOUT_S_ENV} doit être un nombre > 0 (reçu « {raw} »)")
    return value


def apply_short_timeouts() -> None:
    """Délai d'inférence court pour les tags de WAVELOCALAI_E2E_TIMEOUT_TAGS (vrai appel,
    interrompu par le délai de l'application). Tags comparés sous forme normalisée
    (« gemma3 » = « gemma3:latest »)."""
    from tests.e2e.ollama_api import normalize_tag

    raw = os.environ.get(TIMEOUT_TAGS_ENV, "")
    tags = {normalize_tag(t.strip()) for t in raw.split(",") if t.strip()}
    if not tags:
        return
    short_s = short_timeout_s()

    from src.core.inference_service import InferenceService

    original = InferenceService.run_inference

    async def run_inference(model_tag, messages, *args, **kwargs):
        if model_tag and normalize_tag(model_tag) in tags:
            # Délai en 6e position de la signature d'origine, ou en argument nommé.
            if len(args) >= 4:
                args = (*args[:3], short_s, *args[4:])
            else:
                kwargs["timeout"] = short_s
        return await original(model_tag, messages, *args, **kwargs)

    InferenceService.run_inference = staticmethod(run_inference)


def main(argv: list[str]) -> None:
    port, data_dir = int(argv[1]), Path(argv[2]).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    install_network_audit(data_dir / EXTERNAL_LOG_NAME)

    sys.path.insert(0, str(ROOT_DIR))
    # .streamlit/config.toml (serveur sur localhost, thème) est lu dans le dossier courant.
    os.chdir(ROOT_DIR)
    redirect_data(data_dir)
    apply_short_timeouts()

    from streamlit.web.cli import main as streamlit_main

    sys.argv = [
        "streamlit",
        "run",
        str(ROOT_DIR / "src" / "app" / "Accueil.py"),
        "--server.headless",
        "true",
        "--server.port",
        str(port),
        "--server.fileWatcherType",
        "none",
        "--browser.gatherUsageStats",
        "false",
    ]
    streamlit_main()


if __name__ == "__main__":
    main(sys.argv)
