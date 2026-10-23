"""Export d'une conversation en JSON ou en Markdown (UX-DR21, AD-13).

L'export part de `conversation_view` et ne reprend que des champs nommés : messages, modèle et
origine, débit D3, durées, CO2 avec sa méthode. Aucun réglage ni aucune clé n'y entre ; les valeurs
texte passent en plus par `mask_secrets` avec les secrets connus de `Settings`, au cas où une clé
aurait été collée dans un message.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from wavelocalai.errors import mask_secrets

FORMAT = "wavelocalai.conversation/1"
TPS_SOURCES = {
    "ollama_eval": "mesuré par Ollama (D3)",
    "wallclock": "estimé sur l'horloge",
}
ROLES = {"user": "Vous", "assistant": "Modèle", "system": "Système", "tool": "Outil"}


def mask_value(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return mask_secrets(value, secrets)
    if isinstance(value, dict):
        return {key: mask_value(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_value(item, secrets) for item in value]
    return value


def _message(raw: dict[str, Any]) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": raw["role"],
        "content": raw["content"],
        "reasoning": raw["reasoning"],
        "created_at": raw["created_at"],
    }
    run = raw["run"]
    if raw["role"] != "assistant" or run is None:
        return message
    metrics = run["metrics"] or {}
    message.update(
        {
            "model": run["model"],
            "origin": metrics.get("origin"),
            "status": run["status"],
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "tps": metrics.get("tps"),  # débit D3 : tokens générés par seconde de génération
            "tps_source": metrics.get("tps_source"),
            "ttft_s": metrics.get("ttft_s"),
            "load_s": metrics.get("load_s"),
            "eval_s": metrics.get("eval_s"),
            "total_s": metrics.get("total_s"),
            "co2": metrics.get("co2"),
        }
    )
    return message


def export_document(
    view: dict[str, Any], exported_at: str, version: str, secrets: Iterable[str] = ()
) -> dict[str, Any]:
    """Document d'export, secrets masqués."""
    document = {
        "format": FORMAT,
        "exported_at": exported_at,
        "app_version": version,
        "conversation": {
            "id": view["id"],
            "kind": view["kind"],
            "created_at": view["created_at"],
            "model": view["model"],
            "temperature": view["temperature"],
        },
        "definitions": {
            "tps": "Débit D3 : tokens générés par seconde de génération, chargement du modèle "
            "exclu ; `tps_source` dit s'il est mesuré par Ollama (ollama_eval) ou estimé sur "
            "l'horloge (wallclock).",
            "co2": "mg de CO2 équivalent ; `method` dit comment (codecarbon : mesuré sur ce poste, "
            "ecologits : estimé pour un modèle distant, unmeasurable : non mesurable, avec sa "
            "`reason`). Jamais 0 pour un inconnu.",
        },
        "messages": [_message(raw) for raw in view["messages"]],
    }
    return mask_value(document, tuple(secrets))  # type: ignore[no-any-return]


def to_json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _num(value: float | None, unit: str, digits: int = 1) -> str | None:
    if value is None:
        return None
    return f"{value:.{digits}f}".replace(".", ",") + " " + unit


def _co2_line(co2: dict[str, Any] | None) -> str:
    if co2 is None:
        return "CO2 : non renseigné"
    if co2["mg"] is None:
        return f"CO2 : non mesurable ({co2['reason']})"
    estimated = ", estimé" if co2["estimated"] else ", mesuré"
    value = f"{co2['mg']:.3g}".replace(".", ",")
    return f"CO2 : {value} mg ({co2['method']}{estimated})"


def _footer(message: dict[str, Any]) -> str:
    parts = [f"{message['model']}" if message.get("model") else None]
    origin = {"local": "local", "cloud": "cloud"}.get(message.get("origin") or "")
    parts.append(f"origine : {origin}" if origin else None)
    if message.get("status") not in (None, "ok"):
        parts.append(f"réponse {message['status']}")
    rate = _num(message.get("tps"), "tokens/s")
    if rate:
        source = TPS_SOURCES.get(message.get("tps_source") or "", "source inconnue")
        parts.append(f"débit : {rate} ({source})")
    if message.get("output_tokens") is not None:
        parts.append(f"{message['output_tokens']} tokens")
    parts += [
        f"chargement {text}" if (text := _num(message.get("load_s"), "s")) else None,
        f"durée totale {text}" if (text := _num(message.get("total_s"), "s")) else None,
    ]
    parts.append(_co2_line(message.get("co2")))
    return " · ".join(part for part in parts if part)


def to_markdown(document: dict[str, Any]) -> str:
    conv = document["conversation"]
    lines = [
        "# Conversation wavelocalai",
        "",
        f"- Ouverte le {conv['created_at']}",
        f"- Modèle : {conv['model'] or 'inconnu'}",
        f"- Exportée le {document['exported_at']} (wavelocalai {document['app_version']})",
        "",
    ]
    for message in document["messages"]:
        lines += [f"## {ROLES.get(message['role'], message['role'])}", ""]
        if message.get("reasoning"):
            lines += [
                "<details><summary>Raisonnement</summary>",
                "",
                message["reasoning"],
                "",
                "</details>",
                "",
            ]
        lines += [message["content"] or "_(vide)_", ""]
        if message["role"] == "assistant" and "model" in message:
            lines += [f"> {_footer(message)}", ""]
    return "\n".join(lines).rstrip() + "\n"
