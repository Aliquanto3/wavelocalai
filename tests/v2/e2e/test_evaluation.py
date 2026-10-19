"""Écran Évaluation de la qualité (story 7.3) dans un vrai navigateur, sur le vrai serveur.

Le serveur d'évaluation (7.1) a ses propres tests ; ici, l'écran est prouvé sur des flux et des
instantanés fixés par le test (`page.route`, formes du contrat `contrat-api.md`) : le test choisit
chaque note, chaque raison et le moment où chaque événement arrive, ce qu'un vrai juge ne permet pas.
Le vrai serveur sert la page, la liste des modèles est simulée, et deux parcours le sollicitent pour
de bon : un identifiant inconnu (`404 run_not_found`) et la liste des évaluations passées (vide).
Ollama n'est jamais sollicité, aucune requête ne sort de 127.0.0.1 (fixture `context`).

Prouvés ici : le formulaire et ses raisons de lancement (D-29), les trois étapes qui avancent, le
tableau qui se remplit, « non évalué » avec sa raison, le détail d'un score (verdicts et extrait
d'appui), un jeu de questions, la matrice, la réouverture par l'adresse, le résultat partiel (D-28),
la liste des évaluations passées, axe-core clair et sombre.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pytest

from .test_arena import JUDGE_DEFAULT, MODELS, NBSP, install_models, pick
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

URL = "#/documents/evaluation"
RUN = "11111111-2222-3333-4444-555555555555"
QUESTION = "Où dort le chat domestique ?"
A, B = "fake:a", "fake:b"
SOURCES = [
    {
        "n": 1,
        "doc_id": "d1",
        "document": "chats.txt",
        "page": None,
        "chunk_id": "c1",
        "text": "Le chat domestique dort sur le canapé du salon.",
    },
    {
        "n": 2,
        "doc_id": "d2",
        "document": "voitures.txt",
        "page": 3,
        "chunk_id": "c2",
        "text": "La voiture électrique recharge sa batterie la nuit.",
    },
]
VERDICTS = [
    {
        "claim": "Le chat dort sur le canapé.",
        "verdict": "appuyée",
        "support": 1,
        "reason": "Dit dans l'extrait 1.",
    },
    {
        "claim": "Le chat a trois ans.",
        "verdict": "non appuyée",
        "support": None,
        "reason": "Absent des extraits.",
    },
    {
        "claim": "Le chat dort dehors.",
        "verdict": "contredite",
        "support": 2,
        "reason": "L'extrait 2 dit le contraire.",
    },
]
NOT_EVALUATED = "non évalué : sortie du juge invalide"
# Les notes de chaque modèle : une liste par métrique, une valeur par question (`None` : non évalué).
SCORES = {
    A: {"faithfulness": [33], "relevance": [86], "context_precision": [100]},
    B: {"faithfulness": [80], "relevance": [None], "context_precision": [50]},
}
METRICS = ("faithfulness", "relevance", "context_precision")


def mean(values: list[int]) -> int:
    return int(sum(values) / len(values) + 0.5)


@dataclass
class Scenario:
    """Un run d'évaluation : ses événements par phase, et l'instantané qu'en rendrait le serveur."""

    questions: list[str] = field(default_factory=lambda: [QUESTION])
    lanes: list[str] = field(default_factory=lambda: [A, B])
    scores: dict = field(default_factory=lambda: SCORES)
    status: str = "ok"
    partial: bool = False
    stop_after_phase: int | None = None  # le run s'arrête (annulé) après cette phase
    fail_lane: str | None = None  # ce modèle échoue dès la phase des extraits
    fail_error: dict | None = None
    unmeasured: set = field(default_factory=set)  # (lane, question) sans débit ni CO2
    run_id: str = RUN
    phases: list[list[dict]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._seq = 0
        self.rows: list[dict] = []
        self.measures: dict[str, dict] = {}  # lane -> `lane_measures` du dernier `metrics`
        self.build()

    def event(self, kind: str, data: dict) -> dict:
        self._seq += 1
        second = f"{self._seq:02d}" if self._seq < 60 else "59"
        return {
            "seq": self._seq,
            "run_id": self.run_id,
            "type": kind,
            "ts": f"2026-10-19T10:00:{second}+00:00",
            "data": data,
        }

    def total(self) -> int:
        return len(self.questions)

    def note(self, lane: str, qi: int, metric: str) -> dict:
        score = self.scores[lane][metric][qi]
        return {
            "lane": lane,
            "question_index": qi,
            "metric": metric,
            "score": score,
            "reason": None if score is not None else NOT_EVALUATED,
            "verdicts": VERDICTS if metric == "faithfulness" and score is not None else None,
            "questions": (
                ["Où dort le chat ?", "Que fait le chat ?"]
                if metric == "relevance" and score is not None
                else None
            ),
            "useful": [1] if metric == "context_precision" and score is not None else None,
        }

    def aggregate(self, lane: str, metric: str, seen: int, *, settled: bool) -> dict:
        values = self.scores[lane][metric][:seen]
        present = [v for v in values if v is not None]
        unseen = self.total() - seen
        return {
            "score": mean(present) if present else None,
            "evaluated": len(present),
            "not_evaluated": len(values) - len(present) + (unseen if settled else 0),
            "pending": 0 if settled else unseen,
            "total": self.total(),
        }

    def build(self) -> None:
        phases: list[list[dict]] = []
        e = self.event
        # 0 : démarrage
        phases.append(
            [
                e("run_started", {"kind": "eval", "models": self.lanes, "params": {}}),
                e("eval_questions", {"questions": self.questions}),
                e(
                    "judge",
                    {
                        "model": JUDGE_DEFAULT,
                        "origin": "local",
                        "params_active_b": 8,
                        "unreliable": False,
                        "single_judge": False,
                        "chosen": True,
                    },
                ),
                *[e("lane_status", {"lane": lane, "status": "waiting"}) for lane in self.lanes],
            ]
        )
        # 1 : extraits communs
        phase = []
        for qi in range(self.total()):
            phase.append(
                e("retrieval_step", {"strategy": "naive", "step": "search", "question_index": qi})
            )
            phase.append(
                e("sources", {"strategy": "naive", "question_index": qi, "sources": SOURCES})
            )
        phase.append(e("lane_status", {"lane": self.lanes[0], "status": "generating"}))
        if self.fail_lane:
            data = {"lane": self.fail_lane, "status": "failed", "error": self.fail_error}
            phase.append(e("lane_status", data))
        phases.append(phase)
        # 2 : réponses
        phase = []
        for lane_index, lane in enumerate(self.lanes):
            if lane_index:
                phase.append(e("lane_status", {"lane": lane, "status": "generating"}))
            for qi in range(self.total()):
                phase.append(
                    e(
                        "eval_answer",
                        {
                            "lane": lane,
                            "question_index": qi,
                            "text": f"Réponse de {lane} {qi}.",
                            "error": None,
                        },
                    )
                )
                gone = (lane, qi) in self.unmeasured
                mg = None if gone else 1.8 + lane_index
                rate = None if gone else 38.4 - 16 * lane_index
                co2 = {"mg": mg, "estimated": False, "method": "codecarbon"}
                # Les totaux que publierait le serveur (`lane_measures`, revue 7.3 : AD-20) :
                # débit constant par modèle, CO2 additionné sur les questions mesurées.
                n = sum(1 for q in range(qi + 1) if (lane, q) not in self.unmeasured)
                totals = {
                    "tps": (38.4 - 16 * lane_index) if n else None,
                    "tps_measured": n,
                    "co2": {
                        "mg": round((1.8 + lane_index) * n, 6) if n else None,
                        "measured": n,
                        "estimated": False,
                        "unmeasurable": False,
                    },
                    "answered": qi + 1,
                    "total": self.total(),
                }
                self.measures[lane] = totals
                phase.append(
                    e(
                        "metrics",
                        {
                            "lane": lane,
                            "question_index": qi,
                            "tps": rate,
                            "co2": co2,
                            "lane_measures": totals,
                        },
                    )
                )
            phase.append(e("lane_status", {"lane": lane, "status": "judging"}))
        phases.append(phase)
        # 3 et 4 : notes du premier puis du second modèle
        for lane_index, lane in enumerate(self.lanes):
            phase = []
            for qi in range(self.total()):
                for metric in METRICS:
                    note = self.note(lane, qi, metric)
                    agg = self.aggregate(lane, metric, qi + 1, settled=False)
                    phase.append(
                        e("eval_metric", {**note, "question_count": self.total(), "aggregate": agg})
                    )
                    self.rows.append(note)
            if lane_index == len(self.lanes) - 1:
                phase += [e("lane_status", {"lane": tag, "status": "done"}) for tag in self.lanes]
            phases.append(phase)
        phases[-1].append(e("run_ended", {"status": self.status, "error": None}))
        if self.stop_after_phase is not None:
            kept = phases[: self.stop_after_phase + 1]
            self.rows = [
                row
                for phase in kept
                for ev in phase
                if ev["type"] == "eval_metric"
                for row in [ev["data"]]
            ]
            kept[-1] = [ev for ev in kept[-1] if ev["type"] != "run_ended"]
            kept[-1].append(
                self.event("lane_status", {"lane": self.lanes[-1], "status": "cancelled"})
            )
            kept[-1].append(self.event("run_ended", {"status": self.status, "error": None}))
            phases = kept
        self.phases = phases

    @property
    def events(self) -> list[dict]:
        return [ev for phase in self.phases for ev in phase]

    def snapshot(self) -> dict:
        done = {(r["lane"], r["question_index"], r["metric"]) for r in self.rows}
        seen_by_lane = {lane: dict.fromkeys(METRICS, 0) for lane in self.lanes}
        for lane, qi, metric in done:
            seen_by_lane[lane][metric] = max(seen_by_lane[lane][metric], qi + 1)
        summary = {
            lane: {m: self.aggregate(lane, m, seen_by_lane[lane][m], settled=True) for m in METRICS}
            for lane in self.lanes
        }
        missing = [
            {
                "lane": lane,
                "question_index": qi,
                "metric": metric,
                "score": None,
                "reason": "non évalué : évaluation arrêtée",
            }
            for lane in self.lanes
            for qi in range(self.total())
            for metric in METRICS
            if self.partial and (lane, qi, metric) not in done
        ]
        return {
            "run_id": self.run_id,
            "kind": "eval",
            "status": self.status,
            "started_at": "2026-10-19T10:00:00+00:00",
            "ended_at": "2026-10-19T10:00:59+00:00",
            "erased": False,
            "partial": self.partial,
            "config": {
                "questions": self.questions,
                "models": self.lanes,
                "judge": JUDGE_DEFAULT,
                "allow_cloud": False,
            },
            "judge": self.phases[0][2]["data"],
            "evaluations": self.rows,
            "summary": summary,
            "measures": self.measures,
            "missing": missing,
            "children": [],
        }

    def listing(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": "2026-10-19T10:00:00+00:00",
            "ended_at": "2026-10-19T10:00:59+00:00",
            "models": self.lanes,
            "question_count": self.total(),
            "question": self.questions[0],
        }


class Wire:
    """Ce que le test sert à la page : flux, instantané, liste, base et commandes reçues."""

    def __init__(self, page, scenario: Scenario | None, documents: int = 2) -> None:
        self.page = page
        self.scenario = scenario
        self.released = len(scenario.events) if scenario else 0
        self.posts: list[dict] = []
        self.listed: list[dict] = [scenario.listing()] if scenario else []
        self.documents = documents
        self.cancelled = False
        page.route(re.compile(r"/api/rag/documents$"), self.on_documents)
        page.route(re.compile(r"/api/rag/eval/runs(\?.*)?$"), self.on_runs)
        if scenario:
            page.route(re.compile(rf"/api/runs/{scenario.run_id}/events"), self.on_events)
            page.route(re.compile(rf"/api/runs/{scenario.run_id}$"), self.on_snapshot)
            page.route(re.compile(rf"/api/runs/{scenario.run_id}/cancel$"), self.on_cancel)

    def release(self, phase: int) -> None:
        """Rend visibles les événements jusqu'à la fin de la phase `phase` comprise."""
        self.released = sum(len(p) for p in self.scenario.phases[: phase + 1])

    def on_documents(self, route) -> None:
        body = {
            "documents": [],
            "totals": {"documents": self.documents, "chunks": 4 * self.documents},
            "limits": {"max_file_mb": 20, "max_files": 10, "max_import_mb": 100},
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def on_runs(self, route) -> None:
        if route.request.method == "POST":
            self.posts.append(json.loads(route.request.post_data))
            body = {"run_id": self.scenario.run_id}
        else:
            body = {"runs": self.listed}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def on_events(self, route) -> None:
        match = re.search(r"after=(\d+)", route.request.url)
        after = int(match.group(1)) if match else 0
        lines = [
            f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            for ev in self.scenario.events[: self.released]
            if ev["seq"] > after
        ]
        route.fulfill(status=200, content_type="text/event-stream", body="".join(lines))

    def on_snapshot(self, route) -> None:
        body = self.scenario.snapshot()
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def on_cancel(self, route) -> None:
        self.cancelled = True
        route.fulfill(status=200, content_type="application/json", body="{}")


def open_screen(
    page, server, scenario: Scenario | None = None, path: str = URL, documents: int = 2
):
    install_models(page, defaults=(A, B))
    wire = Wire(page, scenario, documents)
    page.goto(f"{server.base_url}/{path}")
    wait_ready(page)
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=arena]')?.values.length === 2"
    )
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1"
    )
    return wire


