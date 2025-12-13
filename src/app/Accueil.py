import streamlit as st
from PIL import Image
import sys
from pathlib import Path
from src.core.green_monitor import GreenTracker

# --- Configuration de la page (Doit être la première commande Streamlit) ---
st.set_page_config(
    page_title="WaveLocalAI Workbench",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SINGLETON GREEN TRACKER (Démarrage Global) ---
if "tracker" not in st.session_state:
    # On initialise le tracker une seule fois pour toute la session
    st.session_state.tracker = GreenTracker(project_name="wavelocal_session")
    st.session_state.tracker.start()
    # On stocke une référence visuelle pour dire que c'est actif
    st.session_state.tracking_active = True

# --- Astuce Lead Tech : Ajout du chemin racine au PYTHONPATH ---
root_path = Path(__file__).parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

# --- Contenu de la Page d'Accueil ---
def main():
    st.title("🌊 WaveLocalAI Workbench")
    st.caption("Architecture de Démonstration IA | Local First • Green IT • Privacy")
    
    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 🗺️ Modules Disponibles")
        st.info("""
        **🔋 01. Socle Hardware & Green**
        * Audit des capacités (CPU/GPU) et monitoring carbone temps réel.
        """)
        
        st.info("""
        **🧠 02. Inférence & Arena**
        * **Chat Libre :** Conversation fluide avec mémoire.
        * **Labo de Tests :** Benchmarks techniques (Tokens/s) sur des cas d'usage précis (Code, JSON, Traduction).
        * **Model Manager :** Téléchargement et gestion des modèles Ollama.
        """)
        
        st.info("""
        **📚 03. RAG Knowledge**
        * Interrogation de documents locaux (PDF/TXT) via vecteur store.
        * Observabilité complète du pipeline (Temps de recherche vs Génération).
        """)
        
        st.info("""
        **🧪 04. Agent Lab**
        * Agents autonomes utilisant des outils (Calculatrice, Recherche interne, Date).
        * Visualisation du raisonnement (Chain of Thought).
        """)

    with col2:
        st.success("### 🛠 État du Système")
        st.markdown("""
        * **Python :** Installs OK
        * **Mode :** Offline Priority
        * **Green Monitor :** Ready
        """)
        
        with st.expander("Philosophie du Projet", expanded=True):
            st.markdown("""
            1.  **Privacy by Design :** Aucune donnée ne sort du PC.
            2.  **Sobriété :** Modèles quantizés (SLM) sur CPU.
            3.  **Transparence :** Mesure d'impact et explicabilité.
            """)

if __name__ == "__main__":
    main()