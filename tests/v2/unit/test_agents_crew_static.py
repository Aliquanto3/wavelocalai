"""Écran Équipe d'agents (story 6.6) : règles de structure, de textes et d'AD-20, sans navigateur. Les
parcours (schéma, suivi, configuration, rapport, email, axe) vivent dans
`tests/v2/e2e/test_agents_crew.py`."""

from __future__ import annotations

import re

from .static_files import STATIC, catalog, read, registry_text, text_file_names

SCRIPTS = [
    "screens/agents-crew.js",
    "screens/agents-crew-track.js",
    "screens/agents-crew-config.js",
    "components/wl-team-graph.js",
]
CATALOG = catalog()


def flat(value, prefix=""):
    if isinstance(value, dict):
        return {k for name, v in value.items() for k in flat(v, f"{prefix}{name}.")}
    return {prefix.rstrip(".")}


def test_the_crew_screen_is_available_with_its_loader_and_its_path_parameter():
    assert re.search(
        r'id: "agents-crew",\s*path: "/agents/equipe",\s*param: "run_id",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./\.\./screens/agents-crew\.js"\)',
        registry_text(),
    )


def test_every_crew_text_is_used_and_exists():
    assert "crew" in text_file_names() and (STATIC / "i18n/fr/crew.json").is_file()
    code = "\n".join(read(name) for name in SCRIPTS)
    used = set(re.findall(r"""["'`]crew\.([\w.]+)["'`]""", code))
    # Noms composés à l'exécution : `crew.journal.ended_${status}`, `crew.journal.${decision}`,
    # `plural("crew.track.tools", n)`, `crew.track.<état>`.
    used |= {f"journal.ended_{s}" for s in ("ok", "cancelled", "error", "interrupted")}
    used |= {f"journal.{d}" for d in ("approved", "rejected", "expired")}
    used |= {"track.tools_one", "track.tools_other"}
    used |= set(re.findall(r"""t\("crew\.([\w.]+)"\)""", code))
    used.discard("track.tools")  # `plural("crew.track.tools", n)` : `_one` et `_other` ci-dessus
    assert flat(CATALOG["crew"]) - used == set()
    assert {name for name in used if "${" not in name} - flat(CATALOG["crew"]) == set()


def test_the_graph_texts_exist_and_the_graph_is_exported_and_styled():
    graph = CATALOG["components"]["team_graph"]
    wanted = set(
        re.findall(r"""components\.team_graph\.(\w+)""", read("components/wl-team-graph.js"))
    )
    wanted |= {"current", "done", "stopped", "notrun"}  # `components.team_graph.${state}`
    assert wanted == set(graph)
    assert 'WlTeamGraph } from "./wl-team-graph.js"' in read("components/index.js")
    html = read("index.html")
    assert "css/components/team-graph.css" in html and "/static/agents-crew.css" in html


def test_the_scripts_never_write_html_and_stay_under_the_size_limit():
    for name in SCRIPTS:
        code = read(name)
        assert "innerHTML" not in code and "insertAdjacentHTML" not in code, name
        assert len(code.splitlines()) <= 600, name


def test_the_screen_computes_no_metric_and_the_download_is_a_server_route():
    """AD-20 : totaux d'un agent (`agent_totals`), de la mission (`totals`, `mission`) lus du serveur."""
    code = "\n".join(read(name) for name in SCRIPTS)
    assert "agent_totals" in code and "snapshot.totals" in code and "snapshot.mission" in code
    assert not re.search(r"\.reduce\(|Math\.(round|floor|ceil)\(|duration_s\s*[-+*/]", code)
    assert "conversationExportUrl" in read("screens/agents-crew.js")
    assert not re.search(r"createObjectURL|new Blob|href = [\"'`]blob", code)


def test_the_screen_answers_an_approval_only_through_the_shared_dialog_and_rewrites_the_address():
    screen = read("screens/agents-crew.js")
    assert "createApproval(" in screen and "answerApproval" not in screen
    # fin de run ; nouvelle mission lancée depuis une adresse de mission
    assert "history.replaceState(" not in screen and screen.count("replaceAddress(") == 2
    assert "location.hash === BASE" in screen
