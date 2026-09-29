"""
États d'interface d'EXPERIENCE.md (State Patterns) partagés par les pages : service
indisponible, erreur et délai dépassé, premier chargement d'un modèle, aucun modèle installé,
évaluation impossible.

Un `alert-error` dit ce qui a échoué et quoi faire ; la trace technique va dans un expander
replié « Détails techniques ».
"""

from contextlib import suppress

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

from src.app.formatting import format_duration
from src.app.modules import ARENA
from src.core.llm_provider import LLMProvider
from src.core.metrics import INTERRUPTED_RESPONSE_DEFAULT
from src.core.model_defaults import BENCH_MIN_SPEED_TPS, JUDGE_MIN_PARAMS_B
from src.core.model_detector import is_api_model
from src.core.providers.groq_provider import is_groq_model

# --- Service indisponible ---
OLLAMA_DOWN_MESSAGE = "Ollama ne répond pas. Démarrez-le, puis rechargez la page."
SYSTEM_AVAILABLE = "Disponible"
SYSTEM_UNAVAILABLE = "Indisponible"
# Durée de cache de l'état « disponible » d'Ollama (s) : pas d'appel à chaque interaction.
# L'état « indisponible » n'est jamais mis en cache : recharger la page suffit à le lever.
OLLAMA_STATUS_TTL_S = 10

# --- Premier chargement ---
LOADING_LABEL = "Chargement du modèle en mémoire…"
LOADING_HINT = "Le premier appel est plus long : le modèle doit d'abord être chargé en mémoire."
LOADED_LABEL = "Modèle chargé en mémoire"
LOADING_FAILED_LABEL = "Génération interrompue"

# Débit (D3) : ce qu'il mesure, en aide des métriques et colonnes « Débit ».
THROUGHPUT_HELP = (
    "Tokens générés par seconde de génération, hors chargement du modèle et lecture de la "
    "question (comme le banc de benchmark). « estimé » : durée de génération non fournie "
    "(modèle cloud), débit calculé sur la durée totale de l'appel."
)

# --- Aucun modèle ---
MANAGER_TAB_LABEL = "Gestion des modèles"
NO_MODEL_IN_ARENA = (
    f"Aucun modèle installé : installez-en un depuis l'onglet « {MANAGER_TAB_LABEL} »."
)
NO_MODEL_ELSEWHERE = (
    f"Aucun modèle installé : installez-en un depuis « {MANAGER_TAB_LABEL} », "
    f"dans l'{ARENA.title}."
)

# --- Évaluation impossible ---
NOT_EVALUATED = "non évalué"
# Réponse sans texte (tout est parti dans le raisonnement) : jamais envoyée au juge.
EMPTY_ANSWER = "Réponse vide"
EMPTY_ANSWER_REASON = "réponse vide."
REASONING_LABEL = "Raisonnement"

# --- Juge par défaut et fiabilité de sa note ---
# Moins de ~4B paramètres actifs, ou taille inconnue : deux causes, deux textes.
WEAK_JUDGE_SMALL = (
    f"Note peu fiable : le juge {{name}} a moins de {JUDGE_MIN_PARAMS_B:g} milliards de "
    "paramètres actifs."
)
WEAK_JUDGE_UNKNOWN = "Note peu fiable : la taille du juge {name} est inconnue."
# Conseil ajouté à l'avertissement, selon qu'un juge fiable tient en mémoire ou non.
STRONGER_JUDGE_ADVICE = (
    f"Choisissez un juge d'au moins {JUDGE_MIN_PARAMS_B:g} milliards de paramètres : un tel "
    "modèle tient en mémoire."
)
NO_STRONGER_JUDGE_ADVICE = "Aucun juge plus gros ne tient en mémoire : lisez la note avec prudence."
JUDGE_UNFIT_WARNING = (
    "Le juge {name} ne tient pas en mémoire : la notation risque d'échouer ou de ralentir la "
    "machine."
)
JUDGE_SELF_CAPTION = (
    "Le juge {name} fait partie des modèles évalués : il note aussi sa propre réponse."
)
# Aide du sélecteur de juge : comment le juge par défaut a été choisi.
JUDGE_HELP_CLOUD = (
    "Cloud autorisé : par défaut, le modèle cloud le plus capable parmi ceux proposés. Tout "
    "ce que le juge reçoit quitte la machine : la question, les réponses notées et, pour "
    "l'évaluation des documents, les extraits."
)
JUDGE_HELP_BENCHMARK = (
    "Choisi d'après le benchmark de ce poste : le modèle local le plus précis parmi ceux "
    f"mesurés à plus de {BENCH_MIN_SPEED_TPS:g} tokens/s, d'au moins "
    f"{JUDGE_MIN_PARAMS_B:g} milliards de paramètres actifs quand il y en a un."
)
JUDGE_HELP_FITS = "Par défaut, le plus gros modèle local qui tient en mémoire."
JUDGE_HELP_NONE_FITS = (
    "Aucun modèle local ne tient en mémoire : par défaut, le plus petit modèle local."
)
JUDGE_HELP_NO_LOCAL = "Aucun modèle local installé : choisissez le juge parmi les modèles proposés."

TECH_DETAILS_LABEL = "Détails techniques"


class _OllamaDownError(Exception):
    """Levée par le cache quand Ollama ne répond pas : st.cache_data ne garde pas les
    exceptions, donc l'état indisponible n'est jamais mis en cache."""


@st.cache_data(ttl=OLLAMA_STATUS_TTL_S, show_spinner=False)
def _ollama_up_cached() -> bool:
    if not LLMProvider.ollama_available():
        raise _OllamaDownError
    return True


