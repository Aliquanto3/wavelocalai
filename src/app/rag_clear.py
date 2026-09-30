"""
« Vider la base documentaire » de l'Assistant documentaire, en deux temps dans le dialogue de
la base (pas de dialogue imbriqué) : le premier clic pose un drapeau de session, remis à zéro
à chaque ouverture du dialogue ; la confirmation nomme la conséquence chiffrée.
Le succès est posé avant st.rerun (qui ferme le dialogue) et affiché au run suivant.
"""

import streamlit as st

from src.app.formatting import pluralize
from src.app.states import render_error

CLEAR_PENDING_KEY = "rag_clear_pending"
LAST_CLEAR_KEY = "rag_last_clear"
# Réponses de la Discussion (avec leurs extraits) : vidées avec la base.
RAG_MESSAGES_KEY = "rag_messages"
CLEAR_LABEL = "Vider la base documentaire"
CLEAR_CONFIRM_LABEL = "Vider définitivement"
CLEAR_CANCEL_LABEL = "Annuler"
CLEAR_FAILED_MESSAGE = (
    "La base documentaire n'a pas pu être vidée. Réessayez ; si l'erreur persiste, "
    "redémarrez l'application."
)


def _clear_scope(stats: dict) -> tuple[str, bool]:
    """« 42 extraits de 3 documents » et vrai si le nombre d'extraits appelle le pluriel."""
    sources = [s for s in stats.get("sources", []) if s]
    count = stats["count"]
    scope = pluralize(count, "extrait")
    if sources:
        scope += f" de {pluralize(len(sources), 'document')}"
    return scope, count >= 2


def clear_warning(stats: dict) -> str:
    """Conséquence chiffrée du vidage : « 42 extraits de 3 documents seront supprimés. »"""
    scope, plural = _clear_scope(stats)
    return f"{scope} {'seront supprimés' if plural else 'sera supprimé'}."


def clear_success(stats: dict) -> str:
    """Succès au même verbe : « Base documentaire vidée : 42 extraits de 3 documents
    supprimés. »"""
    scope, plural = _clear_scope(stats)
    return f"Base documentaire vidée : {scope} {'supprimés' if plural else 'supprimé'}."


def request_clear() -> None:
    """Premier clic : demande la confirmation, sans rien supprimer."""
    st.session_state[CLEAR_PENDING_KEY] = True


def reset_clear() -> None:
    """Ouverture du dialogue : aucune confirmation en attente."""
    st.session_state[CLEAR_PENDING_KEY] = False


def render_clear_section(rag_engine, stats: dict, pending: bool) -> None:
    """
    Section « Vider la base documentaire » du dialogue. Sans demande en attente (`pending`
    faux) : le bouton seul, désactivé si la base est vide ; son rappel pose le drapeau, et le
    run suivant du dialogue affiche la confirmation. En attente : avertissement chiffré,
    « Vider définitivement » et « Annuler » côte à côte (confirm-dialog).
    """
    empty = stats["count"] == 0
    if empty or not pending:
        st.button(
            CLEAR_LABEL,
            type="secondary",
            icon=":material/delete:",
            disabled=empty,
            on_click=request_clear,
            help="La base est déjà vide." if empty else None,
        )
        return

    st.markdown(f"**{CLEAR_LABEL} ?**")
    st.warning(clear_warning(stats), icon=":material/warning:")
    col_confirm, col_cancel = st.columns(2)
    with col_confirm:
        confirmed = st.button(
            CLEAR_CONFIRM_LABEL, type="secondary", icon=":material/delete:", width="stretch"
        )
    with col_cancel:
        cancelled = st.button(CLEAR_CANCEL_LABEL, width="stretch")

    if confirmed:
        success = clear_success(stats)
        try:
            rag_engine.clear_database()
        except Exception as e:
            reset_clear()
            render_error(CLEAR_FAILED_MESSAGE, f"{type(e).__name__}: {e}")
            return
        reset_clear()
        # Les réponses et leurs extraits disparaissent avec les documents.
        st.session_state[RAG_MESSAGES_KEY] = []
        st.session_state[LAST_CLEAR_KEY] = success
        # st.rerun ferme le dialogue : le succès s'affiche au run suivant.
        st.rerun()
    elif cancelled:
        # « Annuler » ferme le dialogue sans rien supprimer.
        reset_clear()
        st.rerun()
