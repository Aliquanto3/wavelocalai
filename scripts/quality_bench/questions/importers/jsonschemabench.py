"""Importeur de JSONSchemaBench (``jsonschemabench``, extraction JSON) : partie test, MIT.

Source : dépôt de données Hugging Face ``epfl-dlab/JSONSchemaBench``, un parquet de test par
sous-ensemble (``json_schema`` en chaîne, ``unique_id``). La question demande une instance JSON
conforme au schéma, donné dans le prompt ; ``format`` reste nul : le banc mesure le modèle, pas
le décodage contraint d'Ollama. La conformité est vérifiée côté client (story 4). Un schéma
trop long pour le plus grand palier de contexte est écarté et compté au journal.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from ...common.canonical import pretty_bytes
from .base import Importer, build_questions
from .remote import RemoteFile

SLUG = "jsonschemabench"
_REPO = "epfl-dlab/JSONSchemaBench"
_REVISION = "5bd0f4640badc6f3f02df796421d21cb0ca0b141"
_TEST_FILES = {
    "Github_trivial": "da64e43b1c08176ab4b3a1ac5f6fb4c22b64a90ed731a2957a4e3d0b4b2c23dc",
    "Github_easy": "beed5774561ad3e2737685ba00d2c04f88a54417266dd68878a9c44470f967ed",
    "Github_medium": "75faffa85c98edf2db596e3e1d2b5bf580b864389f578599c38c6512daf9854d",
    "Github_hard": "fe8ff2dba5e004368e9f0beaa129d55f1e9c54c61591286d8b52cf5caab6da5c",
    "Github_ultra": "8ff71a9ca6cf7cb90974c14c2843193b2e9aba82136f59a4dc77e91c661598cf",
    "Glaiveai2K": "d41787c61640185e34f7c6dc6026313d0e5ac3cdd43c77522688d583c12916a2",
    "JsonSchemaStore": "6bdd762c2b85b3fefe5d741dce814393c7f3efaa02c3d81a9669905cfd209de6",
    "Kubernetes": "963fe0a0496a1eb59798b92e87957ddc73efbcfddbe5e558ac44b762dfd2825c",
    "Snowplow": "89fc3111eb2613b2324229e6d0e62bfe6e43d6d8b762271e6b09575f25794340",
    "WashingtonPost": "213e6bb3b6ac26373c1e3671ae10f2002aa2403e4b06d11b980c0840d9e089f3",
}
FILES = {
    subset: RemoteFile("hf", _REPO, _REVISION, f"{subset}/test-00000-of-00001.parquet", digest)
    for subset, digest in _TEST_FILES.items()
}

PROMPT = (
    "Produis une instance JSON valide contre le schéma JSON ci-dessous. Réponds uniquement "
    "par l'objet JSON, sans texte autour.\n\nSchéma :\n{schema}"
)


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Lignes ``{json_schema, unique_id}`` d'un parquet de test."""
    return pq.read_table(path, columns=["json_schema", "unique_id"]).to_pylist()


def convert_rows(rows_by_subset: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Questions des sous-ensembles, dans l'ordre de ``_TEST_FILES`` puis des fichiers.

    Le numéro suit la position dans la source, écartés compris : un schéma écarté ne décale
    pas les identifiants des suivants.
    """
    return build_questions(SLUG, _items(rows_by_subset))


def _items(rows_by_subset: Mapping[str, list[dict[str, Any]]]) -> Iterator[dict[str, Any]]:
    number = 0
    for subset in _TEST_FILES:
        for row in rows_by_subset.get(subset, []):
            number += 1
            schema = json.loads(row["json_schema"])
            prompt = PROMPT.format(schema=pretty_bytes(schema).decode("utf-8").rstrip("\n"))
            yield {
                "number": number,
                "group": f"{SLUG}/{subset}/{row['unique_id']}",
                "messages": [{"role": "user", "content": prompt}],
                "grader_params": {"schema": schema, "subset": subset},
                "target": None,
            }


def convert(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    return convert_rows({subset: read_rows(local[remote.path]) for subset, remote in FILES.items()})


IMPORTERS = {SLUG: Importer(SLUG, tuple(FILES.values()), convert)}
