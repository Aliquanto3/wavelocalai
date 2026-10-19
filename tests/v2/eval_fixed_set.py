"""Jeu fixe de cas du juge de l'évaluation de la qualité (story 7.2, AD-8, NFR12, NFR13).

Le jeu (`tests/v2/fixtures/eval/cases.json`) réunit des cas inventés : une question, des extraits
numérotés, la réponse d'un assistant, les affirmations de cette réponse avec le verdict attendu
(« appuyée », « non appuyée », « contredite ») et l'extrait d'appui, et les extraits utiles.
Les verdicts attendus sont **proposés, à relire par Anaël** (`review` dans `cases.json`, voir
`tests/v2/fixtures/eval/README.md`).

Deux usages, sur le même code que le service d'évaluation (`evaluation/metrics.py`) :

- **Rejeu** (`ReplayJudge`, test unitaire) : les sorties du juge sont lues dans `judge-replay.json`,
  indexées par l'empreinte de l'invite complète. Une modification de l'invite, du schéma ou du
  découpage change l'empreinte ou le résultat : le test échoue et dit quoi réenregistrer
  (`python -m tests.v2.eval_fixed_set record`, puis relire le diff).
- **Mesure** (`measure`, test `integration` ou `python -m tests.v2.eval_fixed_set measure`) : un
  vrai juge rejoue le jeu, et la part de verdicts identiques aux verdicts attendus est consignée.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wavelocalai.errors import ProviderError
from wavelocalai.evaluation import metrics, prompts, scoring
from wavelocalai.evaluation.judge import JudgeReply
from wavelocalai.inference.judge_port import NOT_EVALUATED_INVALID, NOT_EVALUATED_UNAVAILABLE
from wavelocalai.models.port import ChatModel, ChatRequest, TextDelta

FIXTURES = Path(__file__).parent / "fixtures" / "eval"
CASES_FILE = FIXTURES / "cases.json"
REPLAY_FILE = FIXTURES / "judge-replay.json"
REVIEW_STATES = ("proposed", "confirmed", "corrected")

Ask = Callable[[ChatRequest], Awaitable[JudgeReply]]


def load_cases(path: Path = CASES_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# --- attendus -----------------------------------------------------------------------------------


def verified_claims(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Les affirmations que le service vérifie : les `MAX_CLAIMS` premières."""
    return case["claims"][: prompts.MAX_CLAIMS]


def expected_faithfulness(case: dict[str, Any]) -> int | None:
    """Fidélité attendue ; `None` (non évalué, jamais 0) si la réponse n'a aucune affirmation."""
    claims = verified_claims(case)
    if not claims:
        return None
    return scoring.percent(sum(1 for c in claims if c["verdict"] == prompts.SUPPORTED), len(claims))


def expected_precision(case: dict[str, Any]) -> int:
    return scoring.context_precision(case["useful"], len(case["sources"]))


def expected_verdicts(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"claim": c["claim"], "verdict": c["verdict"], "support": c["support"]}
        for c in verified_claims(case)
    ]


# --- sorties de référence rejouées --------------------------------------------------------------


