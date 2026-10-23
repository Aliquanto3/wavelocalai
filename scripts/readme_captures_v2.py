r"""Captures d'écran de la v2 pour le README (story 8.3), produites par Playwright sur des doublures.

Aucune donnée réelle : le serveur est celui de l'application, en dossier de données temporaire (jamais
`data/`), Ollama est un faux Ollama local, les modèles sont les `fake` du mode test (« Alpha 1B »,
« Factice 1B »), leurs réponses viennent de scripts, et le seul document indexé est la note de cadrage
fictive des tests (`tests/v2/workshop_note.py`). Aucune requête ne sort de 127.0.0.1, aucune clé cloud.
Le matériel montré (processeur, mémoire, accélérateur) est fictif et fixe (`HARDWARE`, `DEMO_GPU`) :
jamais celui du poste qui fait la capture (dépôt public).

Écrit dans `docs/assets/` : `v2-accueil.png`, `v2-arene.png`, `v2-documents.png`, `v2-agents.png`,
`v2-sobriete.png`, puis `v2-demo.gif` (ces captures à la suite, si Pillow est installé).

Usage (depuis la racine du dépôt, après `uv sync`) :

    $env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    .venv\Scripts\python scripts/readme_captures_v2.py

Sans la variable, Chromium de Playwright (`python -m playwright install chromium`).
"""

# isort: skip_file  (imports après `sys.path.insert` : l'ordre y est voulu)
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "docs" / "assets"
GIF_SECONDS = 2.5
GIF_WIDTH = 1100

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.v2.conftest import closed_port  # noqa: E402
from tests.v2.e2e.conftest import (  # noqa: E402
    CHROMIUM_ARGS,
    CHROMIUM_ENV,
    EXTERNAL_URL,
    PAGE_TIMEOUT_MS,
    VIEWPORT,
    Backend,
    FakeOllama,
)
from tests.v2.e2e.test_agents_solo import MODEL as AGENT_MODEL  # noqa: E402
from tests.v2.e2e.test_agents_solo import ask as ask_agent  # noqa: E402
from tests.v2.e2e.test_agents_solo import warm_up  # noqa: E402
from tests.v2.e2e.test_agents_solo import call  # noqa: E402
from tests.v2.e2e.test_agents_solo import install_models as install_agent_models  # noqa: E402
from tests.v2.e2e.test_agents_solo import script as script_agent  # noqa: E402
from tests.v2.e2e.test_agents_solo import steps  # noqa: E402
from tests.v2.e2e.test_arena import (  # noqa: E402
    MODELS,
)
from tests.v2.e2e.test_arena import install_models as install_arena_models  # noqa: E402
from tests.v2.e2e.test_arena import (  # noqa: E402
    launch,
    scripted,
    wait_banner,
)
from tests.v2.e2e.test_discussion import (  # noqa: E402
    ask,
    import_docs,
    script_model,
    source_of,
    wait_done,
)
from tests.v2.e2e.test_flow1 import JUDGE, SCRIPTS  # noqa: E402
from tests.v2.e2e.test_flow2 import DOCX, wait_discussion  # noqa: E402
from tests.v2.e2e.test_home import wait_card  # noqa: E402
from tests.v2.e2e.test_memory_guard import install_chat_models  # noqa: E402
from tests.v2.e2e.test_shell import wait_for, wait_ready  # noqa: E402
from tests.v2.e2e.test_sobriety import set_gpu  # noqa: E402
from tests.v2.e2e.test_topbar import CLOUD_CO2, LOCAL_CO2, run_scripted  # noqa: E402
from tests.v2.workshop_note import ANSWER_SENTENCE, FILE_NAME, make_note  # noqa: E402

# Matériel fictif et neutre, jamais celui du poste qui capture : le serveur lit psutil à travers un
# `sitecustomize` (dossier temporaire en tête de PYTHONPATH) qui rend ces valeurs ; le GPU passe par
# la route de test `POST /api/test/gpu`.
HARDWARE = {"cpu_percent": 18.0, "memory_total_gb": 32.0, "memory_used_gb": 12.4}
DEMO_GPU = {
    "name": "GPU de démonstration",
    "memory_used_gb": 2.4,
    "memory_total_gb": 8.0,
    "temperature_c": 55.0,
    "thermal_throttle": False,
}
SITECUSTOMIZE = """\
import psutil
from collections import namedtuple

_GIB = 1024**3
_total, _used = {memory_total_gb} * _GIB, {memory_used_gb} * _GIB
_svmem = namedtuple("svmem", "total available percent used free")
_memory = _svmem(_total, _total - _used, round(100 * _used / _total, 1), _used, _total - _used)
psutil.virtual_memory = lambda: _memory
psutil.cpu_percent = lambda interval=None, percpu=False: {cpu_percent}
"""

DOCUMENTS_ANSWER = [
    {"text": "Chaque consultant apporte son portable de seize gigaoctets,"},
    {"text": " sans carte graphique [1]."},
]

CAPTURES = ["v2-accueil", "v2-arene", "v2-documents", "v2-agents", "v2-sobriete"]


PARAMS_B = {"fake:a": 1, "fake:b": 2, "fake:c": 3, "fake:d": 8}  # un juge de plus de 4 milliards
SIZED_MODELS = [
    {**m, "params_total_b": PARAMS_B.get(m["tag"]), "params_active_b": PARAMS_B.get(m["tag"])}
    for m in MODELS
]