def launch_button(page):
    return page.get_by_role("button", name="Lancer l'évaluation")


def reason(page) -> str:
    return page.locator(".eval-reason").inner_text().strip()


def fill_question(page, text: str = QUESTION) -> None:
    page.locator("textarea.eval-question").first.fill(text)


def step_state(page, step: str) -> str:
    return page.locator(f".eval-step[data-step={step}] > .eval-step-slot").inner_text().strip()


def cell_text(page, model: str, column: int) -> str:
    row = page.locator(".eval-results tbody tr", has_text=model)
    return row.locator("td, th").nth(column).inner_text().replace("\n", " ").strip()


def start(page, wire) -> None:
    fill_question(page)
    launch_button(page).click()
    wait_for(
        page,
        "() => !!document.querySelector('.eval-run') && !document.querySelector('.eval-run').hidden",
    )


@pytest.fixture
def finished(page, server):
    wire = open_screen(page, server, Scenario())
    start(page, wire)
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )
    return page, wire


# --- Formulaire -----------------------------------------------------------------------------------


def test_the_form_opens_on_the_defaults_with_the_judge_and_the_launch_reason(page, server):
    open_screen(page, server)
    assert page.get_by_role("heading", level=1).inner_text() == "Évaluation de la qualité"
    tabs = page.get_by_role("navigation", name="Écrans du module Documents")
    current = tabs.locator("[aria-current=page]")
    assert current.inner_text() == "Évaluation de la qualité"
    assert current.get_attribute("href") == URL
    assert page.locator("wl-model-picker[purpose=arena]").evaluate("el => el.values") == [A, B]
    assert page.locator("wl-model-picker[purpose=judge]").evaluate("el => el.values") == [
        JUDGE_DEFAULT
    ]
    assert (
        page.locator("wl-model-picker[purpose=judge]")
        .inner_text()
        .count("Le plus gros modèle local")
        >= 1
    )
    assert "Les mêmes extraits sont fournis à tous les modèles." in page.inner_text(
        "form.eval-form"
    )
    assert "moins de 4 milliards de paramètres actifs" in page.inner_text("form.eval-form")
    assert (
        page.get_by_role("radio", name="Question", exact=True).get_attribute("aria-checked")
        == "true"
    )
    # Question vide (D-29) : lancement désactivé, raison visible et reliée au bouton.
    button = launch_button(page)
    assert button.is_disabled()
    assert reason(page) == "Saisissez une question"
    described = button.get_attribute("aria-describedby")
    assert page.locator(f"#{described}").inner_text().strip() == "Saisissez une question"
    fill_question(page)
    assert button.is_enabled()
    assert page.locator(".eval-reason").is_hidden()


