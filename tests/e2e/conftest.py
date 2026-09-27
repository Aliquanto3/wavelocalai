"""
Banc des tests e2e : l'app réelle dans un sous-processus, Ollama et de petits modèles réels,
Chromium piloté par Playwright.

- L'app tourne sur un port libre ; tout ce qu'elle peut écrire pendant les parcours (Chroma,
  CodeCarbon, historique d'émissions, fichiers de l'agent, base et exports de benchmark) va
  dans un dossier temporaire (launch_app.py). Les données réelles (USER_DATA_PATHS) sont
  vérifiées intactes en fin de session.
- Aucun fournisseur simulé ; aucun modèle ni navigateur téléchargé. Ollama arrêté ou modèle
  absent : échec explicite qui dit quoi faire.
- Aucune requête hors de la machine : le navigateur bloque et relève toute requête et tout
  WebSocket externes ; le processus serveur consigne toute connexion ou résolution DNS
  externe dès son démarrage (launch_app.py). Le journal est vérifié après chaque test et, en
  entier, à l'arrêt de l'app ; ses sous-processus éventuels ne sont pas couverts.

Variables d'environnement : voir README.md.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.e2e import helpers
from tests.e2e.launch_app import EXTERNAL_LOG_NAME, is_external_url
from tests.e2e.ollama_api import OLLAMA_URL, normalize_tag, ollama_get

ROOT_DIR = Path(__file__).resolve().parents[2]
LAUNCHER = Path(__file__).resolve().parent / "launch_app.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Rôle → (variable d'environnement, tag Ollama par défaut). Petits modèles du catalogue
# (config/models_catalog.json), ceux des parcours d'audit.
MODEL_ENV = {
    "chat": ("WAVELOCALAI_E2E_MODEL_CHAT", "gemma3:1b"),
    "small": ("WAVELOCALAI_E2E_MODEL_SMALL", "granite4:350m"),
    "agent": ("WAVELOCALAI_E2E_MODEL_AGENT", "qwen3.5:0.8b"),
    # Juge de l'Arène : par défaut, le modèle de chat.
    "judge": ("WAVELOCALAI_E2E_MODEL_JUDGE", None),
}
CHROMIUM_ENV = "WAVELOCALAI_E2E_CHROMIUM"
# Services de fond de Chromium (mises à jour de composants, synchronisation…) : coupés, pour
# qu'aucune requête ne quitte la machine, même hors des pages.
CHROMIUM_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-sync",
    "--no-pings",
]
TIMEOUT_ENV = "WAVELOCALAI_E2E_TIMEOUT_S"

# Largeur de la cible principale (EXPERIENCE.md, Responsive) ; fenêtre haute : le contenu
# défile dans un conteneur interne.
VIEWPORT = {"width": 1440, "height": 1100}

# Environnement de l'app : télémétries coupées, aucun téléchargement Hugging Face, clés cloud
# et SMTP vides (le .env local n'écrase pas une variable déjà définie, même vide).
APP_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "ANONYMIZED_TELEMETRY": "False",
    "CREWAI_DISABLE_TELEMETRY": "true",
    "OTEL_SDK_DISABLED": "true",
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "LANGCHAIN_TRACING_V2": "false",
    "LANGSMITH_TRACING": "false",
    "DO_NOT_TRACK": "1",
    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    "MISTRAL_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "SMTP_SERVER": "",
    "SMTP_PORT": "587",
    "SMTP_USER": "",
    "SMTP_PASSWORD": "",
    "PYTHONUNBUFFERED": "1",
}

# Données de l'utilisateur à laisser intactes : tout ce que l'app écrit par défaut
# (src/core/config.py, agent_tools.OUTPUT_DIR, BenchmarkRepository, MetricsExporter).
USER_DATA_PATHS = (
    ROOT_DIR / "data" / "chroma",
    ROOT_DIR / "data" / "logs",
    ROOT_DIR / "data" / "exports",
    ROOT_DIR / "data" / "benchmarks.db",
    ROOT_DIR / "data" / "models.json",
    ROOT_DIR / "outputs",
)


def _timeout_ms() -> int:
    """Délai de génération (WAVELOCALAI_E2E_TIMEOUT_S) en ms : un nombre de secondes > 0."""
    raw = os.environ.get(TIMEOUT_ENV)
    if raw is None or raw == "":
        return helpers.GENERATION_TIMEOUT_MS
    try:
        seconds = float(raw)
    except ValueError:
        seconds = 0.0
    if not seconds > 0 or seconds == float("inf"):
        pytest.fail(f"{TIMEOUT_ENV} doit être un nombre de secondes > 0 (reçu « {raw} »)")
    return int(seconds * 1000)


# ---------------------------------------------------------------------------
# Rapport : couleurs natives de Streamlit relevées par axe (listées, jamais masquées)
# ---------------------------------------------------------------------------


def pytest_terminal_summary(terminalreporter):
    if not helpers.AXE_NATIVE_FINDINGS:
        return
    terminalreporter.section(
        "axe-core : contrastes non imputables au thème (couleurs natives, composants inactifs)"
    )
    for f in helpers.AXE_NATIVE_FINDINGS:
        terminalreporter.write_line(
            f"{f['scheme']:5} {f['page']:16} {f['category']} : {f['ratio']}:1 (attendu "
            f"{f['expected']}) texte {f['fg']} sur {f['bg']} : {f['html']}"
        )


# ---------------------------------------------------------------------------
# Modèles et Ollama
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_models() -> dict[str, str]:
    """Tag Ollama de chaque rôle, lu dans les variables d'environnement."""
    models = {}
    for role, (env, default) in MODEL_ENV.items():
        value = os.environ.get(env) or default
        models[role] = value
    models["judge"] = models["judge"] or models["chat"]
    return models


