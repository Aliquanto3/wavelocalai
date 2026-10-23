"""Sélecteur de modèle et état de run (story 1.10) sur la page d'essai `fixtures/picker.html`.

Les réponses de `/api/models` et `/api/models/defaults` sont simulées par le test (`page.route`) :
la liste est déterministe et Ollama n'est jamais sollicité. Le run vient de l'adaptateur `fake` du
vrai serveur, par la route de test (`POST /api/test/runs`). Tout se pilote au clavier ; axe-core ne
doit relever aucune violation, clair et sombre, sans exclusion.
"""

from __future__ import annotations

import json
import re

import pytest

from wavelocalai.errors import ERRORS

from .test_shell import assert_no_axe_violations, wait_for

NBSP = "\N{NO-BREAK SPACE}"


def model(tag, name=None, **fields):
    base = {
        "tag": tag,
        "name": name or tag,
        "provider": "ollama",
        "editor": None,
        "origin": "local",
        "kind": "chat",
        "available": True,
        "digest": "abc",
        "params_total_b": None,
        "params_active_b": None,
        "size_gb": None,
        "quantization": None,
        "context_length": None,
        "needed_gb": None,
        "fits": None,
        "tools_verified": False,
        "reasoning": False,
        "throughput_tps": None,
        "accuracy": None,
        "co2_method": "codecarbon",
        "in_catalog": False,
    }
    return {**base, **fields}


LOCAL = [
    model("gemma3:4b", size_gb=3.3, fits=True, needed_gb=4.1),
    model(
        "qwen3:4b",
        size_gb=2.6,
        fits=True,
        needed_gb=3.4,
        throughput_tps=42.5,
        tools_verified=True,
        reasoning=True,
    ),
    model(
        "qwen3:30b-a3b",
        size_gb=18.6,
        fits=False,
        needed_gb=21.4,
        required_gb=24.1,  # 21,4 × 1,1 + 0,5 : le chiffre affiché, celui d'un refus ram_guard
        params_total_b=30.0,
        params_active_b=3.0,
    ),
    model("llama3.2:3b", size_gb=2.0, fits=None),
    model("mystere:1b", origin="unknown", digest=None, fits=None),
    model("nomic-embed-text", kind="embedding", size_gb=0.3, fits=True),
    model("bge-reranker-v2", kind="reranker", size_gb=0.6, fits=True),
]
CLOUD = [
    model(
        "anthropic:claude-haiku-5-5",
        "claude-haiku-5-5",
        provider="anthropic",
        origin="cloud",
        digest=None,
        co2_method="ecologits",
    ),
    model(
        "openai:gpt-4o-mini",
        "gpt-4o-mini",
        provider="openai",
        origin="cloud",
        digest=None,
        co2_method="ecologits",
    ),
]
DEFAULT_REASON = "Le plus capable qui tient en mémoire sur ce poste."


def install_api(page, *, models=None, defaults_status=200, calls=None):
    """Simule les deux routes de lecture. `calls` reçoit les URL demandées."""
    listing = LOCAL if models is None else models

    def on_models(route):
        url = route.request.url
        if calls is not None:
            calls.append(url)
        allow_cloud = "allow_cloud=true" in url
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "models": listing + (CLOUD if allow_cloud else []),
                    "ollama_up": True,
                    "refreshed_at": "2026-10-18T10:00:00Z",
                }
            ),
        )

    def on_defaults(route):
        url = route.request.url
        if calls is not None:
            calls.append(url)
        if defaults_status != 200:
            route.fulfill(
                status=defaults_status,
                content_type="application/json",
                # Textes du vrai catalogue (`errors.py`), accents graves compris.
                body=json.dumps(
                    {
                        "code": "no_model",
                        "message": ERRORS["no_model"].message,
                        "action": ERRORS["no_model"].action,
                        "detail": {"purpose": "chat"},
                    }
                ),
            )
            return
        purpose = re.search(r"purpose=(\w+)", url).group(1)
        tags = ["qwen3:4b", "gemma3:4b"] if purpose == "arena" else ["qwen3:4b"]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"purpose": purpose, "tags": tags, "reason": DEFAULT_REASON, "source": "rule"}
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def open_page(page, fixtures_url, theme="light", **api):
    install_api(page, **api)
    page.goto(f"{fixtures_url}/picker.html?theme={theme}")
    page.locator("body[data-ready='true']").wait_for(state="attached")
    # Les listes sont chargées quand l'aide du défaut est affichée.
    page.locator("#single .wl-picker-help").filter(has_text="Proposé par défaut").wait_for()
    return page