def test_the_launch_reasons_models_questions_and_empty_base(page, server):
    open_screen(page, server)
    fill_question(page)
    button = launch_button(page)
    # 5 modèles : au-delà de 4, lancement désactivé.
    for name in ("Charlie 3B", "Delta 4B", "Echo 5B"):
        pick(page, name)
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=arena]').values.length === 5"
    )
    assert button.is_disabled() and reason(page) == "Choisissez 4 modèles au plus"
    page.locator("wl-model-picker[purpose=arena]").evaluate(
        "el => { el.values = []; el.dispatchEvent(new CustomEvent('wl-model-change', { bubbles: true })); }"
    )
    assert button.is_disabled() and reason(page) == "Choisissez au moins un modèle"
    page.locator("wl-model-picker[purpose=arena]").evaluate(
        "el => { el.values = ['fake:a']; el.dispatchEvent(new CustomEvent('wl-model-change', { bubbles: true })); }"
    )
    assert button.is_enabled()  # un seul modèle suffit
    # Jeu de questions : une par ligne, 20 au plus.
    page.get_by_role("radio", name="Jeu de questions").click()
    area = page.locator("textarea.eval-question").nth(1)
    assert area.is_visible() and button.is_disabled() and reason(page) == "Saisissez une question"
    area.fill("\n".join(f"Question {n} ?" for n in range(21)))
    assert button.is_disabled() and reason(page) == "Posez 20 questions au plus"
    area.fill("\n".join(f"Question {n} ?" for n in range(20)))
    assert button.is_enabled()


