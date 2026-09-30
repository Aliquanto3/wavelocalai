import platform
import socket
import sys

import pandas as pd
import plotly.graph_objects as go
import psutil
import streamlit as st

from src.app.charts import (
    DEFAULT_HISTORY_WINDOW,
    HISTORY_WINDOWS,
    empty_window_text,
    palette_size,
    prepare_emissions_history,
    slot_color,
)
from src.app.formatting import (
    NBSP,
    PLOTLY_SEPARATORS,
    format_co2,
    format_number,
    format_percent,
    format_significant,
    grams_to_kg,
)
from src.app.modules import SOBRIETY
from src.app.ui import (
    FAVICON_PATH,
    MODE_CLOUD_BADGE_HELP,
    MODE_LOCAL_BADGE_HELP,
    cloud_enabled,
    render_badge,
)
from src.core.accelerator import KIND_APPLE, KIND_NVIDIA, detect_accelerator

# --- IMPORT DYNAMIQUE ---
try:
    from src.core.green_monitor import (
        AUDIT_PROJECT,
        GreenTracker,
        HardwareMonitor,
        read_app_emissions,
    )
except ImportError:
    AUDIT_PROJECT = None
    GreenTracker = None
    HardwareMonitor = None
    read_app_emissions = None

# Suivi carbone absent (CodeCarbon non installé) : ni mesure ni historique.
TRACKING_UNAVAILABLE = (
    "Suivi carbone indisponible : le module de mesure (CodeCarbon) n'a pas pu être chargé."
)


# --- CONFIGURATION ---
st.set_page_config(page_title=SOBRIETY.title, page_icon=FAVICON_PATH, layout="wide")

# --- FONCTIONS UTILITAIRES ---


def get_device_info():
    """Accélérateur réellement détecté : (valeur de la métrique, légende, aide).

    « Aucun » si rien n'est détecté ou si la détection échoue ; jamais « Actif » en dur.
    """
    info = detect_accelerator()
    if info.kind == KIND_NVIDIA:
        return info.name, "GPU NVIDIA", f"Détecté par le pilote NVIDIA : {info.name}"
    if info.kind == KIND_APPLE:
        return info.name, "GPU intégré (Metal)", "Puce Apple : le GPU intégré sert à l'inférence."
    return (
        "Aucun",
        "Aucun GPU NVIDIA ni Apple détecté",
        "Aucun GPU NVIDIA ni puce Apple détecté. Un autre GPU (AMD, Intel) n'est pas "
        "recherché ici.",
    )


def get_true_system_metrics():
    """Récupère les métriques temps réel."""
    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    return cpu_pct, mem.percent, round(mem.used / (1024**3), 2), round(mem.total / (1024**3), 2)


def get_co2_equivalencies(emissions_kg):
    """Équivalences parlantes d'une masse de CO₂ en kilogrammes (convertir d'abord les
    grammes de GreenTracker.stop() avec grams_to_kg)."""
    km_car = emissions_kg / 0.110  # Moyenne voiture thermique
    smartphones = (emissions_kg * 1000) / 5  # Charge smartphone ~5g CO2
    return km_car, smartphones


def render_emissions_history(df_emissions):
    """Historique des émissions : une barre par session sur la période choisie, dans l'unité
    CO₂ de la règle (mg le plus souvent) ; aucune liaison entre deux mesures, une période sans
    session reste vide. Valeurs exactes dans une vue tableau repliée."""
    window = st.segmented_control(
        "Période",
        list(HISTORY_WINDOWS),
        default=DEFAULT_HISTORY_WINDOW,
        required=True,
        key="emissions_history_window",
    )
    history = prepare_emissions_history(df_emissions, window or DEFAULT_HISTORY_WINDOW)
    if history.empty:
        st.info(empty_window_text(history.older_count))
        return

    sessions = history.sessions
    day_format = "%d/%m/%Y" if history.show_year else "%d/%m"
    fig = go.Figure(
        go.Bar(
            x=sessions["timestamp"],
            y=sessions["co2"],
            width=sessions["width_ms"],
            # Sessions au même horodatage : côte à côte, jamais superposées.
            offset=sessions["offset_ms"],
            # Une seule série : première couleur de la palette du thème.
            marker={"color": slot_color(0, palette_size())},
            name="CO₂ par session",
            hovertext=sessions["hover"],
            hoverinfo="text",
        )
    )
    # Formats fr-FR sans locale Plotly (chargée depuis un CDN) : dates numériques, virgule
    # décimale, espace fine pour les milliers.
    fig.update_layout(
        title="Émissions de CO₂ par session",
        height=300,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        separators=PLOTLY_SEPARATORS,
        showlegend=False,
        barcornerradius=4,
    )
    fig.update_xaxes(
        title="Date",
        type="date",
        range=list(history.x_range),
        # Graduation d'un jour ou plus : date seule ; en dessous, date et heure ; l'année sur
        # les longues périodes (« Tout ») ou à cheval sur deux années.
        tickformatstops=[
            {"dtickrange": [None, 43_200_000], "value": f"{day_format} %H:%M"},
            {"dtickrange": [43_200_001, None], "value": day_format},
        ],
    )
    fig.update_yaxes(title=f"CO₂ ({history.unit})", rangemode="tozero", separatethousands=True)
    st.plotly_chart(fig, width="stretch")

    with st.expander("Voir les données", expanded=False):
        st.dataframe(
            pd.DataFrame({"Date": sessions["timestamp"], "CO₂": sessions["co2"]}),
            column_config={
                "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY HH:mm"),
                "CO₂": st.column_config.NumberColumn(f"CO₂ ({history.unit})", format="localized"),
            },
            hide_index=True,
            width="stretch",
        )


# --- INIT TRACKER ---
if "tracker" not in st.session_state and GreenTracker:
    st.session_state.tracker = GreenTracker(project_name=AUDIT_PROJECT)
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
accelerator_value, accelerator_caption, accelerator_help = get_device_info()

# Mode lu dans le contrôle global « Autoriser le cloud » (barre latérale commune).
cloud_on = cloud_enabled()
if cloud_on:
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
        st.metric(label="Accélérateur IA", value=accelerator_value, help=accelerator_help)
        st.caption(accelerator_caption)

    with c4:
        st.metric(label="Mode", value=mode_value, help=mode_help)
        render_badge(cloud_on, help=MODE_CLOUD_BADGE_HELP if cloud_on else MODE_LOCAL_BADGE_HELP)

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
    elif GreenTracker is None:
        st.warning(TRACKING_UNAVAILABLE)
    else:
        st.warning("Suivi carbone en pause")
        if "last_emissions" in st.session_state:
            # GreenTracker.stop() renvoie des grammes ; les équivalences prennent des kg.
            em_g = st.session_state.last_emissions
            em_kg = grams_to_kg(em_g)

            st.metric("Total de la session", format_co2(em_g))
            # Valeur absente : pas d'équivalence (jamais « 0 km »).
            if em_kg is not None:
                km, phones = get_co2_equivalencies(em_kg)
                st.caption(f"soit environ {format_significant(km)}{NBSP}km en voiture")

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
        # Sessions de l'app, lues dans le fichier écrit par le suivi (GreenTracker) ; jamais
        # le fichier du benchmark.
        df_emissions = read_app_emissions() if read_app_emissions else None

        if df_emissions is None:
            st.warning(TRACKING_UNAVAILABLE)
        elif not df_emissions.empty:
            render_emissions_history(df_emissions)
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