@pytest.fixture
def picker(page, fixtures_url):
    return open_page(page, fixtures_url)


def option_names(page, scope="#single"):
    return page.locator(f"{scope} [role=option] .wl-picker-option-name").all_inner_texts()


def groups(page, scope="#single"):
    return page.locator(f"{scope} [role=group]").evaluate_all(
        """(nodes) => nodes.map((node) => [
            node.querySelector('.wl-picker-group-title').textContent,
            [...node.querySelectorAll('[role=option] .wl-picker-option-name')].map((n) => n.textContent),
        ])"""
    )


def set_cloud(page, allowed: bool):
    page.evaluate(
        """async (allowed) => {
            const { store } = await import('/static/core/store.js');
            store.set({ allowCloud: allowed });
        }""",
        allowed,
    )


# --- Sélecteur : combobox, filtre, groupes -----------------------------------------------------


def test_the_combobox_follows_the_aria_pattern(picker):
    combo = picker.get_by_role("combobox", name="Modèle", exact=True)
    assert combo.get_attribute("aria-autocomplete") == "list"
    assert combo.get_attribute("aria-expanded") == "false"
    controls = combo.get_attribute("aria-controls")
    assert picker.locator(f"#{controls}").get_attribute("role") == "listbox"
    assert picker.locator(f"#{controls}").is_hidden()
    combo.click()
    assert combo.get_attribute("aria-expanded") == "true"
    assert picker.locator(f"#{controls}").is_visible()
    assert picker.locator("#single [role=option]").count() > 0
    active = combo.get_attribute("aria-activedescendant")
    assert picker.locator(f"#{active}").get_attribute("role") == "option"


def test_the_default_is_chosen_and_its_reason_is_the_help(picker):
    assert picker.locator("#single input").input_value() == "qwen3:4b"
    help_text = picker.locator("#single .wl-picker-help").inner_text()
    assert help_text == f"Proposé par défaut{NBSP}: qwen3:4b. {DEFAULT_REASON}"
    combo = picker.get_by_role("combobox", name="Modèle", exact=True)
    help_id = combo.get_attribute("aria-describedby")
    assert picker.locator(f"#{help_id}").inner_text() == help_text


def test_typing_qwen_filters_the_list_and_enter_picks_the_first(picker):
    combo = picker.get_by_role("combobox", name="Modèle", exact=True)
    combo.click()
    picker.keyboard.type("qwen")
    assert option_names(picker) == ["qwen3:4b", "qwen3:30b-a3b"]  # le défaut d'abord
    assert "2 modèles proposés" in picker.locator("#single [role=status]").all_inner_texts()
    picker.keyboard.press("ArrowDown")
    picker.keyboard.press("Enter")
    assert combo.get_attribute("aria-expanded") == "false"
    assert combo.input_value() == "qwen3:30b-a3b"  # choisissable même s'il ne tient pas
    assert picker.evaluate("window.changes.at(-1)") == {
        "id": "single",
        "values": ["qwen3:30b-a3b"],
    }


def test_a_filter_without_match_says_so_and_escape_restores_the_choice(picker):
    combo = picker.get_by_role("combobox", name="Modèle", exact=True)
    combo.click()
    picker.keyboard.type("zzz")
    assert picker.locator("#single .wl-picker-empty").inner_text() == (
        f"Aucun modèle ne correspond à «{NBSP}zzz{NBSP}»."
    )
    assert picker.locator("#single [role=listbox]").is_hidden()
    picker.keyboard.press("Escape")
    assert combo.input_value() == "qwen3:4b"
    assert combo.get_attribute("aria-expanded") == "false"


def test_groups_are_local_first_without_embedding_or_reranker(picker):
    picker.get_by_role("combobox", name="Modèle", exact=True).click()
    assert groups(picker) == [
        [
            "Sur cette machine",
            ["qwen3:4b", "gemma3:4b", "llama3.2:3b", "mystere:1b", "qwen3:30b-a3b"],
        ]
    ]
    names = option_names(picker)
    assert "nomic-embed-text" not in names and "bge-reranker-v2" not in names
    # Règle : défaut, puis ce qui tient en mémoire, puis le besoin inconnu, puis ce qui ne tient pas.
    assert names.index("gemma3:4b") < names.index("llama3.2:3b") < names.index("qwen3:30b-a3b")