def test_an_empty_base_disables_the_launch_with_a_link_to_the_documents(page, server):
    open_screen(page, server, documents=0)
    fill_question(page)
    assert launch_button(page).is_disabled()
    assert reason(page).startswith("Importez des documents pour évaluer")
    link = page.locator(".eval-reason a")
    assert link.inner_text() == "Ouvrir la Base documentaire"
    assert link.get_attribute("href") == "#/documents/base"


# --- Étapes et tableau ---------------------------------------------------------------------------


def test_the_steps_advance_and_the_table_fills_as_the_events_arrive(page, server):
    scenario = Scenario()
    wire = open_screen(page, server, scenario)
    wire.released = 0
    fill_question(page)
    launch_button(page).click()
    command = wait_post(wire)
    assert command == {
        "questions": [QUESTION],
        "models": [A, B],
        "allow_cloud": False,
        "judge": JUDGE_DEFAULT,
    }
    # Le formulaire cède la place au bandeau ; rien n'est encore arrivé.
    wait_for(page, "() => document.querySelector('form.eval-form').hidden")
    assert "Évaluation en cours" in page.locator(".eval-banner-text").inner_text()
    wire.release(0)
    wait_for(page, "() => document.querySelectorAll('.eval-lane').length === 2")
    assert step_state(page, "retrieval").endswith("en cours")
    assert step_state(page, "answers").endswith("à venir")
    assert step_state(page, "scoring").endswith("à venir")
    assert page.locator(".eval-step-name").all_inner_texts() == [
        "Recherche des extraits communs",
        "Réponses",
        f"Notation{NBSP}: fidélité · pertinence · précision du contexte",
    ]
    wire.release(1)
    wait_for(
        page,
        "() => document.querySelector('.eval-step[data-step=retrieval]').textContent.includes('fait')",
    )
    assert step_state(page, "answers").endswith("en cours")
    lanes = page.locator(".eval-lane")
    assert "rédaction" in lanes.nth(0).inner_text()
    assert "en attente" in lanes.nth(1).inner_text()
    wire.release(2)
    wait_for(
        page,
        "() => document.querySelector('.eval-step[data-step=answers]').textContent.includes('fait')",
    )
    assert "notation" in lanes.nth(0).inner_text()
    wire.release(3)
    wait_for(page, "() => document.querySelectorAll('.eval-score').length === 3")
    assert step_state(page, "scoring").endswith("en cours")
    assert page.locator(".eval-step-count").inner_text() == "3 notes sur 6"
    # Premier modèle noté, second « en cours » (jamais 0).
    assert cell_text(page, "Alpha 1B", 1) == "33/100"
    assert cell_text(page, "Bravo 2B", 1) == "en cours"
    assert not re.search(r"(?<!\d)0/100", page.inner_text(".eval-results"))
    wire.release(4)
    wait_for(
        page, "() => document.querySelector('.eval-banner-text').textContent.includes('terminée')"
    )
    assert step_state(page, "scoring").endswith("fait")
    assert [cell_text(page, "Bravo 2B", n) for n in (1, 2, 3)] == [
        "80/100",
        "non évalué (sortie du juge invalide)",
        "50/100",
    ]
    assert page.locator("form.eval-form").is_visible()  # le formulaire revient, le résultat reste
    assert page.locator(".eval-history-item").count() == 1
    assert "terminée" in page.locator(".eval-history-state").inner_text()


