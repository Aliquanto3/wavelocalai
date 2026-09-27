import platform
import socket
import sys

import pandas as pd
import plotly.express as px
import psutil
import streamlit as st

from src.app.formatting import (
    NBSP,
    PLOTLY_SEPARATORS,
    format_number,
    format_percent,
    format_unit,
)
from src.app.modules import SOBRIETY
from src.app.ui import FAVICON_PATH

# --- IMPORT DYNAMIQUE ---
try:
    from src.core.config import get_emissions_path
    from src.core.green_monitor import GreenTracker, HardwareMonitor
except ImportError:
    GreenTracker = None
    HardwareMonitor = None

    def get_emissions_path():
        return "emissions.csv"


# --- CONFIGURATION ---
st.set_page_config(page_title=SOBRIETY.title, page_icon=FAVICON_PATH, layout="wide")

# --- FONCTIONS UTILITAIRES ---


def get_device_info():
    """Détecte le moteur de calcul (processeur, CUDA ou MPS)."""
    device_type = "Processeur seul"
    device_details = "Processeur x64 ou ARM"

    try:
        import torch

        if torch.cuda.is_available():
            device_type = "GPU NVIDIA (CUDA)"
            device_details = torch.cuda.get_device_name(0)
        elif torch.backends.mps.is_available():
            device_type = "Apple Silicon (MPS)"
            device_details = "Metal Performance Shaders"
    except ImportError:
        pass

    return device_type, device_details


def get_true_system_metrics():
    """Récupère les métriques temps réel."""
    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    return cpu_pct, mem.percent, round(mem.used / (1024**3), 2), round(mem.total / (1024**3), 2)


def get_co2_equivalencies(emissions_kg):
    """Calcule des équivalences parlantes."""
    km_car = emissions_kg / 0.110  # Moyenne voiture thermique
    smartphones = (emissions_kg * 1000) / 5  # Charge smartphone ~5g CO2
    return km_car, smartphones


# --- INIT TRACKER ---
if "tracker" not in st.session_state and GreenTracker:
    st.session_state.tracker = GreenTracker(project_name="wavelocal_audit")
    st.session_state.tracker.start()

# ==========================================
# UI PRINCIPALE
# ==========================================

st.title(SOBRIETY.title)
st.caption("La machine hôte, sa charge et les émissions de CO₂ de sa consommation électrique.")

st.divider()

# --- 1. TÉLÉMÉTRIE TEMPS RÉEL ---
st.header("Santé du système")

cpu_val, ram_pct, ram_used, ram_total = get_true_system_metrics()
device_type, device_details = get_device_info()

# Mode lu dans le contrôle global « Autoriser le cloud » (barre latérale commune).
if st.session_state.get("cloud_enabled", True):
    mode_value = "Cloud"
    mode_help = "Le cloud est autorisé : des données peuvent partir vers Mistral ou OpenAI."
else:
    mode_value = "Local"
    mode_help = "Aucune donnée ne part vers un service cloud : seuls les modèles locaux tournent."

with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            label="Processeur",
            value=format_percent(cpu_val),
            help="Charge actuelle du processeur",
        )

    with c2:
        st.metric(
            label="Mémoire",
            value=f"{format_number(ram_used)} / {format_number(ram_total)}{NBSP}Go",
            help=f"Mémoire vive utilisée / totale, soit {format_percent(ram_pct)}",
        )

    with c3:
        st.metric(
            label="Accélérateur IA",
            value="Actif",
            help=f"Moteur de calcul détecté : {device_details}",
        )
        st.caption(device_type)

    with c4:
        st.metric(label="Mode", value=mode_value, help=mode_help)

# --- 2. GREEN OPS MONITORING ---
st.header("Empreinte carbone")

col_live, col_hist = st.columns([1, 2])

with col_live, st.container(border=True):
    st.subheader("Session en cours")

    if st.session_state.get("tracker") and st.session_state.tracker._is_running:
        st.success("Suivi carbone actif")
        st.caption(
            "Mesure fondée sur la puissance du matériel et le mix électrique local.",
            help="Mesure CodeCarbon",
        )

        if st.button("Arrêter et enregistrer", icon=":material/stop_circle:", width="stretch"):
            em = st.session_state.tracker.stop()
            st.session_state.last_emissions = em
            st.rerun()
    else:
        st.warning("Suivi carbone en pause")
        if "last_emissions" in st.session_state:
            em = st.session_state.last_emissions
            km, phones = get_co2_equivalencies(em)

            st.metric("Total de la session", format_unit(em, "kgCO₂", 5))
            st.caption(f"soit environ {format_unit(km, 'km', 4)} en voiture")

        if st.session_state.get("tracker") and st.button(
            "Reprendre le suivi", icon=":material/play_circle:", width="stretch"
        ):
            st.session_state.tracker.start()
            st.rerun()

    st.info(
        "Cette mesure porte sur la consommation électrique de cette machine. L'impact par "
        "réponse affiché dans les autres modules est une estimation théorique."
    )

with col_hist:
    st.subheader("Historique des émissions")
    try:
        csv_path = get_emissions_path()
        df_emissions = pd.read_csv(csv_path)

        if not df_emissions.empty:
            df_emissions["timestamp"] = pd.to_datetime(df_emissions["timestamp"])
            df_chart = df_emissions.tail(50)

            fig = px.area(
                df_chart,
                x="timestamp",
                y="emissions",
                title="Émissions de CO₂ par session (kg)",
                labels={"emissions": "Émissions (kg CO₂)", "timestamp": "Date"},
            )
            # Formats fr-FR sans locale Plotly (chargée depuis un CDN) : date numérique,
            # virgule décimale, espace fine pour les milliers.
            fig.update_layout(
                height=250,
                margin={"l": 20, "r": 20, "t": 30, "b": 20},
                separators=PLOTLY_SEPARATORS,
            )
            fig.update_xaxes(tickformat="%d/%m %H:%M", hoverformat="%d/%m/%Y %H:%M")

            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Aucune session mesurée pour l'instant.")
    except Exception as e:
        st.warning(f"Impossible de charger l'historique : {e}")

# --- 3. SPÉCIFICATIONS TECHNIQUES ---
st.header("Carte d'identité technique")

with st.expander("Afficher les détails", expanded=False):
    sys_info = {}
    try:
        sys_info["Système d'exploitation"] = f"{platform.system()} {platform.release()}"
        sys_info["Architecture"] = platform.machine()
        sys_info["Nom de la machine"] = socket.gethostname()
        sys_info["Python"] = sys.version.split()[0]
        sys_info["Cœurs logiques"] = psutil.cpu_count(logical=True)
    except Exception:
        # Optionnel : loguer l'erreur pour le débogage
        # print(f"Erreur lors de la lecture du système: {e}")
        sys_info["État"] = "Erreur de lecture du système"

    st.json(sys_info)

# --- FOOTER ACTIONS ---
st.divider()
c_ref, c_spacer = st.columns([1, 5])
with c_ref:
    if st.button("Rafraîchir", icon=":material/refresh:"):
        st.rerun()