def test_the_cloud_group_exists_only_when_the_cloud_is_allowed(picker):
    picker.get_by_role("combobox", name="Modèle", exact=True).click()
    assert [title for title, _ in groups(picker)] == ["Sur cette machine"]
    set_cloud(picker, True)
    picker.locator("#single [role=option]", has_text="claude-haiku-5-5").wait_for()
    assert [title for title, _ in groups(picker)] == ["Sur cette machine", "Cloud"]
    assert groups(picker)[1][1] == ["claude-haiku-5-5", "gpt-4o-mini"]
    set_cloud(picker, False)
    picker.locator("#single [role=option]", has_text="claude-haiku-5-5").wait_for(state="detached")


def test_each_row_shows_badge_size_memory_throughput_and_pills(picker):
    picker.get_by_role("combobox", name="Modèle", exact=True).click()

    def row(name):
        return picker.locator("#single [role=option]").filter(
            has=picker.locator(
                ".wl-picker-option-name", has_text=re.compile(f"^{re.escape(name)}$")
            )
        )

    best = row("qwen3:4b")
    assert best.locator("wl-badge").inner_text().strip() == "Local"
    text = best.inner_text()
    for expected in [
        f"2,6{NBSP}Go",
        "Tient en mémoire",
        f"42,5{NBSP}tokens/s mesurés",
        "Outils vérifiés",
        "Raisonnement",
        "Par défaut",
    ]:
        assert expected in text, expected
    big = row("qwen3:30b-a3b")
    big_text = big.inner_text()
    assert f"Ne tient pas en mémoire (24,1{NBSP}Go requis)" in big_text
    assert "MoE 3B actifs" in big_text
    assert big.get_attribute("aria-disabled") is None  # reste choisissable
    assert "tokens/s" not in big_text  # pas de débit mesuré : rien d'affiché
    assert "Besoin en mémoire inconnu" in row("llama3.2:3b").inner_text()
    unknown = row("mystere:1b")
    assert unknown.locator("wl-badge").inner_text().strip() == "Origine inconnue"


def test_keyboard_alone_opens_moves_picks_and_closes(picker):
    picker.keyboard.press("Tab")  # le lien d'évitement n'existe pas sur cette page : le champ
    combo = picker.get_by_role("combobox", name="Modèle", exact=True)
    assert combo.evaluate("el => el === document.activeElement")
    picker.keyboard.press("ArrowDown")
    assert combo.get_attribute("aria-expanded") == "true"
    first = combo.get_attribute("aria-activedescendant")
    picker.keyboard.press("ArrowDown")
    second = combo.get_attribute("aria-activedescendant")
    assert second != first
    picker.keyboard.press("ArrowUp")
    assert combo.get_attribute("aria-activedescendant") == first
    picker.keyboard.press("ArrowDown")
    picker.keyboard.press("Enter")
    assert combo.input_value() == "gemma3:4b"
    picker.keyboard.press("ArrowDown")
    picker.keyboard.press("Escape")
    assert combo.get_attribute("aria-expanded") == "false"
    picker.keyboard.press("ArrowDown")
    picker.keyboard.press("Tab")  # quitter le champ ferme la liste
    assert combo.get_attribute("aria-expanded") == "false"


def test_an_unreachable_model_is_listed_with_its_reason_and_cannot_be_chosen(page, fixtures_url):
    gone = [model("hors:1b", available=False, fits=True)]
    open_page(page, fixtures_url, models=LOCAL + gone)
    page.get_by_role("combobox", name="Modèle", exact=True).click()
    row = page.locator("#single [role=option]", has_text="hors:1b")
    assert row.get_attribute("aria-disabled") == "true"
    assert "Indisponible : Ollama ne répond pas".replace(" :", f"{NBSP}:") in row.inner_text()
    row.click(force=True)  # Playwright refuse un élément désactivé : on force le clic
    assert page.locator("#single input").input_value() == "qwen3:4b"
    assert (
        page.get_by_role("combobox", name="Modèle", exact=True).get_attribute("aria-expanded")
        == "true"
    )


