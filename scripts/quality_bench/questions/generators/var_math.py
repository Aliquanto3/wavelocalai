"""Générateur VAR-MATH FR (``var-math-fr``, raisonnement, privé) : variantes à graine.

Recette VAR-MATH : chaque problème de collège-lycée est un gabarit dont les nombres sont des
paramètres tirés au hasard ; ses variantes partagent une ``unit`` (réussie seulement si toutes
le sont, AD-17) et un ``group``. Les problèmes vivent dans le fichier privé
``$QUALITY_BENCH_DATA/private/var-math-fr.yaml`` (hors dépôt), au format ``qb.var_math/1`` :

```yaml
schema: qb.var_math/1
problems:
  - number: 1
    text: "Un cycliste roule {v} km/h pendant {h} heures…"   # {nom} : paramètre ou dérivé
    params: {v: {min: 12, max: 30, step: 2}, h: {min: 2, max: 5}}
    derived: {d: "v * h"}                                    # facultatif, dans l'ordre
    constraints: ["d % 4 == 0"]                              # toutes vraies
    answer: "d // 4"                                         # entier
```

Les expressions passent par un évaluateur AST restreint (entiers seulement) : ``+ - * // %``,
``**`` à exposant borné, comparaisons, ``and``, ``or``, ``not``, ``min``, ``max``, ``abs``.
Jamais ``eval`` ni ``exec``. Noyau pur : ``generate`` ne lit aucun fichier.
"""

from __future__ import annotations

import ast
import operator
import random
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ...common.canonical import nfc, sha256_hex
from ..build import build_question

GENERATOR = "var_math_fr@1"
SOURCE = "var-math-fr"
SCHEMA_ID = "qb.var_math/1"
ANSWER_PREFIX = "La réponse est :"
ANSWER_INSTRUCTION = (
    "\n\nRaisonne étape par étape, puis termine ta réponse par une dernière ligne de la forme "
    "« La réponse est : <entier> », où <entier> est la réponse finale, écrite en chiffres, "
    "sans unité."
)
DEFAULT_VARIANTS = 3
MAX_DRAWS_PER_VARIANT = 2000
MAX_EXPONENT = 10
MAX_ABS_VALUE = 10**15

_NAME_RE = re.compile(r"[a-z_][a-z0-9_]*")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PROBLEM_KEYS = {"number", "text", "params", "derived", "constraints", "answer"}
_PARAM_KEYS = {"min", "max", "step"}
_FUNCTIONS: dict[str, Callable[..., int]] = {"min": min, "max": max, "abs": abs}
_RESERVED = set(_FUNCTIONS) | {"and", "or", "not", "True", "False", "None"}


class GeneratorError(ValueError):
    """Problème non instanciable, expression refusée ou fichier ``qb.var_math/1`` invalide."""


class _DrawRejectedError(Exception):
    """Tirage à rejeter (division par zéro, valeur hors bornes) : on retire."""


@dataclass(frozen=True)
class Param:
    name: str
    values: tuple[int, ...]


@dataclass(frozen=True)
class Problem:
    """Gabarit VAR-MATH validé : expressions analysées une fois, au chargement."""

    number: int
    text: str
    params: tuple[Param, ...]
    derived: tuple[tuple[str, ast.Expression], ...]
    constraints: tuple[ast.Expression, ...]
    answer: ast.Expression


# --- Évaluateur restreint ----------------------------------------------------------------

