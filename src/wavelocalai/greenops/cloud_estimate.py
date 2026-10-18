"""Estimation du CO2 d'une réponse cloud par ecologits (AD-10, AD-11).

Après l'appel, `estimate_cloud_co2` demande à `ecologits.tracers.utils.llm_impacts` l'empreinte de la
génération (arguments nommés ; **jamais `EcoLogits.init()`**, qui instrumenterait les SDK). Le calcul
ne lit que les tables livrées avec le paquet : aucun appel réseau. Le résultat est toujours un `Co2` :

- `ecologits` : `mg` est le milieu de la plage d'ecologits, `range_mg` en donne les bornes (kgCO2eq
  converti en mg), `estimated` vaut vrai, `allocation` `direct` ;
- `unmeasurable` : `mg` nul et `reason` en français (jamais 0 pour un inconnu). Un modèle absent du
  référentiel d'ecologits, un Groq sans entrée dans la table de `wavelocalai.toml`, un résultat avec
  `errors` non vide, des jetons ou un délai absents, ou une exception d'ecologits y mènent.

Aucune mesure n'interrompt un run : la fonction ne lève jamais. La zone de mix électrique est celle du
centre de données du fournisseur (`electricity_mix_zone=None`, valeur par défaut d'ecologits) : le
pays de `Settings` décrit ce poste, pas le serveur du fournisseur. `ecologits` n'est importé que dans la
fonction (AD-4).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from wavelocalai.runs.models import Co2

logger = logging.getLogger("wavelocalai.greenops")

KG_TO_MG = 1_000_000.0

# Fournisseur de `wavelocalai.toml` -> fournisseur d'ecologits. Groq n'y figure pas : ses modèles
# passent par la table `[cloud.groq_ecologits]` vers l'entrée `huggingface_hub` du modèle ouvert.
DIRECT_PROVIDERS: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "mistral": "mistralai",
}
GROQ_ECOLOGITS_PROVIDER = "huggingface_hub"
PROVIDER_NAMES = {
    "openai": "OpenAI",
    "groq": "Groq",
    "anthropic": "Anthropic",
    "mistral": "Mistral",
}

# Codes d'erreur d'ecologits -> raison affichée (la raison de repli cite le code).
_ERROR_REASONS: dict[str, str] = {
    "model-not-registered": (
        "{provider} ne publie pas la taille de ce modèle : ecologits ne le connaît pas, "
        "son empreinte ne peut pas être calculée."
    ),
    "zone-not-registered": (
        "ecologits ne connaît pas le mix électrique demandé : l'empreinte ne peut pas être calculée."
    ),
}


def _unmeasurable(reason: str) -> Co2:
    return Co2(mg=None, method="unmeasurable", reason=reason)


def ecologits_target(
    provider: str, model: str, groq_table: Mapping[str, str]
) -> tuple[str, str] | str:
    """`(fournisseur, modèle)` d'ecologits pour un modèle cloud, ou la raison du refus (texte)."""
    name = PROVIDER_NAMES.get(provider, provider)
    if provider in DIRECT_PROVIDERS:
        return DIRECT_PROVIDERS[provider], model
    if provider == "groq":
        mapped = groq_table.get(model)
        if mapped:
            return GROQ_ECOLOGITS_PROVIDER, mapped
        return (
            f"{name} ne publie pas l'architecture de ce modèle et la table de correspondance de "
            "wavelocalai.toml n'a pas d'entrée pour lui : son empreinte ne peut pas être calculée."
        )
    return f"Le fournisseur {name} n'est pas couvert par ecologits : empreinte non calculable."


def _reason_from_errors(errors: list[Any], provider: str) -> str:
    code = str(getattr(errors[0], "code", "") or "")
    name = PROVIDER_NAMES.get(provider, provider)
    template = _ERROR_REASONS.get(code)
    if template is not None:
        return template.format(provider=name)
    return f"ecologits n'a pas pu calculer l'empreinte (code « {code or 'inconnu'} »)."


def _range_mg(value: Any) -> tuple[float, float] | None:
    """Bornes en mg d'un `gwp.value` (plage `min`/`max` ou nombre seul, en kgCO2eq)."""
    low = getattr(value, "min", None)
    high = getattr(value, "max", None)
    if low is None or high is None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        low = high = value
    low_mg, high_mg = float(low) * KG_TO_MG, float(high) * KG_TO_MG
    if not (0 <= low_mg <= high_mg) or not high_mg > 0:  # négatif, inversé, NaN ou nul : jamais 0
        return None
    return low_mg, high_mg


def estimate_cloud_co2(
    provider: str,
    model: str,
    *,
    output_tokens: int | None,
    latency_s: float | None,
    groq_table: Mapping[str, str] | None = None,
    electricity_mix_zone: str | None = None,
) -> Co2:
    """CO2 estimé d'une réponse cloud, ou `unmeasurable` avec sa raison ; ne lève jamais.

    `provider` et `model` sont ceux du tag cloud `fournisseur/modèle` (`groq` + `openai/gpt-oss-120b`).
    """
    try:
        target = ecologits_target(provider, model, groq_table or {})
        if isinstance(target, str):
            return _unmeasurable(target)
        if not output_tokens or output_tokens <= 0:
            return _unmeasurable(
                f"{PROVIDER_NAMES.get(provider, provider)} n'a pas indiqué le nombre de jetons "
                "générés : l'empreinte ne peut pas être calculée."
            )
        if latency_s is None or latency_s <= 0:
            return _unmeasurable("La durée de la réponse est inconnue : empreinte non calculable.")
        from ecologits.tracers.utils import llm_impacts  # lazy : AD-4

        impacts = llm_impacts(
            provider=target[0],
            model_name=target[1],
            output_token_count=int(output_tokens),
            request_latency=float(latency_s),
            electricity_mix_zone=electricity_mix_zone,
        )
        if impacts.errors:
            return _unmeasurable(_reason_from_errors(list(impacts.errors), provider))
        bounds = _range_mg(impacts.gwp.value) if impacts.gwp is not None else None
        if bounds is None:
            return _unmeasurable("ecologits n'a pas rendu d'empreinte carbone pour cette réponse.")
        low, high = bounds
        return Co2(
            mg=(low + high) / 2,
            method="ecologits",
            estimated=True,
            range_mg={"low": low, "high": high},
            allocation="direct",
        )
    except Exception as exc:  # noqa: BLE001 - aucune mesure n'interrompt un run (AD-11)
        logger.warning("Estimation ecologits impossible pour %s/%s : %r", provider, model, exc)
        return _unmeasurable(
            f"L'estimation d'ecologits a échoué ({type(exc).__name__}) : empreinte non calculable."
        )