@pytest.fixture(scope="session")
def ollama_models() -> dict[str, dict]:
    """Modèles installés dans Ollama ({tag: entrée de /api/tags}). Ollama doit répondre."""
    try:
        tags = ollama_get("/api/tags")
    except (urllib.error.URLError, OSError, ValueError) as e:
        pytest.fail(
            f"Ollama ne répond pas sur {OLLAMA_URL} ({e}). Les tests e2e exigent Ollama : "
            "démarrez-le (ollama serve), puis relancez la suite.",
            pytrace=False,
        )
    return {m["model"]: m for m in tags.get("models", []) if m.get("model")}


@pytest.fixture(scope="session")
def require_models(e2e_models, ollama_models):
    """`require_models("chat", "small")` : échoue si un modèle de ces rôles n'est pas
    installé, en nommant le modèle et la commande (hors des tests, jamais par eux)."""

    def check(*roles: str) -> list[str]:
        tags = []
        for role in roles:
            tag = e2e_models[role]
            if normalize_tag(tag) not in {normalize_tag(t) for t in ollama_models}:
                env = MODEL_ENV[role][0]
                pytest.fail(
                    f"Modèle absent d'Ollama : {tag} (rôle « {role} »). Installez-le avant la "
                    f"suite (ollama pull {tag}), ou choisissez un modèle installé avec {env}. "
                    "Les tests ne téléchargent aucun modèle.",
                    pytrace=False,
                )
            tags.append(tag)
        return tags

    return check


def embedding_repo_id() -> str:
    """Dépôt Hugging Face du modèle d'embedding par défaut de l'app (src/core/rag_engine.py) :
    un nom court est résolu dans « sentence-transformers », comme le fait la bibliothèque."""
    from src.core.rag_engine import DEFAULT_EMBEDDING_MODEL

    name = DEFAULT_EMBEDDING_MODEL
    return name if "/" in name else f"sentence-transformers/{name}"


def embedding_model_available() -> bool:
    """Modèle d'embedding de l'assistant documentaire disponible sans téléchargement : un
    dossier de data/models/embeddings (choisi par la page), ou le modèle par défaut en cache."""
    local = ROOT_DIR / "data" / "models" / "embeddings"
    if local.is_dir() and any(p.is_dir() for p in local.iterdir()):
        return True
    from huggingface_hub import try_to_load_from_cache

    return isinstance(try_to_load_from_cache(embedding_repo_id(), "modules.json"), str)