def shot(page, name: str) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)  # les animations de fin d'affichage sont posées
    path = ASSETS / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  {path.relative_to(ROOT)}")


def capture_home_and_arena(context, server) -> None:
    page = context.new_page()
    install_arena_models(page, SIZED_MODELS, defaults=("fake:a", "fake:b", "fake:c"))
    scripted(page, server, SCRIPTS, [], judge=JUDGE)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "system", "Disponible")
    wait_for(page, "() => document.querySelector('[data-demo]')?.dataset.state === 'ready'")
    shot(page, "v2-accueil")
    page.locator("[data-demo]").get_by_role("link", name="Lancer une comparaison").click()
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 3")
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1"
    )
    launch(page)
    wait_banner(page, "Comparaison terminée")
    wait_for(page, "() => document.querySelectorAll('.arena-rank-item').length === 1")
    page.set_viewport_size({"width": VIEWPORT["width"], "height": 1500})  # classement et colonnes
    shot(page, "v2-arene")
    page.close()


def capture_documents(context, server) -> None:
    page = context.new_page()
    install_chat_models(page)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    import_docs(page, server, **{FILE_NAME: (DOCX, make_note())})
    page.evaluate("location.hash = '#/documents'")
    wait_discussion(page)
    # Une réponse qui répond à la question (celle des tests, « Le chat dort… », ne sert qu'aux tests).
    script_model(page, server, {"sleep_s": 0.5}, *DOCUMENTS_ANSWER)
    ask(page, "Que doit apporter chaque consultant à l'atelier ?")
    wait_done(page)
    cited = source_of(page, FILE_NAME).filter(has_text=ANSWER_SENTENCE).first
    cited.get_by_role("button", name="Ouvrir l'extrait", exact=False).first.click()
    cited.locator("mark").wait_for()
    shot(page, "v2-documents")
    page.close()


def capture_agents(context, server) -> None:
    page = context.new_page()
    install_agent_models(page, (AGENT_MODEL,), ("fake:1b",))
    warm_up(server)
    page.goto(f"{server.base_url}/#/agents/seul")
    wait_ready(page)
    wait_for(page, "() => document.querySelectorAll('.agents-tool-list li').length > 0")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    script_agent(
        page,
        server,
        [{"text": "Je calcule la somme."}, call("calculator", expression="1250 + 340 + 87")],
        [{"text": "Le total est **1 677**."}],
    )
    ask_agent(page, "Additionne 1 250, 340 et 87.")
    wait_for(page, "() => document.querySelectorAll('.wl-msg-assistant .wl-md strong').length > 0")
    steps(page).nth(1).get_by_role("button").click()
    shot(page, "v2-agents")
    page.close()


def capture_sobriety(context, server) -> None:
    page = context.new_page()
    set_gpu(page, server, DEMO_GPU)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    run_scripted(page, server, kind="rag", origin="cloud", co2=CLOUD_CO2)
    page.goto(f"{server.base_url}/#/sobriete")
    wait_ready(page)
    wait_for(
        page,
        '() => document.querySelector(\'[data-screen="sobriety"] [data-card="cpu"]\')'
        "?.getAttribute('aria-busy') === 'false'",
    )
    wait_for(page, "() => document.querySelector('.sob-carbon')?.innerText.includes('mg')")
    shot(page, "v2-sobriete")
    page.close()


def build_gif() -> None:
    try:
        from PIL import Image
    except ImportError:
        print("Pillow absent : pas de GIF (les captures PNG suffisent ; `uv pip install pillow`).")
        return
    frames = []
    for name in CAPTURES:
        image = Image.open(ASSETS / f"{name}.png").convert("RGB")
        height = round(image.height * GIF_WIDTH / image.width)
        frames.append(image.resize((GIF_WIDTH, height)).quantize(colors=128))
    target = ASSETS / "v2-demo.gif"
    frames[0].save(
        target,
        save_all=True,
        append_images=frames[1:],
        duration=int(GIF_SECONDS * 1000),
        loop=0,
        optimize=True,
    )
    print(f"  {target.relative_to(ROOT)} ({target.stat().st_size // 1024} Ko)")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    fake_ollama = FakeOllama(closed_port())
    fake_ollama.start()
    with tempfile.TemporaryDirectory(prefix="wavelocalai-captures-") as folder:
        doubles = Path(folder) / "doubles"
        doubles.mkdir()
        (doubles / "sitecustomize.py").write_text(
            SITECUSTOMIZE.format(**HARDWARE), encoding="utf-8"
        )
        python_path = os.pathsep.join(filter(None, [str(doubles), os.environ.get("PYTHONPATH")]))
        backend = Backend(
            Path(folder), ollama_port=fake_ollama.port, env={"PYTHONPATH": python_path}
        )
        server = backend.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.environ.get(CHROMIUM_ENV) or None, args=CHROMIUM_ARGS
                )
                context = browser.new_context(
                    viewport=VIEWPORT, locale="fr-FR", color_scheme="light"
                )
                context.route(
                    EXTERNAL_URL, lambda route: route.abort()
                )  # rien ne sort de la machine
                context.set_default_timeout(PAGE_TIMEOUT_MS)
                print("Captures :")
                capture_home_and_arena(context, server)
                capture_documents(context, server)
                capture_agents(context, server)
                capture_sobriety(context, server)
                browser.close()
        finally:
            backend.stop()
            fake_ollama.stop()
    build_gif()


if __name__ == "__main__":
    main()
