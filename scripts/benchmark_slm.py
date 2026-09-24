#!/usr/bin/env python3
"""
WaveLocalAI - Benchmark SLM Complet
===================================
Script d'évaluation approfondie des Small Language Models (SLM) locaux et API.

Métriques mesurées :
- Performance d'inférence (tokens/s, TTFT, durée)
- Consommation de ressources (RAM, VRAM)
- Impact environnemental (CO2 via CodeCarbon)
- Capacités fonctionnelles (tools, JSON, multilingue, raisonnement)
- Robustesse du contexte (needle-in-haystack)

Auteur: WaveLocalAI Team
Version: 2.0.0
"""

import argparse
import contextlib
import csv
import json
import logging
import random
import re
import shutil
import statistics
import string
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

# Ajout du path pour les imports internes
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

try:
    import ollama
    from codecarbon import OfflineEmissionsTracker

    from src.core.config import (
        BENCHMARKS_DIR,
        DATA_DIR,
        DEFAULT_COUNTRY_ISO_CODE,
        EMISSIONS_DIR,
        MISTRAL_API_KEY,
        MODELS_JSON_PATH,
    )
except ImportError as e:
    print(f"❌ Erreur d'import : {e}")
    print("Assurez-vous d'avoir installé : ollama, codecarbon, python-dotenv")
    sys.exit(1)

# Import optionnel pour l'API Mistral
try:
    from mistralai import Mistral

    MISTRAL_AVAILABLE = True
except ImportError:
    MISTRAL_AVAILABLE = False


# --- CONFIGURATION ---
BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_MD_PATH = DATA_DIR / "benchmark_report.md"
DATASET_CSV_PATH = DATA_DIR / "benchmarks_data.csv"
AUDIT_LOG_FILE = BENCHMARKS_DIR / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Seuils et paramètres
MIN_RAM_MARGIN_GB = 1.0
# Croissance du fichier d'échange à partir de laquelle on considère un vrai swap.
SWAP_DELTA_THRESHOLD_GB = 0.5
CONTEXT_LEVELS = [2048, 4096, 8192, 16384, 32768, 65536, 131072]
TOTAL_RAM_GB = round(psutil.virtual_memory().total / (1024**3), 2)
DEFAULT_OUTPUT_TOKENS = 256
DEFAULT_TIMEOUT_S = 300
DEFAULT_RUNS = 1
# Refroidissement entre modèles : sur un portable, une campagne longue fait
# chuter les fréquences GPU (-27 % observés), ce qui se lit à tort comme une
# différence entre modèles.
DEFAULT_COOLDOWN_TEMP_C = 65
DEFAULT_COOLDOWN_MAX_S = 180
# Valeurs de t de Student à 95 %, par degré de liberté (n-1).
T95 = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262}

# Langues supportées pour les tests multilingues (Listes de synonymes acceptés)
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "hello": "Hello", "expected": ["hello", "hi", "greetings"]},
    "fr": {"name": "French", "hello": "Bonjour", "expected": ["bonjour", "salut", "coucou"]},
    "es": {"name": "Spanish", "hello": "Hola", "expected": ["hola", "buenos días", "buenas"]},
    "de": {"name": "German", "hello": "Hallo", "expected": ["hallo", "guten tag", "hi"]},
    "it": {"name": "Italian", "hello": "Ciao", "expected": ["ciao", "salve", "buongiorno"]},
    "pt": {"name": "Portuguese", "hello": "Olá", "expected": ["olá", "oi", "bom dia"]},
    "zh": {"name": "Chinese", "hello": "你好", "expected": ["你好", "您好"]},
    "ja": {"name": "Japanese", "hello": "こんにちは", "expected": ["こんにちは", "ハロー"]},
    "ko": {"name": "Korean", "hello": "안녕하세요", "expected": ["안녕하세요", "안녕"]},
    "ar": {"name": "Arabic", "hello": "مرحبا", "expected": ["مرحبا", "أهلا", "السلام عليكم"]},
    "ru": {"name": "Russian", "hello": "Привет", "expected": ["привет", "здравствуйте"]},
}

# Plafond de génération pour les tests fonctionnels (évite les boucles infinies)
FUNCTIONAL_MAX_TOKENS = 1024

# Tests de raisonnement logique.
# "match" décrit la façon de valider : number (dernier nombre de la réponse),
# word (mot isolé), compact (comparaison sans espaces) ou contains.
REASONING_TESTS = [
    {
        "id": "logic_syllogism",
        "prompt": "All roses are flowers. All flowers need water. Does a rose need water? Answer only 'yes' or 'no'.",
        "expected": "yes",
        "match": "word",
        "category": "logic",
    },
    {
        "id": "arithmetic_simple",
        "prompt": "What is 17 + 28? Answer with only the number.",
        "expected": "45",
        "match": "number",
        "category": "arithmetic",
    },
    {
        "id": "arithmetic_multi",
        "prompt": "If I have 3 boxes with 4 apples each, and I eat 2 apples, how many apples are left? Answer with only the number.",
        "expected": "10",
        "match": "number",
        "category": "arithmetic",
    },
    {
        "id": "logic_negation",
        "prompt": "If it is NOT true that all cats are black, can there be a white cat? Answer only 'yes' or 'no'.",
        "expected": "yes",
        "match": "word",
        "category": "logic",
    },
    {
        "id": "sequence",
        "prompt": "What is the next number in this sequence: 2, 4, 8, 16, ? Answer with only the number.",
        "expected": "32",
        "match": "number",
        "category": "pattern",
    },
    {
        "id": "logic_transitive",
        "prompt": "All Bloops are Razzies. No Razzies are Lazzies. Can a Bloop be a Lazzie? Answer only 'yes' or 'no'.",
        "expected": "no",
        "match": "word",
        "category": "logic",
    },
    {
        "id": "time_arithmetic",
        "prompt": "A train leaves at 09:15 and the journey takes 2 hours and 50 minutes. At what time does it arrive? Answer only in HH:MM 24-hour format.",
        "expected": "12:05",
        "match": "compact",
        "category": "arithmetic",
    },
    {
        "id": "unit_conversion",
        "prompt": "A tank holds 2.5 cubic meters of water. How many liters is that? Answer with only the number.",
        "expected": "2500",
        "match": "number",
        "category": "arithmetic",
    },
    {
        "id": "percentage",
        "prompt": "A price rises from 80 euros to 100 euros. What is the percentage increase? Answer with only the number.",
        "expected": "25",
        "match": "number",
        "category": "arithmetic",
    },
    {
        "id": "trap_cognitive_reflection",
        "prompt": "A bat and a ball cost 1.10 euros in total. The bat costs 1.00 euro more than the ball. How much does the ball cost, in cents? Answer with only the number.",
        "expected": "5",
        "match": "number",
        "category": "trap",
    },
    {
        "id": "trap_decimal_comparison",
        "prompt": "Which number is larger: 9.11 or 9.9? Answer with only the number.",
        "expected": "9.9",
        "match": "number",
        "category": "trap",
    },
    {
        "id": "trap_letter_counting",
        "prompt": "How many times does the letter 'r' appear in the word 'strawberry'? Answer with only the number.",
        "expected": "3",
        "match": "number",
        "category": "trap",
    },
    {
        "id": "date_arithmetic",
        "prompt": "If today is Wednesday, what day of the week will it be in 10 days? Answer with only the day name in English.",
        "expected": "saturday",
        "match": "word",
        "category": "pattern",
    },
    {
        "id": "ordering",
        "prompt": "Sort these numbers in descending order, separated by commas, and write nothing else: 12, 7, 103, 9",
        "expected": "103,12,9,7",
        "match": "compact",
        "category": "pattern",
    },
]


def _parse_int_list(text: str) -> list[int]:
    """Extrait une liste d'entiers d'une réponse CSV sur une ligne."""
    return [int(x) for x in re.findall(r"-?\d+", text)]


# Tests de suivi d'instructions (contraintes de format strictes)
INSTRUCTION_TESTS = [
    {
        "id": "format_list",
        "prompt": "List exactly 3 colors. Format: one color per line, no numbers, no punctuation.",
        "check": lambda r: len([ln for ln in r.strip().split("\n") if ln.strip()]) == 3
        and not re.search(r"[\d.,;:]", r),
    },
    {
        "id": "format_uppercase",
        "prompt": "Write the word 'hello' in uppercase letters only.",
        "check": lambda r: "HELLO" in r.upper() and r.strip().isupper(),
    },
    {
        "id": "format_json_simple",
        "prompt": 'Return a valid JSON object with exactly two keys: "name" (string) and "age" (number). Nothing else.',
        "check": lambda r: _is_valid_json_with_keys(r, ["name", "age"]),
    },
    {
        "id": "constraint_length",
        "prompt": "Describe the sun in exactly 10 words. Count carefully.",
        "check": lambda r: len(r.split()) == 10,
    },
    {
        "id": "exact_prefix",
        "prompt": "Reply with a single line starting exactly with 'RESULT: ' followed by the capital city of Japan.",
        "check": lambda r: r.strip().startswith("RESULT: ") and "tokyo" in r.lower(),
    },
    {
        "id": "one_word_lowercase",
        "prompt": "What is the capital of France? Reply with exactly one word, all lowercase, no punctuation.",
        "check": lambda r: r.strip() == "paris",
    },
    {
        "id": "csv_constraints",
        "prompt": "Write exactly five even numbers between 10 and 30, separated by commas, on one line, in descending order. Write nothing else.",
        "check": lambda r: (
            lambda nums: len(nums) == 5
            and all(n % 2 == 0 and 10 <= n <= 30 for n in nums)
            and nums == sorted(nums, reverse=True)
        )(_parse_int_list(r)),
    },
    {
        "id": "no_markdown",
        "prompt": "Explain gravity in exactly two sentences. Plain text only: no markdown, no bullet points, no headings.",
        "check": lambda r: not re.search(r"(^|\n)\s*[-*#>]|\*\*", r)
        and len([s for s in re.split(r"(?<=[.!?])\s+", r.strip()) if s.strip()]) == 2,
    },
]

# Tests d'abstention : le modèle doit refuser d'inventer.
ABSTENTION_TESTS = [
    {
        "id": "fictional_entity",
        "prompt": "What was the population of the city of Zyrbandia in 2024? If you do not know, or if it does not exist, reply with exactly: UNKNOWN",
    },
    {
        "id": "future_event",
        "prompt": "Who won the 2031 FIFA World Cup? If it has not happened yet, reply with exactly: UNKNOWN",
    },
]

# Suite de tests d'appel d'outils (détection, choix, paramètres, abstention d'appel)
_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City name"}},
            "required": ["location"],
        },
    },
}
_SUM_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_sum",
        "description": "Add two numbers together",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
    },
}
_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "send_email",
        "description": "Send an email to a recipient",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient address"},
                "body": {"type": "string", "description": "Message body"},
            },
            "required": ["to", "body"],
        },
    },
}
_WEATHER_UNIT_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit",
                },
            },
            "required": ["location", "unit"],
        },
    },
}

