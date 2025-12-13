import streamlit as st
import time
import pandas as pd
import plotly.express as px
from src.core.green_monitor import HardwareMonitor, GreenTracker

# Configuration de la page
st.set_page_config(page_title="Socle Hardware & Green IT", page_icon="🔋", layout="wide")

st.title("🔋 Socle Technique & Green Monitor")
st.markdown("---")

# --- Récupération du Singleton (Lazy Loading de sécurité) ---
if "tracker" not in st.session_state:
    # Au cas où l'utilisateur arriverait directement sur cette page (URL directe)
    st.session_state.tracker = GreenTracker(project_name="wavelocal_audit_direct")
    st.session_state.tracker.start()

# --- Section 1: Dashboard Temps Réel ---
st.subheader("1. Télémétrie Système (Live)")

# Récupération des données
sys_info = HardwareMonitor.get_system_info()
metrics = HardwareMonitor.get_realtime_metrics()

# Layout en colonnes pour les KPIs
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="CPU Usage", 
        value=f"{metrics.cpu_usage_percent}%",
        delta=f"{sys_info['cpu_cores_physical']} Cores Phy",
        delta_color="off"
    )

with col2:
    st.metric(
        label="RAM Usage", 
        value=f"{metrics.ram_usage_percent}%",
        delta=f"{metrics.ram_used_gb}/{metrics.ram_total_gb} GB"
    )

with col3:
    gpu_label = metrics.gpu_name if metrics.gpu_name else "No GPU"
    gpu_val = f"{metrics.gpu_memory_used_gb} GB" if metrics.gpu_memory_used_gb else "0 GB"
    st.metric(
        label="GPU Memory", 
        value=gpu_val, 
        delta=gpu_label,
        delta_color="normal" if metrics.gpu_name != "N/A" else "off"
    )

with col4:
    # Pour l'instant, estimation simple ou lecture du dernier log CodeCarbon
    # Dans une version future, on lira le CSV en temps réel
    st.metric(label="Mode", value="Local Only", delta="Privacy Preserved")

# --- Section 2: Détails Hardware (Audit) ---
st.markdown("### 2. Audit de Configuration")
with st.expander("Voir les détails complets de la machine", expanded=False):
    st.json(sys_info)

# --- Section 3: Green IT Monitor (Optimisée) ---
st.markdown("### 3. Impact Carbone Session")
col_green_1, col_green_2 = st.columns([1, 2])

with col_green_1:
    st.info(
        """
        **Méthodologie :**
        L'estimation se base sur le TDP (Thermal Design Power) de votre CPU/GPU 
        et l'intensité carbone du mix électrique français (environ 50-60 gCO2/kWh).
        """
    )
    
    # Bouton d'action intelligent
    if st.session_state.tracker._is_running:
        if st.button("🛑 Arrêter le tracking & Sauvegarder"):
            # On arrête réellement le tracker global
            emissions = st.session_state.tracker.stop()
            st.session_state.last_emissions = emissions
            st.success(f"Session sauvegardée. Émissions : {emissions:.6f} kg CO2eq")
    else:
        st.warning("Tracking en pause.")
        if st.button("▶️ Reprendre le tracking"):
            st.session_state.tracker.start()
            st.rerun()

with col_green_2:
    # Lecture du fichier d'historique CodeCarbon s'il existe
    try:
        from src.core.config import get_emissions_path
        df_emissions = pd.read_csv(get_emissions_path())
        if not df_emissions.empty:
            fig = px.bar(
                df_emissions.tail(10), 
                x="timestamp", 
                y="emissions", 
                title="Historique des émissions (10 dernières sessions)",
                labels={"emissions": "kg CO2eq"}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Pas encore de données historiques.")
    except FileNotFoundError:
        st.warning("Fichier de logs carbone non trouvé (Premier lancement ?).")

# Bouton de rafraîchissement manuel
if st.button("🔄 Actualiser les métriques"):
    st.rerun()