def wait_post(wire, timeout_s: float = 10.0) -> dict:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if wire.posts:
            return wire.posts[0]
        wire.page.wait_for_timeout(50)
    pytest.fail("la commande n'est pas partie")


def test_the_table_has_no_global_column_and_every_metric_has_its_definition(finished):
    page, _ = finished
    headers = page.locator(".eval-results thead th").all_inner_texts()
    assert [h.strip() for h in headers] == [
        "Modèle",
        "Fidélité",
        "Pertinence",
        "Précision du contexte",
        "Débit",
        "CO₂",
    ]
    assert not [h for h in headers if "Global" in h]
    page.locator(".eval-defs summary").click()
    defs = page.locator(".eval-defs").inner_text()
    assert "Part des affirmations de la réponse appuyées par les extraits." in defs
    assert "Proximité entre la question posée et celles que la réponse permet de retrouver." in defs
    assert "Part des extraits fournis qui servent à répondre." in defs
    assert "Méthode inspirée de Ragas" in defs
    assert "Ragas" not in page.locator(".eval-results thead").inner_text()
    assert cell_text(page, "Alpha 1B", 4) == f"38,4{NBSP}tokens/s"
    assert cell_text(page, "Alpha 1B", 5).startswith("1,8")


def test_the_common_extracts_are_listed_on_demand(finished):
    page, _ = finished
    button = page.locator(".eval-extracts-button")
    assert button.inner_text() == "Voir les extraits"
    assert button.get_attribute("aria-expanded") == "false"
    button.click()
    assert button.get_attribute("aria-expanded") == "true"
    assert button.inner_text() == "Masquer les extraits"
    panel = page.locator(".eval-extracts wl-source-panel")
    assert "Le chat domestique dort sur le canapé du salon." in panel.inner_text()
    assert "voitures.txt" in panel.inner_text()
    button.click()
    assert page.locator(".eval-extracts").is_hidden()


# --- Détail d'une note ---------------------------------------------------------------------------


def test_a_score_unfolds_on_its_verdicts_with_the_supporting_extract(finished):
    page, _ = finished
    score = page.locator(".eval-score[data-lane='fake:a'][data-metric=faithfulness]")
    assert score.get_attribute("aria-expanded") == "false"
    score.click()
    assert score.get_attribute("aria-expanded") == "true"
    detail = page.locator(".eval-detail")
    assert detail.is_visible()
    assert page.evaluate("document.activeElement.className") == "eval-detail-title"
    assert detail.locator("h3").inner_text() == "Alpha 1B · Fidélité"
    assert f"3 affirmations{NBSP}: 1 appuyée, 1 non appuyée, 1 contredite" in detail.inner_text()
    claims = detail.locator(".eval-claim")
    assert claims.count() == 3
    assert [c.get_attribute("data-verdict") for c in claims.all()] == [
        "appuyée",
        "non appuyée",
        "contredite",
    ]
    assert "Le chat dort sur le canapé." in claims.nth(0).inner_text()
    assert "Extrait 1" in claims.nth(0).inner_text() and "(chats.txt)" in claims.nth(0).inner_text()
    assert "Le chat domestique dort sur le canapé du salon." in claims.nth(0).inner_text()
    assert "Aucun extrait cité" in claims.nth(1).inner_text()
    assert "Extrait 2" in claims.nth(2).inner_text()
    assert "(voitures.txt, p. 3)" in claims.nth(2).inner_text()
    detail.locator(".eval-answer summary").click()
    assert "Réponse de fake:a 0." in detail.inner_text()
    # Pertinence : la raison du score et les questions retrouvées ; Précision : les extraits utiles.
    page.locator(".eval-score[data-lane='fake:a'][data-metric=relevance]").click()
    assert detail.locator("h3").inner_text() == "Alpha 1B · Pertinence"
    assert "Questions retrouvées depuis la réponse" in detail.inner_text()
    page.locator(".eval-score[data-lane='fake:a'][data-metric=context_precision]").click()
    assert "Extraits jugés utiles" in detail.inner_text()
    assert "Le chat domestique dort sur le canapé du salon." in detail.inner_text()
    # « Fermer » et Échap ferment le détail et rendent le focus au bouton du score.
    detail.get_by_role("button", name="Fermer le détail").click()
    assert detail.is_hidden()
    assert page.evaluate("document.activeElement.dataset.metric") == "context_precision"
    page.locator(".eval-score[data-lane='fake:b'][data-metric=faithfulness]").click()
    page.keyboard.press("Escape")
    assert detail.is_hidden()
    assert page.evaluate("document.activeElement.dataset.lane") == "fake:b"