TOOL_TESTS = [
    {
        "id": "simple_call",
        "tools": [_WEATHER_TOOL],
        "prompt": "What is the current weather in Paris, France?",
        "expect_call": "get_weather",
        "expect_args": {"location": "paris"},
    },
    {
        "id": "choose_among_tools",
        "tools": [_WEATHER_TOOL, _SUM_TOOL, _EMAIL_TOOL],
        "prompt": "What is 128 plus 47?",
        "expect_call": "calculate_sum",
        "expect_args": {"a": "128", "b": "47"},
    },
    {
        "id": "no_call_needed",
        "tools": [_WEATHER_TOOL],
        "prompt": "What is the capital of France?",
        "expect_call": None,
    },
    {
        "id": "enum_parameter",
        "tools": [_WEATHER_UNIT_TOOL],
        "prompt": "What is the weather in Tokyo, in fahrenheit?",
        "expect_call": "get_weather",
        "expect_args": {"location": "tokyo", "unit": "fahrenheit"},
    },
]

# Schéma JSON pour le test de conformité
JSON_SCHEMA_TEST = {
    "prompt": """Generate a JSON object representing a person with the following structure:
{
  "firstName": string,
  "lastName": string,
  "age": integer (between 0 and 120),
  "email": string (valid email format),
  "active": boolean
}
Return ONLY the JSON, no explanation.""",
    "schema": {
        "type": "object",
        "required": ["firstName", "lastName", "age", "email", "active"],
        "properties": {
            "firstName": {"type": "string"},
            "lastName": {"type": "string"},
            "age": {"type": "integer", "minimum": 0, "maximum": 120},
            "email": {"type": "string", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
            "active": {"type": "boolean"},
        },
    },
}

# Second test JSON : structure imbriquée (objet + tableau + enum), nettement plus discriminant.
JSON_SCHEMA_TEST_NESTED = {
    "prompt": """Generate a JSON object representing a purchase order with this exact structure:
{
  "orderId": string,
  "status": one of "pending", "shipped", "delivered",
  "customer": { "name": string, "vip": boolean },
  "items": array of 2 objects, each { "sku": string, "qty": integer (1 to 99) },
  "total": number
}
Return ONLY the JSON, no explanation.""",
    "schema": {
        "type": "object",
        "required": ["orderId", "status", "customer", "items", "total"],
        "properties": {
            "orderId": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "shipped", "delivered"]},
            "customer": {
                "type": "object",
                "required": ["name", "vip"],
                "properties": {"name": {"type": "string"}, "vip": {"type": "boolean"}},
            },
            "items": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "required": ["sku", "qty"],
                    "properties": {
                        "sku": {"type": "string"},
                        "qty": {"type": "integer", "minimum": 1, "maximum": 99},
                    },
                },
            },
            "total": {"type": "number"},
        },
    },
}

JSON_TESTS = [JSON_SCHEMA_TEST, JSON_SCHEMA_TEST_NESTED]

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# --- HELPERS ---
_THINK_BLOCK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<(think|thinking|reasoning)>.*$", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str | None) -> str:
    """Retire les blocs de raisonnement laissés dans la réponse par certains modèles.

    Sans ce nettoyage, un modèle qui écrit son <think> dans le contenu échoue
    systématiquement aux contrôles de format, ce qui fausse le score.
    """
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_OPEN_RE.sub("", cleaned)
    return cleaned.strip()


def _answer_matches(response: str, expected: str, match: str = "contains") -> bool:
    """Valide une réponse courte selon le mode de comparaison attendu."""
    text = strip_thinking(response).strip().lower()
    exp = expected.lower()

    if match == "number":
        # On compare le DERNIER nombre cité : tolère "17 + 28 = 45".
        def _normalize(value: str) -> str:
            value = value.replace(",", ".")
            # Les zéros finaux ne se suppriment QUE derrière une virgule décimale :
            # sinon "50" deviendrait "5" et validerait une réponse fausse.
            return value.rstrip("0").rstrip(".") if "." in value else value

        numbers = re.findall(r"-?\d+(?:[.,]\d+)?", text)
        if not numbers:
            return False
        return _normalize(numbers[-1]) == _normalize(exp)
    if match == "word":
        return re.search(rf"\b{re.escape(exp)}\b", text) is not None
    if match == "compact":
        return exp.replace(" ", "") in re.sub(r"\s+", "", text)
    return exp in text


def _is_valid_json_with_keys(response: str, required_keys: list) -> bool:
    """Vérifie si la réponse est un JSON valide avec les clés requises."""
    try:
        # Nettoyage des backticks markdown
        clean = re.sub(r"```json\s*|\s*```", "", strip_thinking(response).strip())
        data = json.loads(clean)
        return all(k in data for k in required_keys)
    except (json.JSONDecodeError, TypeError):
        return False


def _value_matches_spec(value, spec: dict) -> bool:
    """Valide une valeur contre un sous-schéma (types, bornes, enum, tableaux, objets)."""
    expected_type = spec.get("type")

    if expected_type == "string" and not isinstance(value, str):
        return False
    if expected_type == "boolean" and not isinstance(value, bool):
        return False
    # bool est un sous-type de int en Python : on l'exclut explicitement.
    if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return False
    if expected_type == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        return False
    if expected_type == "array" and not isinstance(value, list):
        return False
    if expected_type == "object" and not isinstance(value, dict):
        return False

    if "enum" in spec and value not in spec["enum"]:
        return False

    if expected_type in ("integer", "number"):
        if "minimum" in spec and value < spec["minimum"]:
            return False
        if "maximum" in spec and value > spec["maximum"]:
            return False

    if expected_type == "string" and "pattern" in spec and not re.match(spec["pattern"], value):
        return False

    if expected_type == "array":
        if "minItems" in spec and len(value) < spec["minItems"]:
            return False
        if "maxItems" in spec and len(value) > spec["maxItems"]:
            return False
        item_spec = spec.get("items")
        if item_spec and not all(_value_matches_spec(item, item_spec) for item in value):
            return False

    if expected_type == "object":
        if not all(k in value for k in spec.get("required", [])):
            return False
        for key, sub_spec in spec.get("properties", {}).items():
            if key in value and not _value_matches_spec(value[key], sub_spec):
                return False

    return True


def _validate_json_schema(response: str, schema: dict) -> tuple[bool, bool]:
    """
    Valide un JSON contre un schéma simplifié (récursif : objets, tableaux, enum).
    Retourne (json_valide, schema_conforme).
    """
    clean = strip_thinking(response)
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", clean.strip())
    # Certains modèles encadrent le JSON de texte : on isole le premier objet.
    if not clean.startswith("{"):
        start, end = clean.find("{"), clean.rfind("}")
        if start != -1 and end > start:
            clean = clean[start : end + 1]

    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, TypeError):
        return False, False

    return True, _value_matches_spec(data, schema)


def detect_license_type(model_tag: str) -> str:
    """
    Récupère la licence via Ollama et tente de la classifier.
    Retourne : 'Apache 2.0', 'MIT', 'Llama Community', etc.
    """
    try:
        # Récupération des métadonnées brutes
        info = ollama.show(model_tag)
        license_text = info.get("license", "").lower()

        if not license_text:
            return "Non détectée"

        # Heuristiques de classification
        if "apache" in license_text and "2.0" in license_text:
            return "Apache 2.0"
        if "mit license" in license_text:
            return "MIT"
        if "llama" in license_text and "community" in license_text:
            return "Llama Community"
        if "creative commons" in license_text:
            if "nc" in license_text or "noncommercial" in license_text:
                return "CC-BY-NC"
            return "CC-BY"
        if "openrail" in license_text:
            return "OpenRAIL"

        return "Autre (Voir détails)"
    except Exception:
        return "Erreur lecture"


def _get_ux_rating(ttft_ms: float) -> str:
    """Note qualitative de la fluidité (Latence)."""
    if ttft_ms <= 0:
        return "N/A"
    if ttft_ms < 300:
        return "⚡ Instantané"
    if ttft_ms < 800:
        return "🚀 Rapide"
    if ttft_ms < 1500:
        return "🐢 Acceptable"
    return "🐌 Lent"


def _get_efficiency_score(reasoning_score: float, co2_per_1k: float) -> str:
    """
    Score d'efficience : Rapport entre l'intelligence (Reasoning) et le coût (CO2).
    Permet d'identifier les modèles 'intelligents pour leur poids carbone'.
    """
    if co2_per_1k <= 0:
        return "N/A"

    # Conversion en grammes pour lisibilité calcul
    co2_g = co2_per_1k * 1000
    if co2_g == 0:
        return "N/A"

    # Formule : (Score Raisonnement 0-1 * 100) / (Grammes CO2 par 1k tokens)
    # Exemple : Score 0.8 (80%) / 0.1g CO2 = Ratio 800
    score = (reasoning_score * 100) / co2_g

    if score > 500:
        return "🟢 Excellent"
    if score > 200:
        return "🟡 Bon"
    return "🔴 Faible"


GEN_TASK = (
    "Write a detailed technical explanation about how neural networks learn "
    "through backpropagation."
)

# Part de la fenêtre de contexte occupée par le prompt du test de performance.
PREFILL_FILL_RATIO = 0.5

# Texte de remplissage déterministe (reproductibilité entre deux campagnes).
_FILLER_SENTENCES = [
    "The quarterly report details revenue, operating costs and hiring plans across divisions.",
    "Logistics delays in the northern corridor affected delivery times during the last period.",
    "The engineering team migrated the storage layer and reduced median query latency.",
    "Customer support handled a higher ticket volume after the pricing change was announced.",
    "Regulatory filings were updated to reflect the new data retention requirements.",
]


def _build_perf_prompt(context_window: int) -> str:
    """Construit un prompt occupant environ la moitié de la fenêtre de contexte.

    Mesurer le prefill sur un prompt de quelques tokens ne mesure qu'un coût fixe :
    la vitesse de lecture obtenue est alors ininterprétable. On calibre donc le
    prompt sur le contexte testé (≈ 3,5 caractères par token).
    """
    target_chars = int(context_window * PREFILL_FILL_RATIO * 3.5)
    parts: list[str] = []
    length = 0
    idx = 0
    while length < target_chars:
        sentence = _FILLER_SENTENCES[idx % len(_FILLER_SENTENCES)]
        parts.append(sentence)
        length += len(sentence) + 1
        idx += 1
    return f"{' '.join(parts)}\n\n{GEN_TASK}"


