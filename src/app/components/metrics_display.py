# src/app/components/metrics_display.py
"""
Composants d'affichage des métriques.
"""

import streamlit as st

from src.core.metrics_service import DisplayMetrics, get_metrics_service


def render_metrics_badge(
    tokens_per_second: float,
    carbon_g: float,
    compact: bool = True,
) -> None:
    """
    Affiche un badge compact avec les métriques clés.

    Args:
        tokens_per_second: Débit de génération
        carbon_g: Émissions carbone en grammes
        compact: Mode compact (une ligne) ou détaillé
    """
    service = get_metrics_service()

    tps_str = service.format_tokens_per_second(tokens_per_second)
    carbon_str = service.format_carbon(carbon_g)

    if compact:
        st.caption(f"⚡ {tps_str} · 🌱 {carbon_str}")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Vitesse", tps_str)
        with col2:
            st.metric("Carbone", carbon_str)


def render_metrics_expander(
    metrics: DisplayMetrics,
    title: str = "📊 Métriques détaillées",
    expanded: bool = False,
) -> None:
    """
    Affiche les métriques dans un expander.

    Args:
        metrics: Métriques formatées
        title: Titre de l'expander
        expanded: État initial (ouvert/fermé)
    """
    with st.expander(title, expanded=expanded):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**⚡ Performance**")
            st.write(f"Vitesse : {metrics.tokens_per_second}")
            st.write(f"Durée : {metrics.total_duration}")

        with col2:
            st.markdown("**📝 Tokens**")
            st.write(f"Entrée : {metrics.input_tokens}")
            st.write(f"Sortie : {metrics.output_tokens}")

        with col3:
            st.markdown("**🌱 Impact**")
            st.write(f"Carbone : {metrics.carbon_formatted}")
            st.write(f"Énergie : {metrics.energy_wh} Wh")

        # Indicateur local/cloud
        if metrics.is_local:
            st.success("🏠 Inférence locale", icon="✅")
        else:
            st.info("☁️ Inférence cloud", icon="ℹ️")


def render_carbon_indicator(
    carbon_g: float,
    show_equivalence: bool = True,
) -> None:
    """
    Affiche un indicateur visuel de l'empreinte carbone.

    Args:
        carbon_g: Émissions en grammes de CO2
        show_equivalence: Afficher l'équivalence (ex: km en voiture)
    """
    service = get_metrics_service()
    carbon_str = service.format_carbon(carbon_g)

    # Déterminer le niveau (vert/orange/rouge)
    carbon_mg = carbon_g * 1000

    if carbon_mg < 1:
        icon = "🟢"
        level = "Très faible"
    elif carbon_mg < 10:
        icon = "🟡"
        level = "Faible"
    elif carbon_mg < 100:
        icon = "🟠"
        level = "Modéré"
    else:
        icon = "🔴"
        level = "Élevé"

    st.markdown(f"{icon} **{carbon_str}** ({level})")

    if show_equivalence and carbon_g > 0:
        # Équivalences approximatives
        # 1g CO2 ≈ 5m en voiture thermique
        km_voiture = carbon_g * 0.005
        # 1g CO2 ≈ 10 secondes de streaming vidéo HD
        sec_streaming = carbon_g * 10

        if km_voiture >= 0.001:
            st.caption(f"≈ {km_voiture:.3f} km en voiture")
        if sec_streaming >= 1:
            st.caption(f"≈ {sec_streaming:.0f}s de streaming HD")
