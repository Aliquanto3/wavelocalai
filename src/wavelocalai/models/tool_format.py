"""Formats d'appel d'outils : du schéma neutre du port (AD-8) à celui de chaque fournisseur (story 6.1).

Le port parle un seul format (`port.ChatRequest.tools`, `ChatMessage.tool_calls`/`tool_call_id`,
`ToolCall`) ; chaque adaptateur le traduit. Vérifié le 2026-10-19 sur les versions verrouillées
dans `uv.lock` (code lu dans `.venv`, pas de mémoire) :

- Ollama (`ollama` 0.6.3) et OpenAI-compatible (`openai` 2.54.0, Groq) : outil
  `{"type": "function", "function": {name, description, parameters}}` ; appel du modèle dans le
  message `assistant` : `tool_calls`, chacun `{id, type: "function", function: {name, arguments}}`
  (`arguments` est une chaîne JSON chez OpenAI, un objet chez Ollama, qui n'a pas d'`id` : le
  résultat est un message `tool` avec `tool_name`) ; résultat OpenAI : message `tool` avec
  `tool_call_id`. En flux, OpenAI rend les appels par fragments (`delta.tool_calls[]` avec `index`,
  `id` et `function.name` au premier fragment, `function.arguments` en morceaux).
- Anthropic (`anthropic` 1.15.0) : outil `{name, description, input_schema}` ; l'appel est un bloc
  `tool_use` `{id, name, input}` du message `assistant`, rendu en flux par `content_block_start`
  (`tool_use`) puis des `input_json_delta` ; le résultat est un bloc `tool_result`
  `{tool_use_id, content}` dans un message `user`.
- Mistral (`mistralai` 3.2.0) : même forme qu'OpenAI ; le message `tool` porte en plus `name` ;
  `id` vaut la chaîne `"null"` quand le fragment n'en a pas.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from wavelocalai.models.port import ChatMessage, ToolCall

NO_ID = {"", "null", "None"}


def new_call_id() -> str:
    """Identifiant d'un appel d'outil pour un fournisseur qui n'en donne pas (Ollama, fragment
    Mistral sans `id`) : unique, car une boucle d'agent enchaîne plusieurs tours. Neuf caractères
    alphanumériques : le seul format que Mistral accepte en retour (`tool_call_id`), et que les
    autres fournisseurs acceptent aussi."""
    return uuid.uuid4().hex[:9]


def parse_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    """`(arguments, erreur)` : un objet est repris tel quel, une chaîne est lue comme du JSON (vide :
    aucun argument). JSON invalide, ou qui n'est pas un objet : `({}, texte de l'erreur)`."""
    if raw is None:
        return {}, None
    if isinstance(raw, dict):
        return dict(raw), None
    if isinstance(raw, str):
        if not raw.strip():
            return {}, None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {}, f"Arguments illisibles (JSON invalide : {exc.msg}) : {raw[:200]}"
        if isinstance(value, dict):
            return value, None
        return {}, f"Arguments illisibles (un objet JSON est attendu) : {raw[:200]}"
    try:
        return dict(raw), None
    except (TypeError, ValueError):
        return {}, "Arguments illisibles."


def tool_name_of(messages: list[ChatMessage], index: int) -> str | None:
    """Nom de l'outil dont le message `tool` d'indice `index` rend le résultat : retrouvé par
    l'`id` dans les appels du message `assistant` qui précède."""
    wanted = messages[index].tool_call_id
    for earlier in reversed(messages[:index]):
        for call in earlier.tool_calls or ():
            if call.get("id") == wanted:
                return str(call.get("name") or "") or None
    return None


# --- OpenAI, Groq, Mistral -------------------------------------------------------------------


def function_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Outils neutres au format `{"type": "function", "function": {...}}` (OpenAI, Groq, Mistral,
    Ollama)."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


def chat_messages(messages: list[ChatMessage], *, tool_names: bool = False) -> list[dict[str, Any]]:
    """Messages au format Chat Completions (OpenAI, Groq, Mistral). Un message sans texte est écarté,
    sauf un `assistant` qui appelle des outils. `tool_names` : le message `tool` porte aussi `name`
    (Mistral)."""
    wire: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if message.role == "tool":
            if not message.tool_call_id:
                continue
            item: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
            name = tool_name_of(messages, index) if tool_names else None
            if name:
                item["name"] = name
            wire.append(item)
        elif message.role == "assistant" and message.tool_calls:
            wire.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(
                                    call.get("arguments") or {}, ensure_ascii=False
                                ),
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        elif message.role in ("system", "user", "assistant") and message.content:
            wire.append({"role": message.role, "content": message.content})
    return wire


class ToolCallDeltas:
    """Assemble les fragments d'appels d'outils d'un flux Chat Completions (OpenAI, Groq, Mistral) :
    par `index`, le premier fragment porte `id` et `name`, les suivants des morceaux d'`arguments`
    (chaîne JSON ; Mistral peut rendre l'objet entier)."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._by_index: dict[int, dict[str, Any]] = {}

    def __bool__(self) -> bool:
        return bool(self._entries)

    def add(self, index: int | None, call_id: str | None, name: str | None, arguments: Any) -> None:
        position = index or 0
        has_id = bool(call_id) and call_id not in NO_ID
        entry = self._by_index.get(position)
        same_id = has_id and entry is not None and entry["id"] == call_id
        # Un nouvel appel : indice nouveau, autre `id`, ou un nom qui revient sans le même `id`
        # (Mistral rend des appels entiers sur le même indice avec `id = "null"`).
        if (
            entry is None
            or (has_id and entry["id"] and call_id != entry["id"])
            or (name and entry["name"] and not same_id)
        ):
            entry = {"id": None, "name": "", "args": "", "obj": None}
            self._entries.append(entry)
            self._by_index[position] = entry
        if has_id and not entry["id"]:
            entry["id"] = call_id
        if name:
            entry["name"] = name
        if isinstance(arguments, str):
            entry["args"] += arguments
        elif isinstance(arguments, dict):
            entry["obj"] = arguments

    def calls(self) -> list[ToolCall]:
        calls = []
        for entry in self._entries:
            raw = entry["obj"] if entry["obj"] is not None else entry["args"]
            arguments, error = parse_arguments(raw)
            calls.append(ToolCall(entry["id"] or new_call_id(), entry["name"], arguments, error))
        return calls


# --- Anthropic -------------------------------------------------------------------------------


def anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "input_schema": tool.get("parameters") or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


def anthropic_messages(messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
    """`(system, messages)` au format Messages : le `system` à part ; un `assistant` qui appelle des
    outils porte des blocs `text` puis `tool_use` ; les résultats consécutifs sont des blocs
    `tool_result` d'un seul message `user`."""
    system = [m.content for m in messages if m.role == "system" and m.content]
    wire: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            if not message.tool_call_id:
                continue
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            last = wire[-1] if wire else None
            if (
                last is not None
                and last["role"] == "user"
                and isinstance(last["content"], list)
                and all(b.get("type") == "tool_result" for b in last["content"])
            ):
                last["content"].append(block)
            else:
                wire.append({"role": "user", "content": [block]})
        elif message.role == "assistant" and message.tool_calls:
            blocks: list[dict[str, Any]] = []
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            blocks += [
                {
                    "type": "tool_use",
                    "id": call["id"],
                    "name": call["name"],
                    "input": call.get("arguments") or {},
                }
                for call in message.tool_calls
            ]
            wire.append({"role": "assistant", "content": blocks})
        elif message.role in ("user", "assistant") and message.content:
            wire.append({"role": message.role, "content": message.content})
    return ("\n\n".join(system) or None), wire


def ollama_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Messages de `/api/chat` d'Ollama : `tool_calls` `{function: {name, arguments}}` pour
    l'`assistant`, `tool_name` pour le résultat (Ollama n'a pas d'identifiant d'appel)."""
    wire: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        item: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.role == "assistant" and message.tool_calls:
            item["tool_calls"] = [
                {
                    "function": {
                        "name": call["name"],
                        "arguments": call.get("arguments") or {},
                    }
                }
                for call in message.tool_calls
            ]
        elif message.role == "tool":
            name = tool_name_of(messages, index)
            if name:
                item["tool_name"] = name
        wire.append(item)
    return wire