def ollama_available() -> bool:
    """Ollama répond-il ? Appel local à délai court ; seul « disponible » est mis en cache."""
    try:
        return _ollama_up_cached()
    except _OllamaDownError:
        return False


def system_status_label(available: bool) -> str:
    """Valeur de la métrique « Système » : « Disponible » ou « Indisponible »."""
    return SYSTEM_AVAILABLE if available else SYSTEM_UNAVAILABLE


def render_ollama_down_alert() -> None:
    """`alert-error` « service indisponible », en tête de module."""
    st.error(OLLAMA_DOWN_MESSAGE, icon=":material/error:")


def render_answer(text: str | None) -> None:
    """Texte d'une réponse ; « Réponse vide » s'il est vide (tout est parti dans le
    raisonnement), jamais un corps blanc sans explication."""
    if text and text.strip():
        st.markdown(text)
    else:
        st.warning(EMPTY_ANSWER, icon=":material/speaker_notes_off:")


def render_error(message: str, detail: str | None = None) -> None:
    """`alert-error` : ce qui a échoué et quoi faire ; trace technique repliée."""
    st.error(message, icon=":material/error:")
    if detail:
        with st.expander(TECH_DETAILS_LABEL, expanded=False):
            st.code(detail, language=None)


def timeout_message(timeout_s) -> str:
    """« Délai dépassé (2 min) » : le délai au format fr-FR."""
    return f"Délai dépassé ({format_duration(timeout_s)})"


def inference_failure_label(result) -> str:
    """Libellé court d'une inférence en échec (ligne de l'Arène, statut)."""
    if getattr(result, "timed_out", False):
        return timeout_message(result.timeout_s)
    if getattr(result, "interrupted", False):
        return "Réponse interrompue"
    return "Échec de la génération"


def _cloud_provider_name(model_tag: str | None) -> str | None:
    """Nom du fournisseur cloud d'un modèle, ou None pour un modèle local (Ollama)."""
    if not model_tag:
        return None
    if is_groq_model(model_tag):
        return "Groq"
    tag = model_tag.lower()
    if tag.startswith(("gpt-", "o1-")):
        return "OpenAI"
    if tag.startswith("claude-"):
        return "Anthropic"
    if is_api_model(model_tag):
        return "Mistral"
    return None


def generation_failure_advice(model_tag: str | None) -> str:
    """Quoi faire après l'échec d'une génération, selon le fournisseur du modèle."""
    provider = _cloud_provider_name(model_tag)
    if provider:
        return (
            f"Le fournisseur cloud {provider} ne répond pas : vérifiez la connexion, la clé "
            "d'API et son quota, ou repassez en Local avec un modèle local."
        )
    return (
        "Vérifiez qu'Ollama est démarré et que le modèle est installé, ou choisissez un autre "
        "modèle."
    )


# Flux Ollama tronqué (fermé sans fragment final) : jamais présenté comme une réponse.
INTERRUPTED_MESSAGE = (
    f"{INTERRUPTED_RESPONSE_DEFAULT} Réessayez ; si cela se répète, choisissez un autre modèle."
)


def inference_error_message(result, model_tag: str | None = None) -> str:
    """Message d'un `alert-error` pour un InferenceResult en échec : quoi, puis quoi faire."""
    if getattr(result, "interrupted", False):
        return INTERRUPTED_MESSAGE
    if getattr(result, "timed_out", False):
        return (
            f"{timeout_message(result.timeout_s)} : le modèle n'a pas répondu à temps. Le "
            "premier appel comprend son chargement en mémoire : réessayez, ou choisissez une "
            "question plus courte ou un modèle plus petit."
        )
    return f"La génération a échoué. {generation_failure_advice(model_tag)}"


def render_inference_error(result, model_tag: str | None = None) -> None:
    """`alert-error` d'un InferenceResult en échec, détail technique replié."""
    render_error(inference_error_message(result, model_tag), result.error)


def start_loading_status(model_tag: str | None, container=None):
    """
    Affiche « Chargement du modèle en mémoire… » avant la génération si le modèle local n'est
    pas encore chargé dans Ollama (`ollama ps`).

    Retourne le st.status affiché, ou None : modèle déjà chargé, modèle cloud, ou état inconnu
    (`ps()` en échec : ni indicateur ni erreur).
    """
    if not model_tag or LLMProvider.is_model_loaded(model_tag) is not False:
        return None
    target = container if container is not None else st
    status = target.status(LOADING_LABEL, expanded=True)
    status.write(LOADING_HINT)
    return status


def finish_loading_status(status, ok: bool = True) -> None:
    """Passe l'indicateur de chargement à `complete` ou `error` selon le résultat réel."""
    if status is None:
        return
    if ok:
        status.update(label=LOADED_LABEL, state="complete", expanded=False)
    else:
        status.update(label=LOADING_FAILED_LABEL, state="error", expanded=False)


def render_no_models(in_arena: bool = False) -> None:
    """`alert-info` « aucun modèle installé », qui mène à « Gestion des modèles ».

    Rien si Ollama ne répond pas : la liste est vide parce que le service est arrêté, pas
    faute de modèle, et l'alerte « service indisponible » est déjà en tête du module.
    """
    if not ollama_available():
        return
    if in_arena:
        st.info(NO_MODEL_IN_ARENA, icon=":material/info:")
        return
    st.info(NO_MODEL_ELSEWHERE, icon=":material/info:")
    # Le lien ouvre la page (premier onglet) : il porte le nom de la page, le texte ci-dessus
    # nomme l'onglet.
    # Page exécutée hors du routeur (tests) : le chemin relatif n'est pas résolu.
    with suppress(StreamlitPageNotFoundError):
        st.page_link(ARENA.path, label=ARENA.title, icon=ARENA.icon)