_BINARY: dict[type[ast.operator], Callable[[int, int], int]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_COMPARE: dict[type[ast.cmpop], Callable[[int, int], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def parse_expression(source: Any, where: str) -> ast.Expression:
    """Analyse ``source`` et refuse tout nœud hors de la liste permise (``GeneratorError``)."""
    if not isinstance(source, str) or not source.strip():
        raise GeneratorError(f"{where} : expression (chaîne non vide) attendue")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as error:
        raise GeneratorError(f"{where} : expression illisible ({error.msg})") from None
    for node in ast.walk(tree):
        _check_node(node, where)
    return tree


def _check_node(node: ast.AST, where: str) -> None:
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.Name,
        ast.Constant,
        ast.Call,
        ast.Load,
        ast.And,
        ast.Or,
        ast.Not,
        ast.USub,
        ast.UAdd,
        *_BINARY,
        *_COMPARE,
    )
    if not isinstance(node, allowed):
        raise GeneratorError(f"{where} : construction interdite ({type(node).__name__})")
    if isinstance(node, ast.Constant) and (
        not isinstance(node.value, int) or isinstance(node.value, bool)
    ):
        raise GeneratorError(f"{where} : seules les constantes entières sont permises")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise GeneratorError(f"{where} : seuls min, max et abs peuvent être appelés")
        if node.keywords or not node.args:
            raise GeneratorError(f"{where} : appel sans argument nommé et non vide attendu")
    if isinstance(node, ast.Name) and node.id.startswith("_"):
        raise GeneratorError(f"{where} : nom interdit {node.id!r}")


def _names(tree: ast.Expression) -> set[str]:
    called = {
        id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }  # noms de fonction (min, max, abs), exclus des variables
    return {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and id(node) not in called
    }


def evaluate(tree: ast.Expression, env: Mapping[str, int]) -> int | bool:
    """Évalue un arbre déjà vérifié par ``parse_expression`` sur des entiers."""
    return _eval(tree.body, env)


def _eval(node: ast.AST, env: Mapping[str, int]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not value
        return -value if isinstance(node.op, ast.USub) else +value
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Pow) and not 0 <= right <= MAX_EXPONENT:
            raise _DrawRejectedError
        if isinstance(node.op, (ast.FloorDiv, ast.Mod)) and right == 0:
            raise _DrawRejectedError
        result = _BINARY[type(node.op)](left, right)
        if abs(result) > MAX_ABS_VALUE:
            raise _DrawRejectedError
        return result
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for value_node in node.values:
                result = _eval(value_node, env)
                if not result:
                    return result
            return result
        result = False
        for value_node in node.values:
            result = _eval(value_node, env)
            if result:
                return result
        return result
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, env)
            if not _COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        return _FUNCTIONS[node.func.id](*(_eval(arg, env) for arg in node.args))
    raise GeneratorError(f"construction interdite ({type(node).__name__})")  # garde-fou


# --- Chargement du fichier qb.var_math/1 ------------------------------------------------


def _int(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GeneratorError(f"{where} : entier attendu, reçu {value!r}")
    return value


def _param(name: Any, raw: Any, where: str) -> Param:
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name) or name in _RESERVED:
        raise GeneratorError(f"{where} : nom de paramètre invalide {name!r}")
    if not isinstance(raw, Mapping) or not {"min", "max"} <= set(raw) <= _PARAM_KEYS:
        raise GeneratorError(f"{where}.{name} : {{min, max, step?}} attendu")
    low, high = _int(raw["min"], f"{where}.{name}.min"), _int(raw["max"], f"{where}.{name}.max")
    step = _int(raw.get("step", 1), f"{where}.{name}.step")
    if step < 1 or high < low:
        raise GeneratorError(f"{where}.{name} : min ≤ max et step ≥ 1 attendus")
    return Param(name, tuple(range(low, high + 1, step)))


def parse_problem(raw: Any, index: int) -> Problem:
    """Valide un problème ``qb.var_math/1`` ; ``GeneratorError`` qui nomme le problème."""
    where = f"problems[{index}]"
    if not isinstance(raw, Mapping):
        raise GeneratorError(f"{where} : objet attendu")
    unknown = sorted(str(key) for key in raw if key not in _PROBLEM_KEYS)
    missing = sorted({"number", "text", "params", "constraints", "answer"} - set(raw))
    if unknown or missing:
        raise GeneratorError(f"{where} : clés inconnues {unknown}, clés manquantes {missing}")
    number = _int(raw["number"], f"{where}.number")
    if number < 1:
        raise GeneratorError(f"{where}.number : entier ≥ 1 attendu")
    where = f"problème {number}"
    text = raw["text"]
    if not isinstance(text, str) or not text.strip():
        raise GeneratorError(f"{where} : texte non vide attendu")
    if not isinstance(raw["params"], Mapping) or not raw["params"]:
        raise GeneratorError(f"{where} : au moins un paramètre attendu")
    params = tuple(_param(name, spec, where) for name, spec in raw["params"].items())
    known = {param.name for param in params}
    derived = []
    raw_derived = raw.get("derived") or {}
    if not isinstance(raw_derived, Mapping):
        raise GeneratorError(f"{where}.derived : objet {{nom: expression}} attendu")
    for name, source in raw_derived.items():
        if not isinstance(name, str) or not _NAME_RE.fullmatch(name) or name in _RESERVED:
            raise GeneratorError(f"{where}.derived : nom invalide {name!r}")
        if name in known:
            raise GeneratorError(f"{where}.derived : nom déjà défini {name!r}")
        tree = parse_expression(source, f"{where}.derived.{name}")
        _check_names(tree, known, f"{where}.derived.{name}")
        derived.append((name, tree))
        known.add(name)
    raw_constraints = raw["constraints"]
    if not isinstance(raw_constraints, list):
        raise GeneratorError(f"{where}.constraints : liste d'expressions attendue")
    constraints = []
    for position, source in enumerate(raw_constraints):
        tree = parse_expression(source, f"{where}.constraints[{position}]")
        _check_names(tree, known, f"{where}.constraints[{position}]")
        constraints.append(tree)
    answer = parse_expression(raw["answer"], f"{where}.answer")
    _check_names(answer, known, f"{where}.answer")
    placeholders = set(_PLACEHOLDER_RE.findall(text))
    if placeholders - known:
        raise GeneratorError(
            f"{where} : texte qui cite des noms inconnus {sorted(placeholders - known)}"
        )
    if not {param.name for param in params} <= placeholders:
        raise GeneratorError(f"{where} : chaque paramètre doit apparaître dans le texte")
    return Problem(number, nfc(text), params, tuple(derived), tuple(constraints), answer)


def _check_names(tree: ast.Expression, known: set[str], where: str) -> None:
    unknown = _names(tree) - known
    if unknown:
        raise GeneratorError(f"{where} : noms inconnus {sorted(unknown)}")


def parse_problems(document: Any) -> list[Problem]:
    """Valide un document ``qb.var_math/1`` (déjà lu en YAML) et rend ses problèmes triés."""
    if not isinstance(document, Mapping) or set(document) != {"schema", "problems"}:
        raise GeneratorError("fichier VAR-MATH : clés {schema, problems} exactement attendues")
    if document["schema"] != SCHEMA_ID:
        raise GeneratorError(f"fichier VAR-MATH : schéma {SCHEMA_ID} attendu")
    if not isinstance(document["problems"], list) or not document["problems"]:
        raise GeneratorError("fichier VAR-MATH : liste de problèmes non vide attendue")
    problems = [parse_problem(raw, index) for index, raw in enumerate(document["problems"])]
    numbers = [problem.number for problem in problems]
    if len(set(numbers)) != len(numbers):
        raise GeneratorError("fichier VAR-MATH : numéro de problème en double")
    return sorted(problems, key=lambda problem: problem.number)


# --- Génération ----------------------------------------------------------------------------


def _draw(problem: Problem, rng: random.Random) -> tuple[dict[str, int], int] | None:
    """Un tirage : valeurs des noms et réponse, ou ``None`` si le tirage est rejeté."""
    env = {param.name: rng.choice(param.values) for param in problem.params}
    try:
        for name, tree in problem.derived:
            value = evaluate(tree, env)
            if isinstance(value, bool) or not isinstance(value, int):
                raise GeneratorError(f"problème {problem.number} : {name} n'est pas entier")
            env[name] = value
        if not all(evaluate(tree, env) for tree in problem.constraints):
            return None
        answer = evaluate(problem.answer, env)
    except _DrawRejectedError:
        return None
    if isinstance(answer, bool) or not isinstance(answer, int):
        raise GeneratorError(f"problème {problem.number} : réponse non entière")
    return env, answer


def render(problem: Problem, env: Mapping[str, int]) -> str:
    """Texte du problème, chaque ``{nom}`` remplacé par sa valeur (aucun ``str.format``)."""
    return _PLACEHOLDER_RE.sub(lambda match: str(env[match[1]]), problem.text)


def instantiate(problem: Problem, seed: int, variants: int) -> list[tuple[str, int]]:
    """``variants`` variantes distinctes (texte, réponse), par tirage avec rejet borné."""
    rng = random.Random(int(sha256_hex([seed, GENERATOR, problem.number]), 16))
    results: list[tuple[str, int]] = []
    seen: set[str] = set()
    draws = 0
    while len(results) < variants:
        if draws >= MAX_DRAWS_PER_VARIANT * variants:
            raise GeneratorError(
                f"problème {problem.number} : {len(results)} variantes distinctes sur "
                f"{variants} après {draws} tirages (contraintes trop strictes ou trop peu "
                "de valeurs)"
            )
        draws += 1
        drawn = _draw(problem, rng)
        if drawn is None:
            continue
        env, answer = drawn
        text = render(problem, env)
        if text in seen:
            continue
        seen.add(text)
        results.append((text, answer))
    return results


def generate(
    problems: list[Problem], seed: int, variants: int = DEFAULT_VARIANTS
) -> list[dict[str, Any]]:
    """Questions ``var-math-fr`` : ``variants`` par problème, un groupe et une ``unit`` par
    problème (``reasoning/var-math-fr/p<numéro>``), cible entière."""
    if not isinstance(variants, int) or isinstance(variants, bool) or variants < 1:
        raise GeneratorError(f"variants : entier ≥ 1 attendu, reçu {variants!r}")
    questions = []
    number = 0
    for problem in sorted(problems, key=lambda item: item.number):
        group = f"reasoning/{SOURCE}/p{problem.number:04d}"
        for text, answer in instantiate(problem, seed, variants):
            number += 1
            questions.append(
                build_question(
                    source=SOURCE,
                    number=number,
                    group=group,
                    unit=group,
                    messages=[{"role": "user", "content": text + ANSWER_INSTRUCTION}],
                    grader_params={"answer_prefix": ANSWER_PREFIX},
                    target=answer,
                    generator=GENERATOR,
                    generator_seed=seed,
                )
            )
    return questions