# --- Jeu de questions ----------------------------------------------------------------------------


def test_a_set_of_questions_says_how_many_were_evaluated(page, server):
    scores = {
        A: {"faithfulness": [60, 100], "relevance": [90, None], "context_precision": [None, None]},
        B: {"faithfulness": [50, 50], "relevance": [70, 70], "context_precision": [100, 100]},
    }
    scenario = Scenario(questions=["Où dort le chat ?", "Que mange le chat ?"], scores=scores)
    wire = open_screen(page, server, scenario)
    page.get_by_role("radio", name="Jeu de questions").click()
    page.locator("textarea.eval-question").nth(1).fill("Où dort le chat ?\n\nQue mange le chat ?\n")
    launch_button(page).click()
    command = wait_post(wire)
    assert command["questions"] == ["Où dort le chat ?", "Que mange le chat ?"]  # sans ligne vide
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )
    assert "80/100" in cell_text(page, "Alpha 1B", 1)  # moyenne donnée par le serveur
    assert "sur 2 questions" in cell_text(page, "Alpha 1B", 1)
    assert "sur 2 questions (1 non évaluée)" in cell_text(page, "Alpha 1B", 2)
    assert "non évalué (juge indisponible)" not in cell_text(page, "Alpha 1B", 3)
    assert cell_text(page, "Alpha 1B", 3).startswith("non évalué")
    assert page.locator(".eval-results thead th").nth(4).inner_text().strip() == "Débit moyen"
    assert page.locator(".eval-results thead th").nth(5).inner_text().strip() == "CO₂ total"
    assert cell_text(page, "Alpha 1B", 5).startswith("3,6")  # total publié par le serveur
    # Détail par question : une section par question.
    page.locator(".eval-score[data-lane='fake:a'][data-metric=faithfulness]").click()
    sections = page.locator(".eval-detail-question")
    assert sections.count() == 2
    assert (
        "Question 2 · Que mange le chat ?"
        in sections.nth(1).locator("xpath=./summary").inner_text()
    )
    # Les extraits se lisent question par question.
    page.get_by_role("button", name="Voir les extraits").click()
    assert page.get_by_label("Extraits de la question").is_visible()


def test_a_set_says_how_many_answers_were_measured(page, server):
    """Revue 7.3 : le débit moyen et le CO2 total viennent du serveur, avec « n sur m » quand une
    réponse n'a pas de mesure ; l'écran n'additionne rien."""
    scores = {A: {m: [50, 50] for m in METRICS}, B: {m: [70, 70] for m in METRICS}}
    scenario = Scenario(
        questions=["Où dort le chat ?", "Que mange le chat ?"],
        scores=scores,
        unmeasured={(A, 1)},
    )
    wire = open_screen(page, server, scenario)
    page.get_by_role("radio", name="Jeu de questions").click()
    page.locator("textarea.eval-question").nth(1).fill("Où dort le chat ?\nQue mange le chat ?")
    launch_button(page).click()
    wait_post(wire)
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )
    assert cell_text(page, "Alpha 1B", 4) == f"38,4{NBSP}tokens/s (1 question mesurée sur 2)"
    assert cell_text(page, "Alpha 1B", 5).startswith("1,8")
    assert "(1 question mesurée sur 2)" in cell_text(page, "Alpha 1B", 5)
    assert "mesurée" not in cell_text(page, "Bravo 2B", 4)


# --- Matrice -------------------------------------------------------------------------------------


def test_the_matrix_places_each_model_by_faithfulness_and_rate(finished):
    page, _ = finished
    segments = page.get_by_role("radiogroup", name="Présentation des résultats")
    assert segments.get_by_role("radio", name="Tableau").get_attribute("aria-checked") == "true"
    assert "Global" not in segments.inner_text()
    segments.get_by_role("radio", name="Matrice").click()
    chart = page.locator(".eval-results wl-chart-svg")
    chart.locator("svg.wl-chart-svg").wait_for()
    description = chart.locator("svg.wl-chart-svg desc").text_content()
    assert "Alpha 1B" in description and "fidélité 33/100" in description
    assert "Bravo 2B" in description
    assert "Voir le tableau" in chart.inner_text()
    chart.get_by_role("button", name="Voir le tableau").click()
    assert segments.get_by_role("radio", name="Tableau").get_attribute("aria-checked") == "true"
    assert page.locator(".eval-results table").is_visible()


