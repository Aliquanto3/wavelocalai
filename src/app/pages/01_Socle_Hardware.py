import platform
import socket
import sys

import pandas as pd
import plotly.express as px
import psutil
import streamlit as st

from src.app.ui import FAVICON_PATH, render_logo

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
st.set_page_config(page_title="Socle Hardware", page_icon=FAVICON_PATH, layout="wide")
render_logo()

# --- FONCTIONS UTILITAIRES ---


def get_device_info():
    """Détecte intelligemment le type de 'Moteur' (CPU/CUDA/MPS)."""
    device_type = "CPU Only"
    device_details = "Standard x64/ARM"

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

st.title("Cockpit GreenOps & Hardware")
st.caption("Monitoring de l'infrastructure hôte (Scope 2 - Électricité).")

st.divider()

# --- 1. TÉLÉMÉTRIE TEMPS RÉEL ---
st.header("1. Santé du Système")

cpu_val, ram_pct, ram_used, ram_total = get_true_system_metrics()
device_type, device_details = get_device_info()

# Logique de sécurité dynamique (Cohérence avec Accueil.py)
# Utilise le state global défini dans Accueil.py
if st.session_state.get("cloud_enabled", True):
    sec_value = "Hybride"
    sec_delta = "API Active"
    sec_help = (
        "Attention : Des flux sortants vers Mistral/OpenAI sont autorisés par le réglage global."
    )
    sec_color = "normal"
else:
    sec_value = "Confiné"
    sec_delta = "Offline"
    sec_help = (
        "Sécurisé : Aucun flux sortant vers des API publiques. Le mode local strict est activé."
    )
    sec_color = "normal"

with st.container(border=True):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            label="Processeur (CPU)",
            value=f"{cpu_val}%",
            delta="Charge Actuelle",
            delta_color="inverse" if cpu_val > 80 else "normal",
        )

    with c2:
        st.metric(
            label="Mémoire (RAM)",
            value=f"{ram_pct}%",
            delta=f"{ram_used}/{ram_total} GB",
            delta_color="inverse" if ram_pct > 85 else "normal",
        )

    with c3:
        st.metric(
            label="Accélérateur AI",
            value="Actif",
            delta=device_type,
            help=f"Moteur de calcul détecté : {device_details}",
        )

    with c4:
        st.metric(
            label="Sécurité Données",
            value=sec_value,
            delta=sec_delta,
            delta_color=sec_color,
            help=sec_help,
        )

# --- 2. GREEN OPS MONITORING ---
st.header("2. Empreinte Carbone (Machine)")

col_live, col_hist = st.columns([1, 2])

with col_live, st.container(border=True):
    st.subheader("Session Actuelle")

    if st.session_state.get("tracker") and st.session_state.tracker._is_running:
        st.success("Tracking Actif (CodeCarbon)")
        st.caption("Mesure basée sur le TDP matériel et le mix électrique local.")

        if st.button("Arrêter & Sauvegarder", icon=":material/stop_circle:", width="stretch"):
            em = st.session_state.tracker.stop()
            st.session_state.last_emissions = em
            st.rerun()
    else:
        st.warning("Tracking en pause")
        if "last_emissions" in st.session_state:
            em = st.session_state.last_emissions
            km, phones = get_co2_equivalencies(em)

            st.metric("Total Session", f"{em:.5f} kgCO₂")
            st.caption(f"soit ~ **{km:.4f} km** en voiture")

        if st.session_state.get("tracker") and st.button(
            "Reprendre le tracking", icon=":material/play_circle:", width="stretch"
        ):
            st.session_state.tracker.start()
            st.rerun()

    st.info(
        "**Note :** Ceci mesure la consommation électrique de votre PC. L'impact 'par token' affiché dans les autres onglets est une estimation théorique (Scope 3)."
    )

with col_hist:
    st.subheader("Historique d'Émissions")
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
                title="Cumul CO2 (kg) au fil du temps",
                labels={"emissions": "Emissions (kg)", "timestamp": "Temps"},
            )
            fig.update_layout(height=250, margin={"l": 20, "r": 20, "t": 30, "b": 20})

            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Pas assez de données pour afficher l'historique.")
    except Exception as e:
        st.warning(f"Impossible de charger l'historique : {e}")

# --- 3. SPÉCIFICATIONS TECHNIQUES ---
st.header("3. Carte d'Identité Technique")

with st.expander("Voir les détails complets", expanded=False):
    sys_info = {}
    try:
        sys_info["OS"] = f"{platform.system()} {platform.release()}"
        sys_info["Machine"] = platform.machine()
        sys_info["Hostname"] = socket.gethostname()
        sys_info["Python"] = sys.version.split()[0]
        sys_info["CPU Cores"] = psutil.cpu_count(logical=True)
    except Exception:
        # Optionnel : loguer l'erreur pour le débogage
        # print(f"Erreur lors de la lecture du système: {e}")
        sys_info["Status"] = "Erreur lecture système"

    st.json(sys_info)

# --- FOOTER ACTIONS ---
st.divider()
c_ref, c_spacer = st.columns([1, 5])
with c_ref:
    if st.button("Rafraîchir", icon=":material/refresh:"):
        st.rerun()
