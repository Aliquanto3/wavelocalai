"""Campagne synthétique de rédaction et faux services du juge (aucun réseau, aucune clé).

- ``build_campaign`` : jeu ``sets/<set>/``, manifeste et ``generation.jsonl`` d'une campagne
  dont les réponses de rédaction sont synthétiques ;
- ``FakeServer`` : ``/v1/systemone`` et Ollama (``/api/ps``, ``/api/generate``) sur
  ``httpx2.MockTransport`` ;
- ``FakeAnthropic`` : faux client ``anthropic`` réduit à ``messages.batches``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx2

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import pretty_bytes
from scripts.quality_bench.common.jsonl import rewrite_jsonl
from scripts.quality_bench.common.manifest import blocking_hash
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.questions.schema import set_hash, with_hashes

from .factories import manifest
from .grading_factories import answer_output, generation_for
from .set_factories import synthetic_question

CAMPAIGN = "judge-test"
SET_ID = "small-judge"
ANSWER_MARK = "Réponse synthétique numéro"
# Probabilités du faux /v1/systemone par critère : c3 faux, les autres vrais (score 0,75).
PROBABILITIES = {"c1": 0.91, "c2": 0.75, "c3": 0.2, "c4": 0.5}


def _write_json(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_bytes(obj))


def build_campaign(
    writing: int = 2, *, private: bool = False, checked: bool = False
) -> dict[str, Any]:
    """Campagne ``judge-test`` : ``writing`` réponses de rédaction ``ok`` (4 critères chacune),
    une rédaction tronquée et une question de raisonnement (jamais jugées). ``checked`` : le
    critère c1 est vérifié par le code (la réponse a 4 mots) et n'est donc jamais jugé."""
    writing_questions = [synthetic_question("writing-fr", n) for n in range(1, writing + 1)]
    if checked:
        count = {"count": "words", "op": "==", "n": 4}
        writing_questions = [
            synthetic_question(
                "writing-fr",
                n,
                criteria=[
                    {"id": f"c{i}", "question": f"Critère synthétique {i} ?"}
                    | ({"check": count} if i == 1 else {})
                    for i in range(1, 5)
                ],
            )
            for n in range(1, writing + 1)
        ]
    if private:
        writing_questions[0] = with_hashes({**writing_questions[0], "private": True})
    reasoning = synthetic_question("bbeh-mini", 1, target="a")
    question_list = sorted([*writing_questions, reasoning], key=lambda q: q["id"])
    tracks = {"think_off": [q["id"] for q in question_list], "think_on": []}
    rewrite_jsonl(paths.set_questions_path(SET_ID), question_list)
    _write_json(paths.set_tracks_path(SET_ID), tracks)

    generation_manifest = manifest(campaign=CAMPAIGN)
    generation_manifest["blocking"]["set"] = {
        "id": SET_ID,
        "hash": set_hash(question_list, tracks),
        "n": {"think_off": len(question_list), "think_on": 0},
    }
    validate(generation_manifest)
    _write_json(paths.generation_manifest_path(CAMPAIGN), generation_manifest)
    generation_hash = blocking_hash(generation_manifest)

    lines = []
    for index, question in enumerate(writing_questions, start=1):
        lines.append(
            generation_for(
                question,
                answer_output(f"{ANSWER_MARK} {index}."),
                campaign=CAMPAIGN,
                manifest=generation_hash,
            )
        )
    lines.append(
        generation_for(
            writing_questions[0],
            answer_output("Tronquée"),
            campaign=CAMPAIGN,
            manifest=generation_hash,
            status="truncated",
            seed=1,
        )
    )
    lines.append(
        generation_for(
            reasoning,
            answer_output("The answer is: (a)"),
            campaign=CAMPAIGN,
            manifest=generation_hash,
        )
    )
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)
    ok_writing = [line for line in lines if line["usage"] == "writing" and line["status"] == "ok"]
    judged = range(2, 5) if checked else range(1, 5)
    expected_keys = sorted(f"{line['key']}|c{i}" for line in ok_writing for i in judged)
    return {
        "generation_hash": generation_hash,
        "lines": lines,
        "questions": question_list,
        "writing_keys": [line["key"] for line in ok_writing],
        "expected_keys": expected_keys,
    }