# --- Rouvrir -------------------------------------------------------------------------------------


def test_reopening_by_the_address_rebuilds_the_result_without_a_new_run(page, server):
    scenario = Scenario()
    wire = open_screen(page, server, scenario, path=f"{URL}/{RUN}")
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )
    assert wire.posts == []  # aucune commande : le flux enregistré est relu
    assert [step_state(page, s).split()[-1] for s in ("retrieval", "answers", "scoring")] == [
        "fait"
    ] * 3
    assert cell_text(page, "Alpha 1B", 1) == "33/100"
    assert cell_text(page, "Bravo 2B", 2) == "non évalué (sortie du juge invalide)"
    assert page.locator(".eval-results-title").inner_text() == "Résultats"
    assert page.locator(".eval-asked").inner_text().endswith(QUESTION)
    assert "Juge retenu" in page.locator(".eval-judge-info").inner_text()
    page.locator(".eval-score[data-lane='fake:a'][data-metric=faithfulness]").click()
    assert page.locator(".eval-claim").count() == 3  # les verdicts se relisent aussi


def test_the_past_evaluations_are_listed_newest_first_and_reopen_by_their_address(page, server):
    scenario = Scenario()
    wire = open_screen(page, server, scenario)
    older = {**scenario.listing(), "run_id": "older-run", "started_at": "2026-10-18T09:00:00+00:00"}
    older["question"] = "Une question plus ancienne ?"
    wire.listed = [scenario.listing(), older]
    page.reload()
    wait_ready(page)
    items = page.locator(".eval-history-item")
    items.first.wait_for()
    assert items.count() == 2
    assert page.locator(".eval-history h2").inner_text() == "Évaluations passées"
    first = items.first.locator("a")
    assert first.get_attribute("href") == f"#/documents/evaluation/{RUN}"
    text = first.inner_text()
    assert "Alpha 1B, Bravo 2B" in text and "1 question" in text and "terminée" in text
    assert QUESTION in text
    first.click()
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )
    assert page.evaluate("location.hash") == f"#/documents/evaluation/{RUN}"
    assert wire.posts == []


def test_a_partial_result_is_kept_titled_and_never_shows_a_zero(page, server):
    # Annulée après les notes du premier modèle : le second n'a aucune note.
    scenario = Scenario(status="cancelled", partial=True, stop_after_phase=3)
    wire = open_screen(page, server, scenario, path=f"{URL}/{RUN}")
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('arrêtée')"
    )
    assert wire.posts == []
    assert page.locator(".eval-results-title").inner_text() == "Résultat partiel conservé"
    assert "jamais 0" in page.locator(".eval-partial").inner_text()
    assert cell_text(page, "Alpha 1B", 1) == "33/100"
    for column in (1, 2, 3):
        assert cell_text(page, "Bravo 2B", column) == "non évalué (évaluation arrêtée)"
    assert not re.search(
        r"(?<!\d)0/100", page.inner_text(".eval-results")
    ) and "en cours" not in page.inner_text(".eval-results")
    assert step_state(page, "scoring").endswith("arrêtée")
    wait_for(
        page,
        "() => [...document.querySelectorAll('[aria-live=polite]')]"
        ".some((node) => node.textContent.includes('résultats partiels'))",
    )


def test_an_unknown_run_says_run_not_found_with_the_server_message(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests
    install_models(page, defaults=(A, B))
    page.goto(f"{server.base_url}/{URL}/introuvable-123")
    wait_ready(page)
    missing = page.locator(".eval-missing")
    missing.wait_for()
    assert missing.get_attribute("data-code") == "run_not_found"
    assert missing.locator("h2").inner_text() == "Résultat introuvable"
    assert "comparaison" not in missing.inner_text()  # le texte du serveur est neutre (7.1)
    assert (
        missing.get_by_role("link", name="Lancer une nouvelle évaluation").get_attribute("href")
        == URL
    )
    # Le vrai serveur n'a encore aucune évaluation : la liste est vide, donc masquée.
    assert page.locator(".eval-history").is_hidden()


# --- Garde-fou, annulation, états ----------------------------------------------------------------


def test_stopping_asks_the_server_and_the_partial_result_stays(page, server):
    scenario = Scenario(status="cancelled", partial=True, stop_after_phase=2)
    wire = open_screen(page, server, scenario)
    wire.released = 0
    fill_question(page)
    launch_button(page).click()
    wait_post(wire)
    wire.release(1)
    wait_for(
        page,
        "() => document.querySelector('.eval-step[data-step=retrieval]')?.textContent.includes('fait')",
    )
    page.get_by_role("button", name="Arrêter").click()
    wait_for(page, "() => document.querySelector('.eval-stop').disabled")
    assert wire.cancelled
    wire.release(2)
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('arrêtée')"
    )
    assert page.locator(".eval-results-title").inner_text() == "Résultat partiel conservé"
    for column in (1, 2, 3):
        assert cell_text(page, "Alpha 1B", column) == "non évalué (évaluation arrêtée)"
    assert step_state(page, "scoring").endswith("non lancée")