@pytest.fixture(scope="session")
def require_embedding():
    if not embedding_model_available():
        repo = embedding_repo_id()
        pytest.fail(
            "Aucun modèle d'embedding local : placez-en un dans data/models/embeddings/, ou "
            f'mettez {repo} en cache une fois, hors des tests : python -c "from '
            f"sentence_transformers import SentenceTransformer; SentenceTransformer('{repo}')\". "
            "Les tests ne téléchargent rien.",
            pytrace=False,
        )


# ---------------------------------------------------------------------------
# Données de l'utilisateur
# ---------------------------------------------------------------------------


def _snapshot(paths) -> dict[str, tuple[int, int]]:
    """(taille, date de modification) de chaque fichier des chemins donnés."""
    state = {}
    for base in paths:
        files = [base] if base.is_file() else (base.rglob("*") if base.is_dir() else [])
        for path in files:
            if path.is_file():
                stat = path.stat()
                state[str(path.relative_to(ROOT_DIR))] = (stat.st_size, stat.st_mtime_ns)
    return state


@pytest.fixture(scope="session", autouse=True)
def user_data_untouched():
    """Données réelles (USER_DATA_PATHS) : identiques avant et après la suite."""
    before = _snapshot(USER_DATA_PATHS)
    yield
    after = _snapshot(USER_DATA_PATHS)
    changed = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    assert not changed, f"Données de l'utilisateur modifiées par la suite e2e : {changed}"


# ---------------------------------------------------------------------------
# Serveur SMTP local (puits) : l'envoi d'email n'est jamais réel
# ---------------------------------------------------------------------------


@dataclass
class SmtpSink:
    port: int
    connections: list[float] = field(default_factory=list)

    @property
    def env(self) -> dict[str, str]:
        """Configuration SMTP de l'app : ce puits local, identifiants factices."""
        return {
            "SMTP_SERVER": "127.0.0.1",
            "SMTP_PORT": str(self.port),
            "SMTP_USER": "e2e@example.com",
            "SMTP_PASSWORD": "e2e-sans-envoi",
        }


