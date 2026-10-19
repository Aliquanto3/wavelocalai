"""La note de cadrage de l'atelier, document de test du Flow 2 d'`EXPERIENCE.md`.

Quatorze paragraphes d'environ 400 caractères (deux ne tiennent pas dans un même extrait) : avec la
découpe par défaut (800 caractères, 100 de recouvrement), chacun donne un extrait, soit « 14 extraits
ajoutés depuis 1 document ». Un seul paragraphe (`ANSWER_PARAGRAPH`) répond à `QUESTION`, par la
phrase `ANSWER_SENTENCE` : c'est le passage que le serveur désigne et que l'écran surligne (D-21).
"""

from __future__ import annotations

from .rag_files import make_docx

FILE_NAME = "note-de-cadrage-atelier.docx"
QUESTION = "Que doit apporter chaque consultant à l'atelier ?"
ANSWER_SENTENCE = (
    "Chaque consultant apporte son portable de seize gigaoctets, sans carte graphique."
)

_FILLER = (
    "Le groupe avance au rythme des questions et note ce qui reste à éclaircir pour la séance "
    "suivante. Les consignes sont relues à voix haute avant chaque exercice, puis chacun les "
    "applique à son propre poste sans attendre les autres participants."
)

_TOPICS = [
    "Objectif de la journée : montrer qu'un petit modèle de langage installé sur le poste suffit "
    "pour interroger un document interne et vérifier d'où vient chaque réponse.",
    "Public attendu : une douzaine de consultants juniors, répartis en trois tables, encadrés par "
    "un formateur qui anime la séance et par un second qui circule entre les tables.",
    "Salle et horaires : la salle Horizon est réservée de neuf heures à dix-sept heures, avec une "
    "pause à midi trente et deux pauses courtes, le matin et l'après-midi.",
    f"Matériel. {ANSWER_SENTENCE} Les chargeurs et une rallonge par table sont fournis par "
    "l'organisation de la salle.",
    "Installation : le formateur envoie la veille la consigne d'installation, qui tient en une "
    "seule commande, et chacun vérifie que l'application s'ouvre avant d'arriver.",
    "Premier exercice : importer la note de cadrage dans l'assistant documentaire, attendre la "
    "fin de l'indexation et lire le nombre d'extraits ajoutés à la base.",
    "Deuxième exercice : poser une question simple au document, relever la réponse, puis ouvrir "
    "les sources pour retrouver le paragraphe qui la fonde, mot pour mot.",
    "Troisième exercice : comparer deux manières de poser la même question et dire laquelle "
    "ramène les meilleurs extraits, en s'appuyant sur les sources affichées.",
    "Confidentialité : aucun document ne quitte le poste pendant l'atelier, et le mode cloud "
    "reste désactivé, ce que chacun peut vérifier sur la carte Mode de l'accueil.",
    "Sobriété : la mesure du CO₂ de la session est lue en fin de journée, table par table, pour "
    "comparer ce que coûte une question posée à un petit modèle local.",
    "Limites connues : un petit modèle se trompe parfois, ignore ce qui n'est pas dans les "
    "extraits et peut mal citer ; c'est pourquoi les sources passent avant la réponse.",
    "Livrables : chaque table remet une page qui dit ce que le document contient, ce que le "
    "modèle a bien retrouvé et ce qu'il a manqué, avec deux exemples de questions.",
    "Évaluation : le formateur note la capacité à vérifier une source plus que la qualité de la "
    "réponse, car c'est le réflexe que l'atelier cherche à installer chez les juniors.",
    "Suites : une séance de reprise est prévue un mois plus tard, avec des documents de clients "
    "fictifs, afin de mesurer ce que chacun a retenu et appliqué dans ses missions.",
]

PARAGRAPHS = [f"{topic} {_FILLER}" for topic in _TOPICS]
ANSWER_PARAGRAPH = PARAGRAPHS[3]


def make_note() -> bytes:
    """Le `.docx` de la note de cadrage."""
    return make_docx(PARAGRAPHS)
