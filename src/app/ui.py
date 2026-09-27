"""
Éléments d'interface partagés par les pages : logo, contrôle Local/Cloud, badges Local et
Cloud, libellés et sélecteurs de modèles.

Le rendu (couleurs, police, rayon) vient de .streamlit/config.toml ; ce module ne contient
aucune couleur.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

from src.app.states import (
    JUDGE_HELP_FITS,
    JUDGE_HELP_NO_LOCAL,
    JUDGE_HELP_NONE_FITS,
    JUDGE_SELF_CAPTION,
    JUDGE_UNFIT_WARNING,
    NO_STRONGER_JUDGE_ADVICE,
    STRONGER_JUDGE_ADVICE,
    WEAK_JUDGE_SMALL,
    WEAK_JUDGE_UNKNOWN,
)
from src.core.llm_provider import LLMProvider
from src.core.model_defaults import (
    ModelChoice,
    arena_preselection,
    default_judge,
    rank_models,
)
from src.core.models_db import get_friendly_name_from_tag
from src.core.providers.provider_factory import is_cloud_tag
from src.core.resource_manager import ResourceManager

STATIC_DIR = Path(__file__).resolve().parent / "static"
WORDMARK_PATH = STATIC_DIR / "wordmark.svg"
# Favicon local, commun aux pages : une icône Material en page_icon serait téléchargée
# depuis fonts.gstatic.com par le navigateur.
FAVICON_PATH = STATIC_DIR / "favicon.svg"

LOCAL_SUFFIX = "Local"
CLOUD_SUFFIX = "Cloud"

# Contrôle global « Autoriser le cloud » : une seule clé de session, rendue par le routeur
# (Accueil.py). Local à chaque démarrage (D1), même si une clé d'API est présente.
CLOUD_KEY = "cloud_enabled"
CLOUD_DEFAULT = False

# Badges Local (vert) et Cloud (orange, jamais rouge) : DESIGN.md, badge-local et badge-cloud.
# Origine inconnue (tag absent des fournisseurs et du catalogue) : badge neutre gris, jamais
# le vert du local.
UNKNOWN_ORIGIN_LABEL = "Origine inconnue"
BADGE_LOCAL = {"label": LOCAL_SUFFIX, "icon": ":material/computer:", "color": "green"}
BADGE_CLOUD = {"label": CLOUD_SUFFIX, "icon": ":material/cloud:", "color": "orange"}
BADGE_UNKNOWN = {"label": UNKNOWN_ORIGIN_LABEL, "icon": ":material/help:", "color": "gray"}
BADGE_LOCAL_HELP = "Le modèle tourne sur cette machine : les données n'en sortent pas."
BADGE_CLOUD_HELP = (
    "Le modèle tourne chez un fournisseur cloud : les données qui lui sont envoyées quittent "
    "la machine."
)
# Aides du badge du mode global (contrôle « Autoriser le cloud »), distinctes de celles d'un
# modèle.
MODE_LOCAL_BADGE_HELP = "Les modèles tournent sur cette machine."
MODE_CLOUD_BADGE_HELP = "Les modèles cloud reçoivent vos données : elles quittent la machine."
BADGE_UNKNOWN_HELP = (
    "Ce modèle n'est ni proposé par un fournisseur ni décrit dans le catalogue : impossible "
    "de dire si les données quittent la machine."
)


def render_logo() -> None:
    """Affiche le wordmark « WaveLocalAI » en tête de la barre latérale."""
    st.logo(str(WORDMARK_PATH))


def cloud_enabled() -> bool:
    """État du contrôle global « Autoriser le cloud », lu par toutes les pages. Repli :
    désactivé (local), y compris pour une page exécutée sans le routeur."""
    return bool(st.session_state.get(CLOUD_KEY, CLOUD_DEFAULT))


def _origin(is_cloud) -> bool | None:
    """True (cloud), False (local) ou None (inconnue ; NaN d'un tableau pandas compris)."""
    if is_cloud is None or (isinstance(is_cloud, float) and is_cloud != is_cloud):
        return None
    return bool(is_cloud)


def _badge(is_cloud) -> tuple[dict, str]:
    origin = _origin(is_cloud)
    if origin is None:
        return BADGE_UNKNOWN, BADGE_UNKNOWN_HELP
    return (BADGE_CLOUD, BADGE_CLOUD_HELP) if origin else (BADGE_LOCAL, BADGE_LOCAL_HELP)


def origin_label(is_cloud) -> str:
    """« Local », « Cloud » ou « Origine inconnue » (colonne de tableau)."""
    return _badge(is_cloud)[0]["label"]


def badge_markdown(is_cloud: bool | None) -> str:
    """Badge Local, Cloud ou Origine inconnue en directive Markdown, à placer dans une ligne
    de texte (métadonnées d'une réponse) : même rendu que st.badge."""
    badge, _ = _badge(is_cloud)
    return f":{badge['color']}-badge[{badge['icon']} {badge['label']}]"


def render_badge(is_cloud: bool | None, help: str | None = None) -> None:
    """Badge seul : « Local » (vert, ordinateur), « Cloud » (orange, nuage) ou « Origine
    inconnue » (gris), avec une aide qui dit si les données quittent la machine (`help`
    la remplace, par exemple pour le mode global)."""
    badge, default_help = _badge(is_cloud)
    st.badge(**badge, help=help or default_help)


def model_label(friendly_name: str, is_cloud: bool) -> str:
    """Libellé d'un modèle dans un sélecteur : nom, puis « · Local » ou « · Cloud »."""
    return f"{friendly_name} · {CLOUD_SUFFIX if is_cloud else LOCAL_SUFFIX}"


# Clé de session de la mémoire disponible mesurée au premier affichage d'un sélecteur.
MEMORY_SNAPSHOT_KEY = "_model_menu_available_gb"


def available_memory_gb() -> float:
    """
    Mémoire vive disponible (Go) pour les choix par défaut, mesurée une fois par session :
    mémoire libre plus celle des modèles déjà chargés dans Ollama (un modèle résident n'est
    pas déclassé). L'ordre des sélecteurs reste ainsi stable d'un rerun à l'autre : un
    modèle que la conversation vient de charger ne recule pas dans la liste et la sélection
    en cours n'est pas perdue. Remplacée dans les tests par une valeur fixe.
    """
    if MEMORY_SNAPSHOT_KEY not in st.session_state:
        st.session_state[MEMORY_SNAPSHOT_KEY] = (
            ResourceManager.get_available_ram_gb() + LLMProvider.loaded_models_ram_gb()
        )
    return st.session_state[MEMORY_SNAPSHOT_KEY]


@dataclass(frozen=True)
class ModelMenu:
    """Options d'un sélecteur de modèles et choix par défaut, adaptés à la machine."""

    display_to_tag: dict[str, str]
    # Nom affiché, complété par le tag quand deux modèles ont le même libellé : pour
    # l'affichage seulement. Recherches dans le catalogue : get_friendly_name_from_tag(tag).
    tag_to_friendly: dict[str, str]
    labels: list[str]  # triés par la règle de src/core/model_defaults.py ; [0] = défaut
    arena_defaults: list[str]  # libellés présélectionnés dans l'Arène (hors juge)
    judge_default: str | None  # libellé du juge par défaut (None : aucun modèle local)
    weak_judges: frozenset[str]  # libellés dont la note de juge est peu fiable (< ~4B ou inconnu)
    choices: dict[str, ModelChoice] = field(default_factory=dict)  # libellé → faits de la règle

    def is_cloud(self, label: str | None) -> bool | None:
        """Fournisseur réel du modèle d'un libellé : True si ses données quittent la
        machine ; None si le libellé n'est pas dans le sélecteur."""
        choice = self.choices.get(label) if label else None
        return choice.is_cloud if choice is not None else None


def is_cloud_model(tag: str | None, menu: ModelMenu | None = None) -> bool | None:
    """
    Origine d'un modèle, source des badges : le type renvoyé par son fournisseur (règle du
    sélecteur, tags distants d'Ollama compris) prime ; tag hors du sélecteur (agent configuré
    avant un changement de réglage…) : is_cloud_tag (catalogue, tags Ollama locaux sauf
    distants) ; None si l'origine est inconnue.
    """
    if menu is not None:
        for choice in menu.choices.values():
            if choice.tag == tag:
                return choice.is_cloud
    return is_cloud_tag(tag)


def model_menu(models: list[dict], cloud_types: tuple[str, ...] = ("cloud",)) -> ModelMenu:
    """
    Sélecteur de modèles à partir de LLMProvider.list_models : libellés « Nom · Local » /
    « Nom · Cloud », triés par la règle (locaux d'abord, le plus rapide qui tient en mémoire
    en tête, cloud en dernier), juge par défaut et présélection de l'Arène. Les tags ne
    changent pas : seul l'ordre des libellés dépend de la machine. Deux tags au même nom
    affiché : le nom de chacun est complété par son tag, aucun modèle n'est masqué. Une
    entrée sans `model` est ignorée.
    """
    models = [m for m in models if m.get("model")]
    friendly = {m["model"]: get_friendly_name_from_tag(m["model"]) for m in models}
    ranked = rank_models(models, available_memory_gb(), cloud_types=cloud_types, names=friendly)

    # Libellé déjà pris par un autre tag : nom complété par le tag.
    counts = Counter(model_label(friendly[c.tag], c.is_cloud) for c in ranked)
    tag_to_friendly = {
        c.tag: (
            friendly[c.tag]
            if counts[model_label(friendly[c.tag], c.is_cloud)] == 1
            else f"{friendly[c.tag]} ({c.tag})"
        )
        for c in ranked
    }
    tag_to_label = {c.tag: model_label(tag_to_friendly[c.tag], c.is_cloud) for c in ranked}

    judge = default_judge(ranked)
    return ModelMenu(
        display_to_tag={label: tag for tag, label in tag_to_label.items()},
        tag_to_friendly=tag_to_friendly,
        labels=list(tag_to_label.values()),
        arena_defaults=[tag_to_label[t] for t in arena_preselection(ranked, judge)],
        judge_default=tag_to_label[judge.tag] if judge else None,
        weak_judges=frozenset(tag_to_label[c.tag] for c in ranked if c.weak_judge),
        choices={tag_to_label[c.tag]: c for c in ranked},
    )


# ---------------------------------------------------------------------------
# Juge : aide, avertissements et légendes
# ---------------------------------------------------------------------------


def judge_help(menu: ModelMenu | None) -> str:
    """Aide du sélecteur de juge : dit comment le juge par défaut a été choisi."""
    judge = menu.choices.get(menu.judge_default) if menu and menu.judge_default else None
    if judge is None:
        return JUDGE_HELP_NO_LOCAL
    return JUDGE_HELP_FITS if judge.fits else JUDGE_HELP_NONE_FITS


def weak_judge_text(menu: ModelMenu | None, label: str | None) -> str | None:
    """« Note peu fiable » du juge choisi (moins de ~4B, ou taille inconnue), sans conseil ;
    None si sa note est fiable ou s'il est cloud."""
    choice = menu.choices.get(label) if menu and label else None
    if choice is None or not choice.weak_judge:
        return None
    text = WEAK_JUDGE_UNKNOWN if choice.params_b is None else WEAK_JUDGE_SMALL
    return text.format(name=menu.tag_to_friendly.get(choice.tag, label))


def judge_warnings(menu: ModelMenu | None, label: str | None) -> list[str]:
    """Avertissements du juge choisi : il ne tient pas en mémoire ; sa note est peu fiable,
    avec un conseil adapté selon qu'un juge fiable tient en mémoire ou non."""
    choice = menu.choices.get(label) if menu and label else None
    if choice is None or choice.is_cloud:
        return []
    warnings = []
    if not choice.fits:
        name = menu.tag_to_friendly.get(choice.tag, label)
        warnings.append(JUDGE_UNFIT_WARNING.format(name=name))
    weak = weak_judge_text(menu, label)
    if weak:
        reliable_fits = any(
            c.fits and not c.is_cloud and not c.weak_judge for c in menu.choices.values()
        )
        advice = STRONGER_JUDGE_ADVICE if reliable_fits else NO_STRONGER_JUDGE_ADVICE
        warnings.append(f"{weak} {advice}")
    return warnings


def judge_self_caption(tag_to_friendly: dict, judge_tag: str | None, tags: list) -> str | None:
    """Légende quand le juge figure parmi les modèles évalués : il note sa propre réponse."""
    if not judge_tag or judge_tag not in tags:
        return None
    return JUDGE_SELF_CAPTION.format(name=tag_to_friendly.get(judge_tag, judge_tag))