def _generate_needle_haystack(
    context_size: int, depth_percent: float = 0.5
) -> tuple[str, str, str]:
    """
    Génère un test needle-in-haystack.
    depth_percent: Position de l'aiguille (0.0 = début, 0.5 = milieu, 1.0 = fin)
    Retourne (prompt_complet, needle, question).
    """
    # Générer un code secret unique
    secret_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    needle = f"The secret code is: {secret_code}"

    # Calculer la taille du filler (environ 4 chars/token en moyenne)
    target_chars = (context_size * 3) // 4
    filler_paragraphs = []

    topics = [
        "The history of ancient civilizations reveals fascinating patterns of human development.",
        "Modern technology continues to transform how we communicate and work.",
        "Environmental science studies the complex interactions between organisms and their habitats.",
        "Economic theories attempt to explain the behavior of markets and consumers.",
        "Philosophical inquiry examines fundamental questions about existence and knowledge.",
        "Medical research advances our understanding of human health and disease.",
        "Architectural design balances aesthetic beauty with functional requirements.",
        "Literary analysis explores the deeper meanings within written works.",
        "Musical composition combines rhythm, melody, and harmony in creative ways.",
        "Agricultural practices have evolved significantly over thousands of years.",
    ]

    while len(" ".join(filler_paragraphs)) < target_chars:
        filler_paragraphs.append(random.choice(topics) * 3)

    # Insérer le needle à la position demandée
    insert_idx = int(len(filler_paragraphs) * depth_percent)
    insert_idx = max(0, min(insert_idx, len(filler_paragraphs)))  # Bornage

    filler_paragraphs.insert(insert_idx, needle)

    haystack = "\n\n".join(filler_paragraphs)

    prompt = f"""Read the following text carefully and find the secret code hidden within it.

TEXT:
{haystack}

QUESTION: What is the secret code mentioned in the text above? Answer with only the code, nothing else."""

    return prompt, secret_code, "secret_code"


# --- GESTION CSV ---
def get_csv_headers() -> list[str]:
    """Retourne les headers du CSV avec toutes les colonnes."""
    base_headers = [
        "model_name",
        "ollama_tag",
        "model_type",
        "disk_size_gb",
        "context_size",
        "input_tokens",
        "output_tokens",
        "tokens_per_second",
        "prefill_tokens_per_second",
        "time_to_first_token_ms",
        "ttft_full_prompt_ms",
        "ttft_with_load_ms",
        "load_time_ms",
        "duration_s",
        "model_memory_gb",
        "gpu_offload_pct",
        "swap_delta_gb",
        "gpu_temp_c",
        "gpu_clock_mhz",
        "ollama_ram_usage_gb",
        "gpu_vram_usage_gb",
        "ram_peak_gb",
        "co2_kg",
        "co2_per_1k_tokens",
        "status",
        "tool_call_valid",
        "tool_call_function_correct",
        "tool_call_params_correct",
        "tool_suite_score",
        "json_generation_valid",
        "json_schema_compliant",
        "needle_in_haystack_found",
    ]

    # Ajouter les colonnes de langues
    for lang_code in SUPPORTED_LANGUAGES:
        base_headers.append(f"lang_{lang_code}_comprehension")
        base_headers.append(f"lang_{lang_code}_generation")

    # Ajouter les scores de qualité
    base_headers.extend(
        [
            "reasoning_score",
            "instruction_following_score",
            "abstention_score",
            "reasoning_by_category",
            "response_variance",
            "run_id",
            "date",
        ]
    )

    return base_headers