def test_no_model_shows_the_error_message_then_its_action(
    page_tolerating_failed_requests, fixtures_url
):
    page = page_tolerating_failed_requests
    install_api(page, models=[model("nomic-embed-text", kind="embedding")], defaults_status=404)
    page.goto(f"{fixtures_url}/picker.html")
    error = page.locator("#single wl-error")
    error.wait_for(state="visible")
    assert error.locator("p").all_inner_texts() == [
        "Aucun modèle de conversation n'est disponible pour cet usage.",
        "Installez un modèle de conversation dans Ollama (par exemple ollama pull qwen3.5:2b), "
        "puis rechargez la liste.",
    ]
    assert error.locator(".wl-error-action code").inner_text() == "ollama pull qwen3.5:2b"
    page.get_by_role("combobox", name="Modèle", exact=True).click()
    assert page.locator("#single .wl-picker-empty").inner_text() == (
        "Aucun modèle de conversation n'est disponible."
    )


# --- Mode multi ----------------------------------------------------------------------------------


def chips(page):
    return page.locator("#multi .wl-picker-chip-name").all_inner_texts()


def test_multi_ticks_three_models_then_removes_one(picker):
    combo = picker.locator("#multi").get_by_role("combobox", name="Modèles")
    assert chips(picker) == ["qwen3:4b", "gemma3:4b"]  # défauts de l'Arène
    combo.click()
    assert picker.locator("#multi [role=listbox]").get_attribute("aria-multiselectable") == "true"
    picker.locator("#multi [role=option]", has_text="llama3.2:3b").click()
    assert chips(picker) == ["qwen3:4b", "gemma3:4b", "llama3.2:3b"]
    assert combo.get_attribute("aria-expanded") == "true"  # la liste reste ouverte
    picker.locator("#multi [role=option]", has_text="gemma3:4b").click()  # décocher
    assert chips(picker) == ["qwen3:4b", "llama3.2:3b"]
    selected = picker.locator("#multi [role=option][aria-selected=true] .wl-picker-option-name")
    assert selected.all_inner_texts() == ["qwen3:4b", "llama3.2:3b"]
    assert picker.evaluate("window.changes.at(-1)") == {
        "id": "multi",
        "values": ["qwen3:4b", "llama3.2:3b"],
    }


def test_multi_chips_are_removable_by_button_and_by_backspace(picker):
    picker.get_by_role("button", name="Retirer qwen3:4b").click()
    assert chips(picker) == ["gemma3:4b"]
    picker.locator("#multi").get_by_role("combobox").focus()
    picker.keyboard.press("Backspace")
    assert chips(picker) == []
    assert picker.evaluate("document.getElementById('multi').values") == []


def test_a_model_appears_once_and_the_component_exposes_the_list(picker):
    values = picker.evaluate(
        """() => {
            const el = document.getElementById('multi');
            el.values = ['gemma3:4b', 'gemma3:4b', 'qwen3:4b', ''];
            return el.values;
        }"""
    )
    assert values == ["gemma3:4b", "qwen3:4b"]
    assert chips(picker) == ["gemma3:4b", "qwen3:4b"]
    single = picker.evaluate(
        "() => { const el = document.getElementById('single'); el.values = ['a','b']; return [el.value, el.values]; }"
    )
    assert single == ["a", ["a"]]


def test_turning_the_cloud_off_removes_a_cloud_choice_says_so_and_proposes_the_local_default(
    picker,
):
    combo = picker.locator("#single").get_by_role("combobox")
    set_cloud(picker, True)
    combo.click()
    picker.locator("#single [role=option]", has_text="claude-haiku-5-5").click()
    assert combo.input_value() == "claude-haiku-5-5"
    set_cloud(picker, False)
    notice = picker.locator("#single .wl-picker-notice")
    notice.wait_for(state="visible")
    assert notice.locator("p").inner_text() == (
        f"«{NBSP}claude-haiku-5-5{NBSP}» est retiré de la sélection{NBSP}: le cloud n'est plus autorisé."
    )
    assert combo.input_value() == ""
    assert picker.evaluate("document.getElementById('single').values") == []
    notice.get_by_role("button", name="Utiliser qwen3:4b").click()
    assert combo.input_value() == "qwen3:4b"
    assert notice.is_hidden()


def test_multi_cloud_choice_is_removed_and_the_others_stay(picker):
    set_cloud(picker, True)
    # Le sélecteur ne connaît gpt-4o-mini qu'après une liste avec cloud.
    picker.evaluate("document.getElementById('multi').reload()")
    picker.evaluate("document.getElementById('multi').values = ['gemma3:4b', 'openai:gpt-4o-mini']")
    picker.locator("#multi .wl-picker-chip-name", has_text="gpt-4o-mini").wait_for()
    set_cloud(picker, False)
    picker.locator("#multi .wl-picker-notice").wait_for(state="visible")
    assert chips(picker) == ["gemma3:4b"]
    assert "gpt-4o-mini" in picker.locator("#multi .wl-picker-notice p").inner_text()