# --- Faux serveur /v1/systemone et Ollama -----------------------------------------------------


def systemone_answers(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": body["model"],
        "answers": [
            {"id": q["id"], "type": "noul", "noul": PROBABILITIES[q["id"]]}
            for q in body["questions"]
        ],
        "usage": {"prompt_tokens": 801, "completion_tokens": 5},
    }


@dataclass
class FakeServer:
    """Faux service local : ``/v1/systemone`` scénarisé, ``/api/ps`` et ``/api/generate``."""

    loaded: list[str] = field(default_factory=list)
    responder: Callable[[dict[str, Any], FakeServer], Any] = lambda body, fake: systemone_answers(
        body
    )
    requests: list[tuple[str, Any]] = field(default_factory=list)
    unloads: list[str] = field(default_factory=list)
    ollama_down: bool = False
    on_systemone: Callable[[int], None] | None = None

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)

    def systemone_bodies(self) -> list[dict[str, Any]]:
        return [body for path, body in self.requests if path == "/v1/systemone"]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((path, body))
        if path.startswith("/api/") and self.ollama_down:
            raise httpx2.ConnectError("connexion refusée", request=request)
        if path == "/api/ps":
            return httpx2.Response(
                200, json={"models": [{"name": name, "model": name} for name in self.loaded]}
            )
        if path == "/api/generate":
            assert body["keep_alive"] == 0
            self.unloads.append(body["model"])
            return httpx2.Response(200, json={"done": True, "done_reason": "unload"})
        if path == "/v1/systemone":
            if self.on_systemone is not None:
                self.on_systemone(len(self.systemone_bodies()))
            outcome = self.responder(body, self)
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, httpx2.Response):
                return outcome
            return httpx2.Response(200, json=outcome)
        return httpx2.Response(404, json={"error": "inconnu"})


# --- Faux client anthropic (Message Batches) --------------------------------------------------


def message(text: str, *, stop_reason: str = "end_turn", input_tokens=1000, output_tokens=100):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
        ),
    )


def default_outcome(params: dict[str, Any], batch_number: int) -> Any:
    """Verdict faux pour le critère 3, vrai sinon (lu dans le prompt synthétique)."""
    content = params["messages"][0]["content"]
    verdict = "Critère synthétique 3 ?" not in content
    return SimpleNamespace(type="succeeded", message=message(json.dumps({"verdict": verdict})))


@dataclass
class FakeBatches:
    outcome: Callable[[dict[str, Any], int], Any] = default_outcome
    # Statuts rendus par retrieve avant « ended », par lot (défaut : terminé aussitôt).
    pending_polls: int = 0
    created: list[tuple[str, list[dict[str, Any]]]] = field(default_factory=list)
    retrieved: list[str] = field(default_factory=list)
    on_retrieve: Callable[[str, int], None] | None = None
    _polls: dict[str, int] = field(default_factory=dict)

    def create(self, *, requests):
        batch_id = f"msgbatch_{len(self.created) + 1:03d}"
        self.created.append((batch_id, list(requests)))
        return SimpleNamespace(id=batch_id, processing_status="in_progress")

    def retrieve(self, batch_id):
        self.retrieved.append(batch_id)
        polls = self._polls.get(batch_id, 0) + 1
        self._polls[batch_id] = polls
        if self.on_retrieve is not None:
            self.on_retrieve(batch_id, polls)
        status = "in_progress" if polls <= self.pending_polls else "ended"
        return SimpleNamespace(id=batch_id, processing_status=status)

    def results(self, batch_id):
        number = int(batch_id.rsplit("_", 1)[1])
        requests = dict(self.created)[batch_id]
        return iter(
            SimpleNamespace(custom_id=r["custom_id"], result=self.outcome(r["params"], number))
            for r in requests
        )


@dataclass
class FakeAnthropic:
    batches: FakeBatches = field(default_factory=FakeBatches)
    closed: bool = False

    @property
    def messages(self):
        return SimpleNamespace(batches=self.batches)

    def close(self) -> None:
        self.closed = True