def request_key(request: ChatRequest) -> str:
    """Empreinte de l'invite complète (messages, schéma de sortie, température)."""
    payload = {
        "messages": [[m.role, m.content] for m in request.messages],
        "schema": request.response_schema,
        "temperature": request.temperature,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def reference_outputs(case: dict[str, Any]) -> list[tuple[str, ChatRequest, str]]:
    """`(sorte, invite, sortie)` que rendrait un juge d'accord avec les verdicts attendus."""
    question, answer, sources = case["question"], case["answer"], case["sources"]
    out = [
        (
            "claims",
            prompts.claims_request(question, answer),
            json.dumps({"claims": [c["claim"] for c in case["claims"]]}, ensure_ascii=False),
        )
    ]
    for claim in verified_claims(case):
        reply = {
            "verdict": claim["verdict"],
            "support": claim["support"],
            "reason": f"Verdict attendu du jeu fixe : {claim['verdict']}.",
        }
        out.append(
            (
                "verdict",
                prompts.verdict_request(claim["claim"], sources),
                json.dumps(reply, ensure_ascii=False),
            )
        )
    out.append(
        (
            "questions",
            prompts.questions_request(answer),
            json.dumps({"questions": case["relevance_questions"]}, ensure_ascii=False),
        )
    )
    useful = {"useful": case["useful"], "reason": "Extraits utiles attendus du jeu fixe."}
    out.append(
        (
            "useful",
            prompts.useful_request(question, answer, sources),
            json.dumps(useful, ensure_ascii=False),
        )
    )
    return out


class UnrecordedRequestError(AssertionError):
    """Le rejeu a reçu une invite absente de `judge-replay.json` (invite ou découpage modifiés)."""


class ReplayJudge:
    """Un juge qui rend les sorties de `judge-replay.json`, sans modèle."""

    def __init__(self, replay: dict[str, Any]) -> None:
        self._entries: dict[str, dict[str, str]] = replay["entries"]
        self.calls = 0

    async def ask(self, request: ChatRequest) -> JudgeReply:
        self.calls += 1
        entry = self._entries.get(request_key(request))
        if entry is None:
            last = request.messages[-1].content.strip().splitlines()[-1][:80]
            raise UnrecordedRequestError(
                "Invite absente de judge-replay.json (invite, schéma ou découpage modifiés) : "
                f"« …{last} ». Relire l'effet sur les verdicts, puis réenregistrer par "
                "`python -m tests.v2.eval_fixed_set record`."
            )
        return JudgeReply(entry["output"], "")


class HashingEmbedder:
    """Embedding déterministe (sac de mots haché sur 64 dimensions), pour la pertinence rejouée."""

    DIM = 64

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.DIM
        for word in re.findall(r"\w+", text.lower()):
            slot = int.from_bytes(hashlib.sha1(word.encode("utf-8")).digest()[:4], "big")
            vector[slot % self.DIM] += 1.0
        return vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


# --- rejouer un cas -----------------------------------------------------------------------------


async def run_case(
    case: dict[str, Any],
    ask: Ask,
    embed: Callable[[list[str]], Awaitable[list[list[float]]]] | None,
) -> dict[str, metrics.Metric]:
    """Les trois notes d'un cas, par le code du service. Sans `embed`, la pertinence est omise."""
    question, answer, sources = case["question"], case["answer"], case["sources"]
    notes = {
        "faithfulness": await metrics.faithfulness(ask, question, answer, sources),
        "context_precision": await metrics.context_precision(ask, question, answer, sources),
    }
    if embed is not None:
        notes["relevance"] = await metrics.relevance(ask, embed, question, answer)
    return notes


async def replay_all(doc: dict[str, Any], replay: dict[str, Any]) -> dict[str, dict]:
    judge, embedder = ReplayJudge(replay), HashingEmbedder()
    return {case["id"]: await run_case(case, judge.ask, embedder.embed) for case in doc["cases"]}


async def record(doc: dict[str, Any]) -> dict[str, Any]:
    """Le contenu de `judge-replay.json` : sorties de référence et pertinence rejouée."""
    entries: dict[str, dict[str, str]] = {}
    for case in doc["cases"]:
        for kind, request, output in reference_outputs(case):
            entries[request_key(request)] = {"case": case["id"], "kind": kind, "output": output}
    replay: dict[str, Any] = {
        "note": (
            "Sorties du juge rejouées par le test de non-regression (story 7.2), produites à partir "
            "des verdicts attendus de cases.json : `python -m tests.v2.eval_fixed_set record`. "
            "`relevance` : instantané de la pertinence avec l'embedding déterministe du test "
            "(pas une annotation humaine)."
        ),
        "entries": entries,
        "relevance": {},
    }
    results = await replay_all(doc, replay)
    replay["relevance"] = {cid: notes["relevance"].score for cid, notes in results.items()}
    return replay


# --- mesure avec un vrai juge -------------------------------------------------------------------


class ModelAsker:
    """Un modèle réel (`ChatModel`) utilisé comme juge, sans run ni mesure : texte de sa réponse."""

    def __init__(self, model: ChatModel) -> None:
        self._model = model

    async def ask(self, request: ChatRequest) -> JudgeReply:
        text: list[str] = []
        try:
            async for chunk in self._model.stream(request):
                if isinstance(chunk, TextDelta) and chunk.channel == "answer":
                    text.append(chunk.text)
        except ProviderError as exc:
            invalid = getattr(exc, "code", None) == "invalid_output"
            return JudgeReply(None, NOT_EVALUATED_INVALID if invalid else NOT_EVALUATED_UNAVAILABLE)
        return JudgeReply("".join(text), "")


@dataclass
class Agreement:
    """Accord d'un juge avec le jeu fixe."""

    verdicts_same: int = 0
    verdicts_total: int = 0
    verdicts_majority: int = 0  # verdicts du verdict attendu le plus fréquent : l'accord d'un juge
    # qui répondrait toujours pareil (le point de repère, pas un seuil)
    verdicts_invalid: int = (
        0  # comptées dans le total : une sortie inutilisable n'est pas un accord
    )
    support_same: int = 0
    support_total: int = 0
    extracts_same: int = 0
    extracts_total: int = 0
    extracts_majority: int = 0  # extraits bien classés par un juge qui dirait toujours « tous
    # utiles » ou toujours « aucun utile » (le meilleur des deux) : le repère des extraits utiles
    majority_verdict: str = ""
    faithfulness_gaps: list[int] = field(default_factory=list)
    faithfulness_unscored: int = 0
    lines: list[str] = field(default_factory=list)

    @property
    def verdict_rate(self) -> float:
        return self.verdicts_same / self.verdicts_total if self.verdicts_total else 0.0

    @property
    def useful_rate(self) -> float:
        return self.extracts_same / self.extracts_total if self.extracts_total else 0.0

    @property
    def verdicts_informative(self) -> bool:
        """Faux si le juge ne fait pas mieux qu'un juge qui rendrait toujours le même verdict."""
        return self.verdicts_same > self.verdicts_majority

    @property
    def extracts_informative(self) -> bool:
        """Faux si le juge ne fait pas mieux que « tous utiles » ou « aucun utile »."""
        return self.extracts_same > self.extracts_majority

    def shortfalls(self, minimum: dict[str, float]) -> list[str]:
        """Ce qui ne passe pas la garde du jeu fixe : un accord sous `minimum_agreement`, ou un
        juge non informatif (pas meilleur que le juge trivial). Liste vide : la garde passe."""
        out = [
            f"{name} {100 * rate:.0f} % < {100 * minimum[name]:.0f} %"
            for name, rate in (("verdict", self.verdict_rate), ("useful", self.useful_rate))
            if rate < minimum[name]
        ]
        if self.verdicts_total and not self.verdicts_informative:
            out.append(
                f"juge non informatif sur les verdicts ({self.verdicts_same}/{self.verdicts_total}"
                f", pas mieux que toujours « {self.majority_verdict} » : "
                f"{self.verdicts_majority}/{self.verdicts_total})"
            )
        if self.extracts_total and not self.extracts_informative:
            out.append(
                f"juge non informatif sur les extraits utiles ({self.extracts_same}/"
                f"{self.extracts_total}, pas mieux que « tous utiles » ou « aucun utile » : "
                f"{self.extracts_majority}/{self.extracts_total})"
            )
        return out

    @property
    def faithfulness_gap(self) -> float | None:
        gaps = self.faithfulness_gaps
        return sum(gaps) / len(gaps) if gaps else None

    def summary(self, unreviewed: int, cases: int) -> str:
        gap = self.faithfulness_gap
        return (
            f"accord du juge sur le jeu fixe ({cases} cas, {unreviewed} non relus par Anaël) : "
            f"verdicts identiques {self.verdicts_same}/{self.verdicts_total} "
            f"({100 * self.verdict_rate:.0f} %, dont {self.verdicts_invalid} sorties invalides ; "
            f"un juge qui répondrait toujours « {self.majority_verdict} » : "
            f"{self.verdicts_majority}/{self.verdicts_total}"
            + ("" if self.verdicts_informative else ", juge non informatif")
            + ") ; "
            f"extrait d'appui identique {self.support_same}/{self.support_total} ; "
            f"extraits utiles identiques {self.extracts_same}/{self.extracts_total} "
            f"({100 * self.useful_rate:.0f} %, « tous utiles » ou « aucun utile » : "
            f"{self.extracts_majority}/{self.extracts_total}"
            + ("" if self.extracts_informative else ", juge non informatif")
            + ") ; "
            + (
                f"écart moyen de fidélité de bout en bout {gap:.0f} points"
                f" ({len(self.faithfulness_gaps)} cas notés, {self.faithfulness_unscored} non "
                "évalués)"
                if gap is not None
                else "fidélité de bout en bout : aucun cas noté"
            )
        )


def unreviewed_cases(doc: dict[str, Any]) -> int:
    return sum(1 for case in doc["cases"] if case["review"] == "proposed")


async def measure(doc: dict[str, Any], ask: Ask) -> Agreement:
    """Rejoue le jeu avec un vrai juge. Verdicts : chaque affirmation attendue est donnée telle
    quelle au juge (le découpage du juge n'entre pas, il serait incomparable) ; extraits utiles :
    comparés extrait par extrait ; fidélité : de bout en bout (le juge découpe lui-même), écart en
    points avec la note attendue. La pertinence dépend d'un modèle d'embedding et n'est pas mesurée
    ici."""
    result = Agreement()
    expected = [c["verdict"] for case in doc["cases"] for c in verified_claims(case)]
    result.majority_verdict = max(prompts.VERDICTS, key=expected.count)
    result.verdicts_majority = expected.count(result.majority_verdict)
    useful = sum(len(case["useful"]) for case in doc["cases"])
    every = sum(len(case["sources"]) for case in doc["cases"])
    result.extracts_majority = max(useful, every - useful)
    for case in doc["cases"]:
        sources = case["sources"]
        for claim in verified_claims(case):
            reply = await ask(prompts.verdict_request(claim["claim"], sources))
            result.verdicts_total += 1
            got: dict[str, Any] | None = None
            if reply.text is not None:
                try:
                    got = prompts.parse_verdict(reply.text, len(sources))
                except ProviderError:
                    got = None
            if got is None:
                result.verdicts_invalid += 1
                result.lines.append(f"{case['id']} · {claim['verdict']} -> sortie invalide")
                continue
            same = got["verdict"] == claim["verdict"]
            result.verdicts_same += same
            if claim["support"] is not None:
                result.support_total += 1
                result.support_same += got["support"] == claim["support"]
            if not same:
                result.lines.append(
                    f"{case['id']} · attendu {claim['verdict']}, rendu {got['verdict']}"
                )
        useful = await metrics.context_precision(ask, case["question"], case["answer"], sources)
        picked = set((useful.detail or {}).get("useful", [])) if useful.score is not None else None
        for source in sources:
            result.extracts_total += 1
            if picked is not None:
                result.extracts_same += (source["n"] in picked) == (source["n"] in case["useful"])
        faith = await metrics.faithfulness(ask, case["question"], case["answer"], sources)
        wanted = expected_faithfulness(case)
        if faith.score is None or wanted is None:
            result.faithfulness_unscored += faith.score is None and wanted is not None
        else:
            result.faithfulness_gaps.append(abs(faith.score - wanted))
    return result


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def _main(args: argparse.Namespace) -> int:
    doc = load_cases()
    if args.command == "record":
        _write(REPLAY_FILE, await record(doc))
        print(f"{REPLAY_FILE.name} réécrit : relire le diff avant de le commiter.")
        return 0
    from wavelocalai.models.ollama import OllamaChatModel, make_client  # noqa: PLC0415
    from wavelocalai.models.port import ModelRef  # noqa: PLC0415

    ref = ModelRef(args.model, "ollama", "local", "chat")
    asker = ModelAsker(OllamaChatModel(ref, make_client(args.host)))
    agreement = await measure(doc, asker.ask)
    print(agreement.summary(unreviewed_cases(doc), len(doc["cases"])))
    for line in agreement.lines:
        print(" -", line)
    for shortfall in agreement.shortfalls(doc["minimum_agreement"]):
        print("Garde du jeu fixe non passée :", shortfall)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("record", help="réécrit judge-replay.json depuis les verdicts attendus")
    live = sub.add_parser("measure", help="mesure l'accord d'un modèle Ollama installé")
    live.add_argument("--model", default="qwen2.5:1.5b")
    live.add_argument("--host", default="http://127.0.0.1:11434")
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
