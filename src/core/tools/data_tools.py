# src/core/tools/data_tools.py
"""Outils d'analyse de données."""

import logging
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from langchain_core.tools import tool

from src.core.config import OUTPUT_DIR

matplotlib.use("Agg")
logger = logging.getLogger(__name__)

TOOL_METADATA_ANALYZE = {
    "name": "📊 Data Analyzer",
    "description": "Analyse CSV/Excel",
    "category": "data",
    "requires_config": False,
}

TOOL_METADATA_CHART = {
    "name": "📈 Chart Generator",
    "description": "Graphiques PNG",
    "category": "output",
    "requires_config": False,
}


@tool
def analyze_csv(file_path: str, query: str = "describe") -> str:
    """
    Analyse un fichier CSV et retourne des statistiques.

    Args:
        file_path: Chemin vers le fichier CSV
        query: Type d'analyse ("describe", "head", "columns", "shape")

    Returns:
        Résultat de l'analyse ou message d'erreur
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"Erreur: Fichier non trouvé: {file_path}"

        if path.suffix.lower() != ".csv":
            return "Erreur: Le fichier doit être un CSV"

        df = pd.read_csv(path)

        if query == "describe":
            return df.describe().to_string()
        elif query == "head":
            return df.head(10).to_string()
        elif query == "columns":
            return f"Colonnes: {', '.join(df.columns.tolist())}"
        elif query == "shape":
            return f"Dimensions: {df.shape[0]} lignes x {df.shape[1]} colonnes"
        else:
            return df.describe().to_string()

    except Exception as e:
        return f"Erreur d'analyse: {e}"


@tool
def generate_chart(
    file_path: str, x_column: str, y_column: str, chart_type: str = "line", title: str = "Graphique"
) -> str:
    """
    Génère un graphique à partir d'un fichier CSV.

    Args:
        file_path: Chemin vers le fichier CSV
        x_column: Nom de la colonne pour l'axe X
        y_column: Nom de la colonne pour l'axe Y
        chart_type: Type de graphique ("line", "bar", "scatter")
        title: Titre du graphique

    Returns:
        Chemin vers l'image générée ou message d'erreur
    """
    try:
        df = pd.read_csv(file_path)

        if x_column not in df.columns or y_column not in df.columns:
            return f"Erreur: Colonnes non trouvées. Disponibles: {df.columns.tolist()}"

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "line":
            ax.plot(df[x_column], df[y_column])
        elif chart_type == "bar":
            ax.bar(df[x_column], df[y_column])
        elif chart_type == "scatter":
            ax.scatter(df[x_column], df[y_column])
        else:
            ax.plot(df[x_column], df[y_column])

        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        ax.set_title(title)
        plt.xticks(rotation=45)
        plt.tight_layout()

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"chart_{x_column}_{y_column}.png"
        fig.savefig(output_path, dpi=150)
        plt.close(fig)

        return f"Graphique généré: {output_path}"

    except Exception as e:
        return f"Erreur génération graphique: {e}"