def initialize_csv():
    """Crée le CSV, ou l'archive si ses colonnes ne correspondent plus au script.

    Sans ce contrôle, un CSV créé par une version antérieure garde ses anciennes
    colonnes et les nouvelles métriques sont silencieusement perdues à l'écriture
    (DictWriter est en extrasaction="ignore").
    """
    headers = get_csv_headers()

    if DATASET_CSV_PATH.exists():
        with open(DATASET_CSV_PATH, newline="", encoding="utf-8") as f:
            existing = next(csv.reader(f), [])
        if existing == headers:
            return
        archive = DATASET_CSV_PATH.with_name(
            f"{DATASET_CSV_PATH.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        shutil.move(str(DATASET_CSV_PATH), str(archive))
        logger.warning(f"📄 Colonnes du CSV obsolètes : ancien fichier archivé -> {archive.name}")

    with open(DATASET_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(headers)
    logger.info(f"📄 CSV initialisé : {DATASET_CSV_PATH}")


def append_to_csv(results: list[dict]):
    """Ajoute une liste de résultats à la fin du CSV."""
    if not results:
        return

    headers = get_csv_headers()

    with open(DATASET_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        for result in results:
            # S'assurer que toutes les colonnes existent
            row = {h: result.get(h, "") for h in headers}
            writer.writerow(row)


# --- OUTILS SYSTÈME ---
def unload_model(model_tag: str):
    """Décharge un modèle de la mémoire Ollama."""
    try:
        ollama.chat(model=model_tag, messages=[], keep_alive=0)
        time.sleep(2)
    except Exception:
        pass


def get_system_ram_stats() -> tuple[float, float]:
    """Retourne (RAM utilisée, RAM disponible) en GB."""
    mem = psutil.virtual_memory()
    return mem.used / (1024**3), mem.available / (1024**3)


def get_ollama_process_memory_gb() -> float:
    """Mesure la RAM utilisée par les processus Ollama."""
    total_mem_bytes = 0
    try:
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                if "ollama" in proc.info["name"].lower():
                    total_mem_bytes += proc.info["memory_info"].rss
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception:
        pass
    return total_mem_bytes / (1024**3)


def _nvidia_smi(query: str) -> str:
    """Interroge nvidia-smi et retourne la sortie brute, vide en cas d'échec."""
    import subprocess

    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_gpu_memory_usage_gb() -> float:
    """Tente de mesurer l'utilisation VRAM GPU (NVIDIA)."""
    out = _nvidia_smi("memory.used")
    if not out:
        return 0.0
    try:
        # Somme de toutes les GPU
        return sum(int(x) for x in out.split("\n") if x) / 1024
    except ValueError:
        return 0.0


def get_gpu_thermals() -> tuple[float, float]:
    """(température °C, fréquence graphique MHz) du GPU, ou (0, 0).

    Sur un portable, une campagne longue fait chuter les fréquences : jusqu'à
    -27 % observés entre le début et la fin d'un run de 20 modèles. Sans cette
    trace, l'écart se lit à tort comme une différence entre modèles.
    """
    out = _nvidia_smi("temperature.gpu,clocks.current.graphics")
    if not out:
        return 0.0, 0.0
    try:
        temp, clock = out.splitlines()[0].split(",")
        return float(temp), float(clock)
    except (ValueError, IndexError):
        return 0.0, 0.0


def wait_for_cooldown(target_c: float, max_wait_s: float) -> dict:
    """Attend que le GPU redescende sous `target_c`, au plus `max_wait_s`.

    Sans cette pause, les modèles mesurés en fin de campagne le sont à
    fréquence réduite : l'écart avec ceux du début n'a alors rien à voir avec
    les modèles eux-mêmes.
    """
    start_temp, start_clock = get_gpu_thermals()
    if not start_temp or start_temp <= target_c:
        return {"waited_s": 0, "start_temp_c": start_temp, "end_temp_c": start_temp,
                "clock_mhz": start_clock, "reached": True}

    begin = time.perf_counter()
    temp = start_temp
    while temp > target_c and (time.perf_counter() - begin) < max_wait_s:
        time.sleep(5)
        temp, _ = get_gpu_thermals()

    waited = round(time.perf_counter() - begin, 1)
    _, clock = get_gpu_thermals()
    return {"waited_s": waited, "start_temp_c": start_temp, "end_temp_c": temp,
            "clock_mhz": clock, "reached": temp <= target_c}


def dispersion(values: list[float], digits: int = 2) -> dict:
    """Moyenne, écart-type et intervalle de confiance à 95 % d'une série.

    Avec deux ou trois répétitions, l'intervalle reste large : c'est le
    message, pas un défaut du calcul.
    """
    values = [v for v in values if v is not None]
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {"n": 1, "mean": round(values[0], digits)}

    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    half = T95.get(n - 1, 1.96) * sd / (n ** 0.5)
    return {
        "n": n,
        "mean": round(mean, digits),
        "sd": round(sd, digits),
        "min": round(min(values), digits),
        "max": round(max(values), digits),
        "ci95": [round(mean - half, digits), round(mean + half, digits)],
        "ci95_half_width": round(half, digits),
    }


def get_model_memory_gb() -> float:
    """Empreinte mémoire totale du modèle chargé : RAM des processus Ollama + VRAM.

    Sur une machine à GPU, les poids vivent en VRAM et la RAM des processus reste
    proche de zéro : la mesurer seule rend la détection de swap ininterprétable.
    """
    return get_ollama_process_memory_gb() + get_gpu_memory_usage_gb()


def get_loaded_model_footprint(model_tag: str) -> tuple[float, int]:
    """Empreinte du modèle chargé d'après `ollama ps` : (taille totale en GB, % en VRAM).

    On interroge Ollama plutôt que de calculer une différence de mémoire avant/après :
    le déchargement est asynchrone, donc la mesure de référence peut encore contenir
    le modèle précédent et produire une empreinte absurdement faible.
    """
    try:
        for m in ollama.ps().get("models", []):
            if m.get("model") in (model_tag, f"{model_tag}:latest"):
                size = m.get("size") or 0
                pct = round(100 * (m.get("size_vram") or 0) / size) if size else 0
                return round(size / (1024**3), 3), pct
    except Exception:
        pass
    return 0.0, 0


def get_gpu_offload_pct(model_tag: str) -> int:
    """Pourcentage du modèle chargé résidant en VRAM (0 = 100% CPU, 100 = tout GPU)."""
    return get_loaded_model_footprint(model_tag)[1]


_CAPABILITIES_CACHE: dict[str, list[str]] = {}


def get_model_capabilities(model_tag: str) -> list[str]:
    """Capacités déclarées par Ollama (tools, thinking, vision...), mises en cache."""
    if model_tag not in _CAPABILITIES_CACHE:
        try:
            _CAPABILITIES_CACHE[model_tag] = list(ollama.show(model_tag).capabilities or [])
        except Exception:
            _CAPABILITIES_CACHE[model_tag] = []
    return _CAPABILITIES_CACHE[model_tag]


def supports_thinking(model_tag: str) -> bool:
    """Indique si le modèle expose un mode raisonnement désactivable."""
    return "thinking" in get_model_capabilities(model_tag)


def get_real_disk_size(model_tag: str) -> float:
    """Récupère la taille réelle sur disque d'un modèle Ollama."""
    try:
        list_info = ollama.list()
        for m in list_info.get("models", []):
            if m["model"] == model_tag or m["model"] == f"{model_tag}:latest":
                return round(m["size"] / (1024**3), 2)
    except Exception:
        pass
    return 0.0


def check_model_installed(model_tag: str) -> str | None:
    """Vérifie si un modèle est installé et retourne son tag exact."""
    try:
        installed = {m["model"]: m for m in ollama.list().get("models", [])}
        if model_tag in installed:
            return model_tag
        if f"{model_tag}:latest" in installed:
            return f"{model_tag}:latest"
    except Exception:
        pass
    return None


# --- TESTS FONCTIONNELS ---
class ModelTester:
    """Classe encapsulant tous les tests pour un modèle."""

    def __init__(
        self,
        model_tag: str,
        model_type: str = "local",
        country_iso: str = DEFAULT_COUNTRY_ISO_CODE,
        thinking: bool = False,
        vendor_params: bool = False,
    ):
        self.model_tag = model_tag
        self.model_type = model_type
        self.country_iso = country_iso
        # Mode "éditeur" : on n'impose pas la température, laissant s'appliquer
        # les PARAMETER du Modelfile publié par l'éditeur du modèle.
        self.vendor_params = vendor_params
        # Par défaut le raisonnement est désactivé : sinon les modèles "thinking"
        # sont comparés à des modèles qui répondent directement, et chaque test
        # peut durer plusieurs minutes.
        self.thinking = thinking
        self.detail: dict = {}
        self.mistral_client = None

        if model_type == "api" and MISTRAL_AVAILABLE and MISTRAL_API_KEY:
            self.mistral_client = Mistral(api_key=MISTRAL_API_KEY)

    def _call_model(
        self,
        messages: list[dict],
        tools: list | None = None,
        options: dict | None = None,
    ) -> dict | None:
        """Appelle le modèle (local ou API) et retourne la réponse."""
        if self.model_type == "api":
            return self._call_api(messages, tools)
        return self._call_local(messages, tools, options)

    def _call_local(
        self,
        messages: list[dict],
        tools: list | None = None,
        options: dict | None = None,
    ) -> dict | None:
        """Appelle un modèle local via Ollama avec logging détaillé."""
        try:
            # LOGGING: Entrée
            input_text = messages[-1].get("content", "")
            logger.info(
                f"\n   📥 [INPUT] {self.model_tag}:\n{input_text[:300]}{'...' if len(input_text)>300 else ''}"
            )

            kwargs = {"model": self.model_tag, "messages": messages}
            if tools:
                kwargs["tools"] = tools

            opts = dict(options or {})
            opts.setdefault("num_predict", FUNCTIONAL_MAX_TOKENS)
            if self.vendor_params:
                opts.pop("temperature", None)
            kwargs["options"] = opts

            if supports_thinking(self.model_tag):
                kwargs["think"] = self.thinking

            resp = ollama.chat(**kwargs)

            # Certains modèles écrivent leur raisonnement dans le contenu :
            # on le retire pour ne noter que la réponse finale.
            content = strip_thinking(resp.message.content)
            tool_calls = getattr(resp.message, "tool_calls", None)

            # LOGGING: Sortie
            log_content = content if content else (str(tool_calls) if tool_calls else "<Empty>")
            logger.info(
                f"   📤 [OUTPUT] {self.model_tag}:\n{log_content[:300]}{'...' if len(log_content)>300 else ''}\n"
            )

            return {
                "content": content,
                "tool_calls": tool_calls,
                "prompt_eval_count": getattr(resp, "prompt_eval_count", 0) or 0,
                "eval_count": getattr(resp, "eval_count", 0) or 0,
            }
        except Exception as e:
            logger.error(f"Erreur appel local: {e}")
            return None

    def _call_api(self, messages: list[dict], tools: list | None = None) -> dict | None:
        """Appelle l'API Mistral avec logging détaillé."""
        if not self.mistral_client:
            return None

        try:
            # LOGGING: Entrée
            input_text = messages[-1].get("content", "")
            logger.info(
                f"\n   📥 [API INPUT] {self.model_tag}:\n{input_text[:300]}{'...' if len(input_text)>300 else ''}"
            )

            kwargs = {"model": self.model_tag, "messages": messages}
            if tools:
                kwargs["tools"] = tools

            resp = self.mistral_client.chat.complete(**kwargs)
            choice = resp.choices[0].message

            content = choice.content or ""
            tool_calls = getattr(choice, "tool_calls", None)

            # LOGGING: Sortie
            log_content = content if content else (str(tool_calls) if tool_calls else "<Empty>")
            logger.info(
                f"   📤 [API OUTPUT] {self.model_tag}:\n{log_content[:300]}{'...' if len(log_content)>300 else ''}\n"
            )

            return {
                "content": strip_thinking(choice.content),
                "tool_calls": getattr(choice, "tool_calls", None),
                "prompt_eval_count": getattr(resp.usage, "prompt_tokens", 0),
                "eval_count": getattr(resp.usage, "completion_tokens", 0),
            }
        except Exception as e:
            logger.error(f"Erreur appel API: {e}")
            return None

    @staticmethod
    def _parse_tool_call(tool_call) -> tuple[str, dict]:
        """Extrait (nom, arguments) d'un tool call, quel que soit son format."""
        func = getattr(tool_call, "function", tool_call)
        name = getattr(func, "name", None) or (func.get("name") if isinstance(func, dict) else "")
        args = getattr(func, "arguments", None)
        if args is None and isinstance(func, dict):
            args = func.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        return name or "", args or {}

    def test_tool_calling(self) -> dict:
        """Suite d'appels d'outils : détection, choix du bon outil, paramètres, abstention.

        Chaque cas vaut 1 point ; success_rate est la moyenne. Le cas "no_call_needed"
        vérifie que le modèle n'invente pas un appel quand la question n'en demande pas.
        """
        cases: dict[str, bool] = {}
        legacy = {"valid": False, "function_correct": False, "params_correct": False}

        for test in TOOL_TESTS:
            resp = self._call_model(
                [{"role": "user", "content": test["prompt"]}],
                tools=test["tools"],
                options={"temperature": 0, "num_ctx": 2048},
            )
            calls = (resp or {}).get("tool_calls") or []

            if test["expect_call"] is None:
                cases[test["id"]] = bool(resp) and not calls
                continue

            if not calls:
                cases[test["id"]] = False
                continue

            name, args = self._parse_tool_call(calls[0])
            ok = name == test["expect_call"]
            for key, expected in test.get("expect_args", {}).items():
                value = str(args.get(key, "")).lower()
                ok = ok and expected.lower() in value

            cases[test["id"]] = ok

            if test["id"] == "simple_call":
                legacy["valid"] = True
                legacy["function_correct"] = name == test["expect_call"]
                legacy["params_correct"] = ok

        score = round(sum(cases.values()) / len(cases), 2) if cases else 0.0
        self.detail["tool_cases"] = cases
        return {**legacy, "cases": cases, "score": score}

    def test_tool_not_calling(self) -> bool:
        """Test que le modèle ne call PAS un tool quand ce n'est pas pertinent."""
        test_tool = {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        }
        messages = [{"role": "user", "content": "What is the capital of France?"}]
        resp = self._call_model(
            messages, tools=[test_tool], options={"temperature": 0, "num_ctx": 2048}
        )
        if not resp:
            return False
        return not resp.get("tool_calls")

    def test_json_generation(self) -> tuple[float, float]:
        """Génération JSON sur deux schémas (plat puis imbriqué avec tableau et enum).

        Retourne (taux de JSON valides, taux de schémas respectés).
        """
        valid_count = 0
        schema_count = 0
        details = {}

        for idx, test in enumerate(JSON_TESTS):
            resp = self._call_model(
                [{"role": "user", "content": test["prompt"]}],
                options={"temperature": 0, "num_ctx": 2048},
            )
            if not resp or not resp.get("content"):
                details[f"json_{idx}"] = "no_response"
                continue
            valid, conform = _validate_json_schema(resp["content"], test["schema"])
            valid_count += valid
            schema_count += conform
            details[f"json_{idx}"] = {"valid": valid, "schema": conform}

        total = len(JSON_TESTS)
        self.detail["json_cases"] = details
        return round(valid_count / total, 2), round(schema_count / total, 2)

    def test_abstention(self) -> float:
        """Le modèle doit répondre UNKNOWN au lieu d'inventer (entité fictive, futur)."""
        correct = 0
        details = {}
        for test in ABSTENTION_TESTS:
            resp = self._call_model(
                [{"role": "user", "content": test["prompt"]}],
                options={"temperature": 0, "num_ctx": 2048},
            )
            content = (resp or {}).get("content") or ""
            ok = "unknown" in content.lower()
            correct += ok
            details[test["id"]] = ok
        self.detail["abstention_cases"] = details
        return round(correct / len(ABSTENTION_TESTS), 2) if ABSTENTION_TESTS else 0.0

    def test_language(self, lang_code: str) -> dict:
        """Test de support linguistique avec tolérance accrue."""
        result = {"comprehension": False, "generation": False}
        lang_info = SUPPORTED_LANGUAGES.get(lang_code)

        if not lang_info:
            return result

        # Test de génération : Traduction
        if lang_code != "en":
            gen_prompt = f"Translate the English word 'Hello' into {lang_info['name']}. Return ONLY the translated word."
            resp = self._call_model(
                [{"role": "user", "content": gen_prompt}],
                options={"temperature": 0, "num_ctx": 2048},
            )

            if resp and resp.get("content"):
                content = resp["content"].strip().lower()
                # Nettoyage ponctuation
                content = re.sub(r"[^\w\s]", "", content)
                expected_list = lang_info.get("expected", [])

                # Vérification : au moins un des mots attendus est présent
                if any(exp in content for exp in expected_list):
                    result["generation"] = True
                elif len(content) > 0 and "hello" not in content:
                    # Heuristique fallback
                    result["generation"] = True

        # Test de compréhension : Question simple
        # Mise à jour des réponses attendues (listes élargies)
        expected_answers = {
            "en": ["blue", "azure", "clear"],
            "fr": ["bleu", "bleue", "azur", "claire"],
            "es": ["azul", "celeste", "claro"],
            "de": ["blau", "himmelblau", "klar"],
            "it": ["blu", "azzurro", "celeste"],
            "pt": ["azul", "celeste", "claro"],
            "zh": ["蓝", "天蓝", "青"],
            "ja": ["青", "ブルー", "水色"],
            "ko": ["파란", "파랑", "푸른", "하늘색"],
            "ar": ["أزرق", "زرقاء", "سماوي"],
            "ru": ["голубой", "синий", "лазурный"],
        }

        comp_prompts = {
            "en": "What color is the sky on a clear day? Answer in one word.",
            "fr": "De quelle couleur est le ciel par temps clair ? Répondez en un mot.",
            "es": "¿De qué color es el cielo en un día despejado? Responde en una palabra.",
            "de": "Welche Farbe hat der Himmel an einem klaren Tag? Antworte mit einem Wort.",
            "it": "Di che colore è il cielo in una giornata limpida? Rispondi con una parola.",
            "pt": "Qual é a cor do céu em um dia claro? Responda em uma palavra.",
            "zh": "晴天时天空是什么颜色？用一个词回答。",
            "ja": "晴れた日の空は何色ですか？一言で答えてください。",
            "ko": "맑은 날 하늘은 무슨 색인가요? 한 단어로 대답하세요.",
            "ar": "ما لون السماء في يوم صافٍ؟ أجب بكلمة واحدة.",
            "ru": "Какого цвета небо в ясный день? Ответьте одним словом.",
        }

        if lang_code in comp_prompts:
            resp = self._call_model(
                [{"role": "user", "content": comp_prompts[lang_code]}],
                options={"temperature": 0, "num_ctx": 2048},
            )

            if resp and resp.get("content"):
                content = resp["content"].strip().lower()
                expected_list = expected_answers.get(lang_code, [])
                if any(exp in content for exp in expected_list):
                    result["comprehension"] = True

        return result

    def test_reasoning(self) -> float:
        """Exécute les tests de raisonnement et retourne un score 0-1.

        Le détail par test et par catégorie (logic, arithmetic, pattern, trap)
        est conservé dans self.detail pour départager les modèles proches.
        """
        correct = 0
        total = len(REASONING_TESTS)
        per_test: dict[str, bool] = {}
        per_category: dict[str, list[int]] = {}

        for test in REASONING_TESTS:
            resp = self._call_model(
                [{"role": "user", "content": test["prompt"]}],
                options={"temperature": 0, "num_ctx": 2048},
            )
            ok = bool(
                resp
                and resp.get("content")
                and _answer_matches(
                    resp["content"], test["expected"], test.get("match", "contains")
                )
            )
            correct += ok
            per_test[test["id"]] = ok
            per_category.setdefault(test["category"], []).append(int(ok))

        self.detail["reasoning_tests"] = per_test
        self.detail["reasoning_by_category"] = {
            cat: round(sum(v) / len(v), 2) for cat, v in per_category.items()
        }
        return round(correct / total, 2) if total > 0 else 0.0

    def test_instruction_following(self) -> float:
        """Exécute les tests de suivi d'instructions (contraintes de format strictes)."""
        correct = 0
        total = len(INSTRUCTION_TESTS)
        per_test: dict[str, bool] = {}

        for test in INSTRUCTION_TESTS:
            resp = self._call_model(
                [{"role": "user", "content": test["prompt"]}],
                options={"temperature": 0, "num_ctx": 2048},
            )
            ok = False
            if resp and resp.get("content"):
                try:
                    ok = bool(test["check"](resp["content"]))
                except Exception:
                    ok = False
            correct += ok
            per_test[test["id"]] = ok

        self.detail["instruction_tests"] = per_test
        return round(correct / total, 2) if total > 0 else 0.0

    def test_needle_in_haystack(self, context_size: int) -> bool:
        """
        Test needle-in-haystack robuste (Début, Milieu, Fin).
        Le test réussit si le modèle trouve l'aiguille dans TOUTES les positions.
        """
        positions = [0.1, 0.5, 0.9]  # 10%, 50%, 90%
        success_count = 0

        logger.info(
            f"         🔍 Needle-in-haystack ({context_size}): Testing {len(positions)} positions..."
        )

        for pos in positions:
            prompt, expected_code, _ = _generate_needle_haystack(context_size, depth_percent=pos)

            resp = self._call_model(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0, "num_ctx": context_size},
            )

            found = False
            if resp and resp.get("content"):
                content = resp["content"].strip().upper()
                if expected_code in content:
                    found = True

            pos_label = f"{int(pos*100)}%"
            if found:
                success_count += 1
                logger.debug(f"            Pos {pos_label}: ✅ Found")
            else:
                logger.warning(f"            Pos {pos_label}: ❌ Failed (Code: {expected_code})")

        # Règle stricte : Doit réussir partout pour être considéré "fiable"
        # Vous pouvez relaxer ceci en retournant success_count >= 2 par exemple
        is_robust = success_count == len(positions)
        return is_robust


# --- BENCHMARK PRINCIPAL ---
def benchmark_inference(
    model_tag: str,
    context_window: int,
    model_type: str = "local",
    country_iso: str = DEFAULT_COUNTRY_ISO_CODE,
    output_token_limit: int = DEFAULT_OUTPUT_TOKENS,
    thinking: bool = False,
    vendor_params: bool = False,
) -> dict | None:
    """
    Benchmark d'inférence avec mesures complètes.
    """
    if model_type == "local":
        unload_model(model_tag)

        _, sys_ram_avail = get_system_ram_stats()
        if sys_ram_avail < MIN_RAM_MARGIN_GB:
            logger.warning(f"   ⚠️  RAM insuffisante ({sys_ram_avail:.2f}GB dispo)")
            return None

    ollama_ram_start = get_ollama_process_memory_gb() if model_type == "local" else 0
    model_mem_start = get_model_memory_gb() if model_type == "local" else 0
    gpu_vram_start = get_gpu_memory_usage_gb()
    swap_start = psutil.swap_memory().used / (1024**3)

    # Initialiser CodeCarbon
    EMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    tracker = None
    if model_type == "local":
        tracker = OfflineEmissionsTracker(
            country_iso_code=country_iso,
            output_dir=str(EMISSIONS_DIR),
            log_level="error",
        )
        tracker.start()

    start_time = time.perf_counter()
    first_token_time = None

    # Prompt calibré sur le contexte testé : sans cela, prompt_eval_duration ne mesure
    # qu'un coût fixe et la vitesse de lecture affichée n'a pas de sens.
    messages = [{"role": "user", "content": _build_perf_prompt(context_window)}]

    try:
        if model_type == "local":
            chat_kwargs = {
                "model": model_tag,
                "messages": messages,
                "stream": True,
                "options": {
                    "num_ctx": context_window,
                    "temperature": 0.7,
                    "num_predict": output_token_limit,
                },
            }
            if vendor_params:
                chat_kwargs["options"].pop("temperature")
            if supports_thinking(model_tag):
                chat_kwargs["think"] = thinking

            # Mode streaming pour mesurer TTFT
            stream = ollama.chat(**chat_kwargs)

            response_content = ""
            input_tokens = 0
            output_tokens = 0
            eval_duration_ns = 0
            prompt_eval_duration_ns = 0
            load_duration_ns = 0

            for chunk in stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()

                if hasattr(chunk, "message") and chunk.message.content:
                    response_content += chunk.message.content

                # Récupérer les stats à la fin
                if hasattr(chunk, "prompt_eval_count"):
                    input_tokens = chunk.prompt_eval_count or input_tokens
                if hasattr(chunk, "eval_count"):
                    output_tokens = chunk.eval_count or output_tokens
                eval_duration_ns = getattr(chunk, "eval_duration", None) or eval_duration_ns
                prompt_eval_duration_ns = (
                    getattr(chunk, "prompt_eval_duration", None) or prompt_eval_duration_ns
                )
                load_duration_ns = getattr(chunk, "load_duration", None) or load_duration_ns

            if output_tokens == 0:
                output_tokens = len(response_content.split())

        else:
            # Mode API (pas de streaming pour simplifier)
            if not MISTRAL_AVAILABLE or not MISTRAL_API_KEY:
                logger.warning("   ⚠️  API Mistral non configurée")
                return None

            client = Mistral(api_key=MISTRAL_API_KEY)
            first_token_time = time.perf_counter()  # Approximation

            resp = client.chat.complete(
                model=model_tag,
                messages=messages,
                max_tokens=output_token_limit,
            )

            input_tokens = resp.usage.prompt_tokens
            output_tokens = resp.usage.completion_tokens
            response_content = resp.choices[0].message.content
            eval_duration_ns = 0
            prompt_eval_duration_ns = 0
            load_duration_ns = 0

        duration = time.perf_counter() - start_time
        ttft_wall_ms = int((first_token_time - start_time) * 1000) if first_token_time else 0
        load_ms = int(load_duration_ns / 1e6)
        # TTFT du prompt calibré : chargement déduit, mais lecture du prompt incluse.
        ttft_full_prompt_ms = max(0, ttft_wall_ms - load_ms)

        # TTFT "ressenti" : modèle déjà chaud et prompt court, c'est ce que vit
        # l'utilisateur en conversation. C'est cette valeur qui alimente la note UX.
        ttft_ms = ttft_full_prompt_ms
        if model_type == "local":
            try:
                warm_kwargs = {
                    "model": model_tag,
                    "messages": [{"role": "user", "content": "Say hello in one word."}],
                    "stream": True,
                    "options": {"num_ctx": context_window, "temperature": 0, "num_predict": 8},
                }
                if vendor_params:
                    warm_kwargs["options"].pop("temperature")
                if supports_thinking(model_tag):
                    warm_kwargs["think"] = thinking
                warm_start = time.perf_counter()
                warm_first = None
                for chunk in ollama.chat(**warm_kwargs):
                    if warm_first is None:
                        warm_first = time.perf_counter()
                    _ = chunk
                if warm_first:
                    ttft_ms = int((warm_first - warm_start) * 1000)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"TTFT à chaud non mesuré : {e}")

        # Mesures post-inférence
        if model_type == "local":
            ollama_ram_end = get_ollama_process_memory_gb()
            # Empreinte donnée par Ollama lui-même (fiable), avec repli sur la mesure
            # par différence si le modèle a déjà quitté la mémoire.
            model_memory_usage, gpu_offload_pct = get_loaded_model_footprint(model_tag)
            if model_memory_usage == 0:
                model_memory_usage = max(0, get_model_memory_gb() - model_mem_start)
            sys_ram_peak, _ = get_system_ram_stats()
            emissions = tracker.stop() if tracker else 0
            ram_model_usage = max(0, ollama_ram_end - ollama_ram_start)
        else:
            sys_ram_peak = 0
            emissions = 0  # Pas de mesure CO2 pour API
            ram_model_usage = 0
            model_memory_usage = 0
            gpu_offload_pct = 0

        gpu_vram_end = get_gpu_memory_usage_gb()
        gpu_vram_usage = max(0, gpu_vram_end - gpu_vram_start)
        gpu_temp_c, gpu_clock_mhz = get_gpu_thermals()

        # Vitesse de génération pure (hors chargement et hors lecture du prompt).
        if eval_duration_ns:
            tokens_per_second = round(output_tokens / (eval_duration_ns / 1e9), 2)
        else:
            tokens_per_second = round(output_tokens / duration, 2) if duration > 0 else 0
        # Vitesse de lecture du prompt (prefill), déterminante en RAG.
        prefill_tps = (
            round(input_tokens / (prompt_eval_duration_ns / 1e9), 1)
            if prompt_eval_duration_ns
            else 0
        )

        # CO2 par 1000 tokens
        total_tokens = input_tokens + output_tokens
        co2_per_1k = round((emissions / total_tokens) * 1000, 8) if total_tokens > 0 else 0

        status = "OK"
        if output_tokens >= output_token_limit * 0.95:
            status = "MAX_TOKENS_HIT"

        if model_type == "local":
            unload_model(model_tag)

        return {
            "context_size": context_window,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens_per_second": tokens_per_second,
            "prefill_tokens_per_second": prefill_tps,
            "time_to_first_token_ms": ttft_ms,
            "ttft_full_prompt_ms": ttft_full_prompt_ms,
            "ttft_with_load_ms": ttft_wall_ms,
            "load_time_ms": load_ms,
            "duration_s": round(duration, 2),
            "model_memory_gb": round(model_memory_usage, 3),
            "gpu_offload_pct": gpu_offload_pct,
            "swap_delta_gb": round(psutil.swap_memory().used / (1024**3) - swap_start, 3),
            "gpu_temp_c": gpu_temp_c,
            "gpu_clock_mhz": gpu_clock_mhz,
            "ollama_ram_usage_gb": round(ram_model_usage, 3),
            "gpu_vram_usage_gb": round(gpu_vram_usage, 3),
            "ram_peak_gb": round(sys_ram_peak, 2),
            "co2_kg": float(emissions),
            "co2_per_1k_tokens": co2_per_1k,
            "status": status,
        }

    except Exception as e:
        if tracker:
            with contextlib.suppress(Exception):
                tracker.stop()
        logger.error(f"   ❌ Erreur benchmark: {e}")
        return None


def run_full_benchmark(
    model_name: str,
    model_data: dict,
    args: argparse.Namespace,
    run_id: int = 1,
) -> list[dict]:
    """
    Exécute le benchmark complet pour un modèle.
    Retourne une liste de résultats (un par niveau de contexte).
    """
    model_tag = model_data.get("ollama_tag")
    model_type = model_data.get("type", "local")
    max_model_ctx = model_data.get("ctx", 4096)
    disk_size = model_data.get("size_gb", "0")

    # Nettoyer la taille
    if isinstance(disk_size, str):
        disk_size = disk_size.replace(" GB", "").replace("≈", "")
        try:
            disk_size = float(disk_size)
        except ValueError:
            disk_size = 0

    results = []
    thinking = getattr(args, "thinking", "off") == "on"
    vendor = getattr(args, "params", "standard") == "vendor"
    tester = ModelTester(
        model_tag, model_type, args.country, thinking=thinking, vendor_params=vendor
    )

    # --- TESTS FONCTIONNELS (une seule fois) ---
    logger.info("   🔧 Tests fonctionnels...")
    if model_type == "local" and supports_thinking(model_tag):
        logger.info(f"      Mode raisonnement : {'activé' if thinking else 'désactivé'}")

    # Tool calling
    tool_results = {
        "valid": False,
        "function_correct": False,
        "params_correct": False,
        "cases": {},
        "score": 0.0,
    }
    if "tools" in model_data.get("capabilities", []) or args.force_tool_test:
        tool_results = tester.test_tool_calling()
        logger.info(
            f"      Tools: {tool_results['score'] * 100:.0f}% "
            f"({sum(tool_results['cases'].values())}/{len(tool_results['cases'])}) "
            f"détail={tool_results['cases']}"
        )

    # JSON
    json_valid, json_schema = tester.test_json_generation()
    logger.info(f"      JSON: valides={json_valid}, schémas respectés={json_schema}")

    # Abstention (le modèle doit refuser d'inventer)
    abstention_score = tester.test_abstention()
    logger.info(f"      Abstention: {abstention_score * 100:.0f}%")

    # Langues
    # Langues (Test systématique de toutes les langues supportées par le benchmark)
    lang_results = {}
    # On ignore model_data.get("langs") pour forcer la vérification réelle
    for lang_code in SUPPORTED_LANGUAGES:
        lang_results[lang_code] = tester.test_language(lang_code)

    supported_langs = [
        lc for lc, res in lang_results.items() if res["comprehension"] or res["generation"]
    ]
    logger.info(f"      Langues supportées: {supported_langs}")

    # Raisonnement
    reasoning_score = tester.test_reasoning()
    logger.info(
        f"      Raisonnement: {reasoning_score * 100:.0f}% "
        f"par catégorie={tester.detail.get('reasoning_by_category', {})}"
    )

    # Suivi d'instructions
    instruction_score = tester.test_instruction_following()
    failed = [k for k, v in tester.detail.get("instruction_tests", {}).items() if not v]
    logger.info(f"      Instructions: {instruction_score * 100:.0f}% échecs={failed}")

    # --- TESTS DE CONTEXTE ---
    logger.info("   📊 Tests de montée en contexte...")

    prev_ram_usage = 0.0
    context_levels = [c for c in CONTEXT_LEVELS if c <= max_model_ctx]

    if args.max_context:
        context_levels = [c for c in context_levels if c <= args.max_context]

    for ctx in context_levels:
        logger.info(f"      ⚡ Contexte {ctx}...")

        # Benchmark d'inférence
        bench = benchmark_inference(
            model_tag,
            ctx,
            model_type,
            args.country,
            args.output_tokens,
            thinking,
            vendor,
        )

        if not bench:
            logger.warning(f"      ❌ Échec à ctx={ctx}")
            # Enregistrer l'échec
            results.append(
                {
                    "model_name": model_name,
                    "ollama_tag": model_tag,
                    "model_type": model_type,
                    "disk_size_gb": disk_size,
                    "context_size": ctx,
                    "status": "FAILED",
                    "run_id": run_id,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            break

        # Détection du swap (local seulement).
        # On compare l'empreinte RAM + VRAM : la RAM seule vaut ~0 quand le modèle
        # est en VRAM, ce qui déclenchait un faux positif dès le deuxième palier.
        if model_type == "local":
            current_ram = bench.get("model_memory_gb") or bench["ollama_ram_usage_gb"]
            swap_delta = bench.get("swap_delta_gb", 0)
            # Signal direct : le fichier d'échange a grossi pendant l'inférence.
            real_swap = swap_delta > SWAP_DELTA_THRESHOLD_GB

            # Une baisse d'empreinte n'est PAS un swap : quand le contexte grandit,
            # Ollama déplace des couches vers le CPU et la VRAM mesurée diminue.
            # On le signale sans interrompre la montée en contexte.
            if prev_ram_usage > 0.2 and current_ram < prev_ram_usage * 0.8:
                logger.info(
                    f"      ↪️  Report CPU probable : empreinte {prev_ram_usage:.2f} -> "
                    f"{current_ram:.2f} GB, GPU {bench.get('gpu_offload_pct', 0)}%"
                )

            if real_swap:
                logger.warning(
                    f"      📉 SWAP disque détecté (fichier d'échange +{swap_delta:.2f} GB). Arrêt."
                )
                bench["status"] = "SWAP_DETECTED"
                # On garde ce résultat mais on arrête
                results.append(
                    _build_result_row(
                        model_name,
                        model_tag,
                        model_type,
                        disk_size,
                        bench,
                        tool_results,
                        json_valid,
                        json_schema,
                        lang_results,
                        reasoning_score,
                        instruction_score,
                        False,
                        run_id,
                        abstention_score,
                        tester.detail,
                    )
                )
                break
            prev_ram_usage = current_ram

        # Test needle-in-haystack
        needle_found = False
        if ctx >= 4096:  # Seulement pour contextes >= 4K
            needle_found = tester.test_needle_in_haystack(ctx)
            logger.info(f"         Needle-in-haystack: {'✅' if needle_found else '❌'}")

        # Construire le résultat
        result_row = _build_result_row(
            model_name,
            model_tag,
            model_type,
            disk_size,
            bench,
            tool_results,
            json_valid,
            json_schema,
            lang_results,
            reasoning_score,
            instruction_score,
            needle_found,
            run_id,
            abstention_score,
            tester.detail,
        )

        results.append(result_row)

        status_icon = "✅" if bench["status"] == "OK" else "⚠️"
        logger.info(
            f"      {status_icon} {bench['status']} | "
            f"{bench['tokens_per_second']} tok/s | "
            f"TTFT {bench['time_to_first_token_ms']}ms | "
            f"RAM {bench['ollama_ram_usage_gb']}GB | "
            f"GPU {bench.get('gpu_temp_c', 0):.0f}°C {bench.get('gpu_clock_mhz', 0):.0f}MHz"
        )

    # Le needle-in-haystack recharge le modèle après le déchargement opéré par
    # benchmark_inference : sans ce dernier unload, il reste résident pendant le
    # keep_alive (5 min par défaut) et cohabite avec le modèle suivant.
    if model_type == "local":
        unload_model(model_tag)

    return results


def _build_result_row(
    model_name: str,
    model_tag: str,
    model_type: str,
    disk_size: float,
    bench: dict,
    tool_results: dict,
    json_valid: bool,
    json_schema: bool,
    lang_results: dict,
    reasoning_score: float,
    instruction_score: float,
    needle_found: bool,
    run_id: int,
    abstention_score: float = 0.0,
    detail: dict | None = None,
) -> dict:
    """Construit une ligne de résultat complète."""
    detail = detail or {}
    row = {
        "model_name": model_name,
        "ollama_tag": model_tag,
        "model_type": model_type,
        "disk_size_gb": disk_size,
        "context_size": bench.get("context_size", 0),
        "input_tokens": bench.get("input_tokens", 0),
        "output_tokens": bench.get("output_tokens", 0),
        "tokens_per_second": bench.get("tokens_per_second", 0),
        "prefill_tokens_per_second": bench.get("prefill_tokens_per_second", 0),
        "time_to_first_token_ms": bench.get("time_to_first_token_ms", 0),
        "ttft_full_prompt_ms": bench.get("ttft_full_prompt_ms", 0),
        "ttft_with_load_ms": bench.get("ttft_with_load_ms", 0),
        "load_time_ms": bench.get("load_time_ms", 0),
        "duration_s": bench.get("duration_s", 0),
        "model_memory_gb": bench.get("model_memory_gb", 0),
        "gpu_offload_pct": bench.get("gpu_offload_pct", 0),
        "swap_delta_gb": bench.get("swap_delta_gb", 0),
        "gpu_temp_c": bench.get("gpu_temp_c", 0),
        "gpu_clock_mhz": bench.get("gpu_clock_mhz", 0),
        "ollama_ram_usage_gb": bench.get("ollama_ram_usage_gb", 0),
        "gpu_vram_usage_gb": bench.get("gpu_vram_usage_gb", 0),
        "ram_peak_gb": bench.get("ram_peak_gb", 0),
        "co2_kg": bench.get("co2_kg", 0),
        "co2_per_1k_tokens": bench.get("co2_per_1k_tokens", 0),
        "status": bench.get("status", "UNKNOWN"),
        "tool_call_valid": tool_results.get("valid", False),
        "tool_call_function_correct": tool_results.get("function_correct", False),
        "tool_call_params_correct": tool_results.get("params_correct", False),
        "tool_suite_score": tool_results.get("score", 0.0),
        "json_generation_valid": json_valid,
        "json_schema_compliant": json_schema,
        "needle_in_haystack_found": needle_found,
        "reasoning_score": reasoning_score,
        "instruction_following_score": instruction_score,
        "abstention_score": abstention_score,
        "reasoning_by_category": json.dumps(
            detail.get("reasoning_by_category", {}), ensure_ascii=False
        ),
        "response_variance": 0.0,  # TODO: implémenter avec multi-runs
        "run_id": run_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Ajouter les résultats de langues
    for lang_code in SUPPORTED_LANGUAGES:
        lang_res = lang_results.get(lang_code, {})
        row[f"lang_{lang_code}_comprehension"] = lang_res.get("comprehension", False)
        row[f"lang_{lang_code}_generation"] = lang_res.get("generation", False)

    return row


def update_model_json(
    db: dict, model_name: str, results: list[dict], stats_key: str = "benchmark_stats"
):
    """Met à jour le JSON avec les statistiques résumées et les nouvelles métriques."""
    if not results:
        return

    # 1. Filtrage et moyennes de base
    ok_results = [r for r in results if r.get("status") == "OK"]
    if not ok_results:
        ok_results = results

    best = max(ok_results, key=lambda x: x.get("context_size", 0))

    avg_tps = sum(r.get("tokens_per_second", 0) for r in ok_results) / len(ok_results)
    avg_ttft = sum(r.get("time_to_first_token_ms", 0) for r in ok_results) / len(ok_results)
    total_co2 = sum(r.get("co2_kg", 0) for r in results)
    avg_co2_per_1k = sum(r.get("co2_per_1k_tokens", 0) for r in ok_results) / len(ok_results)

    # Scores de qualité
    reasoning_avg = best.get("reasoning_score", 0)
    instruction_avg = best.get("instruction_following_score", 0)

    # Dispersion entre exécutions : une seule valeur par run, prise au contexte
    # le plus élevé validé, sinon la moyenne des paliers mélangerait deux effets.
    by_run: dict[int, list[dict]] = {}
    for r in ok_results:
        by_run.setdefault(r.get("run_id", 1), []).append(r)
    per_run_best = [max(rows, key=lambda x: x.get("context_size", 0)) for rows in by_run.values()]

    runs_stats = {
        "tokens_per_second": dispersion([r.get("tokens_per_second", 0) for r in per_run_best]),
        "reasoning": dispersion([r.get("reasoning_score", 0) for r in per_run_best], digits=3),
        "instruction_following": dispersion(
            [r.get("instruction_following_score", 0) for r in per_run_best], digits=3),
        "gpu_clock_mhz": dispersion([r.get("gpu_clock_mhz", 0) for r in per_run_best], digits=0),
    }

    # 2. Calcul des nouvelles métriques intelligentes
    ux_rating = _get_ux_rating(avg_ttft)
    eff_score = _get_efficiency_score(reasoning_avg, avg_co2_per_1k)

    # 3. Détection automatique de la licence (Ollama uniquement)
    model_tag = db[model_name].get("ollama_tag", "")
    detected_license = "N/A"
    if db[model_name].get("type") == "local":
        detected_license = detect_license_type(model_tag)

    # 4. Construction de l'objet stats complet
    stats = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "max_validated_ctx": best.get("context_size", 0),
        "ram_usage_at_max_ctx_gb": best.get("ollama_ram_usage_gb", 0),
        "model_memory_at_max_ctx_gb": best.get("model_memory_gb", 0),
        "gpu_vram_usage_gb": best.get("gpu_vram_usage_gb", 0),
        # Part du modèle réellement en VRAM : explique l'essentiel des écarts de vitesse.
        "gpu_offload_pct": best.get("gpu_offload_pct", 0),
        # Performance pure (génération seule, chargement exclu)
        "avg_tokens_per_second": round(avg_tps, 2),
        "prefill_tokens_per_second": best.get("prefill_tokens_per_second", 0),
        # Taille du prompt ayant servi à mesurer le prefill (≈ 50 % du contexte).
        "prefill_prompt_tokens": best.get("input_tokens", 0),
        "avg_ttft_ms": int(avg_ttft),
        "ttft_full_prompt_ms": best.get("ttft_full_prompt_ms", 0),
        "load_time_ms": best.get("load_time_ms", 0),
        # Métriques Décisionnelles (Nouvelles)
        "ux_rating": ux_rating,  # ⚡ Instantané, 🚀 Rapide...
        "efficiency_grade": eff_score,  # 🟢 Excellent, 🔴 Faible...
        "detected_license": detected_license,  # Apache 2.0, MIT...
        # RSE
        "total_co2_emissions_kg": total_co2,
        "avg_co2_per_1k_tokens": round(avg_co2_per_1k, 6),
        # Capacités
        "tool_capability": {
            "function_detection": best.get("tool_call_valid", False),
            "parameter_extraction": best.get("tool_call_params_correct", False),
            # Moyenne des 4 cas : appel simple, choix entre outils,
            # abstention d'appel, paramètre enum.
            "success_rate": best.get("tool_suite_score", 0.0),
        },
        "json_capability": {
            "valid_json_rate": float(best.get("json_generation_valid") or 0.0),
            "schema_compliance_rate": float(best.get("json_schema_compliant") or 0.0),
        },
        "needle_in_haystack": {},
        # Dispersion mesurée entre exécutions (vide si un seul run).
        "runs": runs_stats,
        "quality_scores": {
            "reasoning_avg": reasoning_avg,
            "instruction_following_avg": instruction_avg,
            "abstention_avg": best.get("abstention_score", 0),
            "reasoning_by_category": json.loads(best.get("reasoning_by_category") or "{}"),
            "response_variance_avg": best.get("response_variance", 0),
        },
    }

    # Needle-in-haystack
    for r in results:
        ctx = r.get("context_size", 0)
        if ctx >= 4096:
            stats["needle_in_haystack"][f"ctx_{ctx // 1024}k"] = r.get(
                "needle_in_haystack_found", False
            )

    # Langues
    languages_supported = {}
    for lang_code in SUPPORTED_LANGUAGES:
        comp = best.get(f"lang_{lang_code}_comprehension", False)
        gen = best.get(f"lang_{lang_code}_generation", False)
        if comp or gen:
            languages_supported[lang_code] = {"comprehension": comp, "generation": gen}

    # Mise à jour DB
    db[model_name][stats_key] = stats
    if languages_supported:
        db[model_name]["languages_validated"] = languages_supported

    # Capabilities Validated (Tags automatiques)
    validated_caps = []
    # Seuils explicites : les scores sont désormais des taux, pas des booléens.
    if (best.get("tool_suite_score") or 0) >= 0.75:
        validated_caps.append("tools_validated")
    if (best.get("json_schema_compliant") or 0) >= 1.0:
        validated_caps.append("json_validated")

    # Tag automatique multilingue
    if len(languages_supported) >= 5:
        validated_caps.append("multilingual_full")
    elif len(languages_supported) >= 2:
        validated_caps.append("multilingual_partial")

    # Tag automatique licence "Open" (si détecté)
    if detected_license in ["Apache 2.0", "MIT"]:
        validated_caps.append("license_permissive")

    if validated_caps:
        db[model_name]["capabilities_validated"] = validated_caps


def _get_ux_rating(ttft_ms: float) -> str:
    """Retourne une note visuelle pour l'UX basée sur le TTFT."""
    if ttft_ms < 300:
        return "⚡ Instantané"
    if ttft_ms < 800:
        return "🚀 Rapide"
    if ttft_ms < 1500:
        return "🐢 Acceptable"
    return "🐌 Lent"


def _get_efficiency_score(reasoning_score: float, co2_per_1k: float) -> str:
    """Calcule un score d'efficience (Qualité / CO2)."""
    if co2_per_1k <= 0:
        return "N/A"
    # Formule arbitraire pour le score : (Reasoning * 100) / (CO2_g * 10)
    # Plus le score est haut, plus le modèle est "intelligent pour son coût carbone"
    co2_g = co2_per_1k * 1000
    if co2_g == 0:
        return "N/A"

    score = (reasoning_score * 100) / co2_g

    if score > 500:
        return "🟢 Excellent"
    if score > 200:
        return "🟡 Bon"
    return "🔴 Faible"


def generate_markdown_report(db: dict):
    """Génère un rapport Markdown enrichi gérant les ex-aequo."""
    logger.info(f"📝 Génération du rapport enrichi : {REPORT_MD_PATH}")

    # Préparation des données
    models_data = []
    for name, data in db.items():
        stats = data.get("benchmark_stats", {})
        if not stats:
            continue

        # Calculs dérivés
        ttft = stats.get("avg_ttft_ms", 0)
        reasoning = stats.get("quality_scores", {}).get("reasoning_avg", 0)
        co2 = stats.get("avg_co2_per_1k_tokens", 0)

        models_data.append(
            {
                "name": name,
                "type": data.get("type", "local"),
                "size": data.get("size_gb", "?"),
                "ctx": stats.get("max_validated_ctx", 0),
                "tps": stats.get("avg_tokens_per_second", 0),
                "ttft": ttft,
                "co2": co2,
                "reasoning": reasoning,
                "tools": stats.get("tool_capability", {}).get("success_rate", 0) > 0.8,
                "json": stats.get("json_capability", {}).get("schema_compliance_rate", 0) > 0.8,
                "langs": len(data.get("languages_validated", {})),
                "efficiency": _get_efficiency_score(reasoning, co2),
                "ux_rating": _get_ux_rating(ttft),
            }
        )

    if not models_data:
        logger.warning("⚠️ Pas de données pour générer le rapport.")
        return

    # --- GESTION DES CHAMPIONS (AVEC EX-AEQUO) ---

    def get_winners(data, key, reverse=True, filter_func=None):
        """Retourne la liste des modèles ayant le meilleur score."""
        candidates = [d for d in data if filter_func(d)] if filter_func else data
        if not candidates:
            return [], 0

        # Tri pour trouver le meilleur score
        sorted_data = sorted(candidates, key=lambda x: x[key], reverse=reverse)
        best_score = sorted_data[0][key]

        # Récupération de tous les ex-aequo
        winners = [d for d in sorted_data if d[key] == best_score]
        return winners, best_score

    # 1. Raisonnement (Score le plus haut)
    top_reasoning, best_reasoning_score = get_winners(models_data, "reasoning", reverse=True)

    # 2. Vitesse (TPS le plus haut)
    top_speed, best_tps_score = get_winners(models_data, "tps", reverse=True)

    # 3. Frugalité (CO2 le plus bas, strictement positif)
    top_eco, best_eco_score = get_winners(
        models_data, "co2", reverse=False, filter_func=lambda x: x["co2"] > 0
    )

    # Helper pour formater les noms
    def format_names(models_list):
        names = [f"**{m['name']}**" for m in models_list]
        return ", ".join(names)

    # --- CONSTRUCTION DU RAPPORT ---
    lines = [
        "# 📊 WaveLocalAI - Rapport d'Aide à la Décision\n",
        f"> **Date du rapport** : {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n",
        f"> **Contexte** : {len(models_data)} modèles évalués sur {TOTAL_RAM_GB} GB RAM\n",
        "\n---\n",
        "## 🏆 Synthèse Exécutive (Executive Summary)\n",
        "Ce résumé identifie les modèles les plus performants selon vos priorités métier.\n\n",
    ]

    # Bloc Intelligence
    title_perf = "Les plus intelligents" if len(top_reasoning) > 1 else "Le plus intelligent"
    lines.extend(
        [
            f"### 🧠 {title_perf} (Capacités cognitives)\n",
            f"{format_names(top_reasoning) if top_reasoning else 'N/A'}\n",
            (
                f"- Score de raisonnement : **{best_reasoning_score*100:.0f}%**\n"
                if top_reasoning
                else ""
            ),
            "- *Recommandé pour : Agents complexes, RAG, Analyse de documents.*\n\n",
        ]
    )

    # Bloc Vitesse
    title_speed = "Les plus rapides" if len(top_speed) > 1 else "Le plus rapide"
    # On prend l'UX rating du premier (ils sont supposés proches si tps proche, sinon on prend celui du 1er)
    ux_lbl = top_speed[0]["ux_rating"] if top_speed else ""
    lines.extend(
        [
            f"### ⚡ {title_speed} (Expérience Utilisateur)\n",
            f"{format_names(top_speed) if top_speed else 'N/A'}\n",
            f"- Vitesse : **{best_tps_score:.0f} tok/s** ({ux_lbl})\n" if top_speed else "",
            "- *Recommandé pour : Chatbots temps réel, Auto-complétion.*\n\n",
        ]
    )

    # Bloc Écologie
    title_eco = "Les plus frugaux" if len(top_eco) > 1 else "Le plus frugal"
    lines.extend(
        [
            f"### 🌱 {title_eco} (RSE & Green IT)\n",
            f"{format_names(top_eco) if top_eco else 'N/A'}\n",
            f"- Impact : **{best_eco_score*1000:.4f} gCO₂** / 1k tokens\n" if top_eco else "",
            "- *Recommandé pour : Traitement de fond (batch), IoT, Usage massif.*\n\n",
        ]
    )

    lines.extend(
        [
            "\n---\n",
            "## 🚦 Matrice de Décision\n",
            "Comparatif global pour orienter le choix technique.\n",
            "| Modèle | Type | Taille | UX (Latence) | Raisonnement | Efficience RSE | Tools | JSON |\n",
            "|--------|------|--------|--------------|--------------|----------------|-------|------|\n",
        ]
    )

    for m in models_data:
        tools_icon = "✅" if m["tools"] else "❌"
        json_icon = "✅" if m["json"] else "❌"
        reasoning_str = f"{m['reasoning']*100:.0f}%"

        lines.append(
            f"| **{m['name'][:25]}** | {m['type']} | {m['size']} | {m['ux_rating']} | {reasoning_str} | {m['efficiency']} | {tools_icon} | {json_icon} |\n"
        )

    lines.extend(
        [
            "\n---\n",
            "## 🌍 Analyse d'Impact Environnemental (Détail)\n",
            "Focus sur la consommation énergétique relative des modèles.\n",
            "| Modèle | Contexte Max Validé | Émissions (gCO₂/1k tok) | Équivalent |\n",
            "|--------|---------------------|-------------------------|------------|\n",
        ]
    )

    for m in models_data:
        co2_g = m["co2"] * 1000
        equiv = f"{co2_g/4:.2f} emails" if co2_g > 0 else "?"
        lines.append(f"| {m['name']} | {m['ctx']} tokens | **{co2_g:.4f} g** | {equiv} |\n")

    lines.extend(
        [
            "\n---\n",
            "## 📋 Annexe Technique\n",
            "- **UX Rating** : Basé sur le TTFT (Time To First Token). <300ms est imperceptible.\n",
            "- **Efficience RSE** : Ratio entre la qualité de réponse et le coût carbone.\n",
            "- **Méthodologie** : Tests réalisés en local via Ollama + CodeCarbon.\n",
            "\n*Généré par WaveLocalAI v2.1*",
        ]
    )

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


# --- MAIN ---
def main():
    parser = argparse.ArgumentParser(
        description="🔬 WaveLocalAI - Benchmark SLM Complet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python benchmark_slm.py                           # Tous les modèles locaux
  python benchmark_slm.py --models qwen2.5:0.5b     # Un modèle spécifique
  python benchmark_slm.py --type api                # Seulement les modèles API
  python benchmark_slm.py --type all --no-update    # Tous types, sans MAJ JSON
  python benchmark_slm.py --skip-tested             # Ignorer les déjà testés
        """,
    )

    # Filtrage des modèles
    parser.add_argument(
        "--models",
        "-m",
        nargs="+",
        help="Tags Ollama des modèles à tester (ex: qwen2.5:0.5b llama3.2:1b)",
    )
    parser.add_argument(
        "--type",
        "-t",
        choices=["local", "api", "all"],
        default="local",
        help="Type de modèles à tester (défaut: local)",
    )
    parser.add_argument(
        "--skip-tested",
        action="store_true",
        help="Ignorer les modèles ayant déjà des benchmark_stats",
    )

    # Configuration des tests
    parser.add_argument(
        "--max-context",
        type=int,
        help="Contexte maximum à tester (ex: 8192)",
    )
    parser.add_argument(
        "--output-tokens",
        type=int,
        default=DEFAULT_OUTPUT_TOKENS,
        help=f"Nombre de tokens à générer (défaut: {DEFAULT_OUTPUT_TOKENS})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Nombre de runs par modèle pour la variance (défaut: {DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--country",
        default=DEFAULT_COUNTRY_ISO_CODE,
        help=f"Code ISO pays pour CodeCarbon (défaut: {DEFAULT_COUNTRY_ISO_CODE})",
    )

    # Options de tests
    parser.add_argument(
        "--cooldown-temp",
        type=float,
        default=0,
        help=(
            f"Attendre que le GPU redescende sous cette température avant chaque "
            f"exécution (0 = désactivé, {DEFAULT_COOLDOWN_TEMP_C} recommandé sur portable). "
            "Sans cette pause, les modèles de fin de campagne sont mesurés à fréquence réduite."
        ),
    )
    parser.add_argument(
        "--cooldown-max",
        type=float,
        default=DEFAULT_COOLDOWN_MAX_S,
        help=f"Durée maximale d'attente par refroidissement (défaut : {DEFAULT_COOLDOWN_MAX_S}s)",
    )
    parser.add_argument(
        "--params",
        choices=["standard", "vendor"],
        default="standard",
        help=(
            "standard (défaut) : température 0 pour tous, comparaison stricte. "
            "vendor : on laisse s'appliquer les PARAMETER du Modelfile de l'éditeur."
        ),
    )
    parser.add_argument(
        "--stats-key",
        help="Clé d'écriture dans models.json (défaut : benchmark_stats, "
        "ou benchmark_stats_vendor en mode éditeur / raisonnement activé)",
    )
    parser.add_argument(
        "--thinking",
        choices=["off", "on"],
        default="off",
        help=(
            "Mode raisonnement des modèles 'thinking' (défaut: off). "
            "Off = comparaison équitable avec les modèles sans raisonnement et durée bornée."
        ),
    )
    parser.add_argument(
        "--force-tool-test",
        action="store_true",
        help="Forcer le test tool calling même si non déclaré",
    )
    parser.add_argument(
        "--force-lang-test",
        action="store_true",
        help="Tester toutes les langues même si non déclarées",
    )

    # Outputs
    parser.add_argument(
        "--no-update",
        "-n",
        action="store_true",
        help="Ne pas mettre à jour le fichier models.json",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Ne pas générer le rapport Markdown",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Mode verbeux (debug)",
    )

    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Générer uniquement le rapport Markdown depuis models.json sans lancer de benchmark",
    )

    args = parser.parse_args()

    # Une campagne "au mieux" (paramètres éditeur ou raisonnement activé) ne doit
    # pas écraser la campagne standardisée : elle s'écrit sous sa propre clé.
    stats_key = args.stats_key or (
        "benchmark_stats_vendor"
        if (args.params == "vendor" or args.thinking == "on")
        else "benchmark_stats"
    )

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Charger la base de modèles
    if not MODELS_JSON_PATH.exists():
        logger.error(f"❌ Fichier introuvable : {MODELS_JSON_PATH}")
        sys.exit(1)

    with open(MODELS_JSON_PATH, encoding="utf-8") as f:
        db = json.load(f)

    # Backup du JSON
    if not args.no_update:
        shutil.copy(MODELS_JSON_PATH, str(MODELS_JSON_PATH) + ".bak")

    # --- LOGIQUE REPORT-ONLY ---
    if args.report_only:
        logger.info("📄 Mode rapport seul activé.")
        generate_markdown_report(db)
        logger.info(f"✅ Rapport régénéré : {REPORT_MD_PATH}")
        sys.exit(0)
    # ---------------------------

    # Vérifier Ollama pour les modèles locaux
    if args.type in ("local", "all"):
        try:
            ollama.list()
        except Exception:
            logger.error("❌ Ollama non détecté. Lancez 'ollama serve'.")
            if args.type == "local":
                sys.exit(1)

    # Vérifier API Mistral
    if args.type in ("api", "all"):
        if not MISTRAL_AVAILABLE:
            logger.warning("⚠️  Package mistralai non installé")
        if not MISTRAL_API_KEY:
            logger.warning("⚠️  MISTRAL_API_KEY non configurée")

    # Initialiser le CSV
    initialize_csv()

    # Filtrer les modèles à tester
    models_to_test = []
    for name, data in db.items():
        model_type = data.get("type", "local")
        tag = data.get("ollama_tag")

        # Filtrer par type
        if args.type != "all" and model_type != args.type:
            continue

        # Filtrer par tags spécifiques
        if args.models and tag not in args.models:
            continue

        # Ignorer les déjà testés
        if args.skip_tested and data.get(stats_key):
            logger.info(f"⏭️  {name} : Déjà testé, ignoré.")
            continue

        # Vérifier l'installation (local seulement)
        if model_type == "local":
            real_tag = check_model_installed(tag)
            if not real_tag:
                logger.warning(f"⏩ {name} ({tag}) : Non installé, ignoré.")
                continue
            data["_real_tag"] = real_tag
        else:
            data["_real_tag"] = tag

        models_to_test.append((name, data))

    if not models_to_test:
        logger.warning("⚠️  Aucun modèle à tester.")
        sys.exit(0)

    logger.info(f"🚀 Benchmark de {len(models_to_test)} modèle(s)")
    logger.info(
        f"⚙️  Paramètres : {args.params} | raisonnement : {args.thinking} "
        f"| écriture sous : {stats_key}"
    )
    logger.info(f"🖥️  RAM système : {TOTAL_RAM_GB} GB")
    logger.info(f"🌍 Pays CodeCarbon : {args.country}")

    # Exécuter les benchmarks
    for i, (name, data) in enumerate(models_to_test, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i}/{len(models_to_test)}] 🔬 {name}")
        logger.info(f"{'='*60}")

        try:
            all_results = []

            for run_id in range(1, args.runs + 1):
                if args.runs > 1:
                    logger.info(f"   📍 Run {run_id}/{args.runs}")

                if args.cooldown_temp > 0:
                    cd = wait_for_cooldown(args.cooldown_temp, args.cooldown_max)
                    if cd["waited_s"]:
                        verdict = "atteint" if cd["reached"] else "plafond atteint"
                        logger.info(
                            f"   ❄️  Refroidissement {cd['waited_s']:.0f}s : "
                            f"{cd['start_temp_c']:.0f}°C -> {cd['end_temp_c']:.0f}°C "
                            f"({verdict}, {cd['clock_mhz']:.0f}MHz)"
                        )

                results = run_full_benchmark(name, data, args, run_id)
                all_results.extend(results)

            # Sauvegarder dans le CSV
            append_to_csv(all_results)
            logger.info(f"   💾 {len(all_results)} résultats sauvés dans CSV")

            # Mettre à jour le JSON
            if not args.no_update and all_results:
                update_model_json(db, name, all_results, stats_key)
                with open(MODELS_JSON_PATH, "w", encoding="utf-8") as f:
                    json.dump(db, f, indent=4, ensure_ascii=False)
                logger.info("   📝 JSON mis à jour")

        except KeyboardInterrupt:
            logger.warning("\n⚠️  Interruption utilisateur")
            break
        except Exception as e:
            logger.error(f"   ❌ Erreur : {e}")
            if args.verbose:
                import traceback

                traceback.print_exc()
            continue
        finally:
            # Même après une erreur ou une interruption, on libère la mémoire
            # avant de charger le modèle suivant.
            if data.get("type", "local") == "local":
                unload_model(data.get("ollama_tag"))

    # Générer le rapport
    if not args.no_report:
        generate_markdown_report(db)

    logger.info("\n✅ Benchmark terminé !")
    logger.info(f"   📊 CSV : {DATASET_CSV_PATH}")
    logger.info(f"   📝 Rapport : {REPORT_MD_PATH}")
    logger.info(f"   📋 Logs : {AUDIT_LOG_FILE}")


if __name__ == "__main__":
    main()
