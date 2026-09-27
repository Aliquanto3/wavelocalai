"""
Accueil : état du système, mode Local ou Cloud, et accès aux modules.

Page exécutée par le routeur (Accueil.py) ; le chemin de la racine y est déjà ajouté.
"""

from datetime import date

import psutil
import streamlit as st

from src.app.formatting import NBSP, format_number, format_percent
from src.app.modules import APP_NAME, MODULES, RECOMMENDED
from src.app.states import OLLAMA_DOWN_MESSAGE, ollama_available, system_status_label
from src.app.ui import FAVICON_PATH

st.set_page_config(page_title=APP_NAME, page_icon=FAVICON_PATH, layout="wide")


def get_system_health():
    """Charge du processeur (%) et mémoire vive utilisée et totale (Go)."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    return cpu, mem.used / (1024**3), mem.total / (1024**3)


def render_module_card(module, recommended: bool = False) -> None:
    """Carte d'un module : lien au nom exact du module, puis ce qu'il montre."""
    with st.container(border=True):
        st.page_link(module.path, label=module.title, icon=module.icon)
        if recommended:
            st.caption("Démo recommandée")
        st.write(module.pitch)


def main():
    # --- EN-TÊTE ---
    st.title(APP_NAME)
    st.markdown("Le démonstrateur d'IA générative souveraine, frugale et sécurisée.")

    st.divider()

    # --- BANDEAU D'ÉTAT ---
    cpu, mem_used, mem_total = get_system_health()
    cloud_enabled = st.session_state.get("cloud_enabled", True)

    if cloud_enabled:
        mode_value = "Cloud"
        mode_help = (
            "Le cloud est autorisé : les données envoyées aux modèles cloud (Mistral, OpenAI) "
            "quittent la machine."
        )
    else:
        mode_value = "Local"
        mode_help = "Tous les modèles tournent sur cette machine (Ollama). Aucune donnée ne sort."

    col_sys, col_mode, col_cpu, col_mem = st.columns(4)
    with col_sys:
        # État réel d'Ollama (local, délai court), jamais écrit en dur.
        system_ok = ollama_available()
        st.metric(
            "Système",
            system_status_label(system_ok),
            help=(
                "Ollama, le service des modèles locaux, répond."
                if system_ok
                else OLLAMA_DOWN_MESSAGE
            ),
        )
    with col_mode:
        st.metric("Mode", mode_value, help=mode_help)
    with col_cpu:
        st.metric("Processeur", format_percent(cpu), help="Charge actuelle du processeur")
    with col_mem:
        st.metric(
            "Mémoire",
            f"{format_number(mem_used)} / {format_number(mem_total)}{NBSP}Go",
            help="Mémoire vive utilisée / mémoire vive totale",
        )

    st.divider()

    # --- MODULES ---
    st.header("Modules")

    render_module_card(RECOMMENDED, recommended=True)

    others = [m for m in MODULES if m != RECOMMENDED]
    for column, module in zip(st.columns(len(others)), others, strict=True):
        with column:
            render_module_card(module)

    # --- PIED DE PAGE ---
    st.divider()
    st.caption(f"© {date.today().year} {APP_NAME} · Wavestone")


main()