def test_requests_stay_on_the_server_and_ask_for_the_cloud_only_when_allowed(
    page, fixtures_url, traffic
):
    calls: list[str] = []
    open_page(page, fixtures_url, calls=calls)
    assert all("allow_cloud=false" in url for url in calls) and calls
    set_cloud(page, True)
    wait_for(page, "() => document.querySelector('#single .wl-picker-help') !== null")
    assert any("allow_cloud=true" in url for url in calls)
    assert all(url.startswith("http://127.0.0.1") for url in traffic.urls)


# --- État du run ---------------------------------------------------------------------------------


STARTED: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def cancel_leftover_runs(server):
    """Un seul run de chat à la fois : un test n'en laisse aucun en cours au suivant."""
    yield
    import urllib.request

    for base_url, run_id in STARTED:
        request = urllib.request.Request(f"{base_url}/api/runs/{run_id}/cancel", method="POST")
        urllib.request.urlopen(request, timeout=5).close()  # noqa: S310
    STARTED.clear()


def start_run(page, server, script, **extra):
    response = page.request.post(
        f"{server.base_url}/api/test/runs", data={"script": script, "model": "fake:1b", **extra}
    )
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    STARTED.append((server.base_url, run_id))
    return run_id


def follow(page, run_id):
    page.evaluate("(id) => { document.getElementById('status').runId = id; }", run_id)


def stage(page):
    return page.locator("#status .wl-run-stage")


def test_the_run_goes_through_loading_generation_and_the_end(picker, server):
    run_id = start_run(
        picker,
        server,
        [
            {"load": "loading", "duration_s": 0.5},
            {"sleep_s": 1.5},
            {"load": "loaded"},
            {"text": "Bon"},
            {"sleep_s": 1.5},
            {"text": "jour"},
        ],
    )
    follow(picker, run_id)
    stage(picker).filter(has_text="Chargement du modèle en mémoire…").wait_for()
    stage(picker).filter(has_text="Génération…").wait_for()
    assert picker.locator("#status .wl-run-stop").is_visible()
    stage(picker).filter(has_text="Terminé").wait_for()
    assert picker.locator("#status .wl-run-stop").is_hidden()
    assert picker.evaluate("window.ended") == ["ok"]
    assert picker.locator("#status .wl-run-timer").inner_text().endswith(f"{NBSP}s")
    assert picker.locator("#status .wl-run-timer").get_attribute("role") == "timer"


def test_the_timer_runs_locally_and_stops_at_the_end(picker, server):
    run_id = start_run(picker, server, [{"text": "a"}, {"sleep_s": 2.2}, {"text": "b"}])
    follow(picker, run_id)
    timer = picker.locator("#status .wl-run-timer")
    wait_for(
        picker, "() => document.querySelector('#status .wl-run-timer').textContent.startsWith('1')"
    )
    stage(picker).filter(has_text="Terminé").wait_for()
    frozen = timer.inner_text()
    # Durée serveur de `run_started` à `run_ended` : 2,2 s de pause plus la charge de la machine.
    assert frozen in (f"2{NBSP}s", f"3{NBSP}s")
    picker.wait_for_timeout(700)
    assert timer.inner_text() == frozen


def test_the_stop_button_cancels_the_run(picker, server):
    run_id = start_run(picker, server, [{"text": "a"}, {"sleep_s": 30}])
    follow(picker, run_id)
    stage(picker).filter(has_text="Génération…").wait_for()
    picker.get_by_role("button", name="Arrêter").click()
    stage(picker).filter(has_text="Arrêté").wait_for()
    assert picker.evaluate("window.ended") == ["cancelled"]
    snapshot = picker.request.get(f"{server.base_url}/api/runs/{run_id}").json()
    assert snapshot["status"] == "cancelled"


def test_escape_cancels_the_run_from_the_keyboard(picker, server):
    run_id = start_run(picker, server, [{"text": "a"}, {"sleep_s": 30}])
    follow(picker, run_id)
    stage(picker).filter(has_text="Génération…").wait_for()
    picker.keyboard.press("Escape")
    stage(picker).filter(has_text="Arrêté").wait_for()
    assert picker.evaluate("window.ended") == ["cancelled"]