@pytest.fixture(scope="session")
def smtp_sink():
    """Puits SMTP sur la machine locale : compte les connexions, n'accepte aucun message."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    server.settimeout(0.5)
    sink = SmtpSink(port=server.getsockname()[1])
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            sink.connections.append(time.time())
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield sink
    stop.set()
    server.close()
    thread.join(timeout=2)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


@dataclass
class RunningApp:
    base_url: str
    data_dir: Path
    process: subprocess.Popen
    log_path: Path

    @property
    def external_log(self) -> Path:
        return self.data_dir / EXTERNAL_LOG_NAME

    def server_log(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def external_connections(self) -> list[str]:
        if not self.external_log.is_file():
            return []
        text = self.external_log.read_text(encoding="utf-8", errors="replace")
        return [line for line in text.splitlines() if line]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(app: RunningApp, timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if app.process.poll() is not None:
            pytest.fail(
                f"L'app s'est arrêtée au démarrage :\n{app.server_log()[-3000:]}", pytrace=False
            )
        try:
            with urllib.request.urlopen(
                f"{app.base_url}/_stcore/health", timeout=2
            ) as r:  # noqa: S310
                if r.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    pytest.fail(f"L'app ne répond pas après {timeout_s:.0f} s :\n{app.server_log()[-3000:]}")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    # Session propre au lanceur (start_new_session) : Streamlit et ses enfants.
    group = hasattr(os, "killpg")
    try:
        if group:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=20)
    except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
        try:
            if group:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait(timeout=10)


@pytest.fixture(scope="module")
def app_extra_env() -> dict[str, str]:
    """Variables ajoutées à l'environnement de l'app ; un module de test la redéfinit."""
    return {}


@pytest.fixture(scope="module")
def app(ollama_models, app_extra_env, tmp_path_factory):
    """L'app réelle, lancée pour un module de tests, données dans un dossier temporaire."""
    data_dir = tmp_path_factory.mktemp("app-data")
    (data_dir / "tmp").mkdir()
    log_path = data_dir / "server.log"
    port = _free_port()
    tmp = str(data_dir / "tmp")
    env = {**os.environ, **APP_ENV, "TMPDIR": tmp, "TMP": tmp, "TEMP": tmp, **app_extra_env}
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(  # noqa: S603
            [sys.executable, str(LAUNCHER), str(port), str(data_dir)],
            cwd=ROOT_DIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    running = RunningApp(f"http://localhost:{port}", data_dir, process, log_path)
    try:
        _wait_healthy(running)
        yield running
    finally:
        _stop(process)
    # Journal entier, depuis le démarrage : import, lancement, entre les tests, arrêt.
    external = running.external_connections()
    assert external == [], f"Connexions du serveur hors de la machine : {external}"


# ---------------------------------------------------------------------------
# Navigateur
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser():
    """Chromium de Playwright (déjà installé : `python -m playwright install chromium`), ou
    l'exécutable de WAVELOCALAI_E2E_CHROMIUM. Aucun téléchargement pendant les tests."""
    from playwright.sync_api import sync_playwright

    executable = os.environ.get(CHROMIUM_ENV) or None
    with sync_playwright() as p:
        try:
            chromium = p.chromium.launch(executable_path=executable, args=CHROMIUM_ARGS)
        except Exception as e:  # noqa: BLE001
            pytest.fail(
                "Chromium introuvable pour Playwright. Installez-le une fois, hors des tests : "
                f"python -m playwright install chromium ; ou indiquez un exécutable dans "
                f"{CHROMIUM_ENV}. Détail : {(str(e).splitlines() or [repr(e)])[0]}",
                pytrace=False,
            )
        yield chromium
        chromium.close()


@pytest.fixture
def color_scheme() -> str:
    """Thème demandé au navigateur ; paramétrer `color_scheme` pour le sombre."""
    return "light"


@pytest.fixture
def context(browser, app, color_scheme):
    """Contexte de navigation : requêtes hors de la machine bloquées et relevées. En fin de
    test, aucune requête externe, ni du navigateur ni du serveur."""
    ctx = browser.new_context(viewport=VIEWPORT, color_scheme=color_scheme, locale="fr-FR")
    blocked: list[str] = []

    def guard(route):
        blocked.append(route.request.url)
        route.abort()

    def guard_ws(ws):
        blocked.append(ws.url)
        ws.close()

    ctx.route(is_external_url, guard)
    ctx.route_web_socket(is_external_url, guard_ws)
    ctx.set_default_timeout(helpers.PAGE_TIMEOUT_MS)
    already = len(app.external_connections())
    yield ctx
    ctx.close()
    assert not blocked, f"Requêtes du navigateur hors de la machine : {blocked}"
    external = app.external_connections()[already:]
    assert not external, f"Connexions du serveur hors de la machine : {external}"


@pytest.fixture
def page(context):
    """Nouvel onglet (la page à ouvrir : helpers.goto). Exceptions JavaScript relevées."""
    pg = context.new_page()
    js_errors: list[str] = []
    pg.on("pageerror", lambda e: js_errors.append(str(e)))
    yield pg
    assert not js_errors, f"Exceptions JavaScript : {js_errors}"


@pytest.fixture
def generation_timeout_ms() -> int:
    """Délai d'une génération réelle (WAVELOCALAI_E2E_TIMEOUT_S, 300 s par défaut)."""
    return _timeout_ms()


@pytest.fixture(scope="session")
def test_document() -> Path:
    return FIXTURES_DIR / "doc_test_rag.txt"


@pytest.fixture(scope="session")
def report_dir(tmp_path_factory) -> Path:
    """Dossier des rapports (axe) de la session."""
    path = tmp_path_factory.getbasetemp() / "e2e-reports"
    path.mkdir(exist_ok=True)
    return path
