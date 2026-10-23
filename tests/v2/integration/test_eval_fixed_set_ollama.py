"""Accord du vrai juge avec le jeu fixe de cas (story 7.2, marqueur `integration`).

`qwen2.5:1.5b` (déjà installé, rien n'est téléchargé) rejoue le jeu fixe de
`tests/v2/fixtures/eval/` : la part de verdicts identiques aux verdicts attendus, celle des extraits
utiles identiques et l'écart de fidélité de bout en bout sont **rapportés** (sortie du test avec
`-s`, et `record_property`). Un juge de 1,5 milliard de paramètres est peu fiable : le test
n'échoue pas sous le seuil `minimum_agreement` de `cases.json`, ni s'il ne fait pas mieux qu'un
juge trivial (toujours le verdict le plus fréquent, ou « tous utiles » / « aucun utile ») : il émet
un avertissement « juge non informatif » (`WAVELOCALAI_JUDGE_STRICT=1` le rend bloquant, pour une
campagne de mesure ou un changement du juge). Les verdicts attendus étant proposés et non relus (`review`), l'accord mesuré est indicatif.

La même mesure en ligne de commande : `python -m tests.v2.eval_fixed_set measure --model <tag>`.
Saute avec sa raison si Ollama ne répond pas ou si le modèle manque.
"""

from __future__ import annotations

import os
import warnings

import pytest

from wavelocalai.config import load_settings
from wavelocalai.models.ollama import OllamaChatModel, make_client
from wavelocalai.models.port import ModelRef

from .. import eval_fixed_set as fixed
from .test_rag_question_ollama import CHAT_MODEL, _require_chat_model

pytestmark = pytest.mark.integration


async def test_the_real_judge_is_measured_against_the_fixed_set(record_property, tmp_path):
    settings = load_settings(
        env_file=tmp_path / "absent.env", environ={}, overrides={"data": {"dir": tmp_path / "data"}}
    )
    _require_chat_model(settings.ollama.host)
    doc = fixed.load_cases()
    model = OllamaChatModel(
        ModelRef(CHAT_MODEL, "ollama", "local", "chat"), make_client(settings.ollama.host)
    )

    agreement = await fixed.measure(doc, fixed.ModelAsker(model).ask)

    summary = agreement.summary(fixed.unreviewed_cases(doc), len(doc["cases"]))
    print("\n" + summary)
    for line in agreement.lines:
        print(" -", line)
    record_property("agreement", summary)
    expected = sum(len(fixed.verified_claims(case)) for case in doc["cases"])
    assert agreement.verdicts_total == expected > 0
    assert 0.0 <= agreement.verdict_rate <= 1.0 and 0.0 <= agreement.useful_rate <= 1.0

    below = agreement.shortfalls(doc["minimum_agreement"])
    if below:
        message = f"Garde du jeu fixe non passée ({' ; '.join(below)}). {summary}"
        assert os.environ.get("WAVELOCALAI_JUDGE_STRICT") != "1", message
        warnings.warn(message, stacklevel=1)