def test_step_states_are_derived_from_the_events_in_the_page(page, server):
    open_screen(page, server)
    out = page.evaluate(
        """async () => {
            const { createModel } = await import('/static/screens/eval-model.js');
            const model = createModel();
            const states = () => { const s = model.steps(); return [s.retrieval, s.answers, s.scoring]; };
            const out = {};
            model.apply('run_started', { kind: 'eval', models: ['a', 'b'] });
            model.apply('eval_questions', { questions: ['q'] });
            out.started = states();
            model.apply('sources', { question_index: 0, sources: [] });
            out.retrieved = states();
            model.apply('lane_status', { lane: 'a', status: 'failed', error: { code: 'x', message: 'm' } });
            model.apply('lane_status', { lane: 'b', status: 'failed', error: { code: 'x', message: 'm' } });
            out.failed = states();
            model.apply('run_ended', { status: 'error' });
            out.ended = states();
            const early = createModel();
            early.apply('run_started', { kind: 'eval', models: ['a'] });
            early.apply('eval_questions', { questions: ['q'] });
            early.apply('run_ended', { status: 'cancelled' });
            out.cancelled = [early.steps().retrieval, early.steps().answers, early.steps().scoring];
            out.cell = early.cell('a', 'faithfulness');
            return out;
        }"""
    )
    assert out["started"] == ["current", "pending", "pending"]
    assert out["retrieved"] == ["done", "current", "pending"]
    assert out["failed"] == ["done", "failed", "pending"]
    assert out["ended"] == ["done", "failed", "failed"]
    assert out["cancelled"] == ["stopped", "not_started", "not_started"]
    assert out["cell"]["kind"] == "unevaluated"  # arrêtée sans note : jamais 0


def test_a_failed_model_keeps_its_error_and_the_smaller_model_proposal(page, server):
    ram = {
        "code": "ram_guard",
        "message": "Pas assez de mémoire libre pour ce modèle.",
        "action": "Prenez un modèle plus petit.",
        "detail": {"needed_gb": 9.0, "free_gb": 2.0, "suggested_model": "fake:c"},
    }
    scenario = Scenario(fail_lane=B, fail_error=ram)
    wire = open_screen(page, server, scenario)
    wire.released = 0
    fill_question(page)
    launch_button(page).click()
    wait_post(wire)
    wire.release(1)
    lane = page.locator(".eval-lane[data-lane='fake:b']")
    wait_for(page, "() => !!document.querySelector(\".eval-lane[data-lane='fake:b'] wl-error\")")
    assert "échec" in lane.inner_text()
    lane.get_by_role("button", name="Prendre un modèle plus petit").click()
    values = page.locator("wl-model-picker[purpose=arena]").evaluate("el => el.values")
    assert values == [A, "fake:c"]  # le modèle proposé remplace celui qui a échoué


# --- Accessibilité -------------------------------------------------------------------------------


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_form_the_steps_and_the_results(page, server, theme, width):
    page.set_viewport_size({"width": width, "height": 900})
    scenario = Scenario(partial=False)
    wire = open_screen(page, server, scenario)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"formulaire, {width} px, thème {theme}")
    fill_question(page)
    launch_button(page).click()
    wait_post(wire)
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )
    page.get_by_role("button", name="Voir les extraits").click()
    page.locator(".eval-score[data-lane='fake:a'][data-metric=faithfulness]").click()
    page.locator(".eval-history-item").first.wait_for()
    assert_no_axe_violations(page, f"résultat et détail, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)
    page.get_by_role("radio", name="Matrice").click()
    page.locator(".eval-results wl-chart-svg svg.wl-chart-svg").wait_for()
    assert_no_axe_violations(page, f"matrice, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)


def test_axe_finds_no_violation_on_a_partial_result_and_on_a_missing_one(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests
    scenario = Scenario(status="cancelled", partial=True, stop_after_phase=3)
    open_screen(page, server, scenario, path=f"{URL}/{RUN}")
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('arrêtée')"
    )
    assert_no_axe_violations(page, "résultat partiel")
    page.goto(f"{server.base_url}/{URL}/introuvable-123")
    page.locator(".eval-missing").wait_for()
    assert_no_axe_violations(page, "résultat introuvable")


def test_the_question_draft_survives_a_reload_and_nothing_else_is_stored(page, server):
    open_screen(page, server)
    fill_question(page, "Un brouillon de question ?")
    page.reload()
    wait_ready(page)
    assert (
        page.locator("textarea.eval-question").first.input_value() == "Un brouillon de question ?"
    )
    keys = page.evaluate(
        "Object.keys(localStorage).filter((k) => k.startsWith('wavelocalai.draft.'))"
    )
    assert keys == ["wavelocalai.draft.evaluation"]


def test_the_catalog_models_used_here_exist():
    assert {m["tag"] for m in MODELS} >= {A, B, "fake:c", JUDGE_DEFAULT}
