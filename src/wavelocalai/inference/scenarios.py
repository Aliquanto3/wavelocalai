"""Scénarios prédéfinis du Banc d'essai (story 7.4, D-17, D-18).

Copie adaptée de `USE_CASES` de `src/app/tabs/inference/lab.py` (la v2 n'importe jamais `src.*`).
Deux écarts à la v1, voulus : la consigne système est séparée de l'entrée (`instruction` et `input`
ne se mélangent jamais), et un scénario qui attend du JSON porte son **format attendu en schéma
JSON** (`schema`), que le serveur vérifie (`format_verdict`) et qui peut être imposé au modèle
(`response_schema`, AD-8). Un scénario sans format (code, raisonnement, résumé) a `schema: None`.

Les consignes de la v1 sont gardées telles quelles ; celle de l'extraction nomme désormais ses
trois champs (la v1 ne les nommait pas, le verdict n'aurait alors rien de précis à vérifier).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Consigne ajoutée à celle du scénario quand « Réponse concise » est activée.
CONCISE_INSTRUCTION = (
    "Réponse concise : va droit au but, sans introduction ni commentaire superflu."
)


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    instruction: str  # consigne système (D-18)
    input: str  # entrée proposée (modifiable à l'écran)
    schema: dict[str, Any] | None = None  # format attendu, `None` : scénario sans format (D-17)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "instruction": self.instruction,
            "input": self.input,
            "schema": self.schema,
        }


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "classification",
        "Classification (JSON)",
        "Tu es un expert en analyse de sentiment. Réponds UNIQUEMENT avec un JSON : "
        '{"sentiment": "Positif"|"Neutre"|"Négatif", "categorie": "..."}.',
        'Analyse ce feedback : "La formation était top, mais la salle trop chaude."',
        _object(
            {
                "sentiment": {"type": "string", "enum": ["Positif", "Neutre", "Négatif"]},
                "categorie": {"type": "string"},
            }
        ),
    ),
    Scenario(
        "traduction",
        "Traduction technique",
        'Traduis en Anglais, Espagnol, Allemand. Format JSON : {"en": "...", "es": "...", "de": "..."}.',
        "L'inférence locale garantit la confidentialité des données.",
        _object({"en": {"type": "string"}, "es": {"type": "string"}, "de": {"type": "string"}}),
    ),
    Scenario(
        "extraction",
        "Extraction (JSON)",
        "Extrais les entités (Date, Montant, Vendeur). Réponds UNIQUEMENT en JSON : "
        '{"date": "...", "montant": "...", "vendeur": "..."}.',
        "Facture du 12/12/2024 de Wavestone pour 500€.",
        _object(
            {
                "date": {"type": "string"},
                "montant": {"type": ["string", "number"]},
                "vendeur": {"type": "string"},
            }
        ),
    ),
    Scenario(
        "code",
        "Assistant de code (Python)",
        "Tu es un expert Python. Génère du code typé et documenté.",
        "Fonction asynchrone pour appeler une API REST avec retry.",
    ),
    Scenario(
        "raisonnement",
        "Raisonnement pas à pas",
        "Utilise la méthode Chain of Thought : pense étape par étape avant de répondre.",
        "J'ai 3 pommes. J'en mange une. J'en achète deux. J'en jette une. Combien m'en reste-t-il ?",
    ),
    Scenario(
        "resume",
        "Résumé",
        "Fais un résumé exécutif en bullet points.",
        "Compte rendu de réunion : Le projet est en retard à cause de la validation API. "
        "On décale la livraison de 2 semaines.",
    ),
)


def find_scenario(scenario_id: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.id == scenario_id), None)