def test_escape_closes_an_open_list_without_stopping_the_run(picker, server):
    run_id = start_run(picker, server, [{"text": "a"}, {"sleep_s": 3}, {"text": "b"}])
    follow(picker, run_id)
    stage(picker).filter(has_text="Génération…").wait_for()
    picker.get_by_role("combobox", name="Modèle", exact=True).click()
    picker.keyboard.press("Escape")  # ferme la liste seulement
    assert (
        picker.get_by_role("combobox", name="Modèle", exact=True).get_attribute("aria-expanded")
        == "false"
    )
    assert stage(picker).inner_text() == "Génération…"
    assert picker.locator("#status .wl-run-stop").is_visible()
    stage(picker).filter(has_text="Terminé").wait_for()  # le run a continué jusqu'à sa fin


def test_a_failed_run_shows_the_error_envelope(picker, server):
    run_id = start_run(
        picker, server, [{"text": "a"}, {"fail": "ollama_down", "technical": "connexion refusée"}]
    )
    follow(picker, run_id)
    stage(picker).filter(has_text="Échec").wait_for()
    error = picker.locator("#status wl-error")
    error.wait_for(state="visible")
    assert error.get_attribute("role") == "alert"
    assert picker.evaluate("window.ended") == ["error"]


def test_an_unknown_run_ends_as_interrupted_instead_of_generating(
    page_tolerating_failed_requests, fixtures_url
):
    page = open_page(page_tolerating_failed_requests, fixtures_url)
    follow(page, "run-inconnu")
    stage(page).filter(has_text="Interrompu").wait_for()
    assert page.locator("#status .wl-run-stop").is_hidden()
    assert page.evaluate("window.ended") == ["interrupted"]


def test_escape_that_closes_a_topbar_panel_is_marked_as_handled(picker):
    """Un panneau de la barre haute qui se ferme sur Échap retient la touche (`preventDefault`) :
    `wl-run-status` n'arrête pas le run."""
    handled = picker.evaluate(
        """async () => {
            const { bindDisclosure } = await import('/static/core/disclosure.js');
            const scope = document.createElement('div');
            const button = document.createElement('button');
            const panel = document.createElement('div');
            scope.append(button, panel);
            document.body.append(scope);
            bindDisclosure({ button, panel, scope });
            button.click();
            const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
            button.dispatchEvent(event);
            const result = [panel.hidden, event.defaultPrevented];
            scope.remove();
            return result;
        }"""
    )
    assert handled == [True, True]


def test_a_finished_run_is_replayed_to_its_end(picker, server):
    run_id = start_run(picker, server, [{"text": "a"}])
    wait_for(
        picker,
        f"async () => (await (await fetch('/api/runs/{run_id}')).json()).status === 'ok'",
    )
    follow(picker, run_id)
    stage(picker).filter(has_text="Terminé").wait_for()
    assert picker.locator("#status .wl-run-stop").is_hidden()


# --- Accessibilité et trafic -----------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_with_both_lists_open_and_a_run_going(
    page, fixtures_url, server, theme
):
    open_page(page, fixtures_url, theme=theme)
    set_cloud(page, True)
    page.locator("#single").get_by_role("combobox").click()
    page.locator("#single [role=option]", has_text="claude-haiku-5-5").wait_for()
    assert_no_axe_violations(page, f"liste du choix unique ouverte, thème {theme}")
    page.keyboard.press("Escape")

    page.locator("#multi").get_by_role("combobox").click()
    page.keyboard.press("ArrowDown")
    assert_no_axe_violations(page, f"liste multiple ouverte, thème {theme}")
    page.keyboard.press("Escape")

    run_id = start_run(page, server, [{"text": "a"}, {"sleep_s": 3}, {"text": "b"}])
    follow(page, run_id)
    page.locator("#status .wl-run-stage").filter(has_text="Génération…").wait_for()
    assert_no_axe_violations(page, f"état de run, thème {theme}")
    page.locator("#status .wl-run-stage").filter(has_text="Terminé").wait_for()
    assert_no_axe_violations(page, f"état de run terminé, thème {theme}")

    set_cloud(page, False)  # l'avis de retrait ne figure que si un choix cloud existait
    page.locator("#single").get_by_role("combobox").click()
    page.locator("#single [role=option]", has_text="qwen3:30b-a3b").click()
    assert_no_axe_violations(page, f"choix fait, thème {theme}")
