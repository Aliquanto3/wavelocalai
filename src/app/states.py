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
from src.core.model_detector import is_api_model

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
    return "Échec de la génération"


def _cloud_provider_name(model_tag: str | None) -> str | None:
    """Nom du fournisseur cloud d'un modèle, ou None pour un modèle local (Ollama)."""
    if not model_tag:
        return None
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
            f"Le fournisseur cloud {provider} ne répond pas : vérifiez la connexion et la clé "
            "d'API, ou repassez en Local avec un modèle local."
        )
    return (
        "Vérifiez qu'Ollama est démarré et que le modèle est installé, ou choisissez un autre "
        "modèle."
    )


def inference_error_message(result, model_tag: str | None = None) -> str:
    """Message d'un `alert-error` pour un InferenceResult en échec : quoi, puis quoi faire."""
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
